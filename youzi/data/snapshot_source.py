# youzi/data/snapshot_source.py
from __future__ import annotations

from datetime import date as Date

import pandas as pd

from youzi.data.cache import PITStore

_EMPTY_OHLCV = ["date", "open", "high", "low", "close", "volume"]


class SnapshotMissingError(RuntimeError):
    """快照缺池数据(不完整 capture)——大声失败,别静默当 no-trade。"""


class SnapshotSource:
    """从 PITStore 读的离线 MarketDataSource(零 akshare)。eval 时仍被 GuardedSource 套。"""

    def __init__(self, store: PITStore) -> None:
        self._store = store

    def trading_calendar(self) -> list[Date]:
        cal = self._store.get_calendar()
        if cal is None:
            raise SnapshotMissingError("快照缺 calendar.parquet")
        return cal

    def _pool(self, kind: str, day: Date) -> pd.DataFrame:
        df = self._store.get(kind, day)
        if df is None:
            raise SnapshotMissingError(f"快照缺池 {kind}@{day}(capture 不完整?)")
        return df

    def zt_pool(self, day: Date) -> pd.DataFrame:
        return self._pool("zt", day)

    def zt_pool_previous(self, day: Date) -> pd.DataFrame:
        return self._pool("prev", day)

    def zt_pool_blowup(self, day: Date) -> pd.DataFrame:
        return self._pool("blowup", day)

    def dt_pool(self, day: Date) -> pd.DataFrame:
        return self._pool("dt", day)

    def daily_ohlcv(self, code: str, start: Date, end: Date) -> pd.DataFrame:
        df = self._store.get_ohlcv(code)
        if df is None or df.empty:
            return pd.DataFrame(columns=_EMPTY_OHLCV)     # 停牌/退市/未捕获 → 空(ReturnScorer 丢弃)
        df = df.copy()
        df["date"] = pd.to_datetime(df["date"]).dt.date   # parquet 往返稳健:归一回 date 对象
        return df[(df["date"] >= start) & (df["date"] <= end)]
