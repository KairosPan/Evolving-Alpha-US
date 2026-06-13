# tests/data/test_alpaca_normalize.py
from __future__ import annotations
from datetime import date
import pandas as pd
from alpha.data.alpaca import _normalize_bars, _normalize_snapshot


def test_normalize_bars_columns_and_types():
    raw = pd.DataFrame({"timestamp": ["2026-06-12T00:00:00Z"], "open": ["16"], "high": ["18"],
                        "low": ["15"], "close": ["17"], "volume": ["5000000"]})
    out = _normalize_bars(raw)
    assert list(out.columns) == ["date", "open", "high", "low", "close", "volume"]
    assert out.iloc[0]["date"] == date(2026, 6, 12)
    assert out.iloc[0]["close"] == 17.0


def test_normalize_bars_empty():
    out = _normalize_bars(pd.DataFrame())
    assert out.empty and list(out.columns) == ["date", "open", "high", "low", "close", "volume"]


def test_normalize_snapshot_computes_nothing_extra():
    raw = pd.DataFrame({"symbol": ["RUN"], "name": ["Runner"], "open": ["16"], "high": ["18"],
                        "low": ["15"], "close": ["17"], "volume": ["5000000"], "prev_close": ["14"]})
    out = _normalize_snapshot(raw)
    assert list(out.columns) == ["symbol", "name", "open", "high", "low", "close", "volume", "prev_close"]
    assert out.iloc[0]["prev_close"] == 14.0
