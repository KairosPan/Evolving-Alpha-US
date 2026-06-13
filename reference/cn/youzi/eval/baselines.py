from __future__ import annotations

import random

from youzi.eval.decision import Candidate, DecisionPackage
from youzi.schemas.market import MarketState
from youzi.universe.universe import CandidateUniverse


class NoTradePolicy:
    """floor 基线:永远空仓。"""

    def decide(self, state: MarketState, universe: CandidateUniverse) -> DecisionPackage:
        return DecisionPackage(date=state.date, no_trade_reason="baseline:no-trade")


class HighestBoardPolicy:
    """floor 基线:无脑追当日最高连板(超短最朴素的追高)。"""

    def decide(self, state: MarketState, universe: CandidateUniverse) -> DecisionPackage:
        ups = universe.by_status("limit_up")
        if not ups:
            return DecisionPackage(date=state.date, no_trade_reason="无涨停")
        top = max((s.boards or 0) for s in ups)
        if top == 0:
            return DecisionPackage(date=state.date, no_trade_reason="无有效连板数据")
        picks = [s for s in ups if (s.boards or 0) == top]
        cands = [Candidate(code=s.code, name=s.name, pattern="highest_board",
                           reason=f"{s.boards}板最高") for s in picks]
        return DecisionPackage(date=state.date, candidates=cands)


class PoolAveragePolicy:
    """基线:闭眼买当日**整个涨停池**(池内平均,C2 第五臂候选;暂只提供 policy,接线留后续)。

    advantage 口径下其期望≈0(它就是 day_baseline 的定义),是截面超额的零点对照——
    系统由此能回答"agent 比闭眼买整个涨停池好多少"。
    """

    def decide(self, state: MarketState, universe: CandidateUniverse) -> DecisionPackage:
        ups = sorted(universe.by_status("limit_up"), key=lambda s: s.code)   # 排序定序,输出可复现
        if not ups:
            return DecisionPackage(date=state.date, no_trade_reason="无涨停")
        cands = [Candidate(code=s.code, name=s.name, pattern="pool_avg",
                           reason="池内平均基线") for s in ups]
        return DecisionPackage(date=state.date, candidates=cands)


class RandomFromPoolPolicy:
    """基线:从当日涨停池**确定性伪随机**选 k 只("精选 vs 广撒"对照)。

    可复现:同 (seed, 日期, 池成员) → 同选择。先按 code 排序消除集合迭代序的随机性,
    再用 "seed:日期" 字符串播种的 Random 抽样(str 种子走 SHA512,跨进程/跨运行稳定,
    不受 PYTHONHASHSEED 影响);池不足 k 只时全选。
    """

    def __init__(self, k: int, seed: int = 0) -> None:
        if k < 1:
            raise ValueError(f"k 必须 >=1, got {k}")
        self._k = k
        self._seed = seed

    def decide(self, state: MarketState, universe: CandidateUniverse) -> DecisionPackage:
        ups = sorted(universe.by_status("limit_up"), key=lambda s: s.code)
        if not ups:
            return DecisionPackage(date=state.date, no_trade_reason="无涨停")
        rng = random.Random(f"{self._seed}:{state.date.isoformat()}")   # 按日派生,跨日不同但可复现
        picks = sorted(rng.sample(ups, min(self._k, len(ups))), key=lambda s: s.code)
        cands = [Candidate(code=s.code, name=s.name, pattern="random_pool",
                           reason=f"随机选池 k={self._k} seed={self._seed}") for s in picks]
        return DecisionPackage(date=state.date, candidates=cands)
