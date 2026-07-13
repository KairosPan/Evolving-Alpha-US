from __future__ import annotations

from datetime import date as Date

import pandas as pd
from pydantic import BaseModel, ConfigDict

from alpha.universe.universe import CandidateUniverse


def counts(universe: CandidateUniverse) -> tuple[int, int, int]:
    """(gainer_count, gap_up_count, loser_count) by snapshot status."""
    return (len(universe.by_status("gainer")), len(universe.by_status("gap_up")),
            len(universe.by_status("loser")))


def failed_breakout_count(universe: CandidateUniverse) -> int:
    """Gapped up (gap_pct>0) but closed red (close < prev_close) — the 炸板 analog."""
    n = 0
    for s in universe.all():
        if (s.gap_pct is not None and s.gap_pct > 0 and s.close is not None
                and s.prev_close is not None and s.close < s.prev_close):
            n += 1
    return n


def gap_and_go_count(universe: CandidateUniverse) -> int:
    """Gainers that gapped up and held (status gainer with gap_pct>0) — the 弱转强 daily proxy."""
    return sum(1 for s in universe.by_status("gainer") if s.gap_pct is not None and s.gap_pct > 0)


def follow_through_rate(universe: CandidateUniverse, prev_gainers: frozenset[str]) -> float | None:
    """Fraction of yesterday's gainers that are gainers again today (risk-on/off effect).
    None when there were no prior gainers (undefined)."""
    if not prev_gainers:
        return None
    today = {s.symbol for s in universe.by_status("gainer")}
    return len(today & prev_gainers) / len(prev_gainers)


# ── Growth-doctrine breadth family (P0.4) ──────────────────────────────────────────────────────────
# Market-wide breadth measured over a cross-section of {symbol: trailing daily bars}. Every window is
# trailing-only (closes with date <= `day`); the caller assembles each frame from
# GuardedSource.daily_bars(sym, start, day). These are the "赚钱效应/亏钱效应" analogs the research report
# names (docs/research/2026-07-11-us-growth-unknown-unknowns.html §"情绪周期 → 可计算的 regime 度量"):
# % above 200DMA, net new 52-week highs, advance/decline. Prices are RAW/unadjusted (firewall).


class BreadthReading(BaseModel):
    """Point-in-time market-breadth bundle (frozen). Each field is None when no symbol in the
    cross-section had enough history to contribute (never a fabricated 0)."""
    model_config = ConfigDict(frozen=True)
    pct_above_200dma: float | None = None    # fraction of the cross-section trading above its 200-day SMA
    net_new_highs: int | None = None         # (# at a 52-week high) - (# at a 52-week low)
    advances: int | None = None              # symbols up on the day (last close > prior close)
    declines: int | None = None              # symbols down on the day


def _asof_closes(bars: pd.DataFrame | None, day: Date) -> list[float]:
    """Ascending numeric closes with date <= `day` (trailing-only). [] on missing data."""
    if bars is None or getattr(bars, "empty", True) or "date" not in bars.columns:
        return []
    df = bars.copy()
    df["date"] = pd.to_datetime(df["date"]).dt.date
    df = df[df["date"] <= day].sort_values("date")
    return [float(c) for c in pd.to_numeric(df["close"], errors="coerce").dropna()]


def _has_current_bar(bars: pd.DataFrame | None, day: Date) -> bool:
    """True iff the latest bar dated <= `day` is dated EXACTLY `day`. Used by the day-labeled
    advance/decline measure to drop a symbol with no current-day bar, so a lagging close (dated
    < day) is never mislabeled as an up/down move ON `day`."""
    if bars is None or getattr(bars, "empty", True) or "date" not in bars.columns:
        return False
    asof = [d for d in pd.to_datetime(bars["date"]).dt.date if d <= day]
    return bool(asof) and max(asof) == day


def pct_above_ma(bars_by_symbol: dict[str, pd.DataFrame], day: Date, window: int = 200) -> float | None:
    """Fraction of the cross-section whose latest close (<= day) is above its own `window`-day SMA.
    Only symbols with >= `window` closes count toward the denominator; None if none qualify.

    As-of-latest≤day measure (not day-labeled): a symbol with a lagging latest bar still counts on its
    most recent close, since "trades above its own 200-day SMA" is a structural read that a one-day
    stale close does not invalidate (unlike advance_decline, which is guarded to the current day)."""
    above = eligible = 0
    for bars in bars_by_symbol.values():
        closes = _asof_closes(bars, day)
        if len(closes) < window:
            continue
        eligible += 1
        if closes[-1] > sum(closes[-window:]) / window:
            above += 1
    return above / eligible if eligible else None


def net_new_highs(bars_by_symbol: dict[str, pd.DataFrame], day: Date, window: int = 252) -> int | None:
    """Net new 52-week highs = (# whose latest close is the trailing-`window` max) - (# at the min).
    Only symbols with >= `window` closes count; None if none qualify.

    As-of-latest≤day measure (not day-labeled), same rationale as pct_above_ma: a one-day-stale latest
    close is still a valid read of "at its trailing-window extreme"; only advance_decline is guarded to
    the current day."""
    highs = lows = eligible = 0
    for bars in bars_by_symbol.values():
        closes = _asof_closes(bars, day)
        if len(closes) < window:
            continue
        eligible += 1
        win = closes[-window:]
        if closes[-1] >= max(win):
            highs += 1
        elif closes[-1] <= min(win):
            lows += 1
    return (highs - lows) if eligible else None


def advance_decline(bars_by_symbol: dict[str, pd.DataFrame], day: Date) -> tuple[int, int]:
    """(advances, declines) ON `day`: for each symbol, up if its last close (<= day) exceeds the prior
    close, down if below. Needs only two trailing closes, so it is defined for far more of the
    cross-section than the 200/252-day breadth measures.

    Day-membership guard: this is the one day-LABELED measure, so a symbol whose latest bar is not
    dated == `day` (capture lag / halt / stale feed) contributes to NEITHER advances nor declines —
    a stale yesterday-vs-day-before move must not be counted as today's advance/decline."""
    adv = dec = 0
    for bars in bars_by_symbol.values():
        closes = _asof_closes(bars, day)
        if len(closes) < 2 or not _has_current_bar(bars, day):
            continue
        if closes[-1] > closes[-2]:
            adv += 1
        elif closes[-1] < closes[-2]:
            dec += 1
    return adv, dec


def market_breadth(bars_by_symbol: dict[str, pd.DataFrame], day: Date, *,
                   ma_window: int = 200, high_low_window: int = 252) -> BreadthReading:
    """Assemble the breadth family for `day` into one `BreadthReading` a regime reader can consume."""
    adv, dec = advance_decline(bars_by_symbol, day)
    # advances/declines are real (possibly both 0, all-flat) only if some symbol has a current-day bar
    # with >= 2 closes; a cross-section of only stale symbols reports None, never a fabricated 0.
    have_ad = any(_has_current_bar(b, day) and len(_asof_closes(b, day)) >= 2
                  for b in bars_by_symbol.values())
    return BreadthReading(
        pct_above_200dma=pct_above_ma(bars_by_symbol, day, ma_window),
        net_new_highs=net_new_highs(bars_by_symbol, day, high_low_window),
        advances=adv if have_ad else None,
        declines=dec if have_ad else None,
    )
