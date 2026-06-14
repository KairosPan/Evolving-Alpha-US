from __future__ import annotations

from datetime import date as Date
from typing import Protocol

from pydantic import BaseModel, ConfigDict, Field

from alpha.state.market import MarketState
from alpha.universe.universe import CandidateUniverse


class Candidate(BaseModel):
    """One picked ticker (US-1d eval contract: which symbol + declared pattern, for attribution)."""
    model_config = ConfigDict(frozen=True)
    symbol: str
    name: str = ""
    pattern: str = ""              # the matched pattern / skill_id (policy-declared, for by_pattern)
    reason: str = ""
    confidence: float = Field(default=0.5, ge=0.0, le=1.0)


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
