"""Growth-doctrine perception: cross-sectional relative strength (RS) + the Minervini Trend Template.

Computable entirely from existing daily bars (no new data source). Every window here is trailing-only
(closes with date <= `day`); the caller fetches those bars through a GuardedSource(AsOfGuard(day)), so
this module never sees a >day price. Prices are RAW/unadjusted per the firewall contract — see the
split caveat on `rs_raw_score`.

Spec: docs/doctrine/2026-07-12-us-growth-doctrine-draft.md §4.1 `trend_template.rule`.
"""
from __future__ import annotations

from datetime import date as Date

import pandas as pd
from pydantic import BaseModel, ConfigDict

# The eight Minervini criteria, in doctrine order (§4.1). `passes` == all eight True.
TREND_TEMPLATE_CRITERIA = (
    "above_sma50",     # close > 50-day SMA
    "above_sma150",    # close > 150-day SMA
    "above_sma200",    # close > 200-day SMA
    "sma_stack",       # 50-day SMA > 150-day SMA > 200-day SMA
    "sma200_rising",   # 200-day SMA today > 200-day SMA ~1 month ago
    "above_52w_low",   # close >= +30% above the 52-week low
    "near_52w_high",   # close within 25% of the 52-week high (>= 0.75 * high)
    "rs_ge_70",        # cross-sectional RS percentile >= 70
)

# 文献值待校准: horizon/weight constants are the calibration surface, pinned to plausible literature
# defaults until the verdict harness tunes them.
RS_SHORT_WINDOW = 126     # ~6 trading months
RS_LONG_WINDOW = 252      # ~12 trading months (52 weeks)
SMA200_RISING_LOOKBACK = 21   # ~1 trading month
WEEK52_WINDOW = 252
RS_THRESHOLD = 70.0
LOW_52W_MARGIN = 1.30     # close must be >= 130% of the 52-week low
HIGH_52W_MARGIN = 0.75    # close must be >= 75% of the 52-week high (i.e. within 25%)


class TrendTemplateResult(BaseModel):
    """Per-symbol Trend Template evaluation (frozen). `passes` is True iff all eight criteria hold.
    A symbol with insufficient history has `insufficient_history=True`, every uncomputable criterion
    False, and therefore `passes=False` (never silently passing)."""
    model_config = ConfigDict(frozen=True)
    symbol: str
    passes: bool
    rs_percentile: float | None
    insufficient_history: bool
    criteria: dict[str, bool]


def _asof_closes(bars: pd.DataFrame | None, day: Date) -> list[float]:
    """Ascending list of numeric closes with date <= `day` (trailing-only). [] on missing data."""
    if bars is None or getattr(bars, "empty", True) or "date" not in bars.columns:
        return []
    df = bars.copy()
    df["date"] = pd.to_datetime(df["date"]).dt.date
    df = df[df["date"] <= day].sort_values("date")
    return [float(c) for c in pd.to_numeric(df["close"], errors="coerce").dropna()]


def _has_current_bar(bars: pd.DataFrame | None, day: Date) -> bool:
    """True iff the latest bar dated <= `day` is dated EXACTLY `day`. A symbol whose most recent bar
    predates `day` (capture lag, a halt, or a stale feed) has no usable current-day price: it fails
    the screen fail-closed and is dropped from the RS ranking pool so its stale close cannot
    contaminate the cross-sectional percentile. Mirrors the missing-current-day posture documented in
    alpha/universe/universe.py:64-68 (`_runner_up_days`)."""
    if bars is None or getattr(bars, "empty", True) or "date" not in bars.columns:
        return False
    asof = [d for d in pd.to_datetime(bars["date"]).dt.date if d <= day]
    return bool(asof) and max(asof) == day


def _sma(closes: list[float], n: int) -> float | None:
    """Mean of the last `n` closes, or None when fewer than `n` are available."""
    if len(closes) < n:
        return None
    return sum(closes[-n:]) / n


def rs_raw_score(bars: pd.DataFrame | None, day: Date, *,
                 short_window: int = RS_SHORT_WINDOW,
                 long_window: int = RS_LONG_WINDOW) -> float | None:
    """Raw relative-strength score = equal-weighted blend of the trailing 6-month and 12-month total
    returns from RAW closes. Cross-sectional ranking happens in `rs_percentiles`.

    文献值待校准: the {6mo, 12mo} horizon set and the equal 0.5/0.5 weights are a deliberately simple,
    momentum-window-agnostic placeholder for the canonical IBD RS Rating (which quarter-weights the
    trailing year, double-weighting the most recent quarter). Kept plain so the ranking is transparent
    and the weighting is the only thing the verdict harness has to calibrate.

    SPLIT CAVEAT (activation-blocker, honest scope): the returns are computed from RAW/unadjusted
    closes (firewall contract), so any stock split *inside* the trailing window corrupts the return by
    the split ratio. A reverse split fabricates a huge positive raw return -> RS ~= 100 (a fake leader);
    a forward split fabricates a crash -> RS ~= 0 (a fake laggard). Corp-action cross-checking to divide
    out the ratio is deferred (P5 feeds); until it lands, treat Trend Template screening across a split
    event as unreliable — do NOT activate this screen on a universe with recent splits without that
    adjustment.

    None when there is not enough trailing history to form the longer leg, OR the latest bar is stale
    (no current-day close) — either way the symbol is excluded from the ranking pool -> fails the Trend
    Template's RS criterion, never silently passing.
    """
    if not _has_current_bar(bars, day):
        return None
    closes = _asof_closes(bars, day)
    if len(closes) < long_window + 1:
        return None
    r_short = closes[-1] / closes[-(short_window + 1)] - 1.0
    r_long = closes[-1] / closes[-(long_window + 1)] - 1.0
    return 0.5 * r_short + 0.5 * r_long


