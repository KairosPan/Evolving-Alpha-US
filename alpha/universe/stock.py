# alpha/universe/stock.py
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict

StockStatus = Literal["gainer", "gap_up", "loser", "runner"]


class StockSnapshot(BaseModel):
    """Per-symbol daily PIT snapshot (frozen). Missing fields stay None (never fabricated)."""
    model_config = ConfigDict(frozen=True)
    symbol: str
    name: str
    status: StockStatus
    close: float | None = None
    prev_close: float | None = None
    pct_change: float | None = None        # daily % change
    gap_pct: float | None = None           # (open - prev_close) / prev_close
    volume: float | None = None
    rvol: float | None = None              # trailing-only relative volume
    consecutive_up_days: int | None = None
    short_interest: float | None = None    # FINRA short interest as % of float (0-100); US-3c
    days_to_cover: float | None = None      # short shares / avg daily volume; US-3c
    free_float: float | None = None         # tradeable float (millions of shares); US-3d
    options_flow: float | None = None       # net near-the-money call-flow score (gamma fuel); US-3f
    social_sentiment: float | None = None   # social-sentiment score; US-3f
    # consecutive_up_days populated by build_universe (US-3a); short_interest/days_to_cover (US-3c);
    # free_float (US-3d); options_flow/social_sentiment (US-3f); intraday halts -> None until a tick feed
