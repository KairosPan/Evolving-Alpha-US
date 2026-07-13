# tests/data/test_earnings.py
from __future__ import annotations

from datetime import date

import pandas as pd

from alpha.data.earnings import (
    EarningsCalendarEntry,
    EarningsFact,
    calendar_from_frame,
    calendar_to_frame,
    facts_from_frame,
    facts_to_frame,
    known_calendar,
    known_earnings,
)

# Q1 fiscal period ends 3/31 but is only FILED (knowable) on 5/6 — the whole PIT point.
FACTS = [
    EarningsFact(symbol="RUN", fiscal_period="2026Q1", period_end=date(2026, 3, 31),
                 filing_date=date(2026, 5, 6), form="10-Q", actual_eps=1.2, actual_revenue=5.0e8,
                 source="edgar"),
    EarningsFact(symbol="RUN", fiscal_period="2025Q4", period_end=date(2025, 12, 31),
                 filing_date=date(2026, 2, 10), form="10-K", actual_eps=0.9, source="edgar"),
]


def test_known_earnings_filters_by_filing_date_not_period_end():
    # as_of AFTER the fiscal period end (3/31) but BEFORE the filing (5/6): the fact is INVISIBLE.
    # This is the core no-lookahead assertion — period_end must NOT be the availability key.
    assert known_earnings(FACTS, date(2026, 4, 15)) == [FACTS[1]]     # only the already-filed Q4
    # on/after the filing date it appears
    got = known_earnings(FACTS, date(2026, 5, 6))
    assert {f.fiscal_period for f in got} == {"2026Q1", "2025Q4"}


def test_nothing_known_before_first_filing():
    assert known_earnings(FACTS, date(2026, 1, 1)) == []


def test_restatement_invisible_until_its_own_filing_date():
    original = EarningsFact(symbol="ACME", fiscal_period="2026Q1", period_end=date(2026, 3, 31),
                            filing_date=date(2026, 5, 6), actual_eps=1.00)
    restated = EarningsFact(symbol="ACME", fiscal_period="2026Q1", period_end=date(2026, 3, 31),
                            filing_date=date(2026, 8, 20), form="10-K/A", actual_eps=0.80)
    facts = [original, restated]
    assert known_earnings(facts, date(2026, 5, 6)) == [original]      # restatement not yet filed
    assert known_earnings(facts, date(2026, 8, 20)) == [original, restated]   # both after 8/20


def test_earnings_fact_is_frozen():
    import pytest
    with pytest.raises(Exception):
        FACTS[0].actual_eps = 9.9        # frozen model rejects mutation


CAL = [
    # a future report date that became knowable 4/20 (company confirmed it) — pending
    EarningsCalendarEntry(symbol="RUN", expected_date=date(2026, 5, 6), known_asof=date(2026, 4, 20),
                          is_confirmed=True, session="amc", source="vendor"),
    # a date only announced later (5/1) — invisible before then
    EarningsCalendarEntry(symbol="RUN", expected_date=date(2026, 8, 5), known_asof=date(2026, 5, 1)),
]


def test_known_calendar_filters_by_known_asof():
    # 4/25: only the first entry is knowable; the second (known_asof 5/1) is still invisible even though
    # its expected_date is far in the future.
    got = known_calendar(CAL, date(2026, 4, 25))
    assert [e.expected_date for e in got] == [date(2026, 5, 6)]
    assert len(known_calendar(CAL, date(2026, 5, 1))) == 2


def test_calendar_future_known_asof_is_invisible():
    assert known_calendar(CAL, date(2026, 4, 19)) == []              # before the first known_asof


def test_facts_frame_round_trip_preserves_pit_and_optionals():
    df = facts_to_frame(FACTS)
    assert list(df.columns) == list(facts_to_frame([]).columns)      # stable column contract even empty
    back = facts_from_frame(df)
    assert back == FACTS                                             # dates parsed, NaN optionals -> None
    # the Q4 fact had no revenue -> stays None (not NaN) through the round-trip
    q4 = next(f for f in back if f.fiscal_period == "2025Q4")
    assert q4.actual_revenue is None


def test_calendar_frame_round_trip():
    df = calendar_to_frame(CAL)
    back = calendar_from_frame(df)
    assert back == CAL
    assert back[0].is_confirmed is True and back[1].is_confirmed is False


def test_empty_frame_converters():
    assert facts_from_frame(None) == [] and facts_from_frame(pd.DataFrame()) == []
    assert calendar_from_frame(None) == []
