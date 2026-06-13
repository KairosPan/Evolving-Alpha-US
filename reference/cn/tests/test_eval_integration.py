# tests/test_eval_integration.py
from datetime import date
import pandas as pd
from youzi.eval.walk_forward import WalkForwardEval
from youzi.eval.decision import Candidate, DecisionPackage
from tests.conftest import FakeSource


def _src():
    """day0 三标的: X(将continued), Y(将nuked), Z(将faded)。"""
    d0, d1 = date(2024, 6, 27), date(2024, 6, 28)
    frames = {
        ("zt", d0): pd.DataFrame({"code": ["X", "Y", "Z"], "name": ["X", "Y", "Z"], "boards": [1, 1, 1]}),
        ("blowup", d0): pd.DataFrame(), ("dt", d0): pd.DataFrame(),
        # day1: X 仍涨停(continued), Y 跌停(nuked), Z 掉出(faded)
        ("zt", d1): pd.DataFrame({"code": ["X"], "name": ["X"], "boards": [2]}),
        ("blowup", d1): pd.DataFrame(),
        ("dt", d1): pd.DataFrame({"code": ["Y"], "name": ["Y"]}),
    }
    return FakeSource(frames, [d0, d1])


class PickAllPolicy:
    """day0 选 X/Y/Z 各一(pattern=test);仅 day0 被打分。"""
    def __init__(self):
        self.seen = []      # 记录每次 decide 看到的 (date, universe codes)
    def decide(self, state, universe):
        self.seen.append((state.date, frozenset(s.code for s in universe.all())))
        cands = [Candidate(code=c, name=c, pattern="test")
                 for c in sorted(s.code for s in universe.by_status("limit_up"))]
        return DecisionPackage(date=state.date, candidates=cands)


def test_three_outcomes_and_no_lookahead():
    pol = PickAllPolicy()
    rep = WalkForwardEval(_src(), date(2024, 6, 27), date(2024, 6, 28), horizon=1).run(pol)
    # day0 选 X,Y,Z;day1 用次日成员打分:X continued, Y nuked, Z faded
    assert rep.n_candidates == 3
    assert abs(rep.hit_rate - 1 / 3) < 1e-9      # 仅 X continued
    assert abs(rep.nuke_rate - 1 / 3) < 1e-9     # 仅 Y nuked
    assert abs(rep.mean_score - (1 + (-1) + 0) / 3) < 1e-9   # 0.0
    # 无前视:day0 decide 只看到 day0 的成员(X,Y,Z),绝不含 day1 才出现的状态变化
    day0, codes0 = pol.seen[0]
    assert day0 == date(2024, 6, 27)
    assert codes0 == frozenset({"X", "Y", "Z"})   # day0 universe,非未来
    # day1 decide 只看到 day1 成员(X 涨停 + Y 跌停)
    day1, codes1 = pol.seen[1]
    assert codes1 == frozenset({"X", "Y"})
