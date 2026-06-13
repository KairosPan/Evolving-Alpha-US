# youzi/data/capture.py
from __future__ import annotations

from dataclasses import dataclass
from datetime import date as Date

import pandas as pd

from youzi.data.cache import PITStore

_POOLS = [("zt", "zt_pool"), ("prev", "zt_pool_previous"),
          ("blowup", "zt_pool_blowup"), ("dt", "dt_pool")]


@dataclass(frozen=True)
class CaptureSummary:
    n_days: int
    n_codes: int
    n_calls: int


def capture_window(ak_source, store: PITStore, start: Date, end: Date,
                   *, throttle: float = 0.3, sleep=None) -> CaptureSummary:
    """一次性把窗口内 4 池(每日)+ universe 各 code OHLCV + 日历预取进 PITStore。
    幂等(has 跳过);blowup 超 30 日 ValueError → 存空帧;唯一碰 akshare 的部分。"""
    import time as _t
    slp = sleep if sleep is not None else _t.sleep
    calls = 0
    cal = ak_source.trading_calendar()
    store.put_calendar(cal)
    window = [d for d in cal if start <= d <= end]
    codes: set[str] = set()
    for day in window:
        for kind, fname in _POOLS:
            if not store.has(kind, day):
                try:
                    df = getattr(ak_source, fname)(day)
                except ValueError:                       # blowup 30 日限制等确定性错 → 存空帧
                    df = pd.DataFrame(columns=["code"])
                store.put(kind, day, df)
                calls += 1
                slp(throttle)
            df = store.get(kind, day)
            if df is not None and "code" in df.columns:
                codes.update(str(c) for c in df["code"])
    for code in sorted(codes):
        if not store.has_ohlcv(code):
            try:
                df = ak_source.daily_ohlcv(code, start, end)
            except ValueError:                       # 确定性错(新上市/退市/异常代码)→ 存空帧,与池阶段对称、防永久卡死
                df = pd.DataFrame(columns=["date", "open", "high", "low", "close", "volume"])
            store.put_ohlcv(code, df)
            calls += 1
            slp(throttle)
    return CaptureSummary(n_days=len(window), n_codes=len(codes), n_calls=calls)
