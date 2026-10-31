"""Phase 3: predict, at checkout, how many calendar days an order will take to arrive.

Instead of one number, the model predicts a set of quantiles (P50 ... P99). A promise set at the
q-th quantile should be kept for a share q of orders, so quantiles turn directly into promises
with a chosen on-time rate (Phase 4).

Design choices
  * Features come from marts.fct_order_features and are point-in-time (tested in dbt).
  * Time-based split: train on 2017, tune and calibrate on January 2018, test on Feb-Aug 2018,
    which includes the Feb-Mar 2018 disruption the model has never seen.
  * LightGBM quantile regression on log(1 + days); quantiles survive monotone transforms.
  * Split-conformal adjustment on the calibration month so each quantile's coverage is honest.
  * Orders still in transit at extraction ("shipped") are kept in evaluation and count as missed
    promises; dropping them would flatter every method.
"""

from __future__ import annotations

import duckdb
import lightgbm as lgb
import numpy as np
import pandas as pd

SEED = 605
QUANTILES = [0.5, 0.6, 0.7, 0.8, 0.85, 0.9, 0.925, 0.95, 0.975]

TRAIN = ("2017-01-01", "2017-12-31")
CALIB = ("2018-01-01", "2018-01-31")
TEST = ("2018-02-01", "2018-08-31")

NUMERIC = [
    "distance_km",
    "same_state",
    "n_items",
    "n_sellers",
    "items_value",
    "freight_value",
    "freight_share",
    "weight_kg",
    "max_item_volume_cm3",
    "max_installments",
    "purchase_dow",
    "purchase_hour",
    "promised_days",
    "seller_prior_orders",
    "seller_prior_delivery_days",
    "seller_prior_days_to_ship",
    "seller_prior_late_rate",
    "days_since_seller_last_delivery",
    "net_delivery_days_last_14d",
    "net_late_rate_last_14d",
    "net_purchases_last_7d",
    "net_open_orders",
    "state_delivery_days_last_30d",
    "state_delivered_last_30d",
]
CATEGORICAL = ["customer_state", "seller_state", "route", "main_category", "main_payment_type"]
FEATURES = NUMERIC + CATEGORICAL

PARAMS = {
    "learning_rate": 0.05,
    "num_leaves": 31,
    "min_child_samples": 50,
    "feature_fraction": 0.8,
    "bagging_fraction": 0.8,
    "bagging_freq": 1,
    "lambda_l2": 1.0,
    "cat_smooth": 20,
    "verbose": -1,
    "seed": SEED,
}


# --------------------------------------------------------------------------- data


def load(db_path: str) -> pd.DataFrame:
    con = duckdb.connect(db_path, read_only=True)
    df = con.execute(
        f"""
        select *
        from marts.fct_order_features
        where purchase_date between '{TRAIN[0]}' and '{TEST[1]}'
          and (is_analysis_eligible or order_status = 'shipped')
        """
    ).df()
    con.close()
    df["censored"] = df["delivery_days"].isna()
    df["split"] = np.select(
        [df.purchase_date <= pd.Timestamp(TRAIN[1]), df.purchase_date <= pd.Timestamp(CALIB[1])],
        ["train", "calib"],
        "test",
    )
    df["same_state"] = df["same_state"].astype(float)
    for c in CATEGORICAL:
        df[c] = df[c].fillna("unknown").astype("category")
    return df.sort_values("purchased_at").reset_index(drop=True)


