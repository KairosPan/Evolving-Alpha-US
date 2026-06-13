from __future__ import annotations

from datetime import date as Date


def trading_days_between(
    calendar: list[Date], start: Date, end: Date
) -> list[Date]:
    """返回 [start, end] 闭区间内的交易日,升序。"""
    return sorted(d for d in calendar if start <= d <= end)
