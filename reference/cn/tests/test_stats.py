# tests/test_stats.py
"""C1 统一统计裁决层:全离线合成数据,确定性(seed 显式)。"""
import math
from datetime import date, datetime, time

import pytest

from youzi.eval.decision import Candidate, DecisionPackage
from youzi.eval.metrics import ScoredCandidate
from youzi.eval.stats import (StatVerdict, daily_series, mde,
                              moving_block_bootstrap, paired_daily_diff,
                              sign_permutation_pvalue, verdict)
from youzi.eval.trajectory import Trajectory, TrajectoryStep
from youzi.schemas.market import MarketState

D0, D1, D2, D3 = (date(2024, 6, 24), date(2024, 6, 25),
                  date(2024, 6, 26), date(2024, 6, 27))


def _state(d):
    return MarketState(date=d, max_board_height=0, limit_up_count=0,
                       blowup_count=0, blowup_rate=0.0, limit_down_count=0,
                       echelon=[], money_effect_raw=0.0, sentiment_raw=0.0,
                       as_of=datetime.combine(d, time(15, 0)))


def _sc(d, code, score, base):
    return ScoredCandidate(decision_date=d, code=code, pattern="p",
                           outcome="continued", score=score, day_baseline=base)


def _step(d, outcomes=None, scored=True):
    ocs = outcomes or {}
    cands = [Candidate(code=c, pattern="p") for c in ocs]
    return TrajectoryStep(date=d, market=_state(d),
                          decision=DecisionPackage(date=d, candidates=cands),
                          scored=scored, outcomes=ocs)


# ---------- daily_series ----------

def test_daily_series_equal_weight_no_trade_zero_and_tail_excluded():
    # 手算例:d0 两候选 adv=(1−0.5, 0−0.5)→日均 0.0;d1 空仓已评分→0.0;
    # d2 单候选 adv=1−0.25=0.75;d3 scored=False(尾部不足 horizon)→不入列。
    traj = Trajectory(steps=[
        _step(D0, {"A": _sc(D0, "A", 1.0, 0.5), "B": _sc(D0, "B", 0.0, 0.5)}),
        _step(D1),                                            # 空仓日记 0.0
        _step(D2, {"C": _sc(D2, "C", 1.0, 0.25)}),
        _step(D3, scored=False),
    ], horizon=1)
    assert daily_series(traj) == [(D0, 0.0), (D1, 0.0), (D2, 0.75)]


def test_daily_series_sorted_by_date():
    traj = Trajectory(steps=[_step(D2, {"C": _sc(D2, "C", 1.0, 0.0)}), _step(D0)],
                      horizon=1)
    assert [d for d, _ in daily_series(traj)] == [D0, D2]


# ---------- paired_daily_diff ----------

def test_paired_diff_aligned():
    a = [(D0, 1.0), (D1, 0.5)]
    b = [(D0, 0.2), (D1, 0.5)]
    assert paired_daily_diff(a, b) == [pytest.approx(0.8), 0.0]


def test_paired_diff_calendar_mismatch_takes_intersection():
    a = [(D0, 1.0), (D1, 2.0), (D2, 3.0)]
    b = [(D1, 0.5), (D2, 1.0), (D3, 9.0)]   # D0/D3 不共有 → 丢弃
    assert paired_daily_diff(a, b) == [1.5, 2.0]
    assert len(paired_daily_diff(a, b)) == 2    # 交集数量即配对日数


# ---------- moving_block_bootstrap ----------

def test_bootstrap_deterministic_same_seed():
    diffs = [0.1, -0.2, 0.3, 0.05, -0.1, 0.2, 0.15, -0.05, 0.4, 0.1]
    ci1 = moving_block_bootstrap(diffs, n_boot=2000, seed=7)
    ci2 = moving_block_bootstrap(diffs, n_boot=2000, seed=7)
    assert ci1 == ci2                       # 同 seed 同 CI(random.Random(seed))


def test_bootstrap_direction_sanity_all_positive():
    diffs = [0.2 + 0.01 * i for i in range(20)]     # 全正序列
    lo, hi = moving_block_bootstrap(diffs, n_boot=2000, seed=1)
    assert lo > 0 and hi >= lo              # 重抽均值恒正 → ci_low>0


def test_bootstrap_edge_cases():
    with pytest.raises(ValueError):
        moving_block_bootstrap([])
    assert moving_block_bootstrap([0.3]) == (0.3, 0.3)   # n=1 退化


