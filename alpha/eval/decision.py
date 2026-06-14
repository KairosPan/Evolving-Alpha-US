from __future__ import annotations

from datetime import date as Date
from typing import Literal, Protocol

from pydantic import BaseModel, ConfigDict, Field

from alpha.sizing.position import SizeTier
from alpha.state.market import MarketState
from alpha.universe.universe import CandidateUniverse


class FillFeasibility(BaseModel):
    """Whether the pick is realistically buyable (inference-path; spec §7). buyable=False de-ranks."""
    model_config = ConfigDict(frozen=True)
    buyable: bool = True
    reason: str = ""


class TabooCheck(BaseModel):
    """A guard taboo evaluated against the pick (from L4 guard)."""
    model_config = ConfigDict(frozen=True)
    rule: str
    status: Literal["pass", "fail"]


class Candidate(BaseModel):
    """One picked ticker (US-1d eval contract: which symbol + declared pattern, for attribution)."""
    model_config = ConfigDict(frozen=True)
    symbol: str
    name: str = ""
    pattern: str = ""              # the matched pattern / skill_id (policy-declared, for by_pattern)
    reason: str = ""
    confidence: float = Field(default=0.5, ge=0.0, le=1.0)
    # ── full DecisionPackage fields (US-1g, §4.1); all optional so US-1d construction still validates
    skill_id: str = ""
    family: str = ""                                  # runner|swing|event|meme (or "")
    entry: str = ""
    exit_stop: str = ""
    size_tier: SizeTier | None = None                # from L3 sizing
    fill_feasibility: FillFeasibility | None = None  # from eval/fill (inference path)
    taboo_check: list[TabooCheck] = Field(default_factory=list)   # from L4 guard
    counterview: str = ""


class DecisionPackage(BaseModel):
    """A day's decision (US-1d minimal eval subset of the co-pilot's action a_t).

    US-1g enriches this with size_tier / fill_feasibility / taboo_check / regime_read. Here it is the
    eval contract: ranked candidates + no-trade reason + the policy's raw regime read (<=t).
    `symbol`s should be unique; a policy returning duplicates would be double-counted (the scorer
    de-dups defensively).
    """
    model_config = ConfigDict(frozen=True)
    date: Date
    candidates: list[Candidate] = Field(default_factory=list)
    no_trade_reason: str = ""
    regime_read: str = ""


class DecisionPolicy(Protocol):
    """Policy interface: read the day's aggregate state + candidate universe, produce a decision."""
    def decide(self, state: MarketState, universe: CandidateUniverse) -> DecisionPackage: ...
