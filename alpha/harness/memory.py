from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from alpha.harness.regime import is_family, normalize_phases

Outcome = Literal["win", "loss", "principle"]


class Importance(BaseModel):
    """Memory importance (mutable). weight = base * time_decay * regime_decay (double decay)."""
    model_config = ConfigDict(validate_assignment=True)
    base: float = 1.0
    time_decay: float = 1.0
    regime_decay: float = 1.0

    def weight(self) -> float:
        return self.base * self.time_decay * self.regime_decay

    def demote(self, factor: float) -> None:
        if not 0.0 < factor <= 1.0:
            raise ValueError(f"demote factor must be in (0, 1], got {factor}")
        self.time_decay *= factor


class Lesson(BaseModel):
    """An M memory entry (mutable). Phase/family tagged; double-decay importance."""
    model_config = ConfigDict(extra="forbid", validate_assignment=True)
    lesson_id: str
    phases: list[str] = Field(default_factory=list)
    applies_all_phases: bool = False
    family: str | None = None
    pattern: str = ""
    outcome: Outcome
    failure_signature: str = ""
    named_analog: str = ""
    lesson: str
    importance: Importance = Field(default_factory=Importance)

    @classmethod
    def from_seed(cls, d: dict) -> "Lesson":
        phases, applies_all = normalize_phases(d.get("phases", d.get("regime", [])))
        family = d.get("family")
        if family is not None and not is_family(family):
            raise ValueError(f"unknown family: {family!r}")
        rest = {k: v for k, v in d.items() if k not in ("phases", "regime", "applies_all_phases")}
        return cls(**rest, phases=phases, applies_all_phases=applies_all)
