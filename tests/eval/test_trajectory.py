from datetime import date, datetime
from alpha.state.market import MarketState
from alpha.universe.stock import StockSnapshot
from alpha.eval.decision import Candidate, DecisionPackage
from alpha.eval.metrics import ScoredCandidate
from alpha.eval.trajectory import TrajectoryStep, Trajectory, report_from_trajectory


def _state(d=date(2026, 6, 12)):
    return MarketState(date=d, gainer_count=1, gap_up_count=0, loser_count=0,
                       failed_breakout_count=0, max_runner_tier=2, echelon=[], breadth_raw=1.0,
                       as_of=datetime(d.year, d.month, d.day, 16, 0))


def _step(d, scored, sym="RUN", outcome="continued"):
    dec = DecisionPackage(date=d, candidates=[Candidate(symbol=sym, pattern="gap_and_go")])
    entries = {sym: StockSnapshot(symbol=sym, name="Runner", status="gainer", consecutive_up_days=3)}
    outcomes = ({sym: ScoredCandidate(decision_date=d, symbol=sym, pattern="gap_and_go",
                                      outcome=outcome, score=0.3, day_baseline=0.1)} if scored else {})
    return TrajectoryStep(date=d, market=_state(d), decision=dec, entries=entries,
                          outcomes=outcomes, scored=scored)


def test_scored_steps_filters():
    traj = Trajectory(steps=[_step(date(2026, 6, 10), True), _step(date(2026, 6, 12), False)])
    assert [s.date for s in traj.scored_steps()] == [date(2026, 6, 10)]
    assert len(traj.all_scored()) == 1 and traj.all_scored()[0].advantage == 0.3 - 0.1


def test_report_from_trajectory_counts():
    traj = Trajectory(steps=[
        _step(date(2026, 6, 10), True),
        TrajectoryStep(date=date(2026, 6, 11), market=_state(date(2026, 6, 11)),
                       decision=DecisionPackage(date=date(2026, 6, 11)), scored=True),   # no-trade, scored
        _step(date(2026, 6, 12), False),                                                  # unscored tail
    ])
    rep = report_from_trajectory(traj, horizon=2)
    assert rep.n_decisions == 3 and rep.n_no_trade == 1 and rep.n_candidates == 1
    assert rep.hit_rate == 1.0


def test_step_is_frozen():
    import pytest
    s = _step(date(2026, 6, 10), True)
    with pytest.raises(Exception):
        s.scored = False
