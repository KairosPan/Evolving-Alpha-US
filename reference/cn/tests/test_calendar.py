# tests/test_calendar.py
from datetime import date
from youzi.data.calendar import trading_days_between


def test_trading_days_between_filters_and_sorts():
    cal = [date(2024, 6, 26), date(2024, 6, 27), date(2024, 6, 28),
           date(2024, 7, 1)]
    out = trading_days_between(cal, date(2024, 6, 27), date(2024, 6, 28))
    assert out == [date(2024, 6, 27), date(2024, 6, 28)]


def test_trading_days_between_empty_when_no_overlap():
    cal = [date(2024, 6, 26)]
    assert trading_days_between(cal, date(2024, 7, 1), date(2024, 7, 2)) == []