def _align_categories(df: pd.DataFrame, reference: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    for c in CATEGORICAL:
        out[c] = pd.Categorical(out[c].astype(str), categories=reference[c].cat.categories)
    return out


# --------------------------------------------------------------------------- models


def pinball(y: np.ndarray, pred: np.ndarray, q: float) -> float:
    d = y - pred
    return float(np.mean(np.maximum(q * d, (q - 1) * d)))


def fit_quantile_models(train: pd.DataFrame, valid: pd.DataFrame) -> dict[float, lgb.Booster]:
    """One LightGBM model per quantile on log(1 + days), early-stopped on the calibration month."""
    tr = train[~train.censored]
    va = valid[~valid.censored]
    dtrain = lgb.Dataset(tr[FEATURES], np.log1p(tr.delivery_days), categorical_feature=CATEGORICAL, free_raw_data=False)
    dvalid = lgb.Dataset(va[FEATURES], np.log1p(va.delivery_days), reference=dtrain)
    models = {}
    for q in QUANTILES:
        params = {**PARAMS, "objective": "quantile", "alpha": q, "metric": "quantile"}
        models[q] = lgb.train(
            params,
            dtrain,
            num_boost_round=3000,
            valid_sets=[dvalid],
            callbacks=[lgb.early_stopping(100, verbose=False)],
        )
    return models


def predict_quantiles(models: dict[float, lgb.Booster], df: pd.DataFrame) -> np.ndarray:
    """Matrix (n_orders x n_quantiles) in days, sorted across quantiles so they never cross."""
    logp = np.column_stack([models[q].predict(df[FEATURES], num_iteration=models[q].best_iteration) for q in QUANTILES])
    return np.expm1(np.sort(logp, axis=1))


def conformal_offsets(pred_log: np.ndarray, y: np.ndarray, censored: np.ndarray) -> np.ndarray:
    """One-sided split-conformal correction per quantile, computed in log space.

    For quantile q the offset is the q-th empirical quantile (with the n+1 correction) of
    y - prediction on the calibration month. Censored orders get +inf scores: they were not
    delivered within any promise the model could have made.
    """
    y_log = np.where(censored, np.inf, np.log1p(np.nan_to_num(y)))
    offsets = []
    for j, q in enumerate(QUANTILES):
        scores = np.sort(y_log - pred_log[:, j])
        k = min(len(scores) - 1, int(np.ceil((len(scores) + 1) * q)) - 1)
        offsets.append(scores[k])
    return np.array(offsets)


def apply_offsets(pred_days: np.ndarray, offsets: np.ndarray) -> np.ndarray:
    return np.expm1(np.sort(np.log1p(pred_days) + offsets, axis=1))


def route_baseline(train: pd.DataFrame, df: pd.DataFrame, min_orders: int = 30) -> np.ndarray:
    """Empirical delivery-time quantiles per route, falling back to destination state, then global."""
    tr = train[~train.censored]
    out = np.full((len(df), len(QUANTILES)), np.nan)
    for level in ["route", "customer_state"]:
        g = tr.groupby(level, observed=True).delivery_days
        counts = g.size()
        ok = counts[counts >= min_orders].index
        table = g.quantile(QUANTILES).unstack().loc[ok]
        keys = df[level].astype(str)
        table.index = table.index.astype(str)
        hit = keys.isin(table.index).to_numpy() & np.isnan(out[:, 0])
        out[hit] = table.loc[keys[hit]].to_numpy()
    glob = tr.delivery_days.quantile(QUANTILES).to_numpy()
    miss = np.isnan(out[:, 0])
    out[miss] = glob
    return out


# --------------------------------------------------------------------------- evaluation


def promise_days(pred_days: np.ndarray) -> np.ndarray:
    """A promise is a calendar date, so round the predicted days up."""
    return np.ceil(pred_days - 1e-9)


def kept(promise: np.ndarray, df: pd.DataFrame) -> np.ndarray:
    """Whether each order arrived on or before the promised day (in-transit orders never did)."""
    days = df.delivery_days.to_numpy(dtype=float)
    return (~df.censored.to_numpy()) & (days <= promise)


def coverage_table(df: pd.DataFrame, preds: dict[str, np.ndarray]) -> pd.DataFrame:
    """For each method and quantile: on-time rate, average promise, and pinball loss."""
    rows = []
    y = df.delivery_days.to_numpy(dtype=float)
    obs = ~df.censored.to_numpy()
    for name, p in preds.items():
        for j, q in enumerate(QUANTILES):
            prom = promise_days(p[:, j])
            rows.append(
                {
                    "method": name,
                    "quantile": q,
                    "on_time_rate": kept(prom, df).mean(),
                    "avg_promise_days": prom.mean(),
                    "pinball_loss": pinball(y[obs], p[obs, j], q),
                }
            )
    return pd.DataFrame(rows)


def olist_reference(df: pd.DataFrame) -> dict:
    prom = df.promised_days.to_numpy(dtype=float)
    return {"on_time_rate": kept(prom, df).mean(), "avg_promise_days": prom.mean()}


def prob_late(pred_days: np.ndarray, promise: np.ndarray) -> np.ndarray:
    """P(delivered after `promise`) per order, by interpolating the predicted quantile function."""
    qs = np.array(QUANTILES)
    out = np.empty(len(promise))
    for i in range(len(promise)):
        # Anchor the curve at (0 days, 0%) so promises below the median still get a probability.
        cdf = np.interp(promise[i], np.r_[0.0, pred_days[i]], np.r_[0.0, qs], right=qs[-1])
        out[i] = 1 - cdf
    return out
