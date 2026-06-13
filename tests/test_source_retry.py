# tests/test_source_retry.py
import pytest

from youzi.data.source import _retry_ak


def test_retry_ak_succeeds_after_transient():
    calls = {"n": 0}
    sleeps = []

    def fn():
        calls["n"] += 1
        if calls["n"] <= 2:
            raise ConnectionError("connection reset")
        return "ok"

    assert _retry_ak(fn, sleep=lambda d: sleeps.append(d)) == "ok"
    assert calls["n"] == 3 and sleeps == [1.0, 2.0]      # 退避序列 backoff*2**k


def test_retry_ak_reraises_valueerror_immediately():
    calls = {"n": 0}

    def fn():
        calls["n"] += 1
        raise ValueError("炸板股池只能获取最近 30 个交易日的数据")

    with pytest.raises(ValueError):
        _retry_ak(fn, sleep=lambda d: None)
    assert calls["n"] == 1                                # 确定性错误不重试


def test_retry_ak_exhausts_and_raises_last():
    def fn():
        raise ConnectionError("down")

    with pytest.raises(ConnectionError):
        _retry_ak(fn, tries=3, sleep=lambda d: None)
