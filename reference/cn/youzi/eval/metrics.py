from __future__ import annotations

from datetime import date as Date
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, model_validator

from youzi.eval.oracle import Outcome


class ScoredCandidate(BaseModel):
    """一名已评分候选。

    score=原始分(PoolScorer=SCORE[outcome];ReturnScorer=前向收益);
    day_baseline=决策日 limit_up 池基线(同 scorer 口径;空池/缺基线日 None);
    advantage=score−day_baseline(截面超额,去当日市场β;baseline None 时回退=score)。
    """
    model_config = ConfigDict(frozen=True)
    decision_date: Date
    code: str
    pattern: str
    outcome: Outcome
    score: float
    day_baseline: float | None = None   # 决策日池基线(空池日约定:None)
    advantage: float                    # 省略时由 _fill_advantage 回填(兼容旧 JSON/手工构造)

    @model_validator(mode="before")
    @classmethod
    def _fill_advantage(cls, data: Any) -> Any:
        """advantage 缺省回填:有基线= score−day_baseline;无基线回退= score(旧 JSON 兼容)。"""
        if isinstance(data, dict) and data.get("advantage") is None and data.get("score") is not None:
            base = data.get("day_baseline")
            adv = data["score"] - base if base is not None else data["score"]
            data = {**data, "advantage": adv}
        return data


class PatternStat(BaseModel):
    model_config = ConfigDict(frozen=True)
    n: int
    hit_rate: float
    nuke_rate: float
    mean_score: float


class EvalReport(BaseModel):
    model_config = ConfigDict(frozen=True)
    n_decisions: int
    n_no_trade: int
    n_candidates: int
    horizon: int = 1         # 延迟打分窗口(尾部不足 horizon 的决策被丢弃)
    hit_rate: float          # continued / n_candidates
    nuke_rate: float         # nuked / n_candidates
    mean_score: float        # 期望分(expectancy,原始口径,保留)
    mean_excess: float = 0.0  # 截面超额均值(全部已评分候选 advantage 均值;旧 JSON 无此字段 → 0.0)
    by_pattern: dict[str, PatternStat] = Field(default_factory=dict)


def _agg(items: list[ScoredCandidate]) -> tuple[float, float, float, float]:
    """返回 (hit_rate, nuke_rate, mean_score, mean_excess);空列表全 0。"""
    n = len(items)
    if n == 0:
        return (0.0, 0.0, 0.0, 0.0)
    hits = sum(1 for s in items if s.outcome == "continued")
    nukes = sum(1 for s in items if s.outcome == "nuked")
    mean = sum(s.score for s in items) / n
    excess = sum(s.advantage for s in items) / n
    return (hits / n, nukes / n, mean, excess)


def build_report(scored: list[ScoredCandidate], n_decisions: int,
                 n_no_trade: int, horizon: int = 1) -> EvalReport:
    hit, nuke, mean, excess = _agg(scored)
    patterns: dict[str, list[ScoredCandidate]] = {}
    for s in scored:
        patterns.setdefault(s.pattern, []).append(s)
    by_pattern: dict[str, PatternStat] = {}
    for pat, items in patterns.items():
        h, nk, m, _ = _agg(items)
        by_pattern[pat] = PatternStat(n=len(items), hit_rate=h, nuke_rate=nk, mean_score=m)
    return EvalReport(n_decisions=n_decisions, n_no_trade=n_no_trade,
                      n_candidates=len(scored), horizon=horizon, hit_rate=hit,
                      nuke_rate=nuke, mean_score=mean, mean_excess=excess,
                      by_pattern=by_pattern)
