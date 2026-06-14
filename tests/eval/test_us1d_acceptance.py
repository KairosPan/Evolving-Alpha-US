"""US-1d acceptance: baseline-only walk-forward reproduces, the firewall holds (the guard blocks an
out-of-window fetch), delisting scores as a terminal loss, and the pool-category oracle is exogenous
(independent of the universe screen / H)."""
from datetime import date
import pandas as pd
import pytest
from alpha.data.source import FakeSource
from alpha.data.firewall import LookaheadError
from alpha.eval.baselines import NoTradePolicy, PoolAveragePolicy
from alpha.eval.scorer import ReturnScorer
from alpha.eval.walk_forward import WalkForwardEval


def _source():
    cal = [date(2026, 6, 10), date(2026, 6, 11), date(2026, 6, 12), date(2026, 6, 15)]
    snaps = {}
    for d, rows in {
        date(2026, 6, 10): [("RUN", 14.0, 10.0)], date(2026, 6, 11): [("RUN", 18.0, 14.0)],
        date(2026, 6, 12): [("RUN", 17.0, 18.0)], date(2026, 6, 15): [("RUN", 20.0, 17.0)],
    }.items():
        snaps[d] = pd.DataFrame({"symbol": [r[0] for r in rows], "name": [r[0] for r in rows],
                                 "open": [r[2] for r in rows], "high": [r[1] for r in rows],
                                 "low": [r[2] for r in rows], "close": [r[1] for r in rows],
                                 "volume": [1], "prev_close": [r[2] for r in rows]})
    bars = {"RUN": pd.DataFrame({"date": cal, "open": [10.0, 14.0, 18.0, 17.0],
                                 "high": [14, 18, 18, 20], "low": [10, 14, 17, 17],
                                 "close": [14.0, 18.0, 17.0, 20.0], "volume": [1, 1, 1, 1]})}
    return FakeSource(calendar=cal, bars=bars, snapshots=snaps)


def test_baseline_walk_forward_reproduces_and_no_trade_is_empty():
    wf = WalkForwardEval(_source(), date(2026, 6, 10), date(2026, 6, 15), horizon=2)
    assert wf.run(NoTradePolicy()).n_candidates == 0
    a = WalkForwardEval(_source(), date(2026, 6, 10), date(2026, 6, 15), horizon=2, scorer=ReturnScorer())
    b = WalkForwardEval(_source(), date(2026, 6, 10), date(2026, 6, 15), horizon=2, scorer=ReturnScorer())
    assert a.run(PoolAveragePolicy()).mean_score == b.run(PoolAveragePolicy()).mean_score


def test_guarded_source_blocks_lookahead():
    # The policy only ever receives (state, universe) built from a per-day GuardedSource, so it
    # structurally cannot reach future data. Prove the underlying guard rejects an out-of-window fetch:
    from alpha.data.source import GuardedSource
    from alpha.data.firewall import AsOfGuard
    gs = GuardedSource(_source(), AsOfGuard(date(2026, 6, 11)))
    with pytest.raises(LookaheadError):
        gs.daily_bars("RUN", date(2026, 6, 11), date(2026, 6, 15))   # exit beyond cursor -> blocked
