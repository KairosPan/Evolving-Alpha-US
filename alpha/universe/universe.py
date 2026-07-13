# alpha/universe/universe.py
from __future__ import annotations

import os

from alpha.universe.stock import StockSnapshot, StockStatus


class CandidateUniverse:
    """Daily candidate set indexed by symbol."""

    def __init__(self, stocks: dict[str, StockSnapshot]) -> None:
        self._stocks = dict(stocks)

    @classmethod
    def from_stocks(cls, stocks: list[StockSnapshot]) -> "CandidateUniverse":
        index: dict[str, StockSnapshot] = {}
        for s in stocks:
            if s.symbol in index:
                raise ValueError(f"duplicate symbol: {s.symbol}")
            index[s.symbol] = s
        return cls(index)

    def get(self, symbol: str) -> StockSnapshot | None:
        return self._stocks.get(symbol)

    def all(self) -> list[StockSnapshot]:
        return list(self._stocks.values())

    def by_status(self, status: StockStatus) -> list[StockSnapshot]:
        return [s for s in self._stocks.values() if s.status == status]

    def __len__(self) -> int:
        return len(self._stocks)

    def __bool__(self) -> bool:
        return True


# --- trailing-bar helpers + build_universe ---
from datetime import date as Date

import pandas as pd

from alpha.features.runner import consecutive_up_days

RUNNER_LOOKBACK = 30   # max consecutive-up-days probed (a run of n up-days needs n+1 closes)
TREND_TEMPLATE_LOOKBACK = 300   # trailing trading days fetched per symbol for the Trend Template screen
                                # (comfortably covers the RS 12-month + SMA200-rising 1-month windows)

UNIVERSE_SCREEN_ENV = "ALPHA_UNIVERSE_SCREEN"
UNIVERSE_SCREENS = ("gainer", "trend_template")


def resolve_universe_screen(screen: str | None = None) -> str:
    """The single universe-screen resolution, shared by `build_universe` and the verdict/decisions
    producers so the provenance a script prints matches the screen the build actually runs.

    Order: explicit `screen` arg, then env `ALPHA_UNIVERSE_SCREEN`, then the "gainer" default. A
    set-but-EMPTY env behaves like unset (the `or DEFAULT` idiom, mirroring
    `alpha/harness/loader.py::active_pack_name`) — an empty string never crashes the screen dispatch.
    An unknown value raises rather than silently falling back to the wrong screen."""
    resolved = screen or os.environ.get(UNIVERSE_SCREEN_ENV) or "gainer"
    if resolved not in UNIVERSE_SCREENS:
        raise ValueError(f"unknown universe screen: {resolved!r} (want 'gainer' or 'trend_template')")
    return resolved


def _trailing_bars(source, symbol: str, day: Date, lookback: int):
    """One trailing daily-bar fetch ending at `day` (guard-safe: end == day <= as_of), wide enough to
    feed BOTH the RVOL window and the runner-depth count from a single round-trip per symbol."""
    cal = [d for d in source.trading_calendar() if d <= day]
    if not cal:
        return None
    start = cal[-(lookback + 1)] if len(cal) > lookback else cal[0]
    return source.daily_bars(symbol, start, day)


def _runner_up_days(bars, day: Date, max_lookback: int = RUNNER_LOOKBACK) -> int | None:
    """Trailing consecutive up-closes ANCHORED at `day` (multi-day-runner tier).

    Returns None when `bars` has no row dated `day` — the snapshot store and the bar store are
    independent, so a symbol can be screened from the day's snapshot yet lack a current-day bar
    (capture lag). We report tier 'unknown' rather than a stale-positive count ending one day early,
    matching the missing-current-day posture of `_trailing_rvol`. Otherwise delegates the count to
    alpha.features.runner.consecutive_up_days (capped at max_lookback)."""
    if bars is None or getattr(bars, "empty", True) or "date" not in bars.columns:
        return None
    if day not in set(pd.to_datetime(bars["date"]).dt.date):
        return None
    return consecutive_up_days(bars, day, max_lookback=max_lookback)


