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
