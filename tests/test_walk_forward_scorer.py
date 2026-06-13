# tests/test_walk_forward_scorer.py
from datetime import date

import pandas as pd

from youzi.eval.walk_forward import WalkForwardEval
from youzi.eval.scorer import ReturnScorer
from youzi.eval.baselines import HighestBoardPolicy
from tests.conftest import FakeSource


def _src_with_ohlcv():
    """A 连续涨停(continued);带 A 的 OHLCV 使 ReturnScorer 可算收益。"""
    days = [date(2026, 6, 1), date(2026, 6, 2), date(2026, 6, 3)]
    frames = {("zt", d): pd.DataFrame({"code": ["A"], "name": ["甲"], "boards": [2]}) for d in days}
    ohlcv = {"A": pd.DataFrame([(date(2026, 6, 2), 10.0, 11, 9, 10.5, 100),
                                (date(2026, 6, 3), 10.6, 12.5, 10, 12.0, 200)],
                               columns=["date", "open", "high", "low", "close", "volume"])}
    return FakeSource(frames, days, ohlcv=ohlcv)


def test_default_pool_scorer_unchanged():
    # 默认 PoolScorer:mean_score = SCORE 均值(continued=1.0)
    rep = WalkForwardEval(_src_with_ohlcv(), date(2026, 6, 1), date(2026, 6, 3),
                          horizon=1).run(HighestBoardPolicy())
    assert rep.mean_score == 1.0 and rep.hit_rate == 1.0


def test_return_scorer_mean_is_avg_return():
    # ReturnScorer + horizon=1:决策 6/1 → entry 6/2 open=10、exit 6/2 close=10.5 → +0.05
    rep = WalkForwardEval(_src_with_ohlcv(), date(2026, 6, 1), date(2026, 6, 3),
                          horizon=1, scorer=ReturnScorer()).run(HighestBoardPolicy())
    # 6/1 决策(A)entry=exit=6/2:(10.5−10)/10=+0.05;6/2 决策 entry=exit=6/3:(12−10.6)/10.6≈+0.132
    assert rep.n_candidates == 2
    assert abs(rep.mean_score - (0.05 + (12.0 - 10.6) / 10.6) / 2) < 1e-9
    assert rep.hit_rate == 1.0          # outcome 仍池类别(continued)
