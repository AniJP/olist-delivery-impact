"""Promise policies on a tiny hand-built example (no warehouse needed)."""

import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "analysis"))
import policy as Y  # noqa: E402


@pytest.fixture
def orders() -> pd.DataFrame:
    # Order 1: tight distribution around 10 days. Order 2: wide, long-tailed.
    q1 = [10, 10.5, 11, 12, 12.5, 13, 13.5, 14, 15]
    q2 = [10, 12, 15, 20, 23, 27, 30, 35, 45]
    df = pd.DataFrame([q1, q2], columns=Y.QUANTILE_COLS)
    df["promised_days"] = [20, 20]
    df["delivery_days"] = [13.0, np.nan]
    df["censored"] = [False, True]
    return df


def test_cdf_hits_the_predicted_quantiles(orders):
    cdf = Y.cdf_grid(orders)
    assert cdf[0, 13] == pytest.approx(0.9)
    assert cdf[1, 45] == pytest.approx(0.975)
    assert (np.diff(cdf, axis=1) >= -1e-12).all()
    assert cdf[:, 0].max() == 0


def test_uniform_quantile_gives_each_order_its_own_percentile(orders):
    cdf = Y.cdf_grid(orders)
    assert Y.uniform_quantile(cdf, 0.9).tolist() == [13, 27]


def test_cost_aware_pads_tight_orders_more_than_uncertain_ones(orders):
    cdf = Y.cdf_grid(orders)
    p = Y.cost_aware(cdf, r=100)
    # The tight order is promised its 97.5th percentile; the long-tailed one stops at its 90th.
    assert p.tolist() == [15, 27]


def test_never_delivered_orders_count_as_late(orders):
    out = Y.evaluate(np.array([15.0, 999.0]), orders)
    assert out["late_rate"] == 0.5


def test_review_effect_uses_lateness_buckets():
    effects = {name: float(i) for i, (name, _, _) in enumerate(Y.BUCKETS)}
    got = Y.expected_review(np.array([-20, -10, -3, 0, 2, 5, 10, 30]), effects)
    assert got.tolist() == list(range(8))
