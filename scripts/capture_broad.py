"""One-off: build a BROAD, liquidity-ranked PIT snapshot for the HCH-vs-Hexpert verdict.

The 68-name hand-picked basket made the breadth-based regime read meaningless (always washout/
distribution -> near-total L4 veto). The original CN experiment used the whole limit-up pool (a
natural full-market cross-section). This rebuilds that: batch-fetch the shortable US-equity set via
Alpaca's MULTI-symbol bars endpoint (fast), rank by median daily dollar-volume, keep the top-N most
liquid, then populate the PITStore through the SAME `capture_window` logic (faithful snapshot / corp
actions) via a thin pre-fetched-bars adapter.

  python scripts/capture_broad.py <preroll_start> <window_end> <pit_root> <top_n>
  e.g. python scripts/capture_broad.py 2025-11-17 2026-03-30 verdict_pit_broad 800
"""
from __future__ import annotations

import os
import re
import sys
import json
import time
import urllib.request
from datetime import date as Date
from pathlib import Path

import pandas as pd

from alpha.data.alpaca import AlpacaSource, _normalize_bars
from alpha.data.capture import capture_window
from alpha.data.pit_store import PITStore

_MAJOR = {"NASDAQ", "NYSE", "ARCA", "AMEX", "BATS"}


def list_shortable_symbols() -> list[str]:
    key, sec = os.environ["APCA_API_KEY_ID"], os.environ["APCA_API_SECRET_KEY"]
    url = "https://paper-api.alpaca.markets/v2/assets?status=active&asset_class=us_equity"
    req = urllib.request.Request(url, headers={"APCA-API-KEY-ID": key, "APCA-API-SECRET-KEY": sec,
                                               "accept": "application/json"})
    with urllib.request.urlopen(req, timeout=60) as r:
        assets = json.loads(r.read())
    out = [a["symbol"] for a in assets
           if a.get("tradable") and a.get("shortable") and a.get("exchange") in _MAJOR
           and re.fullmatch(r"[A-Z]{1,5}", a["symbol"])]
    return sorted(set(out))


def batch_fetch_bars(symbols: list[str], start: Date, end: Date, chunk: int = 100) -> dict:
    from alpaca.data.historical import StockHistoricalDataClient
    from alpaca.data.requests import StockBarsRequest
    from alpaca.data.timeframe import TimeFrame
    from alpaca.data.enums import Adjustment, DataFeed
    client = StockHistoricalDataClient(os.environ["APCA_API_KEY_ID"], os.environ["APCA_API_SECRET_KEY"])
    feed = os.environ.get("ALPHA_DATA_FEED", "iex").strip().lower() or "iex"
    bars_by_symbol: dict[str, pd.DataFrame] = {}
    for i in range(0, len(symbols), chunk):
        part = symbols[i:i + chunk]
        req = StockBarsRequest(symbol_or_symbols=part, timeframe=TimeFrame.Day,
                               start=pd.Timestamp(start), end=pd.Timestamp(end),
                               adjustment=Adjustment.RAW, feed=DataFeed(feed))
        for attempt in range(4):
            try:
                df = client.get_stock_bars(req).df
                break
            except Exception as e:  # noqa: BLE001 — transient; back off
                if attempt == 3:
                    print(f"  chunk {i}-{i+len(part)} FAILED: {type(e).__name__}: {str(e)[:80]}")
                    df = None
                    break
                time.sleep(1.5 * (2 ** attempt))
        if df is None or df.empty:
            continue
        df = df.reset_index()  # columns: symbol, timestamp, open, high, low, close, volume, ...
        for sym, g in df.groupby("symbol"):
            bars_by_symbol[str(sym)] = _normalize_bars(g)
        print(f"  fetched {i+len(part)}/{len(symbols)} symbols  (have bars for {len(bars_by_symbol)})")
    return bars_by_symbol


def rank_by_dollar_volume(bars_by_symbol: dict, top_n: int, min_dollar_vol: float = 3e6) -> list[str]:
    rows = []
    for sym, b in bars_by_symbol.items():
        if b is None or b.empty:
            continue
        dv = (b["close"] * b["volume"]).median()
        if pd.notna(dv) and dv >= min_dollar_vol:
            rows.append((sym, float(dv)))
    rows.sort(key=lambda x: -x[1])
    return [s for s, _ in rows[:top_n]]


class _BatchedSource:
    """Faithful Source over pre-fetched bars + a real AlpacaSource for calendar / corp actions."""

    def __init__(self, bars_by_symbol: dict, delegate: AlpacaSource) -> None:
        self._bars = bars_by_symbol
        self._delegate = delegate
        self._cal = delegate.trading_calendar()

    def trading_calendar(self):
        return self._cal

    def daily_bars(self, symbol: str, start: Date, end: Date) -> pd.DataFrame:
        b = self._bars.get(symbol)
        if b is None or b.empty:
            return pd.DataFrame(columns=["date", "open", "high", "low", "close", "volume"])
        m = (b["date"] >= start) & (b["date"] <= end)
        return b[m].reset_index(drop=True)

    def corporate_actions_known(self, as_of: Date) -> pd.DataFrame:
        return self._delegate.corporate_actions_known(as_of)


def main() -> None:
    start, end, root, top_n = (Date.fromisoformat(sys.argv[1]), Date.fromisoformat(sys.argv[2]),
                               Path(sys.argv[3]), int(sys.argv[4]))
    syms = list_shortable_symbols()
    print(f"shortable plain-ticker universe: {len(syms)} symbols; fetching bars {start}..{end} ...")
    t0 = time.time()
    bars = batch_fetch_bars(syms, start, end)
    print(f"fetched bars for {len(bars)} symbols in {time.time()-t0:.0f}s")
    kept = rank_by_dollar_volume(bars, top_n)
    print(f"kept top {len(kept)} by median dollar-volume (>= $3M/day)")
    src = _BatchedSource({k: bars[k] for k in kept}, AlpacaSource())
    capture_window(src, PITStore(root), start, end, kept)
    Path(root / "_universe.txt").write_text(" ".join(kept), encoding="utf-8")
    print(f"captured {len(kept)} symbols {start}..{end} -> {root}")


if __name__ == "__main__":
    main()
