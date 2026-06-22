from __future__ import annotations

from datetime import date as Date, datetime
from typing import Literal, Protocol

from pydantic import BaseModel, ConfigDict, Field

from alpha.regime.classifier import RegimeRead
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
    narrative: str = ""                               # sympathy/theme key for L3 correlation netting
                                                      #   (e.g. "ai-compute"); "" = the name stands alone.
                                                      #   Finer than family; the agent sets it (US-5).
    entry: str = ""
    exit_stop: str = ""
    size_tier: SizeTier | None = None                # from L3 sizing
    fill_feasibility: FillFeasibility | None = None  # from eval/fill (inference path)
    taboo_check: list[TabooCheck] = Field(default_factory=list)   # from L4 guard
    counterview: str = ""


class Portfolio(BaseModel):
    """Portfolio-level sizing summary (from L3 sizing). Field names match PortfolioPlan / spec §4.1."""
    model_config = ConfigDict(frozen=True)
    total_exposure_budget: float = 0.0
    correlated_groups: list[list[str]] = Field(default_factory=list)
    total_exposure: float = 0.0      # netted exposure actually taken (same-narrative names = one bet)
    capped: bool = False             # raw netted exposure exceeded the risk-gated budget


class DecisionPackage(BaseModel):
    """A day's decision — the co-pilot's action a_t (the human-confirmation surface + DAgger record).

    US-1d shipped the minimal eval contract (date/candidates/no_trade_reason/regime_read); US-1g adds
    the full §4.1 fields below. All additions are optional so US-1d construction still validates.
    `symbol`s should be unique; a policy returning duplicates would be double-counted (the scorer
    de-dups defensively).
    """
    model_config = ConfigDict(frozen=True)
    date: Date
    candidates: list[Candidate] = Field(default_factory=list)
    no_trade_reason: str = ""
    regime_read: str = ""
    # ── full DecisionPackage fields (US-1g, §4.1); optional so US-1d construction still validates
    as_of: datetime | None = None        # snapshot timestamp; agent sets it on the inference path (US-2)
    regime: RegimeRead | None = None     # structured GLOBAL regime read from G_cycle (§4.1 global_risk_gate
                                         #   + frontside); per-narrative 'lines' -> US-3 (needs theme data).
                                         #   regime_read (str above) stays as the agent's prose read / phase_prior.
    key_risks: list[str] = Field(default_factory=list)
    portfolio: Portfolio | None = None
    human_confirm: str | None = None     # human fills: confirm | reject | modify(+reason) -> DAgger label


class DecisionPolicy(Protocol):
    """Policy interface: read the day's aggregate state + candidate universe, produce a decision."""
    def decide(self, state: MarketState, universe: CandidateUniverse) -> DecisionPackage: ...
