"""US-3d acceptance: the L4 hard veto, wired via GuardedPolicy, enforces the dilution guard on a FRONTSIDE
regime — it drops a name with an announced ATM/shelf offering (open-ended dilution overhang), keeps the
clean low-float runner, surfaces the reason in key_risks, and renders free_float in the agent prompt.
Headline US-3d guarantee: float is live on the snapshot and the dormant dilution veto now fires on real
(PIT-by-announce) offering filings."""
from datetime import date, datetime
import pandas as pd
from alpha.data.source import FakeSource
from alpha.state.market import MarketState
from alpha.eval.decision import Candidate, DecisionPackage
from alpha.universe.universe import build_universe, CandidateUniverse
from alpha.state.builder import build_market_state
from alpha.agent.prompt import build_user_prompt
from alpha.guard.screen import GuardedPolicy

CUR = date(2026, 6, 12)


def _source():
    cal = [date(2026, 6, 11), CUR]
    snap = pd.DataFrame({
        "symbol": ["CLEAN", "DILUTE"], "name": ["Clean", "Diluter"],
        "open": [10.0, 10.0], "high": [13.0, 13.0], "low": [10.0, 10.0],
        "close": [12.0, 12.0], "volume": [5, 5], "prev_close": [10.0, 10.0],
        "free_float": [3.0, 4.0]})                                          # both low-float gainers (+20%)
    corp = pd.DataFrame({"symbol": ["DILUTE"], "announce_date": [date(2026, 6, 9)],
                         "ex_date": [date(2026, 6, 20)], "kind": ["shelf"], "ratio": [None]})
    return FakeSource(calendar=cal, bars={}, snapshots={CUR: snap}, corp_actions=corp)


def _frontside_state():
    return MarketState(date=CUR, gainer_count=2, gap_up_count=0, loser_count=0, failed_breakout_count=0,
                       max_runner_tier=1, echelon=[], breadth_raw=2.0, sentiment_norm=0.7,
                       follow_through_rate=0.5, as_of=datetime(2026, 6, 12, 16, 0))


class _StubPolicy:
    def decide(self, state, universe):
        return DecisionPackage(date=CUR, candidates=[Candidate(symbol=s, pattern="gap_and_go")
                                                     for s in ("CLEAN", "DILUTE")])


def test_guard_enforces_dilution_on_frontside():
    src = _source()
    out = GuardedPolicy(_StubPolicy(), src).decide(_frontside_state(), CandidateUniverse.from_stocks([]))
    assert [c.symbol for c in out.candidates] == ["CLEAN"]                  # the dilution name is dropped
    assert out.regime is not None and out.regime.frontside is True
    assert any("DILUTE" in r and "dilution" in r for r in out.key_risks)   # reason surfaced
    # float is live on the snapshot + rendered in the agent prompt
    uni = build_universe(src, CUR, gainer_pct=10.0, gap_pct=5.0, rvol_window=2)
    assert uni.get("CLEAN").free_float == 3.0
    state = build_market_state(uni, CUR, as_of=datetime(2026, 6, 12, 16, 0))
    assert "float=3M" in build_user_prompt(state, uni)
