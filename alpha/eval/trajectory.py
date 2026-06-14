from __future__ import annotations

from datetime import date as Date

from pydantic import BaseModel, ConfigDict, Field

from alpha.eval.decision import DecisionPackage
from alpha.eval.metrics import ScoredCandidate, build_report, EvalReport
from alpha.state.market import MarketState
from alpha.universe.stock import StockSnapshot


class TrajectoryStep(BaseModel):
    """One decision day's full record. `outcomes` is empty until the decision is scored at t+horizon;
    `scored` marks that the step reached its exit day (the last `horizon` steps never do)."""
    model_config = ConfigDict(frozen=True)
    date: Date
    market: MarketState
    decision: DecisionPackage
    entries: dict[str, StockSnapshot] = Field(default_factory=dict)     # picked symbol -> decision-day snapshot
    outcomes: dict[str, ScoredCandidate] = Field(default_factory=dict)  # symbol -> realized scored outcome
    scored: bool = False


class Trajectory(BaseModel):
    """The ordered per-day record of one walk. Read-only evidence the Refiner consumes."""
    model_config = ConfigDict(frozen=True)
    steps: list[TrajectoryStep] = Field(default_factory=list)

    def scored_steps(self) -> list[TrajectoryStep]:
        return [s for s in self.steps if s.scored]

    def all_scored(self) -> list[ScoredCandidate]:
        return [sc for s in self.scored_steps() for sc in s.outcomes.values()]


def report_from_trajectory(traj: Trajectory, horizon: int = 2) -> EvalReport:
    """Aggregate a Trajectory into the same EvalReport WalkForwardEval.run() always produced:
    n_decisions over all steps, n_no_trade over decisions with no candidates, scored over scored steps."""
    scored = traj.all_scored()
    n_no_trade = sum(1 for s in traj.steps if not s.decision.candidates)
    return build_report(scored, n_decisions=len(traj.steps), n_no_trade=n_no_trade, horizon=horizon)
