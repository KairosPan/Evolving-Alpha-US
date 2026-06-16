from __future__ import annotations

from datetime import date as Date
from typing import Protocol

import pandas as pd

from alpha.data.corp_actions import known_corporate_actions
from alpha.data.firewall import AsOfGuard

_EMPTY_BARS = ["date", "open", "high", "low", "close", "volume"]
_EMPTY_SNAP = ["symbol", "name", "open", "high", "low", "close", "volume", "prev_close",
               "short_interest", "days_to_cover", "free_float", "options_flow", "social_sentiment"]
_EMPTY_CORP = ["symbol", "announce_date", "ex_date", "kind", "ratio"]


class MarketDataSource(Protocol):
    """US market data contract (normalized English columns; RAW/unadjusted prices)."""
    def trading_calendar(self) -> list[Date]: ...
    def daily_bars(self, symbol: str, start: Date, end: Date) -> pd.DataFrame: ...
    def daily_snapshot(self, day: Date) -> pd.DataFrame: ...
    def corporate_actions(self, start: Date, end: Date) -> pd.DataFrame: ...
    def corporate_actions_known(self, as_of: Date) -> pd.DataFrame: ...


class FakeSource:
    """In-memory MarketDataSource for offline tests."""

    def __init__(self, *, calendar: list[Date],
                 bars: dict[str, pd.DataFrame],
                 snapshots: dict[Date, pd.DataFrame],
                 corp_actions: pd.DataFrame | None = None) -> None:
        self._calendar = list(calendar)
        self._bars = {k: v.copy() for k, v in bars.items()}
        self._snapshots = {k: v.copy() for k, v in snapshots.items()}
        self._corp = (corp_actions.copy() if corp_actions is not None
                      else pd.DataFrame(columns=_EMPTY_CORP))

    def trading_calendar(self) -> list[Date]:
        return list(self._calendar)

    def daily_bars(self, symbol: str, start: Date, end: Date) -> pd.DataFrame:
        df = self._bars.get(symbol)
        if df is None or df.empty:
            return pd.DataFrame(columns=_EMPTY_BARS)
        return df[(df["date"] >= start) & (df["date"] <= end)].reset_index(drop=True)

    def daily_snapshot(self, day: Date) -> pd.DataFrame:
        df = self._snapshots.get(day)
        return df.copy() if df is not None else pd.DataFrame(columns=_EMPTY_SNAP)

    def corporate_actions(self, start: Date, end: Date) -> pd.DataFrame:
        df = self._corp
        if df.empty:
            return pd.DataFrame(columns=_EMPTY_CORP)
        return df[(df["ex_date"] >= start) & (df["ex_date"] <= end)].reset_index(drop=True)

    def corporate_actions_known(self, as_of: Date) -> pd.DataFrame:
        """Corp actions ANNOUNCED by as_of (PIT-by-announcement), incl. future ex_dates (pending)."""
        return known_corporate_actions(self._corp, as_of)


class GuardedSource:
    """Wraps any MarketDataSource; routes every dated fetch through AsOfGuard."""

    def __init__(self, inner: MarketDataSource, guard: AsOfGuard) -> None:
        self._inner = inner
        self._guard = guard

    def trading_calendar(self) -> list[Date]:
        return self._inner.trading_calendar()

    def daily_bars(self, symbol: str, start: Date, end: Date) -> pd.DataFrame:
        self._guard.check(end)            # scoring at as_of>=t+N is legal; end>as_of is lookahead
        return self._inner.daily_bars(symbol, start, end)

    def daily_snapshot(self, day: Date) -> pd.DataFrame:
        self._guard.check(day)
        return self._inner.daily_snapshot(day)

    def corporate_actions(self, start: Date, end: Date) -> pd.DataFrame:
        self._guard.check(end)
        return self._inner.corporate_actions(start, end)

    def corporate_actions_known(self, as_of: Date) -> pd.DataFrame:
        self._guard.check(as_of)
        return self._inner.corporate_actions_known(as_of)
