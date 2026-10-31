"""Phase 2: what does a late delivery cost?

Estimates the effect of an order arriving after its promised date on
(a) the customer's review and (b) whether they come back within 180 days.

Every estimator conditions only on things known at checkout (pre-treatment).
Post-treatment variables such as days_to_ship or delivery_days are never used
as controls: they are part of how an order becomes late, so controlling for
them would remove the effect we are trying to measure.

Estimators, from weakest to strongest assumptions about the model:
  naive       difference in means
  ols         linear regression with checkout-time controls, SEs clustered by seller
  ols_fe      the same plus seller fixed effects (compares orders within a seller)
  ipw         inverse-propensity weighting for the effect on the treated (ATT)
  aipw        doubly robust, cross-fitted gradient boosting (ATT)
"""

from __future__ import annotations

from dataclasses import dataclass

import duckdb
import numpy as np
import pandas as pd
import statsmodels.api as sm
from sklearn.ensemble import HistGradientBoostingClassifier, HistGradientBoostingRegressor
from sklearn.linear_model import LogisticRegression
from sklearn.model_selection import StratifiedKFold
from sklearn.preprocessing import StandardScaler

SEED = 605

NUMERIC = [
    "log_distance",
    "distance_missing",
    "same_state",
    "log_items_value",
    "log_freight",
    "freight_share",
    "log_weight",
    "log_volume",
    "n_items",
    "multi_seller",
    "promised_days",
    "max_installments",
    "purchase_hour",
]
CATEGORICAL = ["customer_state", "seller_state", "main_category", "main_payment_type", "purchase_month", "purchase_dow"]

# Months where lateness spiked (Black Friday 2017; Feb-Mar 2018 carrier disruption).
SPIKE_MONTHS = ["2017-11", "2018-02", "2018-03"]


# --------------------------------------------------------------------------- data


