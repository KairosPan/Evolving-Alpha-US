# tests/state/test_market.py
from __future__ import annotations
from datetime import date, datetime
import pytest
from pydantic import ValidationError
from alpha.state.market import MarketState, RunnerRung


def test_runner_rung_frozen():
    r = RunnerRung(tier=3, count=2, representatives=["RUN", "MOON"])
    with pytest.raises(ValidationError):
        r.count = 5


def test_market_state_minimal():
    ms = MarketState(
        date=date(2026, 6, 12), gainer_count=12, gap_up_count=8, loser_count=3,
        failed_breakout_count=4, max_runner_tier=3,
        echelon=[RunnerRung(tier=3, count=1, representatives=["RUN"])],
        breadth_raw=0.6, sentiment_norm=None, as_of=datetime(2026, 6, 12, 16, 0))
    assert ms.gainer_count == 12
    assert ms.sentiment_norm is None


def test_sentiment_norm_bounds():
    with pytest.raises(ValidationError):
        MarketState(date=date(2026, 6, 12), gainer_count=0, gap_up_count=0, loser_count=0,
                    failed_breakout_count=0, max_runner_tier=0, echelon=[], breadth_raw=0.0,
                    sentiment_norm=1.5, as_of=datetime(2026, 6, 12, 16, 0))
