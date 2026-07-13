# alpha/data/capture.py
from __future__ import annotations

from datetime import date as Date

import pandas as pd

from alpha.data.calendar import prev_trading_day
from alpha.data.earnings import calendar_to_frame, facts_to_frame
from alpha.data.float_shares import float_to_frame
from alpha.data.integrity_check import write_checksums
from alpha.data.offerings import events_to_frame
from alpha.data.pit_store import PITStore
from alpha.data.short_interest import si_to_frame


_CORP_COLS = ["symbol", "announce_date", "ex_date", "kind", "ratio"]


def _available(source, name: str) -> bool:
    """Optional-capability probe (fail-closed default False), mirroring GuardedSource's getattr posture:
    a source predating the capability (e.g. AlpacaSource lacks `float_available` entirely) is treated as
    absent, never an AttributeError."""
    probe = getattr(source, name, None)
    return bool(probe()) if callable(probe) else False


def _capture_feeds(source, store: PITStore, symbols: list[str], end: Date) -> None:
    """P5 consume-path activation: persist the OPTIONAL feeds KNOWABLE BY the window end, scoped to the
    captured symbols, so a captured window replays earnings / short-interest / offerings / float offline
    (spec 2026-07-13-p5-consume-path-activations). Each feed is gated on the source's availability — a
    source with none of them writes nothing -> byte-identical capture. SnapshotSource re-filters each read
    on the PIT key (known_* <= query as_of), so capturing at `end` (the whole knowable log) is per-day
    PIT-correct on replay — the exact posture of the corp-actions block above.

    theme-breadth is NOT persisted here: it is DERIVED at state-build time from the (already-captured)
    daily snapshot cross-section + the static sector map (no ingestion feed / no PITStore artifact)."""
    if _available(source, "earnings_available"):
        facts = [f for sym in symbols for f in source.earnings_known(sym, end)]
        store.put_earnings(facts_to_frame(facts))
        cal = [e for e in source.earnings_calendar(end) if e.symbol in symbols]
        store.put_earnings_calendar(calendar_to_frame(cal))
    if _available(source, "short_interest_available"):
        records = [r for sym in symbols for r in source.short_interest_known(sym, end)]
        store.put_short_interest(si_to_frame(records))
    if _available(source, "offerings_available"):
        events = [e for sym in symbols for e in source.offering_events_known(sym, end)]
        store.put_offering_events(events_to_frame(events))
    if _available(source, "float_available"):
        floats = [f for sym in symbols for f in source.float_known(sym, end)]
        store.put_float(float_to_frame(floats))


def capture_window(source, store: PITStore, start: Date, end: Date, symbols: list[str]) -> None:
    """Idempotent prefetch: bars per symbol + a derived daily snapshot cross-section + calendar + the
    announce-keyed corporate actions for the captured symbols.

    The snapshot for each day is derived from the captured raw bars (close/open/volume) plus the
    prior trading day's close, so the offline universe builder has a cross-section to screen. Corp
    actions are persisted too — without them the OFFLINE firewall (reverse-split / dilution veto) is
    silently blind on a captured window.
    """
    cal = source.trading_calendar()
    store.put_calendar(cal)
    bars_by_symbol: dict[str, pd.DataFrame] = {}
    for sym in symbols:
        bars = source.daily_bars(sym, start, end)
        if bars is not None and not bars.empty:
            store.put_bars(sym, bars)
            bars_by_symbol[sym] = bars
    from alpha.data.calendar import trading_days_between
    for day in trading_days_between(cal, start, end):
        prev = prev_trading_day(cal, day)
        rows = []
        for sym, bars in bars_by_symbol.items():
            today = bars[bars["date"] == day]
            if today.empty:
                continue
            pc = bars[bars["date"] == prev]["close"]
            rows.append({"symbol": sym, "name": sym,
                         "open": float(today.iloc[0]["open"]), "high": float(today.iloc[0]["high"]),
                         "low": float(today.iloc[0]["low"]), "close": float(today.iloc[0]["close"]),
                         "volume": float(today.iloc[0]["volume"]),
                         "prev_close": (float(pc.iloc[0]) if not pc.empty else None)})
        if rows:
            store.put_snapshot(day, pd.DataFrame(rows))
    # announce-keyed corp actions as of the window end (includes pending future-ex splits), scoped to
    # the captured symbols so the offline store stays consistent with the bars/snapshots it holds.
    corp = source.corporate_actions_known(end)
    if corp is None:
        corp = pd.DataFrame(columns=_CORP_COLS)
    elif not corp.empty:
        corp = corp[corp["symbol"].isin(symbols)].reset_index(drop=True)
    store.put_corp_actions(corp)
    _capture_feeds(source, store, symbols, end)   # P5: earnings/short-interest/offerings/float (default-off)
    write_checksums(store.root)   # D6: manifest last, so it covers everything the window just wrote
