"""P2 fix #4 — the growth market clock / panic breadth is decoupled from the candidate universe screen.

Under a non-gainer candidate screen (the growth pack's own `trend_template`), the candidate universe
carries NO gainer/loser counts, so a naive `build_market_state` would zero the clock + panic inputs and
they'd silently starve (permanent warm-up / dead panic veto). `tape_breadth` reads the market-wide ±10%
tape independent of the screen, and `build_market_state(market_counts=...)` feeds it to the clock —
byte-identical under the gainer screen, screen-independent otherwise.
"""
from __future__ import annotations

from datetime import date, datetime

import pandas as pd

from alpha.data.firewall import AsOfGuard
from alpha.data.source import FakeSource, GuardedSource
from alpha.features.breadth import counts
from alpha.regime.growth_clock import GrowthMarketClock, MIN_HISTORY
from alpha.state.builder import build_market_state
from alpha.state.market import MarketState
from alpha.universe.stock import StockSnapshot
from alpha.universe.universe import CandidateUniverse, build_universe, tape_breadth

DAY = date(2026, 6, 12)


def _snapshot() -> pd.DataFrame:
    """3 gainers (+12%), 2 losers (-12%), 1 flat — a clear market tape."""
    rows = []
    for s, mult in [("G1", 1.12), ("G2", 1.12), ("G3", 1.12), ("L1", 0.88), ("L2", 0.88), ("F", 1.0)]:
        rows.append({"symbol": s, "name": s, "open": 100.0, "high": 100.0 * max(1.0, mult),
                     "low": 100.0 * min(1.0, mult), "close": 100.0 * mult, "volume": 1, "prev_close": 100.0})
    return pd.DataFrame(rows)


def _src() -> FakeSource:
    return FakeSource(calendar=[DAY], bars={}, snapshots={DAY: _snapshot()})


def _as_of() -> datetime:
    return datetime(DAY.year, DAY.month, DAY.day, 16, 0)


def test_tape_breadth_equals_gainer_screen_counts():
    """Byte-identity anchor: under the gainer screen tape_breadth == counts(universe) gainers/losers."""
    guarded = GuardedSource(_src(), AsOfGuard(DAY))
    u = build_universe(guarded, DAY)
    g, _gu, lo = counts(u)
    assert tape_breadth(_snapshot()) == (g, lo) == (3, 2)


def test_build_market_state_starves_under_trend_template_without_market_counts():
    """A candidate universe of only trend_template-status names has gainer_count 0 -> the clock/panic
    inputs starve when market_counts is not threaded (the bug)."""
    tt = CandidateUniverse.from_stocks(
        [StockSnapshot(symbol=s, name=s, status="trend_template") for s in ("A", "B", "C")])
    starved = build_market_state(tt, DAY, as_of=_as_of())
    assert starved.gainer_count == 0 and starved.loser_count == 0


def test_market_counts_decouples_the_clock_input_from_the_screen():
    """With market_counts=tape_breadth threaded, the SAME starved candidate universe yields the full-tape
    market breadth for the clock/panic (3 gainers / 2 losers), regardless of the candidate screen."""
    tt = CandidateUniverse.from_stocks(
        [StockSnapshot(symbol=s, name=s, status="trend_template") for s in ("A", "B", "C")])
    decoupled = build_market_state(tt, DAY, as_of=_as_of(), market_counts=tape_breadth(_snapshot()))
    assert decoupled.gainer_count == 3 and decoupled.loser_count == 2
    assert decoupled.breadth_raw == 1.0


def _bull_state(g: int, l: int) -> MarketState:
    return build_market_state(
        CandidateUniverse.from_stocks([StockSnapshot(symbol=s, name=s, status="trend_template")
                                       for s in ("A",)]),
        DAY, as_of=_as_of(), market_counts=(g, l))


def test_clock_reads_a_real_uptrend_under_trend_template_not_permanent_warmup():
    """End-to-end: a bull tape fed through market_counts (as a trend_template run would) reads
    confirmed_uptrend — NOT the permanent warm-up/under_pressure the starved (candidate-coupled) inputs
    would force."""
    history = [_bull_state(7, 3) for _ in range(MIN_HISTORY + 3)]     # sustained up-breadth tape
    read = GrowthMarketClock().read(history, _bull_state(8, 2))
    assert read.phase == "market:confirmed_uptrend" and read.frontside is True
