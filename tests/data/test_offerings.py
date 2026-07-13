# tests/data/test_offerings.py
from __future__ import annotations

from datetime import date

import pandas as pd

from alpha.data.offerings import (
    OfferingEvent,
    events_from_frame,
    events_to_frame,
    is_dilution_overhang,
    known_offering_events,
    offering_states,
)


def _announce(oid, d, symbol="RUN"):
    return OfferingEvent(symbol=symbol, offering_id=oid, event="announce", kind="shelf",
                         process_date=d, form="S-3", source="edgar")


def _withdrawn(oid, d, symbol="RUN"):
    return OfferingEvent(symbol=symbol, offering_id=oid, event="withdrawn", kind="shelf",
                         process_date=d, form="RW", source="edgar")


def _expired(oid, d, symbol="RUN"):
    return OfferingEvent(symbol=symbol, offering_id=oid, event="expired", kind="shelf",
                         process_date=d, source="edgar")


def test_known_filters_by_process_date():
    events = [_announce("A", date(2026, 6, 9)), _withdrawn("A", date(2026, 6, 20))]
    got = known_offering_events(events, date(2026, 6, 12))
    assert [e.event for e in got] == ["announce"]                    # the withdrawal not yet knowable


def test_announced_offering_is_overhang():
    events = [_announce("A", date(2026, 6, 9))]
    assert is_dilution_overhang(events, "RUN", date(2026, 6, 12)) is True


def test_withdrawn_shelf_stops_vetoing_as_of_withdrawal_date():
    # THE lifecycle core: announced 6/9 (veto), withdrawn 6/20 -> veto lifts as of 6/20, not before.
    events = [_announce("A", date(2026, 6, 9)), _withdrawn("A", date(2026, 6, 20))]
    assert is_dilution_overhang(events, "RUN", date(2026, 6, 19)) is True    # day before withdrawal
    assert is_dilution_overhang(events, "RUN", date(2026, 6, 20)) is False   # as of the withdrawal
    assert is_dilution_overhang(events, "RUN", date(2026, 7, 1)) is False    # stays closed after


def test_expired_shelf_stops_vetoing_as_of_expiry_date():
    events = [_announce("A", date(2023, 6, 9)), _expired("A", date(2026, 6, 9))]  # 3-year Rule-415 lapse
    assert is_dilution_overhang(events, "RUN", date(2026, 6, 8)) is True     # day before expiry
    assert is_dilution_overhang(events, "RUN", date(2026, 6, 9)) is False    # as of expiry


def test_withdrawn_event_alone_is_not_overhang():
    # A close event with no known announce (defensive) -> "closed" -> no veto.
    assert is_dilution_overhang([_withdrawn("A", date(2026, 6, 20))], "RUN", date(2026, 6, 25)) is False


def test_multi_offering_one_active_one_closed_is_overhang():
    events = [_announce("A", date(2026, 6, 9)), _withdrawn("A", date(2026, 6, 20)),
              _announce("B", date(2026, 6, 15))]                    # B still active
    states = offering_states(events, "RUN", date(2026, 6, 25))
    assert states == {"A": "closed", "B": "active"}
    assert is_dilution_overhang(events, "RUN", date(2026, 6, 25)) is True


def test_symbol_filter():
    events = [_announce("A", date(2026, 6, 9), symbol="OTHER")]
    assert is_dilution_overhang(events, "RUN", date(2026, 6, 12)) is False   # wrong symbol -> no overhang


def test_terminal_is_sticky_a_later_reannounce_does_not_reopen():
    # withdrawn then a stray later announce on the SAME offering_id must not reopen the veto.
    events = [_announce("A", date(2026, 6, 9)), _withdrawn("A", date(2026, 6, 20)),
              _announce("A", date(2026, 6, 25))]
    assert offering_states(events, "RUN", date(2026, 6, 30)) == {"A": "closed"}


def test_offering_event_is_frozen():
    import pytest
    with pytest.raises(Exception):
        _announce("A", date(2026, 6, 9)).event = "withdrawn"


def test_frame_round_trip():
    events = [_announce("A", date(2026, 6, 9)), _expired("A", date(2026, 6, 9))]
    df = events_to_frame(events)
    assert list(df.columns) == list(events_to_frame([]).columns)
    back = events_from_frame(df)
    assert back == events
    assert events_from_frame(None) == [] and events_from_frame(pd.DataFrame()) == []
