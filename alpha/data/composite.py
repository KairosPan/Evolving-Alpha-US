# alpha/data/composite.py
#
# CompositeSource — a MarketDataSource that routes EACH capability to a (possibly different) backend, so
# P5's enrichment feeds (earnings / short-interest / EDGAR offerings / float / theme-breadth) can each be
# a per-capability backend composed with the base bars/snapshot vendor, one feed at a time, without
# touching the base source or the firewall. Spec: docs/superpowers/specs/2026-07-13-p4-composite-source-design.md.
from __future__ import annotations

from collections.abc import Mapping
from datetime import date as Date

import pandas as pd

from alpha.data.earnings import EarningsCalendarEntry, EarningsFact
from alpha.data.float_shares import FloatFact
from alpha.data.offerings import OfferingEvent
from alpha.data.short_interest import ShortInterest
from alpha.data.source import MarketDataSource

# The routable units. `corp_actions` groups the three coupled corp methods so a corp-backend override
# moves corporate_actions + _known + _available together: corp_actions_available() reports whether THAT
# backend can check reverse-split/dilution (the P3 tri-state fix), so routing the probe apart from the
# corp data it describes would let the probe lie. `earnings` (P5a) groups its three coupled methods for
# the same reason (earnings_available describes whichever backend serves the earnings data). `short_interest`
# + `offerings` (P5b) each group their `*_known` + `*_available` methods for the same reason; `float` (P5b)
# groups float_known + float_available. P5 feeds add their own groups when their methods land.
_CAPABILITIES = frozenset({"calendar", "bars", "snapshot", "corp_actions", "earnings",
                           "short_interest", "offerings", "float"})


class CompositeSource:
    """A MarketDataSource routing each capability group to a (possibly different) backend.

    Constructed from a `base` source + optional per-capability `overrides` (capability-group name ->
    backend). An un-overridden capability falls through to `base`; if `base` itself does not implement
    it, base's method raises NotImplementedError — the pure-swap contract, preserved by delegation
    (e.g. CompositeSource(AlpacaSource()) raises NotImplementedError on daily_snapshot, like bare Alpaca).

    Every delegated call is a pure pass-through: it returns the backend's RAW frame unchanged (no
    guarding, no adjustment). A CompositeSource is therefore a RAW source — wrap it in
    GuardedSource+AsOfGuard exactly like any other; the firewall composes on the outside.
    """

    def __init__(self, base: MarketDataSource,
                 overrides: Mapping[str, MarketDataSource] | None = None) -> None:
        overrides = dict(overrides or {})
        unknown = set(overrides) - _CAPABILITIES
        if unknown:
            raise ValueError(f"unknown composite capability {sorted(unknown)} "
                             f"(expected one of {sorted(_CAPABILITIES)})")
        self._base = base
        self._overrides = overrides

    def _route(self, capability: str) -> MarketDataSource:
        return self._overrides.get(capability, self._base)

    def trading_calendar(self) -> list[Date]:
        return self._route("calendar").trading_calendar()

    def daily_bars(self, symbol: str, start: Date, end: Date) -> pd.DataFrame:
        return self._route("bars").daily_bars(symbol, start, end)

    def daily_snapshot(self, day: Date) -> pd.DataFrame:
        return self._route("snapshot").daily_snapshot(day)

    def corporate_actions(self, start: Date, end: Date) -> pd.DataFrame:
        return self._route("corp_actions").corporate_actions(start, end)

    def corporate_actions_known(self, as_of: Date) -> pd.DataFrame:
        return self._route("corp_actions").corporate_actions_known(as_of)

    def corp_actions_available(self) -> bool:
        # Delegates to the corp-actions backend directly (no getattr default-True fallback like
        # GuardedSource — composite backends are full MarketDataSources by contract, no legacy inners).
        # So a composite whose corp backend reports MISSING reports False even if base would report True.
        return self._route("corp_actions").corp_actions_available()

    # ── earnings group (P5a) — routes together to the earnings backend; falls to base (and base's
    #    NotImplementedError) when un-overridden, exactly like the corp path ──
    def earnings_known(self, symbol: str, as_of: Date) -> list[EarningsFact]:
        return self._route("earnings").earnings_known(symbol, as_of)

    def earnings_calendar(self, as_of: Date) -> list[EarningsCalendarEntry]:
        return self._route("earnings").earnings_calendar(as_of)

    def earnings_available(self) -> bool:
        return self._route("earnings").earnings_available()

    # ── short_interest group (P5b) — routes together to the short-interest backend; falls to base (and
    #    base's NotImplementedError) when un-overridden, exactly like the earnings path ──
    def short_interest_known(self, symbol: str, as_of: Date) -> list[ShortInterest]:
        return self._route("short_interest").short_interest_known(symbol, as_of)

    def short_interest_available(self) -> bool:
        return self._route("short_interest").short_interest_available()

    # ── offerings group (P5b) — the lifecycle typed-events feed ──
    def offering_events_known(self, symbol: str, as_of: Date) -> list[OfferingEvent]:
        return self._route("offerings").offering_events_known(symbol, as_of)

    def offerings_available(self) -> bool:
        return self._route("offerings").offerings_available()

    # ── float group (P5b) — free-float feed (float_known + float_available route together) ──
    def float_known(self, symbol: str, as_of: Date) -> list[FloatFact]:
        return self._route("float").float_known(symbol, as_of)

    def float_available(self) -> bool:
        return self._route("float").float_available()
