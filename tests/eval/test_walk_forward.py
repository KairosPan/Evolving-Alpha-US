from datetime import date
import pandas as pd
import pytest
from alpha.data.source import FakeSource
from alpha.eval.baselines import NoTradePolicy, ChaseBiggestGainerPolicy
from alpha.eval.scorer import ReturnScorer
from alpha.eval.walk_forward import WalkForwardEval


def _source():
    cal = [date(2026, 6, 10), date(2026, 6, 11), date(2026, 6, 12), date(2026, 6, 15)]
    snaps = {}
    for d, rows in {
        date(2026, 6, 10): [("RUN", 14.0, 10.0), ("DIP", 8.0, 10.0)],   # RUN +40% gainer
        date(2026, 6, 11): [("RUN", 18.0, 14.0)],                        # RUN +28% gainer
        date(2026, 6, 12): [("RUN", 17.0, 18.0)],
        date(2026, 6, 15): [("RUN", 20.0, 17.0)],
    }.items():
        snaps[d] = pd.DataFrame({"symbol": [r[0] for r in rows], "name": [r[0] for r in rows],
                                 "open": [r[2] for r in rows], "high": [r[1] for r in rows],
                                 "low": [r[2] for r in rows], "close": [r[1] for r in rows],
                                 "volume": [1]*len(rows), "prev_close": [r[2] for r in rows]})
    bars = {"RUN": pd.DataFrame({
        "date": cal, "open": [10.0, 14.0, 18.0, 17.0], "high": [14, 18, 18, 20],
        "low": [10, 14, 17, 17], "close": [14.0, 18.0, 17.0, 20.0], "volume": [1, 1, 1, 1]})}
    return FakeSource(calendar=cal, bars=bars, snapshots=snaps)


def test_horizon_must_be_at_least_two():
    with pytest.raises(ValueError):
        WalkForwardEval(_source(), date(2026, 6, 10), date(2026, 6, 15), horizon=1)


def test_no_trade_yields_no_candidates():
    wf = WalkForwardEval(_source(), date(2026, 6, 10), date(2026, 6, 15), horizon=2)
    rep = wf.run(NoTradePolicy())
    assert rep.n_candidates == 0 and rep.n_no_trade == rep.n_decisions and rep.horizon == 2


def test_chase_baseline_reproduces_deterministically():
    wf1 = WalkForwardEval(_source(), date(2026, 6, 10), date(2026, 6, 15), horizon=2, scorer=ReturnScorer())
    wf2 = WalkForwardEval(_source(), date(2026, 6, 10), date(2026, 6, 15), horizon=2, scorer=ReturnScorer())
    r1 = wf1.run(ChaseBiggestGainerPolicy())
    r2 = wf2.run(ChaseBiggestGainerPolicy())
    assert (r1.n_candidates, r1.mean_score, r1.hit_rate) == (r2.n_candidates, r2.mean_score, r2.hit_rate)
    assert r1.n_candidates == 2            # RUN picked+scored on decision days d0 and d1 (regression guard)
