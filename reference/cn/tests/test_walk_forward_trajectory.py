# tests/test_walk_forward_trajectory.py
from datetime import date

import pandas as pd

from youzi.eval.baselines import HighestBoardPolicy
from youzi.eval.walk_forward import WalkForwardEval, report_from_trajectory
from tests.conftest import FakeSource


def _src():
    """A 连续涨停;B day0 涨停 day1 跌停。复刻 test_walk_forward._src()。"""
    d0, d1, d2 = date(2024, 6, 26), date(2024, 6, 27), date(2024, 6, 28)
    frames = {}
    frames[("zt", d0)] = pd.DataFrame({"code": ["A", "B"], "name": ["A", "B"], "boards": [2, 1]})
    frames[("blowup", d0)] = pd.DataFrame(); frames[("dt", d0)] = pd.DataFrame()
    frames[("zt", d1)] = pd.DataFrame({"code": ["A"], "name": ["A"], "boards": [3]})
    frames[("blowup", d1)] = pd.DataFrame()
    frames[("dt", d1)] = pd.DataFrame({"code": ["B"], "name": ["B"]})
    frames[("zt", d2)] = pd.DataFrame({"code": ["A"], "name": ["A"], "boards": [4]})
    frames[("blowup", d2)] = pd.DataFrame(); frames[("dt", d2)] = pd.DataFrame()
    return FakeSource(frames, [d0, d1, d2])


def test_walk_records_steps_entries_and_delayed_outcomes():
    traj = WalkForwardEval(_src(), date(2024, 6, 26), date(2024, 6, 28), horizon=1).walk(
        HighestBoardPolicy())
    assert traj.n_decisions() == 3
    assert [s.date for s in traj.scored_steps()] == [date(2024, 6, 26), date(2024, 6, 27)]
    s0 = traj.steps[0]
    assert s0.scored is True
    assert "A" in s0.entries and s0.entries["A"].boards == 2       # 入场上下文来自当日 universe
    assert s0.outcomes["A"].outcome == "continued"                # 次日 A 仍涨停
    assert traj.steps[2].scored is False                          # 尾部步保留但未打分


def test_run_equals_report_from_trajectory():
    ev = WalkForwardEval(_src(), date(2024, 6, 26), date(2024, 6, 28), horizon=1)
    rep = ev.run(HighestBoardPolicy())
    rep2 = report_from_trajectory(ev.walk(HighestBoardPolicy()))
    assert rep == rep2
    # 与既有 test_walk_forward 的断言一致(等价性回归)
    assert rep.n_decisions == 3 and rep.n_candidates == 2
    assert rep.hit_rate == 1.0 and rep.mean_score == 1.0
    assert rep.by_pattern["highest_board"].n == 2
