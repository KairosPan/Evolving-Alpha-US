from __future__ import annotations

from datetime import date as Date
from typing import Protocol

import pandas as pd

from alpha.data.corp_actions import known_corporate_actions
from alpha.data.earnings import (
    EarningsCalendarEntry,
    EarningsFact,
    known_calendar,
    known_earnings,
)
from alpha.data.firewall import AsOfGuard
from alpha.data.offerings import OfferingEvent, known_offering_events
from alpha.data.short_interest import ShortInterest, known_short_interest

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
    def corp_actions_available(self) -> bool: ...   # False = corp artifact MISSING (guard cannot check)
    # ── earnings (P5a; OPTIONAL capability — a source without it raises NotImplementedError, like
    #    daily_snapshot on AlpacaSource). filing_date/known_asof are the PIT keys (alpha/data/earnings.py).
    def earnings_known(self, symbol: str, as_of: Date) -> list[EarningsFact]: ...   # filing_date <= as_of
    def earnings_calendar(self, as_of: Date) -> list[EarningsCalendarEntry]: ...    # known_asof  <= as_of
    def earnings_available(self) -> bool: ...        # False = earnings artifact MISSING (fail-closed)
    # ── short interest (P5b; OPTIONAL) — publication_date is the PIT key (alpha/data/short_interest.py).
    def short_interest_known(self, symbol: str, as_of: Date) -> list[ShortInterest]: ...  # publication_date <= as_of
    def short_interest_available(self) -> bool: ...  # False = short-interest artifact MISSING (fail-closed)
    # ── offerings lifecycle (P5b; OPTIONAL) — each event's own process_date is the PIT key
    #    (alpha/data/offerings.py). is_dilution_overhang folds these; corp has_dilution_filing = fail-closed default.
    def offering_events_known(self, symbol: str, as_of: Date) -> list[OfferingEvent]: ...  # process_date <= as_of
    def offerings_available(self) -> bool: ...       # False = offerings artifact MISSING (fail-closed)


class FakeSource:
    """In-memory MarketDataSource for offline tests."""

    def __init__(self, *, calendar: list[Date],
                 bars: dict[str, pd.DataFrame],
                 snapshots: dict[Date, pd.DataFrame],
                 corp_actions: pd.DataFrame | None = None,
                 corp_actions_available: bool = True,
                 earnings: list[EarningsFact] | None = None,
                 earnings_calendar: list[EarningsCalendarEntry] | None = None,
                 earnings_available: bool | None = None,
                 short_interest: list[ShortInterest] | None = None,
                 short_interest_available: bool | None = None,
                 offering_events: list[OfferingEvent] | None = None,
                 offerings_available: bool | None = None) -> None:
        self._calendar = list(calendar)
        self._bars = {k: v.copy() for k, v in bars.items()}
        self._snapshots = {k: v.copy() for k, v in snapshots.items()}
        self._corp = (corp_actions.copy() if corp_actions is not None
                      else pd.DataFrame(columns=_EMPTY_CORP))
        # In-memory sources are always checkable; the flag lets a test simulate a MISSING corp artifact
        # (the file-backed SnapshotSource derives this from PITStore.has_corp_actions).
        self._corp_available = corp_actions_available
        # Earnings default OFF (absent artifact): no earnings passed -> earnings_available() False, so a
        # bare FakeSource stays byte-identical to pre-P5a. Pass earnings=[...] (even empty) to mark present,
        # or set earnings_available explicitly to simulate present-but-empty vs MISSING.
        self._earnings = list(earnings) if earnings is not None else []
        self._earnings_cal = list(earnings_calendar) if earnings_calendar is not None else []
        self._earnings_available = (earnings_available if earnings_available is not None
                                    else earnings is not None or earnings_calendar is not None)
        # Short interest + offerings (P5b): same default-OFF/MISSING posture as earnings — pass the list
        # (even empty) to mark the artifact present, else *_available() is False (byte-identical when off).
        self._short_interest = list(short_interest) if short_interest is not None else []
        self._short_interest_available = (short_interest_available if short_interest_available is not None
                                          else short_interest is not None)
        self._offering_events = list(offering_events) if offering_events is not None else []
        self._offerings_available = (offerings_available if offerings_available is not None
                                     else offering_events is not None)

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

    def corp_actions_available(self) -> bool:
        return self._corp_available

    def earnings_known(self, symbol: str, as_of: Date) -> list[EarningsFact]:
        return [f for f in known_earnings(self._earnings, as_of) if f.symbol == symbol]

    def earnings_calendar(self, as_of: Date) -> list[EarningsCalendarEntry]:
        return known_calendar(self._earnings_cal, as_of)

    def earnings_available(self) -> bool:
        return self._earnings_available

    def short_interest_known(self, symbol: str, as_of: Date) -> list[ShortInterest]:
        return [r for r in known_short_interest(self._short_interest, as_of) if r.symbol == symbol]

    def short_interest_available(self) -> bool:
        return self._short_interest_available

    def offering_events_known(self, symbol: str, as_of: Date) -> list[OfferingEvent]:
        return [e for e in known_offering_events(self._offering_events, as_of) if e.symbol == symbol]

    def offerings_available(self) -> bool:
        return self._offerings_available


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

    def corp_actions_available(self) -> bool:
        # Date-independent (the parquet is the whole PIT snapshot), so no AsOfGuard.check. An inner that
        # predates the capability -> treated as available (byte-identical; same posture as optional collect).
        probe = getattr(self._inner, "corp_actions_available", None)
        return probe() if callable(probe) else True

    # ── earnings (P5a) — guard the two dated fetches on as_of, mirror corporate_actions_known ──
    def earnings_known(self, symbol: str, as_of: Date) -> list[EarningsFact]:
        self._guard.check(as_of)
        return self._inner.earnings_known(symbol, as_of)

    def earnings_calendar(self, as_of: Date) -> list[EarningsCalendarEntry]:
        self._guard.check(as_of)
        return self._inner.earnings_calendar(as_of)

    def earnings_available(self) -> bool:
        # Date-independent, like corp_actions_available. Unlike corp (default-True for legacy inners
        # predating the capability), earnings is brand new with no legacy inners, so an inner lacking it
        # is genuinely MISSING -> default FALSE (fail-closed: a future guard treats absence as "cannot
        # check", never as "no upcoming earnings").
        probe = getattr(self._inner, "earnings_available", None)
        return probe() if callable(probe) else False

    # ── short interest + offerings (P5b) — guard the dated fetches on as_of; availability passthrough,
    #    fail-closed default-FALSE when the inner lacks the capability (both are brand-new, like earnings) ──
    def short_interest_known(self, symbol: str, as_of: Date) -> list[ShortInterest]:
        self._guard.check(as_of)
        return self._inner.short_interest_known(symbol, as_of)

    def short_interest_available(self) -> bool:
        probe = getattr(self._inner, "short_interest_available", None)
        return probe() if callable(probe) else False

    def offering_events_known(self, symbol: str, as_of: Date) -> list[OfferingEvent]:
        self._guard.check(as_of)
        return self._inner.offering_events_known(symbol, as_of)

    def offerings_available(self) -> bool:
        probe = getattr(self._inner, "offerings_available", None)
        return probe() if callable(probe) else False
