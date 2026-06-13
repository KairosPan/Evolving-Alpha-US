# tests/test_trajectory.py
from datetime import date, datetime, time

import pytest
from pydantic import ValidationError

from youzi.eval.decision import Candidate, DecisionPackage
from youzi.eval.metrics import ScoredCandidate
from youzi.eval.trajectory import EntrySnap, Trajectory, TrajectoryStep
from youzi.schemas.market import MarketState


def _state(d, max_board=0):
    return MarketState(date=d, max_board_height=max_board, limit_up_count=0,
                       blowup_count=0, blowup_rate=0.0, limit_down_count=0,
                       echelon=[], money_effect_raw=0.0, sentiment_raw=0.0,
                       as_of=datetime.combine(d, time(15, 0)))


def _step(d, codes, scored=False, outcomes=None):
    cands = [Candidate(code=c, pattern="p") for c in codes]
    return TrajectoryStep(
        date=d, market=_state(d),
        decision=DecisionPackage(date=d, candidates=cands),
        entries={c: EntrySnap(code=c, status="limit_up", boards=1) for c in codes},
        scored=scored, outcomes=outcomes or {})


def test_trajectory_step_is_frozen():
    s = _step(date(2024, 6, 26), ["A"])
    with pytest.raises(ValidationError):
        s.scored = True


def test_entry_snap_boards_can_be_none():
    e = EntrySnap(code="A", status="limit_up")
    assert e.boards is None


def test_trajectory_counts_and_scored_steps():
    d0, d1, d2 = date(2024, 6, 26), date(2024, 6, 27), date(2024, 6, 28)
    sc = ScoredCandidate(decision_date=d0, code="A", pattern="p",
                         outcome="continued", score=1.0)
    steps = [
        _step(d0, ["A"], scored=True, outcomes={"A": sc}),
        _step(d1, [], scored=True),                     # no-trade
        _step(d2, ["B"], scored=False),                 # 尾部未打分
    ]
    traj = Trajectory(steps=steps, horizon=1)
    assert traj.n_decisions() == 3
    assert traj.n_no_trade() == 1
    assert [s.date for s in traj.scored_steps()] == [d0, d1]
    assert bool(traj) is True


def test_empty_trajectory_is_truthy():
    assert bool(Trajectory()) is True
