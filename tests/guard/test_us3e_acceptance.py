"""US-3e acceptance: the L4 hard veto, wired via GuardedPolicy, enforces the halt-then-dump guard on a
FRONTSIDE regime — it drops a name that spiked >=15% intraday (a likely LULD halt-up) then round-tripped to
close red, keeps the clean runner that held its spike, and surfaces the reason in key_risks. Headline US-3e
guarantee: the dormant halt_then_dump veto now fires on a daily-OHLC proxy (real intraday LULD/MWCB/
fill-feasibility are deferred — no intraday feed)."""
from datetime import date, datetime
import pandas as pd
from alpha.data.source import FakeSource
from alpha.state.market import MarketState
from alpha.eval.decision import Candidate, DecisionPackage
from alpha.universe.universe import CandidateUniverse
from alpha.guard.screen import GuardedPolicy

CUR = date(2026, 6, 12)


def _source():
    cal = [date(2026, 6, 11), CUR]
    snap = pd.DataFrame({
        "symbol": ["CLEAN", "SPIKE"], "name": ["Clean", "Spiker"],
        "open": [10.0, 10.0], "high": [12.0, 14.0], "low": [10.0, 9.0],
        "close": [12.0, 9.5], "volume": [5, 9], "prev_close": [10.0, 10.0]})
    # CLEAN: +20% intraday high but CLOSED green (12) -> not a halt-then-dump.
    # SPIKE: +40% intraday high (likely halt-up) but CLOSED red (9.5 <= 10) -> halt-then-dump.
    return FakeSource(calendar=cal, bars={}, snapshots={CUR: snap})


def _frontside_state():
    return MarketState(date=CUR, gainer_count=2, gap_up_count=0, loser_count=0, failed_breakout_count=0,
                       max_runner_tier=1, echelon=[], breadth_raw=2.0, sentiment_norm=0.7,
                       follow_through_rate=0.5, as_of=datetime(2026, 6, 12, 16, 0))


class _StubPolicy:
    def decide(self, state, universe):
        return DecisionPackage(date=CUR, candidates=[Candidate(symbol=s, pattern="gap_and_go")
                                                     for s in ("CLEAN", "SPIKE")])


def test_guard_enforces_halt_then_dump_on_frontside():
    out = GuardedPolicy(_StubPolicy(), _source()).decide(_frontside_state(), CandidateUniverse.from_stocks([]))
    assert [c.symbol for c in out.candidates] == ["CLEAN"]                       # the spiked-and-dumped name is dropped
    assert out.regime is not None and out.regime.frontside is True
    assert any("SPIKE" in r and "halt-then-dump" in r for r in out.key_risks)   # reason surfaced
