# youzi/eval/stats.py
"""统一统计裁决层(C1):日级等权聚合 + 配对差 + 移动块 bootstrap CI + 符号置换 + MDE。

动机(spec C1):池化均值被高产日加权、同日候选强相关,裸符号判胜(d>0)对
Δ=±0.003 也判胜负,结构上不可证伪。本模块把"谁赢"的判定收敛到一个纯函数:

    日级等权(消同日相关/高产日加权)→ 两臂按日配对差(免费方差缩减)
    → 移动块 bootstrap CI(块保留日间自相关)+ 符号置换 p + MDE 诚实标尺
    → 四值 verdict(win/loss/flat/insufficient)。

接口约定(spec 修订第⑥条):臂对臂判胜必须走 stats.verdict(小窗→insufficient
即保守不动作)。本期消费点:compare_harnesses 与 web compare 视图;1b-3c 影子
Hexpert 地板与孵化锦标赛落地时复用。现有熔断(rolling vs 阈值)非臂对臂,本期不动。

纯 stdlib(random/statistics/math),离线可测,seed 必显式可控。
"""
from __future__ import annotations

import math
import random
import statistics
from datetime import date as Date
from typing import Literal

from pydantic import BaseModel, ConfigDict

from youzi.eval.trajectory import Trajectory

# 默认参数(spec:B≥10000、n_perm=20000、配对日<8→insufficient、块长 2-5 自适应)
DEFAULT_N_BOOT = 10_000
DEFAULT_N_PERM = 20_000
DEFAULT_MIN_DAYS = 8
DEFAULT_SEED = 0


class StatVerdict(BaseModel):
    """一次臂对臂统计裁决的完整快照(frozen;可随 ComparisonReport 持久化)。

    verdict 判定规则:配对日 < min_days → insufficient;ci_low>0 → win;
    ci_high<0 → loss;否则 flat。ci/p/mde 在 n_days<2 时为 None(算不出方差)。
    """
    model_config = ConfigDict(frozen=True)
    verdict: Literal["win", "loss", "flat", "insufficient"]
    n_days: int                      # 配对日数(两臂日历交集)
    mean_diff: float                 # 日级配对差均值(a−b,advantage 口径)
    ci_low: float | None = None      # 移动块 bootstrap 95% CI 下界
    ci_high: float | None = None     # 移动块 bootstrap 95% CI 上界
    p_value: float | None = None     # 符号置换检验双侧 p(以日为交换单元)
    mde: float | None = None         # 该样本量/方差下最小可检测效应(诚实标尺)
    seed: int = DEFAULT_SEED         # 复现实验的随机种子
    block_len: int = 1               # bootstrap 实际块长
    n_boot: int = DEFAULT_N_BOOT
    n_perm: int = DEFAULT_N_PERM


def daily_series(traj: Trajectory) -> list[tuple[Date, float]]:
    """日级等权聚合:每个**已评分步**取当日全部已评分候选的 advantage 均值。

    空仓日/无已评分候选日记 0.0(与 Hmin_notrade 口径一致),保证两臂同窗
    走出的日历逐日对齐——以 trajectory 的步日历为准,尾部 scored=False 的步
    (不足 horizon 未回填)不入列:两臂同 horizon 同窗,尾部对称缺失,不破坏配对。
    按日期升序返回。
    """
    out: list[tuple[Date, float]] = []
    for step in traj.steps:
        if not step.scored:
            continue
        cands = list(step.outcomes.values())
        v = sum(c.advantage for c in cands) / len(cands) if cands else 0.0
        out.append((step.date, v))
    out.sort(key=lambda t: t[0])
    return out


def paired_daily_diff(a: list[tuple[Date, float]],
                      b: list[tuple[Date, float]]) -> list[float]:
    """两臂日级序列按日期对齐的配对差(a−b),按日期升序返回。

    同窗同 oracle 下两臂日历应当一致;若不一致(防御:某臂窗口被截/旧数据),
    取日期交集做配对——交集天数即 len(返回值),由调用方记入 StatVerdict.n_days。
    """
    da, db = dict(a), dict(b)
    common = sorted(set(da) & set(db))
    return [da[d] - db[d] for d in common]


def _default_block_len(n: int) -> int:
    """块长自适应:~n^(1/3) 夹在 [2,5](spec:2-5 连续交易日保留自相关),再夹到 n。"""
    if n <= 1:
        return 1
    return min(max(2, round(n ** (1 / 3))), 5, n)


