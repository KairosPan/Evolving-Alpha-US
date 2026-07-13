"""Theme/sector breadth DATA MODELS (P5b) — the frozen pydantic bundle, split out from the compute.

Kept dependency-light on purpose (pydantic + datetime only, NO pandas / breadth / universe imports) so
`alpha/state/market.py` can carry a `ThemeBreadthReading | None` field without a circular import
(`market -> theme_breadth -> features.breadth -> universe -> features.runner -> state.market`). The
compute (`alpha/features/theme_breadth.py::theme_breadth`) imports and re-exports these, so callers may
import either module; the theme-lifecycle clock (`alpha/regime/theme_clock.py`) reads them.
"""
from __future__ import annotations

from datetime import date as Date

from pydantic import BaseModel, ConfigDict


class GroupBreadthReading(BaseModel):
    """Point-in-time breadth for one sector/theme group (frozen). A group with fewer than `min_members`
    symbols in the cross-section is UNDETERMINED: `determined=False` and every signal None (never a
    fabricated 0). Within a determined group, each signal is independently None when no member qualifies
    (no member with enough history, no earlier as-of, <2 ranked members)."""
    model_config = ConfigDict(frozen=True)
    group: str
    member_count: int
    determined: bool
    # ── per-group breadth snapshot (levels) — same undetermined semantics as market_breadth ──
    pct_above_200dma: float | None = None    # fraction of the group above its own MA (as-of-latest<=day)
    net_new_highs: int | None = None         # group 52-week new highs minus new lows
    advances: int | None = None              # group members up ON `day`
    declines: int | None = None              # group members down ON `day`
    # ── per-group relative strength: cross-sectional (whole-tape) RS percentile, aggregated ──
    rs_mean: float | None = None
    rs_median: float | None = None
    # ── §1.2 theme-lifecycle raw inputs (additive; the theme clock differences/classifies) ──
    rs_dispersion: float | None = None       # leader_rs_mean - laggard_rs_mean (within-group RS gap)
    laggard_rs_mean: float | None = None     # the group's bottom-half RS level (the laggard_timer input)
    breadth_trend: float | None = None       # pct_above_200dma(day) - pct_above_200dma(day-lookback)
    rs_trend: float | None = None            # rs_mean(day) - rs_mean(day-lookback)


class ThemeBreadthReading(BaseModel):
    """Per-day bundle: one `GroupBreadthReading` per sector/theme group (incl. the 'unmapped' bucket).
    Additive — threaded into `MarketState` default-None (byte-identical when absent), the P0.4->P2
    breadth-family precedent. Consumed by `alpha/regime/theme_clock.py::GrowthThemeClock`."""
    model_config = ConfigDict(frozen=True)
    day: Date
    groups: dict[str, GroupBreadthReading]
