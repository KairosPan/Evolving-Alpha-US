"""Acceptance: with the richer state builder wired + screen default-on, the live perception reads frontside
on a genuine uptrend (so the guard keeps the clean runner) AND still drops a real SSR name (prior-day
<= -10%). This is the production posture: the L4 guard is always live and correct, not over-firing on every
uptrend."""
from datetime import date, datetime
import pandas as pd
from alpha.data.source import FakeSource
from alpha.state.builder import build_market_state
from alpha.universe.universe import build_universe, CandidateUniverse
from alpha.regime.classifier import GCycle
from alpha.eval.decision import Candidate, DecisionPackage
from alpha.guard.screen import GuardedPolicy

CUR = date(2026, 6, 12)


def _source():
    # SSR (Reg SHO) needs the prior-day close-to-close drop, which ssr_active reads via two calendar days
    # <= the prior trading day -> the calendar must include 6/10, 6/11 AND 6/12 (a 2-day calendar makes
    # _prior_day_pct return None and SSR never fires).
    cal = [date(2026, 6, 10), date(2026, 6, 11), CUR]
    snap = pd.DataFrame({
        "symbol": ["RUN", "KNIFE"], "name": ["Runner", "Knife"],
        "open": [10.0, 10.0], "high": [12.0, 10.0], "low": [10.0, 8.0],
        "close": [12.0, 9.0], "volume": [1, 1], "prev_close": [10.0, 10.0]})   # RUN +20% gainer; KNIFE -10% today
    bars = {"KNIFE": pd.DataFrame({"date": [date(2026, 6, 10), date(2026, 6, 11)],
                                   "open": [10.0, 8.8], "high": [10, 9], "low": [8, 8],
                                   "close": [10.0, 8.8], "volume": [1, 1]})}     # KNIFE -12% on 6/11 -> SSR on 6/12
    return FakeSource(calendar=cal, bars=bars, snapshots={CUR: snap})


class _StubPolicy:
    def decide(self, state, universe):
        return DecisionPackage(date=CUR, candidates=[Candidate(symbol=s, pattern="gap_and_go")
                                                     for s in ("RUN", "KNIFE")])


def test_richer_state_frontside_keeps_runner_but_drops_ssr():
    src = _source()
    uni = build_universe(src, CUR, gainer_pct=10.0, gap_pct=5.0, rvol_window=2)
    state = build_market_state(uni, CUR, as_of=datetime(2026, 6, 12, 16, 0),
                               history=[], prev_gainers=frozenset({"RUN"}))   # RUN persisted -> ft populated
    assert GCycle().read(state).frontside is True                  # frontside, not over-firing backside
    out = GuardedPolicy(_StubPolicy(), src).decide(state, CandidateUniverse.from_stocks([]))
    assert [c.symbol for c in out.candidates] == ["RUN"]           # clean frontside runner kept
    assert any("KNIFE" in r and "SSR" in r for r in out.key_risks) # the real SSR name still vetoed
