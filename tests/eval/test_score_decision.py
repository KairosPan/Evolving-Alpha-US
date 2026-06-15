from datetime import date
import pandas as pd
from alpha.data.source import FakeSource, GuardedSource
from alpha.data.firewall import AsOfGuard
from alpha.eval.oracle import PoolRecord, classify_day
from alpha.eval.scorer import ReturnScorer
from alpha.eval.walk_forward import WalkForwardEval, score_decision
from alpha.eval.decision import Candidate, DecisionPackage


def _source():
    cal = [date(2026, 6, 10), date(2026, 6, 11), date(2026, 6, 12), date(2026, 6, 15)]
    rows = {date(2026, 6, 10): [("RUN", 14.0, 10.0)], date(2026, 6, 11): [("RUN", 18.0, 14.0)],
            date(2026, 6, 12): [("RUN", 17.0, 18.0)], date(2026, 6, 15): [("RUN", 20.0, 17.0)]}
    snaps = {d: pd.DataFrame({"symbol": ["RUN"], "name": ["RUN"], "open": [r[2] for r in v],
                              "high": [r[1] for r in v], "low": [r[2] for r in v], "close": [r[1] for r in v],
                              "volume": [1], "prev_close": [r[2] for r in v]}) for d, v in rows.items()}
    bars = {"RUN": pd.DataFrame({"date": cal, "open": [10.0, 14.0, 18.0, 17.0], "high": [14, 18, 18, 20],
                                 "low": [10, 14, 17, 17], "close": [14.0, 18.0, 17.0, 20.0], "volume": [1, 1, 1, 1]})}
    return FakeSource(calendar=cal, bars=bars, snapshots=snaps)


def test_score_decision_dict_matches_score_list():
    src = _source()
    days = src.trading_calendar()
    record = PoolRecord()
    for d in days:
        record.record(d, classify_day(GuardedSource(src, AsOfGuard(d)).daily_snapshot(d)))
    dec = DecisionPackage(date=days[0], candidates=[Candidate(symbol="RUN", pattern="gap_and_go")])
    wf = WalkForwardEval(src, days[0], days[-1], horizon=2, scorer=ReturnScorer())
    as_dict = score_decision(src, wf._scorer, dec, days, 0, 2, days[2], record)   # decision j=0, exit cursor=days[2]
    as_list = wf._score(dec, days, 0, days[2], record)
    assert list(as_dict.values()) == as_list                # wrapper delegates to the function
    assert all(k == v.symbol for k, v in as_dict.items())   # keyed by symbol
