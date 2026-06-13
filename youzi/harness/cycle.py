from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class Transition(BaseModel):
    model_config = ConfigDict(extra="forbid")

    to: str
    signal: str


class EmotionPhase(BaseModel):
    model_config = ConfigDict(extra="forbid")

    phase: str
    you_see: list[str] = Field(default_factory=list)
    transitions: list[Transition] = Field(default_factory=list)
    source_lines: list[int] = Field(default_factory=list)


class StateMachine(BaseModel):
    """情绪周期状态机(G_cycle 种子;只读结构,Phase-0b-1 不做推断)。"""
    phases: list[EmotionPhase] = Field(default_factory=list)

    def get(self, phase: str) -> EmotionPhase | None:
        return next((p for p in self.phases if p.phase == phase), None)

    def next_signals(self, phase: str) -> list[tuple[str, str]]:
        p = self.get(phase)
        return [(t.to, t.signal) for t in p.transitions] if p else []

    def phase_names(self) -> list[str]:
        return [p.phase for p in self.phases]

    @classmethod
    def from_seed_list(cls, items: list[dict]) -> "StateMachine":
        phases = [EmotionPhase(**d) for d in items]
        seen: set[str] = set()
        for p in phases:
            if p.phase in seen:
                raise ValueError(f"重复 phase: {p.phase}")
            seen.add(p.phase)
        return cls(phases=phases)
