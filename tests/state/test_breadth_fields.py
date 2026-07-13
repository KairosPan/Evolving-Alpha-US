"""Growth-doctrine breadth exposed on MarketState (P0.4): additive fields, default None, threaded in via
`breadth` like history/prev_gainers, byte-identical to the pre-P0.4 build when omitted."""
from datetime import date, datetime

import pandas as pd

from alpha.data.source import FakeSource
from alpha.features.breadth import BreadthReading
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


def test_breadth_fields_default_none():
    ms = build_market_state(_uni(), DAY, as_of=ASOF)          # no breadth threaded
    assert ms.pct_above_200dma is None and ms.net_new_highs is None
    assert ms.advances is None and ms.declines is None


def test_marketstate_backward_compatible_defaults():
    # Constructing MarketState the old way (no breadth kwargs) still works -> additive/default-None.
    ms = MarketState(date=DAY, gainer_count=0, gap_up_count=0, loser_count=0, failed_breakout_count=0,
                     max_runner_tier=0, echelon=[], breadth_raw=0.0, sentiment_norm=None, as_of=ASOF)
    assert ms.pct_above_200dma is None and ms.net_new_highs is None


def test_breadth_threaded_populates_fields():
    reading = BreadthReading(pct_above_200dma=0.62, net_new_highs=14, advances=310, declines=190)
    ms = build_market_state(_uni(), DAY, as_of=ASOF, breadth=reading)
    assert ms.pct_above_200dma == 0.62 and ms.net_new_highs == 14
    assert ms.advances == 310 and ms.declines == 190


def test_off_is_byte_identical_to_no_breadth():
    # Threading breadth=None must yield exactly the same MarketState as omitting it (default-off proof).
    a = build_market_state(_uni(), DAY, as_of=ASOF)
    b = build_market_state(_uni(), DAY, as_of=ASOF, breadth=None)
    assert a.model_dump() == b.model_dump()
