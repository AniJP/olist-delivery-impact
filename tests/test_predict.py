"""Unit tests for the promise-model helpers (no warehouse needed)."""

import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "analysis"))
import predict as P  # noqa: E402


def test_promise_rounds_up_to_whole_days():
    assert P.promise_days(np.array([3.0, 3.01, 0.2])).tolist() == [3.0, 4.0, 1.0]


def test_in_transit_orders_never_count_as_kept():
    df = pd.DataFrame({"delivery_days": [5.0, np.nan, 12.0], "censored": [False, True, False]})
    assert P.kept(np.array([10.0, 999.0, 10.0]), df).tolist() == [True, False, False]


def test_conformal_offset_restores_coverage():
    rng = np.random.default_rng(0)
    n = 20000
    y = rng.lognormal(2.3, 0.5, n)
    # A model whose quantile predictions are all 30% too low.
    true_q = np.exp(2.3 + 0.5 * np.array([0.0, 0.253, 0.524, 0.842, 1.036, 1.282, 1.440, 1.645, 1.960]))
    pred = np.tile(true_q * 0.7, (n, 1))
    censored = np.zeros(n, dtype=bool)
    off = P.conformal_offsets(np.log1p(pred[: n // 2]), y[: n // 2], censored[: n // 2])
    fixed = P.apply_offsets(pred[n // 2 :], off)
    coverage = (y[n // 2 :, None] <= fixed).mean(axis=0)
    assert np.allclose(coverage, P.QUANTILES, atol=0.015)


def test_censored_orders_push_offsets_up():
    y = np.full(100, 10.0)
    pred = np.full((100, len(P.QUANTILES)), 10.0)
    none = P.conformal_offsets(np.log1p(pred), y, np.zeros(100, dtype=bool))
    some = P.conformal_offsets(np.log1p(pred), y, np.arange(100) < 5)
    assert (some >= none).all() and some[-1] > none[-1]


def test_prob_late_is_monotone_in_promise():
    pred = np.array([[10, 11, 12, 14, 15, 17, 18, 20, 24]], dtype=float)
    probs = [P.prob_late(pred, np.array([d]))[0] for d in [5, 10, 15, 20, 30]]
    assert probs == sorted(probs, reverse=True)
    assert probs[1] == pytest.approx(0.5)
    assert probs[-1] == pytest.approx(1 - P.QUANTILES[-1])
