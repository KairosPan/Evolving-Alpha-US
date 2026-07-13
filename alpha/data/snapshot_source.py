from __future__ import annotations

from datetime import date as Date

import pandas as pd

from alpha.data.corp_actions import known_corporate_actions
from alpha.data.earnings import (
    EarningsCalendarEntry,
    EarningsFact,
    calendar_from_frame,
    facts_from_frame,
    known_calendar,
    known_earnings,
)
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

    def corp_actions_available(self) -> bool:
        """False iff corp_actions.parquet is absent — the guard could not check reverse-split/dilution.
        True for a present (even empty) artifact. Distinguishes MISSING from checked-and-clean, which
        both otherwise collapse to an empty frame -> False flags (see alpha/data/corp_actions.py)."""
        return self._store.has_corp_actions()

    # ── earnings (P5a) — served from PITStore fixtures, PIT-filtered on filing_date / known_asof ──
    def earnings_known(self, symbol: str, as_of: Date) -> list[EarningsFact]:
        facts = facts_from_frame(self._store.get_earnings())
        return [f for f in known_earnings(facts, as_of) if f.symbol == symbol]

    def earnings_calendar(self, as_of: Date) -> list[EarningsCalendarEntry]:
        return known_calendar(calendar_from_frame(self._store.get_earnings_calendar()), as_of)

    def earnings_available(self) -> bool:
        """False iff the earnings artifact is absent (MISSING) — mirrors corp_actions_available."""
        return self._store.has_earnings()
