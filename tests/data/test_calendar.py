# tests/data/test_calendar.py
from datetime import date
from alpha.data.calendar import trading_days_between, next_trading_day, prev_trading_day

CAL = [date(2026, 6, 8), date(2026, 6, 9), date(2026, 6, 10), date(2026, 6, 11), date(2026, 6, 12)]


def test_trading_days_between_inclusive_sorted():
    out = trading_days_between(CAL, date(2026, 6, 9), date(2026, 6, 11))
    assert out == [date(2026, 6, 9), date(2026, 6, 10), date(2026, 6, 11)]


def test_next_and_prev_trading_day():
    assert next_trading_day(CAL, date(2026, 6, 10)) == date(2026, 6, 11)
    assert prev_trading_day(CAL, date(2026, 6, 10)) == date(2026, 6, 9)


def test_next_at_end_returns_none():
    assert next_trading_day(CAL, date(2026, 6, 12)) is None
    assert prev_trading_day(CAL, date(2026, 6, 8)) is None
