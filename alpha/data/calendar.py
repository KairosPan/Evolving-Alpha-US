# alpha/data/calendar.py
from __future__ import annotations

from datetime import date as Date


def trading_days_between(calendar: list[Date], start: Date, end: Date) -> list[Date]:
    """All calendar days in [start, end], ascending."""
    return sorted(d for d in calendar if start <= d <= end)


def next_trading_day(calendar: list[Date], day: Date) -> Date | None:
    later = sorted(d for d in calendar if d > day)
    return later[0] if later else None


def prev_trading_day(calendar: list[Date], day: Date) -> Date | None:
    earlier = sorted(d for d in calendar if d < day)
    return earlier[-1] if earlier else None
