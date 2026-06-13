# youzi/eval/return_oracle.py
from __future__ import annotations

from datetime import date as Date

import pandas as pd


def forward_return(ohlcv: pd.DataFrame, entry_day: Date, exit_day: Date) -> float | None:
    """次日开盘买→t+N 收盘卖:(close@exit_day − open@entry_day) / open@entry_day。

    entry_day/exit_day 不在 ohlcv、open 缺/≤0、close 缺 → None(诚实缺失,不臆造)。
    纯函数:只读传入 df,不取数、无副作用。
    """
    if ohlcv is None or ohlcv.empty or "date" not in ohlcv.columns:
        return None
    e = ohlcv.loc[ohlcv["date"] == entry_day]
    x = ohlcv.loc[ohlcv["date"] == exit_day]
    if e.empty or x.empty:
        return None
    op = e.iloc[0].get("open")
    cl = x.iloc[0].get("close")
    if op is None or cl is None or pd.isna(op) or pd.isna(cl) or op <= 0:
        return None
    return float((cl - op) / op)


class ReturnOracle:
    """前向收益 oracle(打分时刻用已实现 OHLCV)。决策日 t 不调用;片 2 传 GuardedSource 守界。"""

    def __init__(self, source) -> None:
        self._source = source

    def score(self, code: str, entry_day: Date, exit_day: Date) -> float | None:
        ohlcv = self._source.daily_ohlcv(code, entry_day, exit_day)
        return forward_return(ohlcv, entry_day, exit_day)
