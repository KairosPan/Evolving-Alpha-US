# alpha/data/alpaca.py
from __future__ import annotations

import os
from datetime import date as Date

import pandas as pd

_BARS_COLS = ["date", "open", "high", "low", "close", "volume"]
_SNAP_COLS = ["symbol", "name", "open", "high", "low", "close", "volume", "prev_close"]


def _normalize_bars(df: pd.DataFrame) -> pd.DataFrame:
    if df is None or df.empty:
        return pd.DataFrame(columns=_BARS_COLS)
    out = df.copy()
    if "date" not in out.columns:                    # rename one source column, never two -> "date"
        for src in ("timestamp", "t"):
            if src in out.columns:
                out = out.rename(columns={src: "date"})
                break
    out["date"] = pd.to_datetime(out["date"]).dt.date
    for c in ("open", "high", "low", "close", "volume"):
        out[c] = pd.to_numeric(out[c], errors="coerce")
    return out[_BARS_COLS].reset_index(drop=True)


def _normalize_snapshot(df: pd.DataFrame) -> pd.DataFrame:
    if df is None or df.empty:
        return pd.DataFrame(columns=_SNAP_COLS)
    out = df.copy()
    out["symbol"] = out["symbol"].astype(str)
    if "name" not in out.columns:
        out["name"] = ""
    for c in ("open", "high", "low", "close", "volume", "prev_close"):
        out[c] = pd.to_numeric(out[c], errors="coerce")
    return out[_SNAP_COLS].reset_index(drop=True)


class AlpacaSource:
    """Real Alpaca adapter (smoke-only; requires the `live` extra + APCA_API_KEY_ID/SECRET env)."""

    def __init__(self) -> None:
        key = os.environ.get("APCA_API_KEY_ID")
        secret = os.environ.get("APCA_API_SECRET_KEY")
        if not key or not secret:
            raise RuntimeError("missing APCA_API_KEY_ID / APCA_API_SECRET_KEY")
        from alpaca.data.historical import StockHistoricalDataClient  # lazy import
        self._client = StockHistoricalDataClient(key, secret)

    def trading_calendar(self) -> list[Date]:
        import pandas_market_calendars as mcal  # lazy import
        sched = mcal.get_calendar("XNYS").schedule(start_date="2016-01-01",
                                                   end_date=pd.Timestamp.today().date().isoformat())
        return [d.date() for d in sched.index]

    def daily_bars(self, symbol: str, start: Date, end: Date) -> pd.DataFrame:
        from alpaca.data.requests import StockBarsRequest
        from alpaca.data.timeframe import TimeFrame
        from alpaca.data.enums import Adjustment
        req = StockBarsRequest(symbol_or_symbols=symbol, timeframe=TimeFrame.Day,
                               start=pd.Timestamp(start), end=pd.Timestamp(end),
                               adjustment=Adjustment.RAW)
        df = self._client.get_stock_bars(req).df
        if df is None or df.empty:
            return pd.DataFrame(columns=_BARS_COLS)
        return _normalize_bars(df.reset_index())

    def daily_snapshot(self, day: Date) -> pd.DataFrame:
        # Smoke-only: a full-market gainer cross-section needs a broad symbol list / snapshots API.
        # Built by capture_window for the configured symbol set; not exercised in unit tests.
        raise NotImplementedError("use capture_window to build daily snapshots from bars")

    def corporate_actions(self, start: Date, end: Date) -> pd.DataFrame:
        from alpaca.data.requests import CorporateActionsRequest
        req = CorporateActionsRequest(start=start, end=end)
        df = self._client.get_corporate_actions(req).df
        cols = ["symbol", "announce_date", "ex_date", "kind", "ratio"]
        if df is None or df.empty:
            return pd.DataFrame(columns=cols)
        return df  # field mapping refined during smoke against real payloads