def rs_percentiles(raw_scores: dict[str, float | None]) -> dict[str, float]:
    """Cross-sectional percentile rank in [0, 100] of each symbol's raw RS score.

    Symbols with a None raw score are dropped from the ranking pool (insufficient history) and get no
    percentile. Convention: percentile = 100 * (fraction of the pool with score <= x) — the same `<=`
    convention as `alpha.features.sentiment.normalize_sentiment`, so the strongest name scores 100 and
    RS >= 70 means the top ~30%.
    """
    pool = {s: v for s, v in raw_scores.items() if v is not None}
    n = len(pool)
    if n == 0:
        return {}
    vals = list(pool.values())
    return {s: 100.0 * sum(1 for v in vals if v <= x) / n for s, x in pool.items()}


def evaluate_trend_template(bars: pd.DataFrame | None, day: Date, rs_percentile: float | None, *,
                            symbol: str = "", rs_threshold: float = RS_THRESHOLD,
                            sma_rising_lookback: int = SMA200_RISING_LOOKBACK,
                            week52: int = WEEK52_WINDOW) -> TrendTemplateResult:
    """Evaluate the eight Minervini criteria for one symbol given its trailing bars and its
    (cross-sectionally computed) RS percentile.

    Insufficient history: any criterion whose window cannot be formed is False. A symbol with fewer
    than 200 closes cannot compute the 200-day SMA and so fails criteria 3/4/5 outright; fewer than
    252 closes fails the 52-week-window criteria. `insufficient_history` is flagged whenever the full
    Trend Template window (max of the 52-week and SMA200-rising needs) is unavailable.

    Fail-closed on a missing current-day bar: a symbol whose latest bar predates `day` (capture lag /
    halt / stale feed) has no usable current-day price, so every criterion is False and it fails —
    never evaluated on a stale close that would compare an out-of-date price to today's SMAs.
    """
    closes = _asof_closes(bars, day)
    if not _has_current_bar(bars, day):
        return TrendTemplateResult(
            symbol=symbol, passes=False, rs_percentile=rs_percentile,
            insufficient_history=len(closes) < max(week52, 200 + sma_rising_lookback),
            criteria={c: False for c in TREND_TEMPLATE_CRITERIA})
    close = closes[-1] if closes else None

    sma50 = _sma(closes, 50)
    sma150 = _sma(closes, 150)
    sma200 = _sma(closes, 200)
    # SMA200 ~1 month ago: the 200 closes ending `sma_rising_lookback` bars before today.
    sma200_prior = (sum(closes[-(200 + sma_rising_lookback):-sma_rising_lookback]) / 200
                    if len(closes) >= 200 + sma_rising_lookback else None)
    win = closes[-week52:] if len(closes) >= week52 else None
    low52 = min(win) if win else None
    high52 = max(win) if win else None

    def _gt(a: float | None, b: float | None) -> bool:
        return a is not None and b is not None and a > b

    criteria = {
        "above_sma50": _gt(close, sma50),
        "above_sma150": _gt(close, sma150),
        "above_sma200": _gt(close, sma200),
        "sma_stack": _gt(sma50, sma150) and _gt(sma150, sma200),
        "sma200_rising": _gt(sma200, sma200_prior),
        "above_52w_low": close is not None and low52 is not None and close >= LOW_52W_MARGIN * low52,
        "near_52w_high": close is not None and high52 is not None and close >= HIGH_52W_MARGIN * high52,
        "rs_ge_70": rs_percentile is not None and rs_percentile >= rs_threshold,
    }
    insufficient = len(closes) < max(week52, 200 + sma_rising_lookback)
    return TrendTemplateResult(
        symbol=symbol, passes=all(criteria.values()), rs_percentile=rs_percentile,
        insufficient_history=insufficient, criteria=criteria)


def trend_template_screen(bars_by_symbol: dict[str, pd.DataFrame], day: Date, *,
                          short_window: int = RS_SHORT_WINDOW, long_window: int = RS_LONG_WINDOW,
                          rs_threshold: float = RS_THRESHOLD,
                          sma_rising_lookback: int = SMA200_RISING_LOOKBACK,
                          week52: int = WEEK52_WINDOW) -> dict[str, TrendTemplateResult]:
    """Batch Trend Template over a cross-section of symbols -> {symbol: TrendTemplateResult}.

    Two passes: (1) raw RS score per symbol; (2) cross-sectional percentile; (3) per-symbol eight-way
    evaluation. RS is inherently cross-sectional, so it can only be evaluated here, not one symbol at
    a time. Trailing-only: each `bars` frame is expected to end on/before `day`.
    """
    raw = {sym: rs_raw_score(bars, day, short_window=short_window, long_window=long_window)
           for sym, bars in bars_by_symbol.items()}
    pct = rs_percentiles(raw)
    return {sym: evaluate_trend_template(bars, day, pct.get(sym), symbol=sym,
                                         rs_threshold=rs_threshold,
                                         sma_rising_lookback=sma_rising_lookback, week52=week52)
            for sym, bars in bars_by_symbol.items()}
