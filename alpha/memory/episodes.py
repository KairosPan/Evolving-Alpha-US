# alpha/memory/episodes.py
from __future__ import annotations
from datetime import date as Date
from pydantic import BaseModel, ConfigDict, Field, model_validator

class Episode(BaseModel):
    """One scored pick (observation-channel; NOT a gated H edit). learned_asof = exit_date (the date the
    outcome became knowable), the PIT key recall masks on."""
    model_config = ConfigDict(frozen=True)
    episode_id: str
    symbol: str
    skill_id: str
    family: str | None = None
    phase: str = ""
    narrative: str = ""
    entry_date: Date
    exit_date: Date
    outcome: str                       # "continued" | "faded" | "nuked" (the oracle's labels)
    advantage: float = 0.0
    score: float = 0.0
    failure_kind: str = ""
    reflection_text: str = ""
    learned_asof: Date | None = None   # defaults to exit_date (set below)

    @model_validator(mode="after")
    def _default_learned_asof(self) -> "Episode":
        if self.learned_asof is None:
            object.__setattr__(self, "learned_asof", self.exit_date)   # frozen model
        return self


def episodes_from_step(step, h) -> list[Episode]:
    """Build one Episode per scored pick in a matured TrajectoryStep. Uses step.exit_date as the PIT key.
    [] if the step is unscored or has no exit_date (the last `horizon` steps never mature)."""
    from alpha.refine.credit import resolve_skill  # local import: avoid heavy import at module load
    if not step.scored or step.exit_date is None:
        return []
    narratives = {c.symbol: getattr(c, "narrative", "") for c in step.decision.candidates}
    phase = getattr(step.decision, "regime_read", "") or ""
    out: list[Episode] = []
    for symbol, sc in step.outcomes.items():
        skill = resolve_skill(getattr(sc, "pattern", ""), h)
        skill_id = skill.skill_id if skill is not None else (getattr(sc, "pattern", "") or "__unattributed__")
        family = skill.family if skill is not None else None
        out.append(Episode(
            episode_id=f"{step.exit_date.isoformat()}:{symbol}:{skill_id}",
            symbol=symbol, skill_id=skill_id, family=family, phase=phase,
            narrative=narratives.get(symbol, "") or "",
            entry_date=step.date, exit_date=step.exit_date,
            outcome=getattr(sc, "outcome", ""), advantage=getattr(sc, "advantage", 0.0),
            score=getattr(sc, "score", 0.0),
            failure_kind=getattr(sc, "failure_signature", "") or "",
            reflection_text=getattr(sc, "reflection", "") or "",
        ))
    return out
