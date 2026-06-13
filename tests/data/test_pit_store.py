from __future__ import annotations
from datetime import date
import pandas as pd
from alpha.data.pit_store import PITStore


def test_snapshot_roundtrip(tmp_path):
    store = PITStore(tmp_path)
    df = pd.DataFrame({"symbol": ["RUN"], "close": [17.0]})
    assert store.has_snapshot(date(2026, 6, 12)) is False
    store.put_snapshot(date(2026, 6, 12), df)
    assert store.has_snapshot(date(2026, 6, 12)) is True
    out = store.get_snapshot(date(2026, 6, 12))
    pd.testing.assert_frame_equal(out, df)


def test_bars_roundtrip(tmp_path):
    store = PITStore(tmp_path)
    df = pd.DataFrame({"date": [date(2026, 6, 12)], "open": [16.0], "high": [18.0],
                       "low": [15.0], "close": [17.0], "volume": [5_000_000]})
    store.put_bars("RUN", df)
    out = store.get_bars("RUN")
    assert out is not None and out.iloc[0]["close"] == 17.0


def test_calendar_and_corp_roundtrip(tmp_path):
    store = PITStore(tmp_path)
    store.put_calendar([date(2026, 6, 11), date(2026, 6, 12)])
    assert store.get_calendar() == [date(2026, 6, 11), date(2026, 6, 12)]
    corp = pd.DataFrame({"symbol": ["RUN"], "announce_date": [date(2026, 6, 9)],
                         "ex_date": [date(2026, 6, 20)], "kind": ["reverse_split"], "ratio": [0.1]})
    store.put_corp_actions(corp)
    got = store.get_corp_actions()
    assert list(got["kind"]) == ["reverse_split"]
    assert got.iloc[0]["announce_date"] == date(2026, 6, 9)


def test_missing_returns_none(tmp_path):
    store = PITStore(tmp_path)
    assert store.get_snapshot(date(2026, 6, 12)) is None
    assert store.get_bars("NOPE") is None
    assert store.get_calendar() is None
    assert store.get_corp_actions() is None
