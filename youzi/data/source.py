from __future__ import annotations

from datetime import date as Date
from typing import Protocol

import pandas as pd

from youzi.replay.firewall import AsOfGuard

# akshare 中文列 -> 统一英文列
_RENAME = {
    "代码": "code", "名称": "name", "连板数": "boards",
    "涨跌幅": "pct", "炸板次数": "blowups", "昨日连板数": "boards",
    "封板资金": "seal_amount",
    "换手率": "turnover_rate",
    "首次封板时间": "first_seal_time",
    "所属行业": "industry",
    "流通市值": "float_mcap",
}


def _normalize(df: pd.DataFrame) -> pd.DataFrame:
    if df is None or df.empty:
        return pd.DataFrame(columns=["code", "name", "boards", "pct", "blowups"])
    out = df.rename(columns=_RENAME).copy()
    out = out.loc[:, ~out.columns.duplicated()]  # 防 _RENAME 把多列映射到同名(如 boards)导致重复列
    if "code" in out.columns:
        out["code"] = out["code"].astype(str).str.zfill(6)
    for col in ("boards", "pct", "blowups", "seal_amount", "turnover_rate", "float_mcap"):
        if col in out.columns:
            out[col] = pd.to_numeric(out[col], errors="coerce")
    return out


_OHLCV_RENAME = {"日期": "date", "开盘": "open", "收盘": "close",
                 "最高": "high", "最低": "low", "成交量": "volume"}


def _normalize_ohlcv(df: pd.DataFrame) -> pd.DataFrame:
    """akshare 日线中文列 -> 英文;date->date 对象;OHLCV->数值。空 -> 带列空 df。"""
    if df is None or df.empty:
        return pd.DataFrame(columns=["date", "open", "high", "low", "close", "volume"])
    out = df.rename(columns=_OHLCV_RENAME).copy()
    out = out.loc[:, ~out.columns.duplicated()]
    if "date" in out.columns:
        out["date"] = pd.to_datetime(out["date"]).dt.date
    for c in ("open", "high", "low", "close", "volume"):
        if c in out.columns:
            out[c] = pd.to_numeric(out[c], errors="coerce")
    return out


def _ymd(day: Date) -> str:
    return day.strftime("%Y%m%d")


def _retry_ak(fn, tries: int = 4, backoff: float = 1.0, sleep=None):
    """akshare 取数重试:网络抖动(connection reset 等)指数退避重试;ValueError(如炸板池 30 日限制)
    等确定性错误不重试。多日多窗实盘 eval 必需——否则单次瞬时抖动崩整轮。sleep 可注入便于测试。"""
    import time as _t
    slp = sleep if sleep is not None else _t.sleep
    last: Exception | None = None
    for k in range(tries):
        try:
            return fn()
        except ValueError:
            raise                       # akshare 确定性错误(范围限制/无数据),不重试
        except Exception as e:          # noqa: BLE001 — 网络抖动:退避重试
            last = e
            if k < tries - 1:
                slp(backoff * (2 ** k))
            else:
                raise
    raise last  # pragma: no cover


class MarketDataSource(Protocol):
    """市场数据源契约(规整后英文列:code/name/boards/pct)。"""
    def trading_calendar(self) -> list[Date]: ...
    def zt_pool(self, day: Date) -> pd.DataFrame: ...
    def zt_pool_previous(self, day: Date) -> pd.DataFrame: ...
    def zt_pool_blowup(self, day: Date) -> pd.DataFrame: ...
    def dt_pool(self, day: Date) -> pd.DataFrame: ...
    def daily_ohlcv(self, code: str, start: Date, end: Date) -> pd.DataFrame: ...


class AkshareSource:
    """真实 akshare 适配器。函数名见 PROJECT_STATE.md 第 4 节。"""

    def __init__(self) -> None:
        import akshare as ak
        self._ak = ak

    def trading_calendar(self) -> list[Date]:
        df = _retry_ak(lambda: self._ak.tool_trade_date_hist_sina())
        return [pd.to_datetime(d).date() for d in df["trade_date"]]

    def zt_pool(self, day: Date) -> pd.DataFrame:
        return _normalize(_retry_ak(lambda: self._ak.stock_zt_pool_em(date=_ymd(day))))

    def zt_pool_previous(self, day: Date) -> pd.DataFrame:
        return _normalize(_retry_ak(lambda: self._ak.stock_zt_pool_previous_em(date=_ymd(day))))

    def zt_pool_blowup(self, day: Date) -> pd.DataFrame:
        return _normalize(_retry_ak(lambda: self._ak.stock_zt_pool_zbgc_em(date=_ymd(day))))

    def dt_pool(self, day: Date) -> pd.DataFrame:
        return _normalize(_retry_ak(lambda: self._ak.stock_zt_pool_dtgc_em(date=_ymd(day))))

    def daily_ohlcv(self, code: str, start: Date, end: Date) -> pd.DataFrame:
        return _normalize_ohlcv(_retry_ak(lambda: self._ak.stock_zh_a_hist(
            symbol=code, period="daily", start_date=_ymd(start),
            end_date=_ymd(end), adjust="qfq")))


class GuardedSource:
    """把每次取数日期过 AsOfGuard,杜绝未来函数。包裹任意 MarketDataSource。"""

    def __init__(self, inner: MarketDataSource, guard: AsOfGuard) -> None:
        self._inner = inner
        self._guard = guard

    def trading_calendar(self) -> list[Date]:
        return self._inner.trading_calendar()

    def zt_pool(self, day: Date) -> pd.DataFrame:
        self._guard.check(day)
        return self._inner.zt_pool(day)

    def zt_pool_previous(self, day: Date) -> pd.DataFrame:
        self._guard.check(day)
        return self._inner.zt_pool_previous(day)

    def zt_pool_blowup(self, day: Date) -> pd.DataFrame:
        self._guard.check(day)
        return self._inner.zt_pool_blowup(day)

    def dt_pool(self, day: Date) -> pd.DataFrame:
        self._guard.check(day)
        return self._inner.dt_pool(day)

    def daily_ohlcv(self, code: str, start: Date, end: Date) -> pd.DataFrame:
        self._guard.check(end)            # 打分时刻 as_of≥t+N 合法;越界(end>as_of)→ LookaheadError
        return self._inner.daily_ohlcv(code, start, end)
