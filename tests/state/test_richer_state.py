"""Richer-state wiring: the unified builder computes follow_through_rate / sentiment_raw from a prebuilt
universe + threaded prev_gainers/history, and the live walk threads them so GCycle reads frontside on a
persistent runner (the precondition for screen-default-on)."""
from datetime import date, datetime
import pandas as pd
from alpha.data.source import FakeSource
from alpha.universe.universe import build_universe
from alpha.state.builder import build_market_state
from alpha.regime.classifier import GCycle


def _uni(day):
    src = FakeSource(calendar=[day], bars={}, snapshots={day: pd.DataFrame({
        "symbol": ["RUN"], "name": ["R"], "open": [10.0], "high": [13.0], "low": [10.0],
        "close": [12.0], "volume": [1], "prev_close": [10.0]})})           # +20% gainer
    return build_universe(src, day, gainer_pct=10.0, gap_pct=5.0, rvol_window=2)


def test_unified_builder_threads_follow_through_and_sentiment():
    day = date(2026, 6, 12)
    uni = _uni(day)
    ms = build_market_state(uni, day, as_of=datetime(2026, 6, 12, 16, 0),
                            prev_gainers=frozenset({"RUN"}), history=[])
    assert ms.follow_through_rate == 1.0          # RUN was a prior gainer and still is
    assert ms.sentiment_raw != 0.0                # composite computed (not the default)
    assert ms.sentiment_norm is None              # empty history < min_samples -> None (never fabricated)


def test_unified_builder_backcompat_defaults_match_minimal():
    day = date(2026, 6, 12)
    ms = build_market_state(_uni(day), day, as_of=datetime(2026, 6, 12, 16, 0))   # no history/prev_gainers
    assert ms.follow_through_rate is None and ms.sentiment_norm is None   # defaults reproduce the minimal


def test_gcycle_reads_frontside_on_persistent_runner():
    day = date(2026, 6, 12)
    ms = build_market_state(_uni(day), day, as_of=datetime(2026, 6, 12, 16, 0),
                            prev_gainers=frozenset({"RUN"}), history=[])
    read = GCycle().read(ms)
    assert read.frontside is True and read.phase == "trend"   # ft=1.0 + strong tape -> trend (was backside)
