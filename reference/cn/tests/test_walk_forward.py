# tests/test_walk_forward.py
from datetime import date
import pandas as pd
from youzi.eval.walk_forward import WalkForwardEval
from youzi.eval.baselines import HighestBoardPolicy, NoTradePolicy
from tests.conftest import FakeSource


def _src():
    """3 天:A 连续涨停(continued);B day0 涨停 day1 跌停(nuked,但 HighestBoard 不选 B)。"""
    d0, d1, d2 = date(2024, 6, 26), date(2024, 6, 27), date(2024, 6, 28)
    frames = {}
    # day0: A(2板,最高), B(1板)
    frames[("zt", d0)] = pd.DataFrame({"code": ["A", "B"], "name": ["A", "B"], "boards": [2, 1]})
    frames[("blowup", d0)] = pd.DataFrame(); frames[("dt", d0)] = pd.DataFrame()
    # day1: A(3板,最高); B 跌停
    frames[("zt", d1)] = pd.DataFrame({"code": ["A"], "name": ["A"], "boards": [3]})
    frames[("blowup", d1)] = pd.DataFrame()
    frames[("dt", d1)] = pd.DataFrame({"code": ["B"], "name": ["B"]})
    # day2: A(4板)
    frames[("zt", d2)] = pd.DataFrame({"code": ["A"], "name": ["A"], "boards": [4]})
    frames[("blowup", d2)] = pd.DataFrame(); frames[("dt", d2)] = pd.DataFrame()
    return FakeSource(frames, [d0, d1, d2])


def test_walk_forward_scores_highest_board():
    rep = WalkForwardEval(_src(), date(2024, 6, 26), date(2024, 6, 28), horizon=1).run(
        HighestBoardPolicy())
    # day0 选A(2板)→day1 A涨停=continued; day1 选A(3板)→day2 A涨停=continued; day2 选A 但无次日→不打分
    assert rep.n_decisions == 3
    assert rep.n_candidates == 2          # 只有 day0、day1 的决策被打分
    assert rep.hit_rate == 1.0 and rep.mean_score == 1.0
    assert rep.by_pattern["highest_board"].n == 2


def test_walk_forward_no_trade_yields_empty_report():
    rep = WalkForwardEval(_src(), date(2024, 6, 26), date(2024, 6, 28), horizon=1).run(
        NoTradePolicy())
    assert rep.n_decisions == 3 and rep.n_no_trade == 3 and rep.n_candidates == 0
    assert rep.hit_rate == 0.0


def test_walk_forward_dedups_candidate_codes():
    from youzi.eval.decision import Candidate, DecisionPackage
    class DupPolicy:
        def decide(self, state, universe):
            return DecisionPackage(date=state.date, candidates=[
                Candidate(code="A", pattern="t"), Candidate(code="A", pattern="t")])
    rep = WalkForwardEval(_src(), date(2024, 6, 26), date(2024, 6, 28), horizon=1).run(DupPolicy())
    # day0+day1 各去重为 1 个候选(day2 无次日丢弃)= 2
    assert rep.n_candidates == 2


def test_walk_forward_horizon_exceeds_range_empty():
    rep = WalkForwardEval(_src(), date(2024, 6, 26), date(2024, 6, 28), horizon=9).run(
        HighestBoardPolicy())
    assert rep.n_candidates == 0 and rep.horizon == 9   # 无决策能凑满 horizon
