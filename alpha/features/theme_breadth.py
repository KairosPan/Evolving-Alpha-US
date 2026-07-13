"""Theme/sector breadth (P5b): per-group breadth signals + §1.2 theme-lifecycle raw inputs.

The per-group analog of P0.4's market-wide breadth family (`alpha.features.breadth`). Partition the
cross-section by a `SectorMap` and measure breadth over each group's bar subset — the DATA the growth
doctrine's §1.2 赛道时钟 (theme-lifecycle clock: `emerging → institutional → public_laggard → exhaustion`)
will read. **This module builds the feed + signals; it does NOT classify lifecycle states** — that is
the deferred theme-clock consumer step, exactly as P2's market clock consumed P0.4's breadth family.

Everything is computable from EXISTING daily bars (no new source) and is trailing-only: every window
closes with date <= `day`; the caller assembles each frame via `GuardedSource(AsOfGuard(day))`, so this
module never fetches. Prices are RAW/unadjusted — the RS legs inherit `trend_template`'s split caveat.

Spec: docs/superpowers/specs/2026-07-13-p5b-theme-breadth-design.md; doctrine §1.2 / §3.4 `laggard_timer`.
"""
from __future__ import annotations

from datetime import date as Date
from statistics import mean, median

import pandas as pd
from pydantic import BaseModel, ConfigDict

from alpha.data.sector_map import SectorMap
from alpha.features.breadth import market_breadth, pct_above_ma
from alpha.features.trend_template import (
    RS_LONG_WINDOW, RS_SHORT_WINDOW, rs_percentiles, rs_raw_score,
)

# 文献值待校准: the trend lookback is a calibration surface, pinned to the repo's ~1-month convention
# (trend_template.SMA200_RISING_LOOKBACK). The theme clock reviews weekly (doctrine §1.4 clock_cadence),
# but the raw trend inputs are exposed self-contained per day so a consumer need not persist a series.
DEFAULT_TREND_LOOKBACK = 21
DEFAULT_MIN_MEMBERS = 3     # < this many members in the cross-section => the group read is UNDETERMINED


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
    # ── §1.2 theme-lifecycle raw inputs (additive; the deferred clock differences/classifies) ──
    rs_dispersion: float | None = None       # leader_rs_mean - laggard_rs_mean (within-group RS gap)
    laggard_rs_mean: float | None = None     # the group's bottom-half RS level (the laggard_timer input)
    breadth_trend: float | None = None       # pct_above_200dma(day) - pct_above_200dma(day-lookback)
    rs_trend: float | None = None            # rs_mean(day) - rs_mean(day-lookback)


class ThemeBreadthReading(BaseModel):
    """Per-day bundle: one `GroupBreadthReading` per sector/theme group (incl. the 'unmapped' bucket).
    Additive — a future regime reader threads this into `MarketState` default-None (byte-identical when
    absent), the P0.4->P2 breadth-family precedent. See the spec's deferred theme-clock handoff."""
    model_config = ConfigDict(frozen=True)
    day: Date
    groups: dict[str, GroupBreadthReading]


def _asof_trading_days(bars_by_symbol: dict[str, pd.DataFrame], day: Date) -> list[Date]:
    """Sorted distinct bar dates <= `day` across the whole cross-section — a PIT trading-calendar proxy
    (uses only dates on/before `day`, never a >day fetch)."""
    seen: set[Date] = set()
    for bars in bars_by_symbol.values():
        if bars is None or getattr(bars, "empty", True) or "date" not in bars.columns:
            continue
        for d in pd.to_datetime(bars["date"]).dt.date:
            if d <= day:
                seen.add(d)
    return sorted(seen)


def _partition(bars_by_symbol: dict[str, pd.DataFrame],
               sector_map: SectorMap) -> dict[str, dict[str, pd.DataFrame]]:
    """Group the cross-section by `sector_map.sector_of` (unknown symbols land in the 'unmapped' bucket)."""
    groups: dict[str, dict[str, pd.DataFrame]] = {}
    for sym, bars in bars_by_symbol.items():
        groups.setdefault(sector_map.sector_of(sym), {})[sym] = bars
    return groups


