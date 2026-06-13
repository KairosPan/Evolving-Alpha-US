# tests/test_cache.py
from datetime import date
import pandas as pd
from youzi.data.cache import PITStore


def test_put_then_get_roundtrip(tmp_path):
    store = PITStore(root=tmp_path)
    df = pd.DataFrame({"code": ["000001"], "boards": [7]})
    store.put("zt", date(2024, 6, 27), df)
    got = store.get("zt", date(2024, 6, 27))
    assert got is not None
    assert list(got["code"]) == ["000001"]
    assert int(got["boards"].iloc[0]) == 7


def test_get_missing_returns_none(tmp_path):
    store = PITStore(root=tmp_path)
    assert store.get("zt", date(2024, 6, 27)) is None


def test_has(tmp_path):
    store = PITStore(root=tmp_path)
    assert not store.has("zt", date(2024, 6, 27))
    store.put("zt", date(2024, 6, 27), pd.DataFrame({"code": ["1"]}))
    assert store.has("zt", date(2024, 6, 27))


def test_ohlcv_roundtrip_and_missing(tmp_path):
    store = PITStore(root=tmp_path)
    assert store.get_ohlcv("000001") is None and not store.has_ohlcv("000001")
    df = pd.DataFrame([(date(2026, 6, 2), 10.0, 11, 9, 10.5, 100)],
                      columns=["date", "open", "high", "low", "close", "volume"])
    store.put_ohlcv("000001", df)
    assert store.has_ohlcv("000001")
    got = store.get_ohlcv("000001")
    assert len(got) == 1 and float(got["close"].iloc[0]) == 10.5


def test_calendar_roundtrip_and_missing(tmp_path):
    store = PITStore(root=tmp_path)
    assert store.get_calendar() is None
    days = [date(2026, 6, 1), date(2026, 6, 2), date(2026, 6, 3)]
    store.put_calendar(days)
    assert store.get_calendar() == days        # date 对象,顺序保持


def test_atomic_writes_leave_no_tmp(tmp_path):
    # 原子写:三类写都经 temp+os.replace,完成后不留 .tmp(硬 kill 只留 .tmp 被 has() 忽略,不留截断文件)
    store = PITStore(root=tmp_path)
    store.put("zt", date(2026, 6, 2), pd.DataFrame({"code": ["A"]}))
    store.put_ohlcv("A", pd.DataFrame([(date(2026, 6, 2), 1.0, 1, 1, 1, 1)],
                                      columns=["date", "open", "high", "low", "close", "volume"]))
    store.put_calendar([date(2026, 6, 2)])
    assert list(tmp_path.rglob("*.tmp")) == []
