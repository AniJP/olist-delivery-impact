"""Power calculations and simulation helpers for the Phase 5 experiment design."""

import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "analysis"))
import experiment as E  # noqa: E402


def test_sample_size_matches_textbook_value():
    # 10% -> 12%, alpha 5%, power 80%: about 3,840 per arm (unpooled-variance formula).
    assert E.n_per_arm_proportions(0.10, 0.12) == pytest.approx(3839, rel=0.01)


def test_mde_inverts_sample_size():
    n = E.n_per_arm_means(sd=1.3, delta=0.06)
    assert E.mde_mean(sd=1.3, n_per_arm=n) == pytest.approx(0.06)


def test_covariates_shrink_sample_size_proportionally():
    assert E.n_per_arm_means(1.0, 0.1, r2=0.5) == pytest.approx(E.n_per_arm_means(1.0, 0.1) / 2)


def test_customers_keep_one_arm():
    rng = np.random.default_rng(1)
    customers = pd.Series(["a", "a", "b", "c", "c", "c"])
    arms = E.assign_customers(customers, 0.5, rng)
    assert arms.groupby(customers).nunique().max() == 1


def test_aa_false_positive_rate_is_nominal():
    rng = np.random.default_rng(2)
    n = 3000
    df = pd.DataFrame({"customer_unique_id": rng.integers(0, 2000, n).astype(str), "y": rng.binomial(1, 0.1, n)})
    aa = E.aa_test(df, "y", n_sims=200, seed=3)
    assert 0.01 <= aa.significant.mean() <= 0.10


def test_geo_power_is_calibrated_and_increases_with_lift():
    rng = np.random.default_rng(4)
    weekly = pd.DataFrame(rng.poisson(lam=rng.uniform(20, 200, size=(60, 1)), size=(60, 30)))
    res = E.geo_power(weekly, pre_weeks=8, test_weeks=8, lifts=[0.0, 0.3], n_sims=200, seed=5)
    assert res.power.iloc[0] < 0.12
    assert res.power.iloc[1] > 0.9
