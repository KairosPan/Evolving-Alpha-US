from __future__ import annotations

from datetime import date as Date

import pandas as pd

from alpha.data.corp_actions import known_corporate_actions
from alpha.data.pit_store import PITStore

_EMPTY_BARS = ["date", "open", "high", "low", "close", "volume"]


class SnapshotMissingError(RuntimeError):
    """A required snapshot is absent (incomplete capture) — fail loudly, never silent no-trade."""


class SnapshotSource:
    """Offline MarketDataSource backed by PITStore (zero network). Still wrapped by GuardedSource in eval."""

    def __init__(self, store: PITStore) -> None:
        self._store = store

    def trading_calendar(self) -> list[Date]:
        cal = self._store.get_calendar()
        if cal is None:
            raise SnapshotMissingError("snapshot missing calendar.parquet")
        return cal

    def daily_snapshot(self, day: Date) -> pd.DataFrame:
        df = self._store.get_snapshot(day)
        if df is None:
            raise SnapshotMissingError(f"snapshot missing for {day} (incomplete capture?)")
        return df

    def daily_bars(self, symbol: str, start: Date, end: Date) -> pd.DataFrame:
        df = self._store.get_bars(symbol)
        if df is None or df.empty:
            return pd.DataFrame(columns=_EMPTY_BARS)
        df = df.copy()
        df["date"] = pd.to_datetime(df["date"]).dt.date
        return df[(df["date"] >= start) & (df["date"] <= end)].reset_index(drop=True)

    def corporate_actions(self, start: Date, end: Date) -> pd.DataFrame:
        df = self._store.get_corp_actions()
        if df is None or df.empty:
            return pd.DataFrame(columns=["symbol", "announce_date", "ex_date", "kind", "ratio"])
        return df[(df["ex_date"] >= start) & (df["ex_date"] <= end)].reset_index(drop=True)

    def corporate_actions_known(self, as_of: Date) -> pd.DataFrame:
        return known_corporate_actions(self._store.get_corp_actions(), as_of)