def _features(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    out["distance_missing"] = out["distance_km"].isna().astype(int)
    out["log_distance"] = np.log1p(out["distance_km"].fillna(out["distance_km"].median()))
    out["same_state"] = out["same_state"].fillna(False).astype(int)
    out["log_items_value"] = np.log1p(out["items_value"])
    out["log_freight"] = np.log1p(out["freight_value"])
    out["freight_share"] = out["freight_share"].fillna(0)
    out["log_weight"] = np.log1p(out["weight_kg"].fillna(out["weight_kg"].median()))
    out["log_volume"] = np.log1p(out["max_item_volume_cm3"].fillna(out["max_item_volume_cm3"].median()))
    out["multi_seller"] = (out["n_sellers"] > 1).astype(int)
    out["max_installments"] = out["max_installments"].fillna(1)
    out["main_payment_type"] = out["main_payment_type"].fillna("unknown")
    out["purchase_month"] = pd.to_datetime(out["purchase_month"]).dt.strftime("%Y-%m")
    out["purchase_dow"] = out["purchase_dow"].astype(str)
    for c in ["customer_state", "seller_state", "main_category"]:
        out[c] = out[c].fillna("unknown")
    return out


def load_orders(db_path: str) -> pd.DataFrame:
    """Eligible, reviewed orders with checkout-time features."""
    con = duckdb.connect(db_path, read_only=True)
    df = con.execute(
        """
        select *
        from marts.fct_orders
        where is_analysis_eligible and has_review
        """
    ).df()
    con.close()
    df = _features(df)
    df["late"] = df["is_late"].astype(int)
    df["one_star"] = (df["review_score"] == 1).astype(int)
    return df.reset_index(drop=True)


def load_customers(db_path: str) -> pd.DataFrame:
    """One row per first-time customer with a full 180-day follow-up window.

    Features come from the largest order in the customer's first purchase session.
    """
    con = duckdb.connect(db_path, read_only=True)
    df = con.execute(
        """
        with first_orders as (
            select *
            from marts.fct_orders
            where session_number = 1
            qualify row_number() over (
                partition by customer_unique_id order by payment_value desc nulls last, order_id
            ) = 1
        )
        select
            c.customer_unique_id,
            c.first_session_any_late,
            c.first_session_max_days_late,
            c.first_session_min_review,
            c.first_session_orders,
            c.repeat_within_window,
            o.* exclude (customer_unique_id, customer_state),
            c.customer_state
        from marts.fct_customer_first_purchase c
        join first_orders o using (customer_unique_id)
        where c.has_full_followup and c.first_session_eligible
        """
    ).df()
    con.close()
    df = _features(df)
    df["late"] = df["first_session_any_late"].astype(int)
    df["repeat"] = df["repeat_within_window"].astype(int)
    return df.reset_index(drop=True)


def design_matrix(df: pd.DataFrame, min_level: int = 30) -> pd.DataFrame:
    """Numeric controls plus one-hot categoricals.

    Levels with fewer than `min_level` rows fold into "other" so no dummy identifies a
    handful of orders (which made the design rank-deficient), and the most common level
    of each categorical is the dropped reference.
    """
    num = df[NUMERIC].astype(float)
    parts = [num]
    for c in CATEGORICAL:
        counts = df[c].value_counts()
        col = df[c].where(df[c].map(counts) >= min_level, "other")
        dummies = pd.get_dummies(col, prefix=c, dtype=float)
        parts.append(dummies.drop(columns=f"{c}_{counts.index[0]}"))
    X = pd.concat(parts, axis=1)
    return X.loc[:, X.std() > 0]


# --------------------------------------------------------------------------- estimators


@dataclass
class Estimate:
    method: str
    estimate: float
    se: float
    n: int

    @property
    def ci(self) -> tuple[float, float]:
        return self.estimate - 1.96 * self.se, self.estimate + 1.96 * self.se

    def row(self) -> dict:
        lo, hi = self.ci
        return {
            "method": self.method,
            "estimate": self.estimate,
            "se": self.se,
            "ci_low": lo,
            "ci_high": hi,
            "n": self.n,
        }


def naive(df: pd.DataFrame, y: str, t: str = "late") -> Estimate:
    a, b = df.loc[df[t] == 1, y], df.loc[df[t] == 0, y]
    se = np.sqrt(a.var() / len(a) + b.var() / len(b))
    return Estimate("naive difference", a.mean() - b.mean(), se, len(df))


def ols(df: pd.DataFrame, y: str, t: str = "late", cluster: str = "seller_id") -> Estimate:
    X = sm.add_constant(pd.concat([df[[t]].astype(float), design_matrix(df)], axis=1))
    fit = sm.OLS(df[y].astype(float), X).fit(cov_type="cluster", cov_kwds={"groups": pd.factorize(df[cluster])[0]})
    return Estimate("regression + controls", fit.params[t], fit.bse[t], len(df))


def ols_seller_fe(df: pd.DataFrame, y: str, t: str = "late", fe: str = "seller_id") -> Estimate:
    """Within-group estimator (default: seller): demean outcome, treatment and controls by group (FWL)."""
    sizes = df.groupby(fe)[fe].transform("size")
    d = df.loc[sizes > 1].reset_index(drop=True)
    X = pd.concat([d[[t]].astype(float), design_matrix(d)], axis=1)
    X = X.loc[:, X.std() > 0]
    Y = d[y].astype(float)
    g = d[fe]
    Xw = X - X.groupby(g).transform("mean")
    Yw = Y - Y.groupby(g).transform("mean")
    Xw = Xw.loc[:, Xw.abs().sum() > 1e-9]
    fit = sm.OLS(Yw, Xw).fit(cov_type="cluster", cov_kwds={"groups": pd.factorize(g)[0]})
    return Estimate("regression + seller fixed effects", fit.params[t], fit.bse[t], len(d))


def propensity_logit(df: pd.DataFrame, t: str = "late") -> np.ndarray:
    X = StandardScaler().fit_transform(design_matrix(df))
    model = LogisticRegression(C=1.0, max_iter=2000)
    model.fit(X, df[t])
    return model.predict_proba(X)[:, 1]


def ipw_att(df: pd.DataFrame, y: str, t: str = "late", ps: np.ndarray | None = None, clip: float = 0.01) -> Estimate:
    """Effect on the treated: weight controls by e/(1-e) so they resemble late orders."""
    e = np.clip(propensity_logit(df, t) if ps is None else ps, clip, 1 - clip)
    D, Y = df[t].to_numpy(), df[y].to_numpy(dtype=float)
    w = np.where(D == 1, 1.0, e / (1 - e))
    mu1 = Y[D == 1].mean()
    mu0 = np.sum(w[D == 0] * Y[D == 0]) / np.sum(w[D == 0])
    # Bootstrap-free SE from the weighted-mean influence function.
    p = D.mean()
    psi = (D * (Y - mu1) - (1 - D) * w * (Y - mu0) * (D.sum() / w[D == 0].sum())) / p
    se = np.sqrt(np.var(psi) / len(Y))
    return Estimate("propensity weighting (ATT)", mu1 - mu0, se, len(df))


def aipw_att(df: pd.DataFrame, y: str, t: str = "late", folds: int = 5, clip: float = 0.01) -> Estimate:
    """Doubly robust ATT with cross-fitted gradient boosting for both nuisance models."""
    X = design_matrix(df).to_numpy()
    D, Y = df[t].to_numpy(), df[y].to_numpy(dtype=float)
    binary = set(np.unique(Y)) <= {0.0, 1.0}
    e = np.zeros(len(Y))
    m0 = np.zeros(len(Y))
    kf = StratifiedKFold(folds, shuffle=True, random_state=SEED)
    for train, test in kf.split(X, D):
        clf = HistGradientBoostingClassifier(max_iter=300, learning_rate=0.05, random_state=SEED)
        clf.fit(X[train], D[train])
        e[test] = clf.predict_proba(X[test])[:, 1]
        ctrl = train[D[train] == 0]
        if binary:
            out = HistGradientBoostingClassifier(max_iter=300, learning_rate=0.05, random_state=SEED)
            out.fit(X[ctrl], Y[ctrl].astype(int))
            m0[test] = out.predict_proba(X[test])[:, 1]
        else:
            out = HistGradientBoostingRegressor(max_iter=300, learning_rate=0.05, random_state=SEED)
            out.fit(X[ctrl], Y[ctrl])
            m0[test] = out.predict(X[test])
    e = np.clip(e, clip, 1 - clip)
    p = D.mean()
    psi = (D * (Y - m0) - (1 - D) * e / (1 - e) * (Y - m0)) / p
    tau = psi.mean()
    se = np.sqrt(np.var(psi - D * tau / p) / len(Y))
    return Estimate("doubly robust, cross-fitted (ATT)", tau, se, len(df))


def all_estimates(df: pd.DataFrame, y: str, t: str = "late", include_fe: bool = True) -> pd.DataFrame:
    ests = [naive(df, y, t), ols(df, y, t)]
    if include_fe:
        ests.append(ols_seller_fe(df, y, t))
    ests += [ipw_att(df, y, t), aipw_att(df, y, t)]
    return pd.DataFrame([e.row() for e in ests])


# --------------------------------------------------------------------------- diagnostics


def balance_table(df: pd.DataFrame, t: str = "late", ps: np.ndarray | None = None, clip: float = 0.01) -> pd.DataFrame:
    """Standardised mean differences of the numeric controls, before and after ATT weighting."""
    e = np.clip(propensity_logit(df, t) if ps is None else ps, clip, 1 - clip)
    D = df[t].to_numpy()
    w = np.where(D == 1, 1.0, e / (1 - e))
    rows = []
    for c in NUMERIC:
        x = df[c].astype(float).to_numpy()
        sd = np.sqrt((x[D == 1].var() + x[D == 0].var()) / 2) or 1.0
        raw = (x[D == 1].mean() - x[D == 0].mean()) / sd
        wtd = (x[D == 1].mean() - np.average(x[D == 0], weights=w[D == 0])) / sd
        rows.append({"variable": c, "smd_before": raw, "smd_after": wtd})
    return pd.DataFrame(rows)


def dose_response(df: pd.DataFrame, y: str, reference: str = "3. 1-7 days early") -> pd.DataFrame:
    """Adjusted outcome by lateness bucket, relative to arriving 1-7 days early."""
    buckets = pd.get_dummies(df["lateness_bucket"], dtype=float).drop(columns=[reference])
    X = sm.add_constant(pd.concat([buckets, design_matrix(df)], axis=1))
    fit = sm.OLS(df[y].astype(float), X).fit(cov_type="cluster", cov_kwds={"groups": pd.factorize(df["seller_id"])[0]})
    rows = [{"bucket": reference, "effect": 0.0, "ci_low": 0.0, "ci_high": 0.0}]
    for b in buckets.columns:
        rows.append(
            {
                "bucket": b,
                "effect": fit.params[b],
                "ci_low": fit.params[b] - 1.96 * fit.bse[b],
                "ci_high": fit.params[b] + 1.96 * fit.bse[b],
            }
        )
    out = pd.DataFrame(rows).sort_values("bucket").reset_index(drop=True)
    out["n"] = out["bucket"].map(df["lateness_bucket"].value_counts())
    return out


def e_value(rr: float) -> float:
    """VanderWeele & Ding E-value for a risk ratio (how strong hidden confounding must be)."""
    rr = 1 / rr if rr < 1 else rr
    return rr + np.sqrt(rr * (rr - 1))


def placebo_shuffle(df: pd.DataFrame, y: str, t: str = "late", n: int = 20) -> np.ndarray:
    """Shuffle lateness within purchase month x customer state cells, then re-estimate.

    The shuffled flag keeps each cell's late rate, so the placebo regression absorbs the
    cells with fixed effects; with the link to the outcome broken the effect should be ~0.
    """
    rng = np.random.default_rng(SEED)
    d = df.copy()
    d["cell"] = d["purchase_month"] + "|" + d["customer_state"]
    out = []
    for _ in range(n):
        d[t] = d.groupby("cell")[t].transform(lambda s: rng.permutation(s.to_numpy()))
        out.append(ols_seller_fe(d, y, t, fe="cell").estimate)
    return np.array(out)
