# alpha/state/market.py
from __future__ import annotations

from datetime import date as Date, datetime as DateTime

from pydantic import BaseModel, ConfigDict, Field

from alpha.features.theme_breadth_types import ThemeBreadthReading


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
    # ── growth-doctrine breadth family (P0.4) — default None ("not computed"), consumed by a future
    #    (P2) three-clock regime reader; None until the caller threads a BreadthReading in ──
    pct_above_200dma: float | None = None         # fraction of the market above its 200-day SMA
    net_new_highs: int | None = None              # 52-week new highs minus new lows
    advances: int | None = None                   # symbols up on the day
    declines: int | None = None                   # symbols down on the day
    # ── growth-doctrine theme/sector breadth (P5b) — default None ("not computed"), consumed by the
    #    theme-lifecycle clock (`alpha/regime/theme_clock.py`). None until the caller threads a
    #    ThemeBreadthReading in; default None keeps every current MarketState byte-identical ──
    theme_breadth: ThemeBreadthReading | None = None
    as_of: DateTime                              # snapshot timestamp (lookahead audit)