# ---------- sign_permutation_pvalue ----------

def test_permutation_small_p_for_all_positive():
    diffs = [0.3 + 0.02 * i for i in range(15)]
    p = sign_permutation_pvalue(diffs, n_perm=2000, seed=3)
    assert p < 0.01                         # 全正 → 翻符号几乎不可能更极端


def test_permutation_large_p_for_symmetric():
    diffs = [0.5, -0.5] * 8                 # 均值 0 → 任意翻转都 ≥ 观测
    p = sign_permutation_pvalue(diffs, n_perm=2000, seed=3)
    assert p > 0.5
    assert sign_permutation_pvalue([], seed=0) == 1.0    # 空序列无证据


# ---------- mde ----------

def test_mde_monotone_in_variance():
    low_var = [0.1, -0.1] * 15
    high_var = [1.0, -1.0] * 15             # 同 n,方差更大
    assert mde(high_var) > mde(low_var)


def test_mde_edges():
    assert mde([0.5]) == math.inf           # n<2 无方差信息
    assert mde([0.5, 0.5, 0.5]) == 0.0      # sd=0
    # 手算锚:±1×24 + 0 → 样本 sd 恰为 1,n=25 → (1.960+0.842)×1/5 ≈ 0.5604
    diffs = [1.0, -1.0] * 12 + [0.0]
    assert mde(diffs) == pytest.approx(0.5604, abs=0.001)


# ---------- verdict 四分支 + 门 ----------

def test_verdict_win_branch():
    diffs = [0.3 + 0.01 * i for i in range(12)]      # 全正,n=12≥8
    v = verdict(diffs, n_boot=2000, n_perm=2000, seed=5)
    assert v.verdict == "win" and v.ci_low > 0
    assert v.n_days == 12 and v.mean_diff > 0
    assert v.p_value < 0.05 and v.mde > 0


def test_verdict_loss_branch():
    diffs = [-(0.3 + 0.01 * i) for i in range(12)]
    v = verdict(diffs, n_boot=2000, n_perm=2000, seed=5)
    assert v.verdict == "loss" and v.ci_high < 0


def test_verdict_flat_branch():
    # 均值 0 的非周期序列(周期 ±x 会让每个长2块和恒为0,CI 退化为点)
    diffs = [0.5, -0.4, 0.3, -0.5, 0.2, -0.3, 0.4, -0.2, 0.1, -0.1, 0.35, -0.35]
    v = verdict(diffs, n_boot=2000, n_perm=2000, seed=5)
    assert v.verdict == "flat"
    assert v.ci_low <= 0 <= v.ci_high


def test_verdict_insufficient_gate():
    diffs = [0.5] * 7                                # 全正但 7<8 → 保守不下结论
    v = verdict(diffs, n_boot=500, n_perm=500, seed=5)
    assert v.verdict == "insufficient"
    assert v.n_days == 7
    assert v.ci_low is not None                      # n≥2 仍附信息,只是不判胜负
    v9 = verdict([0.5] * 7 + [0.5, 0.5], n_boot=500, n_perm=500, seed=5)
    assert v9.verdict == "win"                       # 过门(9≥8)即正常判


def test_verdict_empty_and_tiny():
    v = verdict([])
    assert v.verdict == "insufficient" and v.n_days == 0
    assert v.ci_low is None and v.p_value is None and v.mde is None
    v1 = verdict([0.3])
    assert v1.verdict == "insufficient" and v1.mean_diff == pytest.approx(0.3)


def test_verdict_deterministic_and_records_params():
    diffs = [0.1, 0.2, -0.05, 0.3, 0.15, 0.0, 0.25, 0.1, -0.1, 0.2]
    v1 = verdict(diffs, n_boot=2000, n_perm=2000, seed=11)
    v2 = verdict(diffs, n_boot=2000, n_perm=2000, seed=11)
    assert v1 == v2                                  # 同 seed 全字段一致
    assert v1.seed == 11 and v1.n_boot == 2000 and v1.n_perm == 2000
    assert v1.block_len == 2                         # round(10^(1/3))=2(自适应 2-5)


def test_stat_verdict_frozen():
    v = verdict([0.5] * 10, n_boot=500, n_perm=500, seed=1)
    assert isinstance(v, StatVerdict)
    with pytest.raises(Exception):
        v.verdict = "loss"                           # frozen
