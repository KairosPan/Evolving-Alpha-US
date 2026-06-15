from __future__ import annotations

from datetime import date as Date
from typing import Literal

from pydantic import BaseModel, ConfigDict

from alpha.eval.trajectory import Trajectory
from alpha.harness.state import HarnessState
from alpha.refine.credit import resolve_skill

FailureKind = Literal["chased_blowoff", "weak_laggard_nuke", "generic_nuke", "faded_miss"]


class FailureSignature(BaseModel):
    """Deterministic, read-only 'where it lost' tag for one non-continued scored pick."""
    model_config = ConfigDict(frozen=True)
    date: Date
    symbol: str
    pattern: str
    skill_id: str | None
    kind: FailureKind
    score: float
    evidence: str


def extract_signatures(traj: Trajectory, h: HarnessState) -> list[FailureSignature]:
    """Per non-continued scored pick, classify the failure. Continued (win) -> no signature.
    nuked split by entry context: chased a top-tier extended runner vs took a laggard.

    As of US-3a build_universe populates consecutive_up_days, so on real walks step.entries carry a
    runner tier and step.market.max_runner_tier is non-zero -> the chased_blowoff / weak_laggard_nuke
    discrimination is live (it degrades to generic_nuke only when a pick's tier is genuinely unknown)."""
    sigs: list[FailureSignature] = []
    for step in traj.scored_steps():
        max_tier = step.market.max_runner_tier
        for sym, sc in step.outcomes.items():
            if sc.outcome == "continued":
                continue
            skill = resolve_skill(sc.pattern, h)
            skill_id = skill.skill_id if skill is not None else None
            if sc.outcome == "faded":
                kind: FailureKind = "faded_miss"
                ev = "no follow-through (idle, score 0 — not a loss)"
            else:  # nuked
                snap = step.entries.get(sym)
                cud = snap.consecutive_up_days if snap is not None else None
                if cud is None or max_tier <= 0:
                    kind, ev = "generic_nuke", "nuked; entry runner-tier unknown"
                elif cud >= max_tier:
                    kind, ev = "chased_blowoff", f"chased a top runner (up_days {cud} >= max_tier {max_tier}) into a nuke"
                else:
                    kind, ev = "weak_laggard_nuke", f"took a laggard (up_days {cud} < max_tier {max_tier}); dumped"
            sigs.append(FailureSignature(date=step.date, symbol=sym, pattern=sc.pattern,
                                         skill_id=skill_id, kind=kind, score=sc.score, evidence=ev))
    return sigs
