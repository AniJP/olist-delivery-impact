"""Smoke test: the dashboard renders from the committed aggregates without errors."""

from pathlib import Path

import pytest

st_testing = pytest.importorskip("streamlit.testing.v1")

APP = Path(__file__).resolve().parents[1] / "dashboard" / "app.py"


def test_dashboard_renders():
    at = st_testing.AppTest.from_file(str(APP), default_timeout=60).run()
    assert not at.exception
    assert len(at.metric) >= 4
    assert len(at.tabs) == 4


def test_frontier_slider_updates_metrics():
    at = st_testing.AppTest.from_file(str(APP), default_timeout=60).run()
    before = at.metric[4].value
    at.slider[0].set_value(0.85).run()
    assert not at.exception
    assert at.metric[4].value != before
