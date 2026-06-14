# alpha/state/market.py
from __future__ import annotations

from datetime import date as Date, datetime as DateTime

from pydantic import BaseModel, ConfigDict, Field


class RunnerRung(BaseModel):
    """One rung of the runner echelon (连板梯队 analog): a tier, its count, representative tickers."""
    model_config = ConfigDict(frozen=True)
    tier: int = Field(ge=1)               # consecutive-up-days bucket (or move-magnitude tier)
    count: int = Field(ge=0)
    representatives: list[str] = Field(default_factory=list)


class MarketState(BaseModel):
    """Point-in-time daily market state at close (US-0 minimal set; features enrich in US-1)."""
    model_config = ConfigDict(frozen=True)
    date: Date
    gainer_count: int = Field(ge=0)
    gap_up_count: int = Field(ge=0)
    loser_count: int = Field(ge=0)
    failed_breakout_count: int = Field(ge=0)     # gap-up that closed red
    max_runner_tier: int = Field(ge=0)
    echelon: list[RunnerRung]                    # runner echelon (tier descending)
    breadth_raw: float                           # raw composite breadth
    sentiment_norm: float | None = Field(default=None, ge=0.0, le=1.0)  # regime-relative; None if insufficient
    # ── L1 perception features (US-1e) ──
    sentiment_raw: float = 0.0                    # raw composite (normalized into sentiment_norm)
    follow_through_rate: float | None = None      # fraction of prior-day gainers still gainers today
    gap_and_go_count: int = 0                     # gainers that gapped up and held
    as_of: DateTime                              # snapshot timestamp (lookahead audit)
