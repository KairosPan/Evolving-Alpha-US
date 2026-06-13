# tests/test_capture.py
from datetime import date

import pandas as pd

from youzi.data.cache import PITStore
from youzi.data.capture import capture_window
from tests.conftest import FakeSource


def _src():
    days = [date(2026, 6, 1), date(2026, 6, 2), date(2026, 6, 3)]
    frames = {("zt", d): pd.DataFrame({"code": ["A"], "name": ["甲"], "boards": [2]}) for d in days}
    ohlcv = {"A": pd.DataFrame([(date(2026, 6, 2), 10.0, 11, 9, 10.5, 100)],
                               columns=["date", "open", "high", "low", "close", "volume"])}
    return FakeSource(frames, days, ohlcv=ohlcv)


def test_capture_ohlcv_valueerror_stored_empty(tmp_path):
    # OHLCV 取数抛 ValueError(新上市/退市/异常代码)→ 存空帧、capture 完成,不永久卡死
    class _OhlcvRaises(FakeSource):
        def daily_ohlcv(self, code, start, end):
            raise ValueError("代码异常")
    days = [date(2026, 6, 2)]
    frames = {("zt", days[0]): pd.DataFrame({"code": ["A"], "boards": [2]})}
    store = PITStore(tmp_path)
    capture_window(_OhlcvRaises(frames, days, ohlcv={}), store, days[0], days[0], sleep=lambda d: None)
    assert store.has_ohlcv("A") and store.get_ohlcv("A").empty


def test_capture_writes_pools_ohlcv_calendar(tmp_path):
    store = PITStore(tmp_path)
    summ = capture_window(_src(), store, date(2026, 6, 1), date(2026, 6, 3), sleep=lambda d: None)
    assert summ.n_days == 3 and summ.n_codes == 1
    assert store.get_calendar() == [date(2026, 6, 1), date(2026, 6, 2), date(2026, 6, 3)]
    assert list(store.get("zt", date(2026, 6, 2))["code"]) == ["A"]    # 池每日落
    assert store.has("dt", date(2026, 6, 1))                          # 空池也落(不缺)
    assert store.has_ohlcv("A")                                       # universe 各 code OHLCV 落


def test_capture_idempotent_skips(tmp_path):
    store = PITStore(tmp_path)
    capture_window(_src(), store, date(2026, 6, 1), date(2026, 6, 3), sleep=lambda d: None)
    calls = []
    summ2 = capture_window(_src(), store, date(2026, 6, 1), date(2026, 6, 3),
                           sleep=lambda d: calls.append(d))
    assert calls == []                # 全 has 命中 → 不再取数/sleep


def test_capture_blowup_valueerror_stored_empty(tmp_path):
    class _BlowupRaises(FakeSource):
        def zt_pool_blowup(self, day):
            raise ValueError("炸板股池只能获取最近 30 个交易日的数据")
    store = PITStore(tmp_path)
    capture_window(_BlowupRaises({}, [date(2026, 6, 1)], ohlcv={}),
                   store, date(2026, 6, 1), date(2026, 6, 1), sleep=lambda d: None)
    assert store.has("blowup", date(2026, 6, 1))     # 存空帧,不崩、不缺
