from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from youzi.harness.regime import parse_regime_field

Outcome = Literal["win", "loss", "principle"]


class Importance(BaseModel):
    """记忆重要度(可变)。weight = base × time_decay × regime_decay(双衰减,蓝图 §8)。"""
    model_config = ConfigDict(validate_assignment=True)
    base: float = 1.0
    time_decay: float = 1.0
    regime_decay: float = 1.0

    def weight(self) -> float:
        return self.base * self.time_decay * self.regime_decay

    def demote(self, factor: float) -> None:
        if not 0.0 < factor <= 1.0:
            raise ValueError(f"demote factor 必须在 (0,1], got {factor}")
        self.time_decay *= factor


class Lesson(BaseModel):
    """M 记忆条目(可变)。regime 解析为多值 phases/ecologies/applies_all。"""
    model_config = ConfigDict(extra="forbid", validate_assignment=True)
    lesson_id: str
    regime_raw: str = ""              # 原始 regime 串(可溯源)
    phases: list[str] = Field(default_factory=list)
    ecologies: list[str] = Field(default_factory=list)
    applies_all: bool = False
    pattern: str = ""
    outcome: Outcome
    failure_signature: str = ""
    named_analog: str = ""
    lesson: str
    source_lines: list[int] = Field(default_factory=list)
    importance: Importance = Field(default_factory=Importance)

    @classmethod
    def from_seed(cls, d: dict) -> "Lesson":
        raw = d.get("regime", "")
        phases, ecologies, applies_all = parse_regime_field(raw)
        rest = {k: v for k, v in d.items() if k != "regime"}
        return cls(**rest, regime_raw=raw, phases=phases,
                   ecologies=ecologies, applies_all=applies_all)
