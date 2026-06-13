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
    # float / short_interest / halts -> None until US-3 enrichment
