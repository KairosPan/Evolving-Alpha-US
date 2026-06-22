# alpha/data/capture.py
from __future__ import annotations

from datetime import date as Date

import pandas as pd

from alpha.data.calendar import prev_trading_day
from alpha.data.pit_store import PITStore


_CORP_COLS = ["symbol", "announce_date", "ex_date", "kind", "ratio"]


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
