from datetime import date
import pandas as pd
from alpha.data.source import FakeSource
from alpha.eval.walk_forward import WalkForwardEval
from alpha.eval.scorer import ReturnScorer
from alpha.eval.baselines import ChaseBiggestGainerPolicy
from alpha.eval.trajectory import Trajectory, report_from_trajectory


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


def test_walk_returns_trajectory_with_scored_outcomes():
    wf = WalkForwardEval(_source(), date(2026, 6, 10), date(2026, 6, 15), horizon=2, scorer=ReturnScorer())
    traj = wf.walk(ChaseBiggestGainerPolicy())
    assert isinstance(traj, Trajectory) and len(traj.steps) == 4
    # horizon=2 over 4 days -> decisions 0,1 scored; last 2 unscored
    assert [s.scored for s in traj.steps] == [True, True, False, False]
    assert traj.scored_steps()[0].outcomes                      # day-0 decision has a realized outcome


def test_run_equals_report_from_walk():
    wf = WalkForwardEval(_source(), date(2026, 6, 10), date(2026, 6, 15), horizon=2, scorer=ReturnScorer())
    pol = ChaseBiggestGainerPolicy()
    report = wf.run(pol)
    traj = wf.walk(pol)
    rebuilt = report_from_trajectory(traj, horizon=2)
    assert (report.n_decisions, report.n_candidates, report.n_no_trade) == \
           (rebuilt.n_decisions, rebuilt.n_candidates, rebuilt.n_no_trade)
    assert report.mean_score == rebuilt.mean_score and report.hit_rate == rebuilt.hit_rate
    assert report.n_decisions == 4 and report.n_candidates == 2          # absolute pin (not just self-consistency)
