"""US-3b acceptance: the L4 hard veto, wired via GuardedPolicy, enforces the immutable dont_fight_ssr +
reverse-split doctrine on a FRONTSIDE regime — it drops an SSR name (prior-day -12%) and a reverse-split
name, keeps the clean runner, surfaces the reasons in key_risks, and populates the structured regime.
This is the headline US-3b guarantee: the dormant guard now fires on real, PIT-computed data flags."""
from datetime import date, datetime
import pandas as pd
from alpha.data.source import FakeSource
from alpha.state.market import MarketState
from alpha.eval.decision import Candidate, DecisionPackage
from alpha.universe.universe import CandidateUniverse
from alpha.guard.screen import GuardedPolicy

CUR = date(2026, 6, 12)


def _source():
    cal = [date(2026, 6, 10), date(2026, 6, 11), CUR]
    bars = {
        "CLEAN": pd.DataFrame({"date": cal, "open": [10, 11, 12.0], "high": [11, 12, 13],
                               "low": [10, 11, 12], "close": [10.0, 11.0, 12.0], "volume": [1, 1, 1]}),
        "KNIFE": pd.DataFrame({"date": cal, "open": [10, 8.8, 9.0], "high": [10, 9, 10],
                               "low": [8, 8, 8], "close": [10.0, 8.8, 9.0], "volume": [1, 1, 1]}),  # -12% on 6/11
        "RSPLIT": pd.DataFrame({"date": cal, "open": [10, 11, 12.0], "high": [11, 12, 13],
                                "low": [10, 11, 12], "close": [10.0, 11.0, 12.0], "volume": [1, 1, 1]}),
    }
    corp = pd.DataFrame({"symbol": ["RSPLIT"], "announce_date": [date(2026, 6, 9)],
                         "ex_date": [date(2026, 6, 20)], "kind": ["reverse_split"], "ratio": [0.1]})
    return FakeSource(calendar=cal, bars=bars, snapshots={}, corp_actions=corp)


def _frontside_state():
    # sentiment_norm=0.7 + follow_through=0.5 + fb_rate 0 -> GCycle reads trend/frontside, risk_gate 0.7
    return MarketState(date=CUR, gainer_count=3, gap_up_count=0, loser_count=0, failed_breakout_count=0,
                       max_runner_tier=1, echelon=[], breadth_raw=3.0, sentiment_norm=0.7,
                       follow_through_rate=0.5, as_of=datetime(2026, 6, 12, 16, 0))


class _StubPolicy:
    def decide(self, state, universe):
        return DecisionPackage(date=CUR, candidates=[Candidate(symbol=s, pattern="gap_and_go")
                                                     for s in ("CLEAN", "KNIFE", "RSPLIT")])


def test_guard_enforces_ssr_and_reverse_split_on_frontside():
    out = GuardedPolicy(_StubPolicy(), _source()).decide(_frontside_state(), CandidateUniverse.from_stocks([]))
    assert [c.symbol for c in out.candidates] == ["CLEAN"]              # only the clean runner survives
    assert out.regime is not None and out.regime.frontside is True      # structured regime populated
    assert any("KNIFE" in r and "SSR" in r for r in out.key_risks)      # SSR veto surfaced
    assert any("RSPLIT" in r and "reverse split" in r for r in out.key_risks)   # reverse-split veto surfaced
