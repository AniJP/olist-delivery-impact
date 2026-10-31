"""Phase 5: sizing an experiment that tests model-based delivery promises.

Closed-form power for proportions and means, plus simulations on historical orders:

  * A/A tests: split real customers at random, check the analysis gives ~5% false positives.
  * Replay: for treated customers, re-score lateness under the model's promise. Only the promise
    changes, so the real delivery dates still apply. This gives the late-rate effect without
    any modelling assumptions.
  * Geo design: randomise regions (two-digit CEP prefix) and estimate the minimum detectable
    sales lift from real weekly order counts.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import statsmodels.api as sm
from scipy import stats

SEED = 605


# --------------------------------------------------------------------------- closed form


def _z(alpha: float, power: float) -> float:
    return stats.norm.ppf(1 - alpha / 2) + stats.norm.ppf(power)


def n_per_arm_proportions(p0: float, p1: float, alpha: float = 0.05, power: float = 0.8) -> float:
    """Units per arm to detect p0 -> p1 with a two-sided two-sample z-test."""
    return _z(alpha, power) ** 2 * (p0 * (1 - p0) + p1 * (1 - p1)) / (p1 - p0) ** 2


def n_per_arm_means(sd: float, delta: float, alpha: float = 0.05, power: float = 0.8, r2: float = 0.0) -> float:
    """Units per arm to detect a mean difference `delta`; `r2` is the variance explained by covariates (CUPED)."""
    return 2 * _z(alpha, power) ** 2 * sd**2 * (1 - r2) / delta**2


def mde_proportion(p0: float, n_per_arm: float, alpha: float = 0.05, power: float = 0.8) -> float:
    """Smallest absolute change from p0 detectable with n per arm (variance at p0)."""
    return _z(alpha, power) * np.sqrt(2 * p0 * (1 - p0) / n_per_arm)


def mde_mean(sd: float, n_per_arm: float, alpha: float = 0.05, power: float = 0.8, r2: float = 0.0) -> float:
    return _z(alpha, power) * sd * np.sqrt(2 * (1 - r2) / n_per_arm)


# --------------------------------------------------------------------------- order-level simulations


def assign_customers(customers: pd.Series, share: float, rng: np.random.Generator) -> pd.Series:
    """Randomise at customer level: every order of a customer gets the same arm."""
    ids = customers.unique()
    treated = set(ids[rng.random(len(ids)) < share])
    return customers.isin(treated).astype(int)


def estimate(df: pd.DataFrame, y: str, covariates: list[str] | None = None) -> tuple[float, float]:
    """Treatment effect and customer-clustered SE, optionally regression-adjusted (CUPED-style)."""
    cols = ["treat"] + (covariates or [])
    X = sm.add_constant(df[cols].astype(float))
    fit = sm.OLS(df[y].astype(float), X).fit(
        cov_type="cluster", cov_kwds={"groups": pd.factorize(df["customer_unique_id"])[0]}
    )
    return float(fit.params["treat"]), float(fit.bse["treat"])


def aa_test(
    df: pd.DataFrame, y: str, n_sims: int = 200, covariates: list[str] | None = None, seed: int = SEED
) -> pd.DataFrame:
    """Repeated A/A splits of real orders: share of false positives and the empirical SE."""
    rng = np.random.default_rng(seed)
    rows = []
    for _ in range(n_sims):
        d = df.assign(treat=assign_customers(df.customer_unique_id, 0.5, rng))
        est, se = estimate(d, y, covariates)
        rows.append({"estimate": est, "se": se, "significant": abs(est / se) > 1.96})
    return pd.DataFrame(rows)


def replay_power(
    df: pd.DataFrame,
    control_late: np.ndarray,
    treated_late: np.ndarray,
    sample_sizes: list[int],
    n_sims: int = 200,
    seed: int = SEED,
) -> pd.DataFrame:
    """Power to detect the late-rate change, replaying real deliveries against each arm's promise.

    For a random subsample of n orders, customers are randomised 50/50; treated orders are scored
    with `treated_late` (lateness under the model promise), control orders with `control_late`.
    """
    rng = np.random.default_rng(seed)
    rows = []
    for n in sample_sizes:
        hits = []
        for _ in range(n_sims):
            idx = rng.choice(len(df), size=n, replace=False)
            d = df.iloc[idx].copy()
            d["treat"] = assign_customers(d.customer_unique_id, 0.5, rng).to_numpy()
            d["late"] = np.where(d.treat == 1, treated_late[idx], control_late[idx]).astype(float)
            est, se = estimate(d, "late")
            hits.append(abs(est / se) > 1.96)
        rows.append({"orders": n, "power": float(np.mean(hits))})
    return pd.DataFrame(rows)


# --------------------------------------------------------------------------- geo design


def weekly_region_orders(orders: pd.DataFrame, region: str = "region") -> pd.DataFrame:
    """Orders per region per week (regions x weeks)."""
    w = orders.assign(week=orders.purchase_date.dt.to_period("W").dt.start_time)
    return w.groupby([region, "week"]).size().unstack(fill_value=0)


def geo_power(
    weekly: pd.DataFrame,
    pre_weeks: int,
    test_weeks: int,
    lifts: list[float],
    n_sims: int = 500,
    min_pre_orders: int = 20,
    seed: int = SEED,
) -> pd.DataFrame:
    """Power of a region-randomised test on order volume, simulated on real weekly orders.

    For a random start week, regions with at least `min_pre_orders` in the pre-period are sorted by
    size and randomised within adjacent pairs. The estimate is the paired difference in
    log(test-period orders / pre-period orders), tested with a one-sample t-test across pairs.
    The lift is applied multiplicatively to the treated regions' test-period orders.
    """
    rng = np.random.default_rng(seed)
    cols = weekly.columns
    starts = np.arange(pre_weeks, len(cols) - test_weeks + 1)
    rows = []
    for lift in lifts:
        hits = []
        for _ in range(n_sims):
            s = rng.choice(starts)
            pre = weekly[cols[s - pre_weeks : s]].sum(axis=1)
            post = weekly[cols[s : s + test_weeks]].sum(axis=1)
            keep = pre >= min_pre_orders
            pre, post = pre[keep].to_numpy(float), post[keep].to_numpy(float)
            order = np.argsort(-pre)[: keep.sum() // 2 * 2].reshape(-1, 2)
            flip = rng.random(len(order)) < 0.5
            t_idx = np.where(flip, order[:, 0], order[:, 1])
            c_idx = np.where(flip, order[:, 1], order[:, 0])
            growth_t = np.log((post[t_idx] * (1 + lift) + 0.5) / (pre[t_idx] + 0.5))
            growth_c = np.log((post[c_idx] + 0.5) / (pre[c_idx] + 0.5))
            hits.append(stats.ttest_1samp(growth_t - growth_c, 0.0).pvalue < 0.05)
        rows.append({"lift": lift, "test_weeks": test_weeks, "power": float(np.mean(hits))})
    return pd.DataFrame(rows)
