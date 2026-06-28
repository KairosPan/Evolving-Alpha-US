from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from alpha.harness.regime import is_family, normalize_phases

SkillType = Literal["pattern", "feature", "failure_detector"]
SkillStatus = Literal["active", "incubating", "dormant", "retired"]


class GateSpec(BaseModel):
    """Machine-readable trigger gate: deterministic match against a StockSnapshot (US fields).

    Strongly typed (extra='forbid') so a typo key from a Refiner patch is rejected, not silently
    swallowed. All fields optional; None = unconstrained (all-None matches any snapshot).
    Match semantics live in the consumer (eval/rule_policy), not here (avoid harness->universe dep).
    """
    model_config = ConfigDict(extra="forbid")
    min_consecutive_up_days: int | None = None
    max_consecutive_up_days: int | None = None
    status_in: list[str] | None = None       # StockStatus values: gainer/gap_up/loser/runner
    min_rvol: float | None = None


class SkillStats(BaseModel):
    """Rolling skill performance (mutable, updated at runtime by credit assignment in US-1d/2)."""
    n: int = 0
    wins: int = 0
    losses: int = 0
    nukes: int = 0                       # times the pick got nuked; nuke_rate = nukes/n
    ewma_winrate: float | None = None
    pnl_ratio: float | None = None
    expectancy: float | None = None      # advantage (score - same-day baseline); set in US-1d
    expectancy_raw: float | None = None  # raw score mean (legacy lens); set in US-1d
    oracle_gap: float | None = None

    def record(self, win: bool, decay: float = 0.1) -> None:
        """Record one outcome. First sample seeds the EWMA; then ewma = decay*x + (1-decay)*ewma."""
        if not 0.0 < decay <= 1.0:
            raise ValueError(f"decay must be in (0, 1], got {decay}")
        x = 1.0 if win else 0.0
        self.n += 1
        self.wins += int(win)
        self.losses += int(not win)
        self.ewma_winrate = x if self.ewma_winrate is None else decay * x + (1 - decay) * self.ewma_winrate


class Skill(BaseModel):
    """A K skill (mutable harness state; the Refiner edits these in later phases)."""
    model_config = ConfigDict(extra="forbid", validate_assignment=True)
    skill_id: str
    name: str
    type: SkillType
    family: str | None = None                                    # runner|swing|event|meme
    phases: list[str] = Field(default_factory=list)             # canonical US phases
    applies_all_phases: bool = False                            # phases contained 'all'
    trigger: str = ""
    entry: str = ""
    exit_stop: str = ""
    taboo: list[str] = Field(default_factory=list)
    depends_on: list[str] = Field(default_factory=list)
    examples: list[str] = Field(default_factory=list)
    domain: Literal["trading", "operational"] = "trading"
    status: SkillStatus = "incubating"
    notes: str = ""
    stats: SkillStats = Field(default_factory=SkillStats)
    gate: GateSpec | None = None

    @classmethod
    def from_seed(cls, d: dict) -> "Skill":
        raw_phases = d.get("phases", d.get("applicable_regime", []))
        phases, applies_all = normalize_phases(raw_phases)
        family = d.get("family")
        if family is not None and not is_family(family):
            raise ValueError(f"unknown family: {family!r}")
        rest = {k: v for k, v in d.items() if k not in ("phases", "applicable_regime", "applies_all_phases")}
        return cls(**rest, phases=phases, applies_all_phases=applies_all)
