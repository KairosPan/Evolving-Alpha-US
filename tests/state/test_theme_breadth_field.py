"""P5b-consumer additive perception exposure: `MarketState.theme_breadth` threaded through
`build_market_state`, default None, byte-identical when omitted (the P0.4 breadth-family precedent, one
level up — a nested `ThemeBreadthReading` bundle instead of four scalars)."""
from datetime import date, datetime

import pandas as pd

from alpha.data.source import FakeSource
from alpha.features.theme_breadth import GroupBreadthReading, ThemeBreadthReading
from alpha.state.builder import build_market_state
from alpha.state.market import MarketState
from alpha.universe.universe import build_universe

DAY = date(2026, 6, 12)
ASOF = datetime(2026, 6, 12, 16, 0)


def _uni(day=DAY):
    src = FakeSource(calendar=[day], bars={}, snapshots={day: pd.DataFrame({
        "symbol": ["RUN"], "name": ["R"], "open": [10.0], "high": [13.0], "low": [10.0],
        "close": [12.0], "volume": [1], "prev_close": [10.0]})})
    return build_universe(src, day, gainer_pct=10.0, gap_pct=5.0, rvol_window=2)


def _bundle():
    return ThemeBreadthReading(day=DAY, groups={
        "ai": GroupBreadthReading(group="ai", member_count=5, determined=True,
                                  pct_above_200dma=0.7, rs_dispersion=30.0, rs_trend=5.0)})


def test_theme_breadth_defaults_none():
    ms = build_market_state(_uni(), DAY, as_of=ASOF)          # nothing threaded
    assert ms.theme_breadth is None


def test_marketstate_backward_compatible_default():
    ms = MarketState(date=DAY, gainer_count=0, gap_up_count=0, loser_count=0, failed_breakout_count=0,
                     max_runner_tier=0, echelon=[], breadth_raw=0.0, sentiment_norm=None, as_of=ASOF)
    assert ms.theme_breadth is None


def test_theme_breadth_threaded_populates_field():
    ms = build_market_state(_uni(), DAY, as_of=ASOF, theme_breadth=_bundle())
    assert ms.theme_breadth is not None
    assert ms.theme_breadth.groups["ai"].pct_above_200dma == 0.7
    assert ms.theme_breadth.groups["ai"].rs_dispersion == 30.0


def test_off_is_byte_identical_to_no_theme_breadth():
    """Threading theme_breadth=None must yield exactly the same MarketState as omitting it — the
    default-off / DORMANT proof (no theme_breadth threaded => byte-identical MarketState)."""
    a = build_market_state(_uni(), DAY, as_of=ASOF)
    b = build_market_state(_uni(), DAY, as_of=ASOF, theme_breadth=None)
    assert a.model_dump() == b.model_dump()
