from __future__ import annotations

from datetime import date as Date

from pydantic import BaseModel, ConfigDict, Field

from youzi.eval.decision import DecisionPackage
from youzi.eval.metrics import ScoredCandidate
from youzi.schemas.market import MarketState
from youzi.universe.stock import StockStatus


class EntrySnap(BaseModel):
    """入选 code 在决策日的客观入场上下文(≤t)。"""
    model_config = ConfigDict(frozen=True)
    code: str
    status: StockStatus
    boards: int | None = None      # 连板数;源未给则 None(不臆造 0)


class TrajectoryStep(BaseModel):
    """某决策日一步:决策日采 market/decision/entries;horizon 日回填 outcomes/scored。"""
    model_config = ConfigDict(frozen=True)
    date: Date
    market: MarketState
    decision: DecisionPackage
    entries: dict[str, EntrySnap] = Field(default_factory=dict)
    scored: bool = False
    outcomes: dict[str, ScoredCandidate] = Field(default_factory=dict)


class Trajectory(BaseModel):
    """一次回放走出的轨迹(frozen 容器)。"""
    model_config = ConfigDict(frozen=True)
    steps: list[TrajectoryStep] = Field(default_factory=list)
    horizon: int = 1

    def scored_steps(self) -> list[TrajectoryStep]:
        return [s for s in self.steps if s.scored]

    def n_decisions(self) -> int:
        return len(self.steps)

    def n_no_trade(self) -> int:
        return sum(1 for s in self.steps if not s.decision.candidates)

    def __bool__(self) -> bool:
        return True
