from datetime import date
import pandas as pd
import pytest
from alpha.eval.decision import Candidate, DecisionPackage
from alpha.eval.oracle import DayMembership
from alpha.eval.return_oracle import ReturnOracle
from alpha.eval.scorer import PoolScorer, ReturnScorer
from alpha.data.source import FakeSource


def _decision(*symbols):
    return DecisionPackage(date=date(2026, 6, 11),
                           candidates=[Candidate(symbol=s, pattern="p") for s in symbols])


def test_pool_scorer_outcome_and_advantage():
    decision_mem = DayMembership(gainers=frozenset({"WIN", "B"}), losers=frozenset())
    exit_mem = DayMembership(gainers=frozenset({"WIN"}), losers=frozenset({"B"}))
    sc = PoolScorer().score_step(_decision("WIN"), decision_mem, exit_mem,
                                 date(2026, 6, 12), date(2026, 6, 15), oracle=None)
    # baseline = mean SCORE over decision gainers {WIN:continued=1, B:nuked=-1} = 0.0
    assert sc["WIN"].outcome == "continued" and sc["WIN"].score == 1.0
    assert sc["WIN"].day_baseline == 0.0 and sc["WIN"].advantage == 1.0


def test_return_scorer_uses_forward_return_and_keeps_delist():
    cal = [date(2026, 6, 11), date(2026, 6, 12), date(2026, 6, 15)]
    bars = {
        "WIN": pd.DataFrame({"date": [date(2026, 6, 12), date(2026, 6, 15)], "open": [10.0, 11.0],
                             "high": [11, 13], "low": [10, 11], "close": [10.5, 13.0], "volume": [1, 1]}),
        "DEAD": pd.DataFrame({"date": [date(2026, 6, 12)], "open": [10.0], "high": [10], "low": [9],
                              "close": [9.5], "volume": [1]}),
    }
    corp = pd.DataFrame({"symbol": ["DEAD"], "announce_date": [date(2026, 6, 11)],
                         "ex_date": [date(2026, 6, 15)], "kind": ["delist"], "ratio": [0.0]})
    src = FakeSource(calendar=cal, bars=bars, snapshots={}, corp_actions=corp)
    decision_mem = DayMembership(gainers=frozenset({"WIN"}), losers=frozenset())
    exit_mem = DayMembership(gainers=frozenset({"WIN"}), losers=frozenset({"DEAD"}))
    out = ReturnScorer().score_step(_decision("WIN", "DEAD"), decision_mem, exit_mem,
                                    date(2026, 6, 12), date(2026, 6, 15), oracle=ReturnOracle(src))
    assert abs(out["WIN"].score - 0.30) < 1e-9            # (13-10)/10
    assert out["DEAD"].score == -1.0                       # delist = terminal loss, NOT discarded
    assert out["DEAD"].outcome == "nuked"


def test_return_scorer_discards_genuine_missing():
    src = FakeSource(calendar=[date(2026, 6, 12), date(2026, 6, 15)], bars={}, snapshots={})
    decision_mem = DayMembership(gainers=frozenset(), losers=frozenset())
    exit_mem = DayMembership(gainers=frozenset(), losers=frozenset())
    out = ReturnScorer().score_step(_decision("GHOST"), decision_mem, exit_mem,
                                    date(2026, 6, 12), date(2026, 6, 15), oracle=ReturnOracle(src))
    assert out == {}                                       # no data, not a delist -> discarded


def test_scorer_dedups_duplicate_symbols():
    decision_mem = DayMembership(gainers=frozenset(), losers=frozenset())
    exit_mem = DayMembership(gainers=frozenset({"X"}), losers=frozenset())
    dec = DecisionPackage(date=date(2026, 6, 11),
                          candidates=[Candidate(symbol="X", pattern="p"), Candidate(symbol="X", pattern="p")])
    out = PoolScorer().score_step(dec, decision_mem, exit_mem,
                                  date(2026, 6, 12), date(2026, 6, 15), oracle=None)
    assert len(out) == 1                                    # duplicate symbol counted once