def moving_block_bootstrap(diffs: list[float], block_len: int | None = None,
                           n_boot: int = DEFAULT_N_BOOT,
                           seed: int = DEFAULT_SEED) -> tuple[float, float]:
    """移动块 bootstrap:对日级配对差均值给 95% CI(百分位法)。

    每轮重抽 ceil(n/L) 个起点∈[0, n−L],拼接长度 L 的连续块、截断到 n 后取均值;
    块保留相邻交易日的自相关(独立重抽单日会低估方差)。block_len=None 时按
    序列长自适应(2-5)。seed 必显式可控(random.Random(seed),确定性优先)。
    n<2 时退化返回 (mean, mean)。
    """
    n = len(diffs)
    if n == 0:
        raise ValueError("moving_block_bootstrap: 空序列")
    if n == 1:
        return (diffs[0], diffs[0])
    L = block_len if block_len is not None else _default_block_len(n)
    L = max(1, min(L, n))
    rng = random.Random(seed)
    n_blocks = math.ceil(n / L)
    max_start = n - L                      # 起点上界(含)
    means: list[float] = []
    for _ in range(n_boot):
        sample: list[float] = []
        for _ in range(n_blocks):
            s = rng.randint(0, max_start)
            sample.extend(diffs[s:s + L])
        del sample[n:]                     # 截断到原长
        means.append(sum(sample) / n)
    means.sort()
    lo_idx = int(0.025 * n_boot)
    hi_idx = min(n_boot - 1, int(0.975 * n_boot))
    return (means[lo_idx], means[hi_idx])


def sign_permutation_pvalue(diffs: list[float], n_perm: int = DEFAULT_N_PERM,
                            seed: int = DEFAULT_SEED) -> float:
    """符号置换检验(双侧):以日为交换单元,按日随机翻转配对差符号。

    H0:两臂可交换(配对差关于 0 对称)→ 每日符号 ±1 等概率。
    p = (1 + #{|置换均值| ≥ |观测均值|}) / (1 + n_perm)(加一平滑,p 永不为 0)。
    seed 显式可控;空序列返回 1.0(无证据)。
    """
    n = len(diffs)
    if n == 0:
        return 1.0
    obs = abs(sum(diffs) / n)
    rng = random.Random(seed)
    hits = 0
    for _ in range(n_perm):
        s = sum(d if rng.random() < 0.5 else -d for d in diffs)
        if abs(s / n) >= obs:
            hits += 1
    return (1 + hits) / (1 + n_perm)


def mde(diffs: list[float], alpha: float = 0.05, power: float = 0.8) -> float:
    """该样本量/方差下的最小可检测效应(诚实标尺:当前样本能分辨多大效应)。

    正态近似:MDE = (z_{1−α/2} + z_{power}) × sd / √n,其中 sd 为配对差样本
    标准差(n−1)。近似假设:日级配对差近独立同分布、均值近正态(CLT)、
    双侧检验、方差用样本估计代替真值;**忽略日间自相关**(自相关为正时
    实际 MDE 更大,本值偏乐观)——量级标尺够用,不作精确功效分析。
    n<2 或 sd=0 时返回 inf/0 边界:n<2 → inf(无方差信息);sd=0 → 0.0。
    """
    n = len(diffs)
    if n < 2:
        return math.inf
    sd = statistics.stdev(diffs)
    if sd == 0.0:
        return 0.0
    nd = statistics.NormalDist()
    z = nd.inv_cdf(1 - alpha / 2) + nd.inv_cdf(power)
    return z * sd / math.sqrt(n)


def verdict(diffs: list[float], min_days: int = DEFAULT_MIN_DAYS, *,
            block_len: int | None = None, n_boot: int = DEFAULT_N_BOOT,
            n_perm: int = DEFAULT_N_PERM, seed: int = DEFAULT_SEED) -> StatVerdict:
    """统一裁决入口:日级配对差 → StatVerdict。

    判定规则(臂对臂判胜的唯一口径):
      配对日 < min_days → insufficient(样本不足,保守不动作);
      ci_low > 0 → win;ci_high < 0 → loss;否则 flat。
    insufficient 但 n_days≥2 时仍附 CI/p/MDE(信息照给,只是不下结论)。
    """
    n = len(diffs)
    mean = sum(diffs) / n if n else 0.0
    ci_lo: float | None = None
    ci_hi: float | None = None
    p: float | None = None
    m: float | None = None
    eff_block = 1
    if n >= 2:
        eff_block = block_len if block_len is not None else _default_block_len(n)
        eff_block = max(1, min(eff_block, n))
        ci_lo, ci_hi = moving_block_bootstrap(diffs, block_len=eff_block,
                                              n_boot=n_boot, seed=seed)
        p = sign_permutation_pvalue(diffs, n_perm=n_perm, seed=seed)
        m = mde(diffs)
    if n < min_days:
        v: Literal["win", "loss", "flat", "insufficient"] = "insufficient"
    elif ci_lo is not None and ci_lo > 0:
        v = "win"
    elif ci_hi is not None and ci_hi < 0:
        v = "loss"
    else:
        v = "flat"
    return StatVerdict(verdict=v, n_days=n, mean_diff=mean, ci_low=ci_lo,
                       ci_high=ci_hi, p_value=p, mde=m, seed=seed,
                       block_len=eff_block, n_boot=n_boot, n_perm=n_perm)
