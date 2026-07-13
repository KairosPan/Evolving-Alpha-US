# tests/data/test_short_interest.py
from __future__ import annotations

from datetime import date

import pandas as pd

from alpha.data.short_interest import (
    ShortInterest,
    known_short_interest,
    si_from_frame,
    si_to_frame,
)

# Settlement 6/14 but only DISSEMINATED (knowable) on 6/25 — the whole PIT point.
RECORDS = [
    ShortInterest(symbol="RUN", settlement_date=date(2026, 6, 14), publication_date=date(2026, 6, 25),
                  shares_short=1.2e7, avg_daily_volume=2.0e6, days_to_cover=6.0, source="finra"),
    ShortInterest(symbol="RUN", settlement_date=date(2026, 5, 30), publication_date=date(2026, 6, 10),
                  shares_short=9.0e6, avg_daily_volume=3.0e6, days_to_cover=3.0, source="finra"),
]


def test_known_filters_by_publication_date_not_settlement_date():
    # as_of AFTER the settlement (6/14) but BEFORE dissemination (6/25): the observation is INVISIBLE.
    # This is the core no-lookahead assertion — settlement_date must NOT be the availability key.
    got = known_short_interest(RECORDS, date(2026, 6, 20))
    assert [r.settlement_date for r in got] == [date(2026, 5, 30)]      # only the already-published one
    # on/after the dissemination date it appears
    assert len(known_short_interest(RECORDS, date(2026, 6, 25))) == 2


def test_nothing_known_before_first_publication():
    assert known_short_interest(RECORDS, date(2026, 6, 1)) == []


def test_short_interest_is_frozen():
    import pytest
    with pytest.raises(Exception):
        RECORDS[0].shares_short = 9.9        # frozen model rejects mutation


def test_frame_round_trip_preserves_pit_and_optionals():
    df = si_to_frame(RECORDS)
    assert list(df.columns) == list(si_to_frame([]).columns)           # stable column contract even empty
    back = si_from_frame(df)
    assert back == RECORDS                                              # dates parsed, NaN optionals -> None
    # a record with no percent_of_float stays None (not NaN) through the round-trip
    assert back[0].percent_of_float is None


def test_empty_frame_converters():
    assert si_from_frame(None) == [] and si_from_frame(pd.DataFrame()) == []
