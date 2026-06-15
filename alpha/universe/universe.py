# alpha/universe/universe.py
from __future__ import annotations

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


# --- append to alpha/universe/universe.py ---
from datetime import date as Date

import pandas as pd

from alpha.data.calendar import trading_days_between
from alpha.features.runner import consecutive_up_days

RUNNER_LOOKBACK = 30   # max consecutive-up-days probed (a run of n up-days needs n+1 closes)


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
                   gap_pct: float = 5.0, rvol_window: int = 20) -> CandidateUniverse:
    """Screen the daily cross-section for gainers / gap-ups / losers; attach trailing-only RVOL."""
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
        )
    return CandidateUniverse(stocks)