def _trailing_rvol(source, symbol: str, day: Date, window: int, *, bars=None) -> float | None:
    """today_volume / mean(volume over the `window` trading days strictly BEFORE `day`).
    Optionally reuse a pre-fetched (wider) bar frame to avoid a second round-trip per symbol;
    the internal date masks slice the RVOL window out of any wider frame."""
    cal = source.trading_calendar()
    prior = [d for d in cal if d < day]
    if len(prior) < window:
        return None
    win = sorted(prior)[-window:]
    if bars is None:
        bars = source.daily_bars(symbol, win[0], day)    # end=day is legal (<=as_of)
    if bars is None or bars.empty:
        return None
    today = bars[bars["date"] == day]
    trailing = bars[(bars["date"] >= win[0]) & (bars["date"] < day)]   # strictly trailing
    if today.empty or trailing.empty:
        return None
    avg = float(trailing["volume"].mean())
    if avg <= 0:
        return None
    return float(today.iloc[0]["volume"]) / avg


def build_universe(source, day: Date, *, gainer_pct: float = 10.0,
                   gap_pct: float = 5.0, rvol_window: int = 20,
                   screen: str | None = None) -> CandidateUniverse:
    """Screen the daily cross-section for gainers / gap-ups / losers; attach trailing-only RVOL.

    Switchable screen (P0.4): `screen` selects the entry — "gainer" (the momo default, this body) or
    "trend_template" (the growth-doctrine Minervini filter). Resolution (explicit arg / env
    `ALPHA_UNIVERSE_SCREEN` / "gainer" default, empty env == unset) is shared with the producers via
    `resolve_universe_screen`. Default is byte-identical to the pre-P0.4 behavior; an unknown value
    raises rather than silently falling back to the wrong screen."""
    resolved = resolve_universe_screen(screen)
    if resolved == "trend_template":
        return build_trend_template_universe(source, day)
    snap = source.daily_snapshot(day)
    stocks: dict[str, StockSnapshot] = {}
    if snap is None or snap.empty:
        return CandidateUniverse(stocks)
    for rec in snap.to_dict("records"):
        symbol = str(rec["symbol"])
        close, prev = rec.get("close"), rec.get("prev_close")
        open_ = rec.get("open")
        pct = ((close - prev) / prev * 100.0) if (close is not None and prev) else None
        gap = ((open_ - prev) / prev * 100.0) if (open_ is not None and prev) else None
        if pct is not None and pct >= gainer_pct:
            status: StockStatus = "gainer"
        elif gap is not None and gap >= gap_pct:
            status = "gap_up"
        elif pct is not None and pct <= -gainer_pct:
            status = "loser"
        else:
            continue
        if status == "loser":                      # down on the day -> not a runner; cud 0, RVOL only
            rvol = _trailing_rvol(source, symbol, day, rvol_window)
            cud: int | None = 0
        else:                                      # gainer / gap_up: ONE fetch feeds RVOL + runner depth
            bars = _trailing_bars(source, symbol, day, max(rvol_window, RUNNER_LOOKBACK))
            rvol = _trailing_rvol(source, symbol, day, rvol_window, bars=bars)
            cud = _runner_up_days(bars, day)
        stocks[symbol] = StockSnapshot(
            symbol=symbol, name=str(rec.get("name", "")), status=status,
            close=(float(close) if close is not None else None),
            prev_close=(float(prev) if prev is not None else None),
            pct_change=pct, gap_pct=gap,
            volume=(float(rec["volume"]) if rec.get("volume") is not None else None),
            rvol=rvol, consecutive_up_days=cud,
            short_interest=_opt_float(rec.get("short_interest")),
            days_to_cover=_opt_float(rec.get("days_to_cover")),
            free_float=_opt_float(rec.get("free_float")),
            options_flow=_opt_float(rec.get("options_flow")),
            social_sentiment=_opt_float(rec.get("social_sentiment")),
        )
    return CandidateUniverse(stocks)


