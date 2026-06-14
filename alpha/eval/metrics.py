from __future__ import annotations

from datetime import date as Date
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, model_validator

from alpha.eval.oracle import Outcome


class ScoredCandidate(BaseModel):
    """One scored candidate.

    score = raw score (ReturnScorer: forward return; PoolScorer: SCORE[outcome]);
    day_baseline = the decision-day gainer-pool baseline (same scorer lens; None on empty pool);
    advantage = score - day_baseline (cross-sectional excess, de-market-beta; falls back to score).
    """
    model_config = ConfigDict(frozen=True)
    decision_date: Date
    symbol: str
    pattern: str
    outcome: Outcome
    score: float
    day_baseline: float | None = None
    advantage: float

    @model_validator(mode="before")
    @classmethod
    def _fill_advantage(cls, data: Any) -> Any:
        if isinstance(data, dict) and data.get("advantage") is None and data.get("score") is not None:
            base = data.get("day_baseline")
            data = {**data, "advantage": data["score"] - base if base is not None else data["score"]}
        return data


class PatternStat(BaseModel):
    model_config = ConfigDict(frozen=True)
    n: int
    hit_rate: float
    nuke_rate: float
    mean_score: float


class EvalReport(BaseModel):
    # Mixed lens (by design, spec §7): hit_rate/nuke_rate come from the exogenous pool-category
    # (outcome), while mean_score/mean_excess come from the scorer's score (forward return under
    # ReturnScorer). The two lenses can disagree per-candidate (e.g. positive return but outcome
    # 'nuked'); the return lens is primary, the category is a coarse diagnostic.
    model_config = ConfigDict(frozen=True)
    n_decisions: int
    n_no_trade: int
    n_candidates: int
    horizon: int = 2
    hit_rate: float          # continued / n_candidates
    nuke_rate: float         # nuked / n_candidates
    mean_score: float        # expectancy (raw lens)
    mean_excess: float = 0.0  # mean advantage (cross-sectional excess)
    by_pattern: dict[str, PatternStat] = Field(default_factory=dict)


def _agg(items: list[ScoredCandidate]) -> tuple[float, float, float, float]:
    n = len(items)
    if n == 0:
        return (0.0, 0.0, 0.0, 0.0)
    hits = sum(1 for s in items if s.outcome == "continued")
    nukes = sum(1 for s in items if s.outcome == "nuked")
    mean = sum(s.score for s in items) / n
    excess = sum(s.advantage for s in items) / n
    return (hits / n, nukes / n, mean, excess)


def build_report(scored: list[ScoredCandidate], n_decisions: int,
                 n_no_trade: int, horizon: int = 2) -> EvalReport:
    hit, nuke, mean, excess = _agg(scored)
    patterns: dict[str, list[ScoredCandidate]] = {}
    for s in scored:
        patterns.setdefault(s.pattern, []).append(s)
    by_pattern = {pat: PatternStat(n=len(items), hit_rate=_agg(items)[0],
                                   nuke_rate=_agg(items)[1], mean_score=_agg(items)[2])
                  for pat, items in patterns.items()}
    return EvalReport(n_decisions=n_decisions, n_no_trade=n_no_trade, n_candidates=len(scored),
                      horizon=horizon, hit_rate=hit, nuke_rate=nuke, mean_score=mean,
                      mean_excess=excess, by_pattern=by_pattern)
