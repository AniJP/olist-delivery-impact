"""The estimators must recover a known effect from simulated, confounded data."""

import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "analysis"))
import causal as C  # noqa: E402

TRUE_EFFECT = -2.0


@pytest.fixture(scope="module")
def confounded() -> pd.DataFrame:
    """Distance raises both the chance of being late and (independently) lowers the review."""
    rng = np.random.default_rng(0)
    n = 8000
    df = pd.DataFrame({c: rng.normal(size=n) for c in C.NUMERIC})
    df["log_distance"] = rng.normal(6, 1, n)
    for c in C.CATEGORICAL:
        df[c] = rng.choice(["a", "b", "c"], size=n)
    df["seller_id"] = rng.integers(0, 200, n).astype(str)
    p_late = 1 / (1 + np.exp(-(-3 + 1.2 * (df["log_distance"] - 6))))
    df["late"] = (rng.random(n) < p_late).astype(int)
    df["review"] = 4.3 - 0.4 * (df["log_distance"] - 6) + TRUE_EFFECT * df["late"] + rng.normal(0, 0.8, n)
    return df


def test_naive_is_biased(confounded):
    assert C.naive(confounded, "review").estimate < TRUE_EFFECT - 0.2


@pytest.mark.parametrize("estimator", [C.ols, C.ols_seller_fe, C.ipw_att, C.aipw_att])
def test_adjusted_estimators_recover_effect(confounded, estimator):
    est = estimator(confounded, "review")
    lo, hi = est.ci
    assert lo - 0.05 < TRUE_EFFECT < hi + 0.05, (est.method, est.estimate)


def test_weighting_balances_confounder(confounded):
    bal = C.balance_table(confounded).set_index("variable")
    assert abs(bal.loc["log_distance", "smd_before"]) > 0.5
    assert abs(bal.loc["log_distance", "smd_after"]) < 0.1


def test_e_value_known_case():
    # VanderWeele & Ding: RR = 2 gives E-value 2 + sqrt(2) = 3.41
    assert C.e_value(2.0) == pytest.approx(3.414, abs=1e-3)
    assert C.e_value(0.5) == pytest.approx(3.414, abs=1e-3)
