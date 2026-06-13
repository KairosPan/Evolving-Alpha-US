# tests/test_baselines.py
from datetime import date, datetime

import pytest

from youzi.schemas.market import MarketState
from youzi.universe.stock import StockSnapshot
from youzi.universe.universe import CandidateUniverse
from youzi.eval.baselines import (HighestBoardPolicy, NoTradePolicy,
                                  PoolAveragePolicy, RandomFromPoolPolicy)


def _state(d=date(2024, 6, 27)):
    return MarketState(date=d, max_board_height=7, limit_up_count=3, blowup_count=1,
                       blowup_rate=0.25, limit_down_count=1, echelon=[],
                       money_effect_raw=0.0, sentiment_raw=0.0, sentiment_norm=None,
                       as_of=datetime(2024, 6, 27, 15, 0))


def _uni():
    return CandidateUniverse.from_stocks([
        StockSnapshot(code="A", name="龙", status="limit_up", boards=7),
        StockSnapshot(code="B", name="中", status="limit_up", boards=3),
        StockSnapshot(code="C", name="炸", status="blowup", boards=None),
    ])


def test_no_trade_policy():
    pkg = NoTradePolicy().decide(_state(), _uni())
    assert pkg.candidates == [] and pkg.no_trade_reason


def test_highest_board_policy_picks_top_boards():
    pkg = HighestBoardPolicy().decide(_state(), _uni())
    assert {c.code for c in pkg.candidates} == {"A"}          # 7板最高
    assert pkg.candidates[0].pattern == "highest_board"


def test_highest_board_policy_no_limit_up():
    empty = CandidateUniverse.from_stocks([
        StockSnapshot(code="C", name="炸", status="blowup")])
    pkg = HighestBoardPolicy().decide(_state(), empty)
    assert pkg.candidates == [] and pkg.no_trade_reason


def test_highest_board_policy_ties_pick_all():
    u = CandidateUniverse.from_stocks([
        StockSnapshot(code="A", name="甲", status="limit_up", boards=5),
        StockSnapshot(code="B", name="乙", status="limit_up", boards=5),
        StockSnapshot(code="C", name="丙", status="limit_up", boards=2)])
    pkg = HighestBoardPolicy().decide(_state(), u)
    assert {c.code for c in pkg.candidates} == {"A", "B"}


# ── C2:PoolAveragePolicy / RandomFromPoolPolicy ─────────────────────────────

def test_pool_average_policy_picks_whole_limit_up_pool():
    pkg = PoolAveragePolicy().decide(_state(), _uni())
    assert [c.code for c in pkg.candidates] == ["A", "B"]      # 全涨停池(按 code 排序);炸板 C 不选
    assert all(c.pattern == "pool_avg" for c in pkg.candidates)


def test_pool_average_policy_empty_pool_no_trade():
    empty = CandidateUniverse.from_stocks([
        StockSnapshot(code="C", name="炸", status="blowup")])
    pkg = PoolAveragePolicy().decide(_state(), empty)
    assert pkg.candidates == [] and pkg.no_trade_reason


def _big_uni():
    return CandidateUniverse.from_stocks(
        [StockSnapshot(code=f"S{i}", name=f"股{i}", status="limit_up", boards=1)
         for i in range(8)])


def test_random_from_pool_deterministic_same_seed_same_picks():
    # 同 (seed, 日期, 池) → 同选择(跨实例可复现);确定性伪随机
    p1 = RandomFromPoolPolicy(k=3, seed=42).decide(_state(), _big_uni())
    p2 = RandomFromPoolPolicy(k=3, seed=42).decide(_state(), _big_uni())
    assert [c.code for c in p1.candidates] == [c.code for c in p2.candidates]
    assert len(p1.candidates) == 3
    assert all(c.pattern == "random_pool" for c in p1.candidates)


def test_random_from_pool_seed_and_date_vary_picks():
    base = [c.code for c in RandomFromPoolPolicy(k=3, seed=42).decide(_state(), _big_uni()).candidates]
    other_seed = [c.code for c in RandomFromPoolPolicy(k=3, seed=43).decide(_state(), _big_uni()).candidates]
    other_day = [c.code for c in RandomFromPoolPolicy(k=3, seed=42)
                 .decide(_state(date(2024, 6, 28)), _big_uni()).candidates]
    assert base != other_seed                                   # 换 seed → 不同选择(8 选 3,撞车概率可忽略)
    assert base != other_day                                    # 换日期 → 派生流不同


def test_random_from_pool_k_exceeds_pool_takes_all_and_empty_no_trade():
    pkg = RandomFromPoolPolicy(k=10, seed=0).decide(_state(), _uni())
    assert {c.code for c in pkg.candidates} == {"A", "B"}      # 池只有 2 只 → 全选
    empty = CandidateUniverse.from_stocks([])
    pkg2 = RandomFromPoolPolicy(k=2, seed=0).decide(_state(), empty)
    assert pkg2.candidates == [] and pkg2.no_trade_reason


def test_random_from_pool_rejects_degenerate_k():
    with pytest.raises(ValueError):
        RandomFromPoolPolicy(k=0)
