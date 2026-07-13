# tests/features/test_earnings.py
from __future__ import annotations

from datetime import date

from alpha.data.earnings import EarningsCalendarEntry, EarningsFact
from alpha.features.earnings import (
    days_to_earnings,
    has_upcoming_earnings,
    latest_actual,
    next_earnings,
)

CAL = [
    EarningsCalendarEntry(symbol="RUN", expected_date=date(2026, 5, 6), known_asof=date(2026, 4, 20)),
    EarningsCalendarEntry(symbol="RUN", expected_date=date(2026, 8, 5), known_asof=date(2026, 5, 1)),
    EarningsCalendarEntry(symbol="OTH", expected_date=date(2026, 5, 4), known_asof=date(2026, 4, 1)),
]


def test_next_earnings_skips_past_and_picks_soonest_future():
    # on 5/1: RUN's 5/6 is the next; the 8/5 is later and OTH belongs to another symbol.
    nxt = next_earnings(CAL, "RUN", date(2026, 5, 1))
    assert nxt is not None and nxt.expected_date == date(2026, 5, 6)


def test_next_earnings_none_when_all_past():
    assert next_earnings(CAL, "RUN", date(2026, 9, 1)) is None       # both RUN dates behind us


def test_days_to_earnings():
    assert days_to_earnings(CAL, "RUN", date(2026, 5, 1)) == 5       # 5/1 -> 5/6
    assert days_to_earnings(CAL, "RUN", date(2026, 5, 6)) == 0       # reports today
    assert days_to_earnings(CAL, "ZZZ", date(2026, 5, 1)) is None    # unknown symbol -> None


def test_has_upcoming_earnings_t3_boundary():
    # T-3: exactly 3 days out is inside the default window; 4 days is outside.
    assert has_upcoming_earnings(CAL, "RUN", date(2026, 5, 3)) is True    # 3 days -> True
    assert has_upcoming_earnings(CAL, "RUN", date(2026, 5, 2)) is False   # 4 days -> False (default 3)
    assert has_upcoming_earnings(CAL, "RUN", date(2026, 5, 2), within_days=4) is True
    assert has_upcoming_earnings(CAL, "RUN", date(2026, 5, 6)) is True    # reports today (0 days)


def test_empty_calendar_is_default_safe():
    # no feed -> None/False everywhere (byte-identical when the consume path is off)
    assert next_earnings([], "RUN", date(2026, 5, 1)) is None
    assert days_to_earnings([], "RUN", date(2026, 5, 1)) is None
    assert has_upcoming_earnings([], "RUN", date(2026, 5, 1)) is False


FACTS = [
    EarningsFact(symbol="RUN", fiscal_period="2026Q1", period_end=date(2026, 3, 31),
                 filing_date=date(2026, 5, 6), actual_eps=1.00),
    EarningsFact(symbol="RUN", fiscal_period="2026Q1", period_end=date(2026, 3, 31),
                 filing_date=date(2026, 8, 20), form="10-K/A", actual_eps=0.80),   # restatement
    EarningsFact(symbol="OTH", fiscal_period="2026Q1", period_end=date(2026, 3, 31),
                 filing_date=date(2026, 5, 6), actual_eps=0.20),
]


def test_latest_actual_is_restatement_aware():
    # as_of 5/6: only the original is filed -> eps 1.00
    assert latest_actual(FACTS, "RUN", date(2026, 5, 6)).actual_eps == 1.00
    # as_of after the 8/20 restatement: the later filing wins -> eps 0.80
    assert latest_actual(FACTS, "RUN", date(2026, 8, 20)).actual_eps == 0.80
    # symbol filter + not-yet-reported
    assert latest_actual(FACTS, "OTH", date(2026, 5, 6)).symbol == "OTH"
    assert latest_actual(FACTS, "RUN", date(2026, 4, 1)) is None
    assert latest_actual([], "RUN", date(2026, 5, 6)) is None
