from __future__ import annotations
from datetime import date
import pandas as pd
import pytest
from alpha.data.pit_store import PITStore
from alpha.data.snapshot_source import SnapshotSource, SnapshotMissingError


def _seed(tmp_path):
    store = PITStore(tmp_path)
    store.put_calendar([date(2026, 6, 11), date(2026, 6, 12)])
    store.put_snapshot(date(2026, 6, 12), pd.DataFrame({
        "symbol": ["RUN"], "name": ["Runner Inc"], "open": [16.0], "high": [18.0],
        "low": [15.0], "close": [17.0], "volume": [5_000_000], "prev_close": [14.0]}))
    # RAW bars: a low-priced runner pre reverse-split (would look ~$170 if future-adjusted 1:10)
    store.put_bars("RUN", pd.DataFrame({
        "date": [date(2026, 6, 11), date(2026, 6, 12)],
        "open": [12.5, 16.0], "high": [15.0, 18.0], "low": [12.0, 15.0],
        "close": [14.0, 17.0], "volume": [3_000_000, 5_000_000]}))
    return SnapshotSource(store)


def test_snapshot_present(tmp_path):
    src = _seed(tmp_path)
    snap = src.daily_snapshot(date(2026, 6, 12))
    assert snap.iloc[0]["symbol"] == "RUN"


def test_missing_snapshot_raises(tmp_path):
    src = _seed(tmp_path)
    with pytest.raises(SnapshotMissingError):
        src.daily_snapshot(date(2026, 6, 11))   # not captured


def test_missing_bars_returns_empty(tmp_path):
    src = _seed(tmp_path)
    out = src.daily_bars("NOPE", date(2026, 6, 11), date(2026, 6, 12))
    assert out.empty and list(out.columns) == ["date", "open", "high", "low", "close", "volume"]


def test_bars_are_raw_not_future_adjusted(tmp_path):
    """Firewall surface: stored prices are RAW; a $14 close stays $14, not future-split-rebased."""
    src = _seed(tmp_path)
    bars = src.daily_bars("RUN", date(2026, 6, 11), date(2026, 6, 11))
    assert bars.iloc[0]["close"] == 14.0     # raw, NOT 140.0