def tape_breadth(snap, *, gainer_pct: float = 10.0, gap_pct: float = 5.0) -> tuple[int, int]:
    """Market-wide breadth `(gainers, losers)` over the WHOLE daily snapshot under the same ±gainer_pct /
    gap screen `build_universe` uses — the market TAPE, independent of whatever screen selects candidates.

    This decouples the market-clock / panic breadth from the candidate universe: under the "gainer" screen
    it equals `counts(build_universe(...))` gainers/losers exactly (byte-identical, mirroring the gainer /
    gap_up / loser if-elif order), and under "trend_template" (which classifies every name "trend_template",
    zeroing the gainer/loser counts) the clock + panic still read the real tape instead of starving. `snap`
    is a daily-snapshot DataFrame (or None -> (0, 0))."""
    g = lo = 0
    for rec in (snap.to_dict("records") if snap is not None and not getattr(snap, "empty", True) else []):
        close, prev, open_ = rec.get("close"), rec.get("prev_close"), rec.get("open")
        pct = ((close - prev) / prev * 100.0) if (close is not None and prev) else None
        gap = ((open_ - prev) / prev * 100.0) if (open_ is not None and prev) else None
        if pct is not None and pct >= gainer_pct:
            g += 1
        elif gap is not None and gap >= gap_pct:
            continue                              # gap_up: neither gainer nor loser (mirror build_universe)
        elif pct is not None and pct <= -gainer_pct:
            lo += 1
    return g, lo


def build_trend_template_universe(source, day: Date, *,
                                  lookback: int = TREND_TEMPLATE_LOOKBACK) -> CandidateUniverse:
    """Growth-doctrine universe (P0.4): the day's cross-section filtered to names that pass ALL EIGHT
    Minervini Trend Template criteria (docs/doctrine §4.1 `trend_template.rule`). Each kept name carries
    status "trend_template" and its cross-sectional `rs_percentile`.

    RS is cross-sectional, so this is a two-pass screen: fetch each snapshot symbol's trailing bars
    (one guard-safe end==day fetch per symbol), rank RS across the whole snapshot, then keep the
    passers. Symbols without enough history fail explicitly inside `trend_template_screen` (never
    silently pass). FIREWALL: bars are fetched with end==day (<=as_of); pass a GuardedSource."""
    from alpha.features.trend_template import trend_template_screen

    snap = source.daily_snapshot(day)
    stocks: dict[str, StockSnapshot] = {}
    if snap is None or snap.empty:
        return CandidateUniverse(stocks)
    records = {str(rec["symbol"]): rec for rec in snap.to_dict("records")}
    bars_by_symbol = {sym: _trailing_bars(source, sym, day, lookback) for sym in records}
    for symbol, res in trend_template_screen(bars_by_symbol, day).items():
        if not res.passes:
            continue
        rec = records[symbol]
        close, prev, open_ = rec.get("close"), rec.get("prev_close"), rec.get("open")
        pct = ((close - prev) / prev * 100.0) if (close is not None and prev) else None
        gap = ((open_ - prev) / prev * 100.0) if (open_ is not None and prev) else None
        stocks[symbol] = StockSnapshot(
            symbol=symbol, name=str(rec.get("name", "")), status="trend_template",
            close=(float(close) if close is not None else None),
            prev_close=(float(prev) if prev is not None else None),
            pct_change=pct, gap_pct=gap,
            volume=(float(rec["volume"]) if rec.get("volume") is not None else None),
            rs_percentile=res.rs_percentile,
            short_interest=_opt_float(rec.get("short_interest")),
            days_to_cover=_opt_float(rec.get("days_to_cover")),
            free_float=_opt_float(rec.get("free_float")),
            options_flow=_opt_float(rec.get("options_flow")),
            social_sentiment=_opt_float(rec.get("social_sentiment")),
        )
    return CandidateUniverse(stocks)


def _opt_float(value) -> float | None:
    """None-and-NaN-safe float. FINRA short-interest coverage is partial, so a present column can carry
    NaN for uncovered symbols — treat that as missing (None), never a fabricated 0/nan."""
    return None if value is None or pd.isna(value) else float(value)
