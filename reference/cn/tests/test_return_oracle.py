# tests/test_return_oracle.py
from datetime import date

import pandas as pd
import pytest

from youzi.data.source import _normalize_ohlcv, GuardedSource
from youzi.eval.return_oracle import forward_return, ReturnOracle
from youzi.replay.firewall import AsOfGuard, LookaheadError
from tests.conftest import FakeSource


def _ohlcv(rows):
    """rows: list[(date, open, high, low, close, volume)]"""
    return pd.DataFrame(rows, columns=["date", "open", "high", "low", "close", "volume"])


def test_normalize_ohlcv_renames_and_types():
    raw = pd.DataFrame({"日期": ["2026-06-01", "2026-06-02"], "开盘": [10.0, 11.0],
                        "收盘": [11.0, 12.0], "最高": [11.5, 12.5], "最低": [9.5, 10.5],
                        "成交量": [1000, 2000]})
    out = _normalize_ohlcv(raw)
    assert {"date", "open", "high", "low", "close", "volume"}.issubset(out.columns)
    assert out.iloc[0]["date"] == date(2026, 6, 1)
    assert out.iloc[0]["open"] == 10.0 and out.iloc[1]["close"] == 12.0


def test_normalize_ohlcv_empty():
    out = _normalize_ohlcv(pd.DataFrame())
    assert list(out.columns) == ["date", "open", "high", "low", "close", "volume"]
    assert out.empty


def test_fake_source_daily_ohlcv_range_filter():
    df = _ohlcv([(date(2026, 6, 1), 10, 11, 9, 10.5, 100),
                 (date(2026, 6, 2), 10.5, 12, 10, 11.5, 200),
                 (date(2026, 6, 3), 11.5, 13, 11, 12.5, 300)])
    src = FakeSource({}, [], ohlcv={"000001": df})
    got = src.daily_ohlcv("000001", date(2026, 6, 2), date(2026, 6, 3))
    assert list(got["date"]) == [date(2026, 6, 2), date(2026, 6, 3)]
    assert src.daily_ohlcv("999999", date(2026, 6, 2), date(2026, 6, 3)).empty


def test_guarded_daily_ohlcv_blocks_future():
    df = _ohlcv([(date(2026, 6, 2), 10, 11, 9, 10.5, 100)])
    gs = GuardedSource(FakeSource({}, [], ohlcv={"000001": df}), AsOfGuard(date(2026, 6, 2)))
    # end <= as_of:正常
    assert not gs.daily_ohlcv("000001", date(2026, 6, 2), date(2026, 6, 2)).empty
    # end > as_of:拦截
    with pytest.raises(LookaheadError):
        gs.daily_ohlcv("000001", date(2026, 6, 2), date(2026, 6, 5))


def test_forward_return_normal_and_negative():
    df = _ohlcv([(date(2026, 6, 2), 10.0, 11, 9.5, 10.5, 100),
                 (date(2026, 6, 3), 10.6, 12.5, 10.4, 12.0, 200)])
    # entry open@6/2=10.0, exit close@6/3=12.0 → +0.20
    assert forward_return(df, date(2026, 6, 2), date(2026, 6, 3)) == 0.20
    # 负收益:entry open=10.0, exit close=8.0
    df2 = _ohlcv([(date(2026, 6, 2), 10.0, 11, 9, 10, 100),
                  (date(2026, 6, 3), 9.0, 9.5, 7.5, 8.0, 200)])
    assert forward_return(df2, date(2026, 6, 2), date(2026, 6, 3)) == -0.20


def test_forward_return_missing_returns_none():
    df = _ohlcv([(date(2026, 6, 2), 10.0, 11, 9.5, 10.5, 100)])
    assert forward_return(df, date(2026, 6, 1), date(2026, 6, 2)) is None   # entry 不在
    assert forward_return(df, date(2026, 6, 2), date(2026, 6, 9)) is None   # exit 不在
    assert forward_return(pd.DataFrame(), date(2026, 6, 2), date(2026, 6, 3)) is None  # 空 df


def test_forward_return_bad_open_returns_none():
    nan_open = _ohlcv([(date(2026, 6, 2), float("nan"), 11, 9, 10, 100),
                       (date(2026, 6, 3), 10, 12, 10, 11, 200)])
    assert forward_return(nan_open, date(2026, 6, 2), date(2026, 6, 3)) is None
    zero_open = _ohlcv([(date(2026, 6, 2), 0.0, 11, 9, 10, 100),
                        (date(2026, 6, 3), 10, 12, 10, 11, 200)])
    assert forward_return(zero_open, date(2026, 6, 2), date(2026, 6, 3)) is None


def test_return_oracle_score():
    df = _ohlcv([(date(2026, 6, 2), 10.0, 11, 9.5, 10.5, 100),
                 (date(2026, 6, 3), 10.6, 12.5, 10.4, 12.0, 200)])
    o = ReturnOracle(FakeSource({}, [], ohlcv={"000001": df}))
    assert o.score("000001", date(2026, 6, 2), date(2026, 6, 3)) == 0.20
    assert o.score("999999", date(2026, 6, 2), date(2026, 6, 3)) is None    # 缺该 code → None
