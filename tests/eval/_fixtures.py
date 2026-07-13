"""Shared lightweight trajectory fixtures for the P6 eval-methodology tests (purged CV / stratify /
ablation). Pure constructors — no source/LLM. Kept minimal: only the fields the tools read."""
from __future__ import annotations

from datetime import date as Date, datetime as DateTime

from alpha.eval.decision import Candidate, DecisionPackage
from alpha.eval.metrics import ScoredCandidate
from alpha.eval.trajectory import Trajectory, TrajectoryStep
from alpha.state.market import MarketState


def market(day: Date, *, gainers: int = 5, losers: int = 5, **kw) -> MarketState:
    """A minimal MarketState carrying the breadth counts the regime readers use."""
    return MarketState(date=day, gainer_count=gainers, gap_up_count=0, loser_count=losers,
                       failed_breakout_count=0, max_runner_tier=0, echelon=[], breadth_raw=0.0,
                       as_of=DateTime(day.year, day.month, day.day, 16, 0), **kw)


def step(day: Date, *, scored: bool = True, n_cands: int = 1, outcome: str = "continued",
         pattern: str = "gap_and_go", advantage: float = 1.0, score: float | None = None,
         gainers: int = 5, losers: int = 5, **market_kw) -> TrajectoryStep:
    """One trajectory step. `n_cands` scored candidates (all same outcome/pattern/advantage)."""
    cands = [Candidate(symbol=f"S{i}", pattern=pattern) for i in range(n_cands)]
    outcomes = {f"S{i}": ScoredCandidate(decision_date=day, symbol=f"S{i}", pattern=pattern,
                                         outcome=outcome, score=advantage if score is None else score,
                                         advantage=advantage)
                for i in range(n_cands)} if scored else {}
    return TrajectoryStep(date=day, market=market(day, gainers=gainers, losers=losers, **market_kw),
                          decision=DecisionPackage(date=day, candidates=cands),
                          outcomes=outcomes, scored=scored)


def trajectory(days: list[Date], *, horizon: int = 2, **step_kw) -> Trajectory:
    """A trajectory over `days` with the last `horizon` steps unscored (the structural purge)."""
    n = len(days)
    steps = [step(d, scored=(i <= n - 1 - horizon), **step_kw) for i, d in enumerate(days)]
    return Trajectory(steps=steps)


def days(n: int, *, start: Date = Date(2026, 6, 1)) -> list[Date]:
    from datetime import timedelta
    return [start + timedelta(days=i) for i in range(n)]
