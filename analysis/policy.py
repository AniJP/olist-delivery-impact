"""Phase 4: turn delivery-time predictions into promise policies and price the trade-off.

A promise policy maps each order to a promised number of calendar days. Three families:

  olist_shift(k)        Olist's own promise, moved by k days for every order (the uniform lever)
  uniform_quantile(q)   the model's q-th predicted quantile for every order (same risk for all)
  cost_aware(r)         per order, the promise d that minimises  d + r * P(late | d)
                        where r = days of promise you would give up to avoid one late order.
                        Orders with a tight, predictable delivery get a promise close to their
                        tail; orders with a long uncertain tail are not padded all the way.

Every policy is evaluated on what actually happened: late rate (never-delivered orders count as
late), average promise, and the expected change in review score using the Phase 2 dose-response.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

QUANTILE_COLS = ["q500", "q600", "q700", "q800", "q850", "q900", "q925", "q950", "q975"]
QUANTILES = np.array([0.5, 0.6, 0.7, 0.8, 0.85, 0.9, 0.925, 0.95, 0.975])
MAX_DAYS = 120

# Adjusted review change by arrival vs promise, relative to arriving 1-7 days early
# (Phase 2 dose-response, regression with checkout-time controls).
BUCKETS = [
    ("1. 15+ days early", -np.inf, -15),
    ("2. 8-14 days early", -14, -8),
    ("3. 1-7 days early", -7, -1),
    ("4. on the day", 0, 0),
    ("5. 1-3 days late", 1, 3),
    ("6. 4-7 days late", 4, 7),
    ("7. 8-14 days late", 8, 14),
    ("8. 15+ days late", 15, np.inf),
]


# --------------------------------------------------------------------------- predicted distribution


def cdf_grid(pred: pd.DataFrame, max_days: int = MAX_DAYS) -> np.ndarray:
    """P(delivered within d days) for d = 0..max_days, one row per order.

    Linear interpolation between predicted quantiles, anchored at (0 days, 0%); beyond the
    highest predicted quantile the CDF stays flat at 97.5% (the model never promises certainty).
    """
    knots_x = np.column_stack([np.zeros(len(pred)), pred[QUANTILE_COLS].to_numpy(dtype=float)])
    knots_y = np.r_[0.0, QUANTILES]
    days = np.arange(max_days + 1, dtype=float)
    out = np.empty((len(pred), len(days)))
    for j, d in enumerate(days):
        idx = (knots_x <= d).sum(axis=1) - 1  # last knot at or below d
        top = idx >= knots_x.shape[1] - 1
        idx_c = np.clip(idx, 0, knots_x.shape[1] - 2)
        x0 = knots_x[np.arange(len(pred)), idx_c]
        x1 = knots_x[np.arange(len(pred)), idx_c + 1]
        y0, y1 = knots_y[idx_c], knots_y[idx_c + 1]
        frac = np.where(x1 > x0, (d - x0) / np.where(x1 > x0, x1 - x0, 1.0), 1.0)
        out[:, j] = np.where(top, knots_y[-1], y0 + np.clip(frac, 0, 1) * (y1 - y0))
    return out


# --------------------------------------------------------------------------- policies


def olist_shift(pred: pd.DataFrame, k: int) -> np.ndarray:
    return np.maximum(pred.promised_days.to_numpy(dtype=float) + k, 1)


def uniform_quantile(cdf: np.ndarray, q: float) -> np.ndarray:
    """Smallest whole day by which the predicted on-time probability reaches q."""
    reached = cdf >= q - 1e-12
    first = reached.argmax(axis=1).astype(float)
    first[~reached.any(axis=1)] = cdf.shape[1] - 1
    return np.maximum(first, 1)


def cost_aware(cdf: np.ndarray, r: float) -> np.ndarray:
    """argmin_d  d + r * (1 - CDF(d))  for each order."""
    days = np.arange(cdf.shape[1], dtype=float)
    cost = days[None, :] + r * (1 - cdf)
    return np.maximum(cost.argmin(axis=1).astype(float), 1)


# --------------------------------------------------------------------------- evaluation


def days_late(promise: np.ndarray, pred: pd.DataFrame) -> np.ndarray:
    """Arrival minus promise in days; never-delivered orders are treated as 15+ days late."""
    d = pred.delivery_days.to_numpy(dtype=float)
    out = d - promise
    return np.where(pred.censored.to_numpy(), 999.0, out)


def bucket_effects(dose_response: pd.DataFrame) -> dict[str, float]:
    return dict(zip(dose_response.bucket, dose_response.effect, strict=True))


def expected_review(late_days: np.ndarray, effects: dict[str, float]) -> np.ndarray:
    out = np.empty(len(late_days))
    for name, lo, hi in BUCKETS:
        m = (late_days >= lo) & (late_days <= hi)
        out[m] = effects[name]
    return out


def evaluate(promise: np.ndarray, pred: pd.DataFrame, effects: dict[str, float] | None = None) -> dict:
    late = days_late(promise, pred)
    row = {
        "late_rate": float((late > 0).mean()),
        "avg_promise_days": float(promise.mean()),
        "median_promise_days": float(np.median(promise)),
    }
    if effects is not None:
        row["avg_review_effect"] = float(expected_review(late, effects).mean())
    return row


def frontier(pred: pd.DataFrame, cdf: np.ndarray, effects: dict[str, float] | None = None) -> pd.DataFrame:
    """Sweep each policy family's parameter and evaluate every setting."""
    rows = []
    for k in range(-12, 16):
        rows.append({"policy": "Olist promise shifted", "param": k, **evaluate(olist_shift(pred, k), pred, effects)})
    for q in np.round(np.arange(0.70, 0.976, 0.005), 3):
        rows.append({"policy": "model, same quantile", "param": q, **evaluate(uniform_quantile(cdf, q), pred, effects)})
    for r in np.geomspace(5, 2000, 45):
        rows.append({"policy": "model, cost-aware", "param": r, **evaluate(cost_aware(cdf, r), pred, effects)})
    return pd.DataFrame(rows)


def tune(pred: pd.DataFrame, cdf: np.ndarray, family: str, metric: str, target: float) -> float:
    """Pick the parameter whose `metric` on `pred` is closest to `target` (done on the calibration month)."""
    grid = {
        "olist_shift": (range(-12, 16), lambda p: olist_shift(pred, p)),
        "uniform_quantile": (np.round(np.arange(0.70, 0.976, 0.0025), 4), lambda p: uniform_quantile(cdf, p)),
        "cost_aware": (np.geomspace(5, 2000, 120), lambda p: cost_aware(cdf, p)),
    }[family]
    values, make = grid
    scores = [(abs(evaluate(make(v), pred)[metric] - target), v) for v in values]
    return min(scores)[1]


def promise_for(pred: pd.DataFrame, cdf: np.ndarray, family: str, param: float) -> np.ndarray:
    if family == "olist_shift":
        return olist_shift(pred, int(param))
    if family == "uniform_quantile":
        return uniform_quantile(cdf, param)
    return cost_aware(cdf, param)