def _member_pcts(members: dict[str, pd.DataFrame], pct: dict[str, float]) -> list[float]:
    """The members' cross-sectional RS percentiles (members with no percentile dropped)."""
    return [pct[s] for s in members if s in pct]


def _dispersion(member_pcts: list[float]) -> tuple[float | None, float | None]:
    """(rs_dispersion, laggard_rs_mean): split the group's ranked members at their RS median into a
    bottom (laggard) and top (leader) half; dispersion = leader_mean - laggard_mean. The doctrine's
    laggard_timer (§3.4): a WIDE gap = leaders dominate (early); a COMPRESSING gap = laggards catching
    up (the public_laggard tell). None when fewer than two members carry a percentile."""
    ranked = sorted(member_pcts)
    n = len(ranked)
    if n < 2:
        return None, None
    half = n // 2                                    # odd middle member dropped (belongs to neither half)
    laggard_mean = mean(ranked[:half])
    leader_mean = mean(ranked[n - half:])
    return leader_mean - laggard_mean, laggard_mean


def theme_breadth(bars_by_symbol: dict[str, pd.DataFrame], sector_map: SectorMap, day: Date, *,
                  ma_window: int = 200, high_low_window: int = 252,
                  rs_short_window: int = RS_SHORT_WINDOW, rs_long_window: int = RS_LONG_WINDOW,
                  trend_lookback: int = DEFAULT_TREND_LOOKBACK,
                  min_members: int = DEFAULT_MIN_MEMBERS) -> ThemeBreadthReading:
    """Assemble per-group breadth + §1.2 lifecycle raw inputs for `day` over the whole cross-section.

    RS is ranked ONCE over the entire tape (a group's RS is its members' standing relative to everything,
    not within-group), at `day` and — for `rs_trend` — again at the earlier as-of. Trailing-only: a
    future-dated row is ignored (belt-and-suspenders on the caller's AsOfGuard).
    """
    trading_days = _asof_trading_days(bars_by_symbol, day)
    earlier = trading_days[-1 - trend_lookback] if len(trading_days) > trend_lookback else None

    raw_now = {s: rs_raw_score(b, day, short_window=rs_short_window, long_window=rs_long_window)
               for s, b in bars_by_symbol.items()}
    pct_now = rs_percentiles(raw_now)
    if earlier is not None:
        raw_prev = {s: rs_raw_score(b, earlier, short_window=rs_short_window, long_window=rs_long_window)
                    for s, b in bars_by_symbol.items()}
        pct_prev = rs_percentiles(raw_prev)
    else:
        pct_prev = {}

    groups: dict[str, GroupBreadthReading] = {}
    for name, members in _partition(bars_by_symbol, sector_map).items():
        count = len(members)
        if count < min_members:                      # UNDETERMINED: too few names to read a group breadth
            groups[name] = GroupBreadthReading(group=name, member_count=count, determined=False)
            continue

        b = market_breadth(members, day, ma_window=ma_window, high_low_window=high_low_window)
        now_pcts = _member_pcts(members, pct_now)
        rs_mean = mean(now_pcts) if now_pcts else None
        rs_dispersion, laggard_rs_mean = _dispersion(now_pcts)

        breadth_trend = None
        if earlier is not None:
            now_above = pct_above_ma(members, day, ma_window)
            prev_above = pct_above_ma(members, earlier, ma_window)
            if now_above is not None and prev_above is not None:
                breadth_trend = now_above - prev_above

        rs_trend = None
        if earlier is not None:
            prev_pcts = _member_pcts(members, pct_prev)
            if rs_mean is not None and prev_pcts:
                rs_trend = rs_mean - mean(prev_pcts)

        groups[name] = GroupBreadthReading(
            group=name, member_count=count, determined=True,
            pct_above_200dma=b.pct_above_200dma, net_new_highs=b.net_new_highs,
            advances=b.advances, declines=b.declines,
            rs_mean=rs_mean, rs_median=(median(now_pcts) if now_pcts else None),
            rs_dispersion=rs_dispersion, laggard_rs_mean=laggard_rs_mean,
            breadth_trend=breadth_trend, rs_trend=rs_trend)

    return ThemeBreadthReading(day=day, groups=groups)
