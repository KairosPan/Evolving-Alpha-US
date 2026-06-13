# youzi/eval/scorer.py
from __future__ import annotations

from datetime import date as Date
from typing import Protocol

from youzi.eval.decision import DecisionPackage
from youzi.eval.metrics import ScoredCandidate
from youzi.eval.oracle import SCORE, DayMembership, outcome
from youzi.eval.return_oracle import ReturnOracle


class Scorer(Protocol):
    """把一步成熟决策打分成 code→ScoredCandidate(去重;可丢弃缺数候选)。

    mems=持有路径 entry..exit 逐日池成员(由 PoolRecord 取,长度=horizon);
    池制(PoolScorer)只看终点 mems[-1](=现行 exit 日语义);收益制(ReturnScorer)
    可吃整条路径做 stop-on-nuke。decision_mem=决策日(≤t)池成员,只用于按日基线
    day_baseline 的集合定义。一律事后消费 t+ 标签,不引入决策路径(防火墙)。
    空池日约定:decision_mem 为 None 或 limit_up 为空 → day_baseline=None,
    advantage 回退=score(显式回退,不臆造 0 基线)。
    """
    def score_step(self, decision: DecisionPackage, mems: list[DayMembership],
                   entry_day: Date, exit_day: Date, source,
                   decision_mem: DayMembership | None = None) -> dict[str, ScoredCandidate]: ...


class PoolScorer:
    """默认:池成员制 outcome + SCORE[outcome](= 现行为)。entry/exit/source 忽略。

    day_baseline=决策日 limit_up 池**全体成员**按 exit 日成员判 outcome 的 SCORE 均值
    (="闭眼买整个涨停池"的同日期望;PoolRecord 已录两日成员,零额外取数)。
    按 (决策日成员, exit 日成员) 缓存——同日跨臂复用免重算(DayMembership frozen 可哈希)。
    """

    def __init__(self) -> None:
        self._baseline_cache: dict[tuple[DayMembership, DayMembership], float | None] = {}

    def _day_baseline(self, decision_mem: DayMembership | None,
                      mem: DayMembership) -> float | None:
        if decision_mem is None or not decision_mem.limit_up:
            return None                               # 空池日:无基线(advantage 回退=score)
        key = (decision_mem, mem)
        if key not in self._baseline_cache:
            pool = decision_mem.limit_up
            self._baseline_cache[key] = sum(SCORE[outcome(c, mem)] for c in pool) / len(pool)
        return self._baseline_cache[key]

    def score_step(self, decision: DecisionPackage, mems: list[DayMembership],
                   entry_day: Date, exit_day: Date, source,
                   decision_mem: DayMembership | None = None) -> dict[str, ScoredCandidate]:
        mem = mems[-1]                                # 池制只看终点(exit 日),保持现行为
        base = self._day_baseline(decision_mem, mem)
        seen: set[str] = set()
        out: dict[str, ScoredCandidate] = {}
        for c in decision.candidates:
            if c.code in seen:
                continue
            seen.add(c.code)
            oc = outcome(c.code, mem)
            score = SCORE[oc]
            out[c.code] = ScoredCandidate(decision_date=decision.date, code=c.code,
                                          pattern=c.pattern, outcome=oc, score=score,
                                          day_baseline=base,
                                          advantage=score - base if base is not None else score)
        return out


class ReturnScorer:
    """收益打分:outcome 仍池成员制;score=前向收益;收益 None → 丢弃该候选。

    day_baseline=决策日 limit_up 池成员的前向收益均值,**只对有 OHLCV 的成员求**
    (与候选"缺收益丢弃"规则一致;全员缺收益 → None)。池基线的 entry/exit 沿用
    与候选完全相同的 entry_day/exit_day(T+1 对称),fill-feasibility 偏差两边对称。
    按 (池成员, entry, exit) 缓存;同一 scorer 实例假定同一数据源(compare 四臂同源)。
    """

    def __init__(self) -> None:
        self._baseline_cache: dict[tuple[frozenset[str], Date, Date], float | None] = {}

    def _day_baseline(self, decision_mem: DayMembership | None, entry_day: Date,
                      exit_day: Date, oracle: ReturnOracle) -> float | None:
        if decision_mem is None or not decision_mem.limit_up:
            return None                               # 空池日:无基线(advantage 回退=score)
        key = (decision_mem.limit_up, entry_day, exit_day)
        if key not in self._baseline_cache:
            rets = [r for code in sorted(decision_mem.limit_up)
                    if (r := oracle.score(code, entry_day, exit_day)) is not None]
            self._baseline_cache[key] = sum(rets) / len(rets) if rets else None
        return self._baseline_cache[key]

    def score_step(self, decision: DecisionPackage, mems: list[DayMembership],
                   entry_day: Date, exit_day: Date, source,
                   decision_mem: DayMembership | None = None) -> dict[str, ScoredCandidate]:
        oracle = ReturnOracle(source)
        base = self._day_baseline(decision_mem, entry_day, exit_day, oracle)
        seen: set[str] = set()
        out: dict[str, ScoredCandidate] = {}
        for c in decision.candidates:
            if c.code in seen:
                continue
            seen.add(c.code)
            ret = oracle.score(c.code, entry_day, exit_day)
            if ret is None:
                continue                              # 丢弃缺收益候选
            oc = outcome(c.code, mems[-1])
            out[c.code] = ScoredCandidate(decision_date=decision.date, code=c.code,
                                          pattern=c.pattern, outcome=oc, score=ret,
                                          day_baseline=base,
                                          advantage=ret - base if base is not None else ret)
        return out
