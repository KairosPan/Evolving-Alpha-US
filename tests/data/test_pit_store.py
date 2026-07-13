from __future__ import annotations
from datetime import date
import pandas as pd
from alpha.data.pit_store import PITStore


def test_snapshot_roundtrip(tmp_path):
    store = PITStore(tmp_path)
    df = pd.DataFrame({"symbol": ["RUN"], "close": [17.0]})
    assert store.has_snapshot(date(2026, 6, 12)) is False
    store.put_snapshot(date(2026, 6, 12), df)
    assert store.has_snapshot(date(2026, 6, 12)) is True
    out = store.get_snapshot(date(2026, 6, 12))
    pd.testing.assert_frame_equal(out, df)


def test_bars_roundtrip(tmp_path):
    store = PITStore(tmp_path)
    df = pd.DataFrame({"date": [date(2026, 6, 12)], "open": [16.0], "high": [18.0],
                       "low": [15.0], "close": [17.0], "volume": [5_000_000]})
    store.put_bars("RUN", df)
    out = store.get_bars("RUN")
    assert out is not None and out.iloc[0]["close"] == 17.0


def test_calendar_and_corp_roundtrip(tmp_path):
    store = PITStore(tmp_path)
    store.put_calendar([date(2026, 6, 11), date(2026, 6, 12)])
    assert store.get_calendar() == [date(2026, 6, 11), date(2026, 6, 12)]
    corp = pd.DataFrame({"symbol": ["RUN"], "announce_date": [date(2026, 6, 9)],
                         "ex_date": [date(2026, 6, 20)], "kind": ["reverse_split"], "ratio": [0.1]})
    store.put_corp_actions(corp)
    got = store.get_corp_actions()
    assert list(got["kind"]) == ["reverse_split"]
    assert got.iloc[0]["announce_date"] == date(2026, 6, 9)


def test_missing_returns_none(tmp_path):
    store = PITStore(tmp_path)
    assert store.get_snapshot(date(2026, 6, 12)) is None
    assert store.get_bars("NOPE") is None
    assert store.get_calendar() is None
    assert store.get_corp_actions() is None


def test_has_corp_actions_distinguishes_missing_from_present_but_empty(tmp_path):
    # P3: the tri-state seam — the ONLY place "artifact absent" is knowable. `get_corp_actions()`
    # collapses absent(None)/empty into a False-yielding empty frame downstream; has_corp_actions keeps it.
    store = PITStore(tmp_path)
    assert store.has_corp_actions() is False                          # MISSING: no parquet written
    store.put_corp_actions(pd.DataFrame(
        columns=["symbol", "announce_date", "ex_date", "kind", "ratio"]))
    assert store.has_corp_actions() is True                           # PRESENT-BUT-EMPTY: checked, nothing announced
    store.put_corp_actions(pd.DataFrame({"symbol": ["RUN"], "announce_date": [date(2026, 6, 9)],
                                         "ex_date": [date(2026, 6, 20)], "kind": ["reverse_split"],
                                         "ratio": [0.1]}))
    assert store.has_corp_actions() is True                           # AVAILABLE with rows


def test_earnings_roundtrip_preserves_dates_and_optionals(tmp_path):
    # P5a: facts persist via the earnings.py frame converters (iso dates on write, parsed on read),
    # round-tripping back to the exact models incl. None optionals (revenue absent stays None, not NaN).
    from alpha.data.earnings import (EarningsCalendarEntry, EarningsFact,
                                     calendar_from_frame, calendar_to_frame,
                                     facts_from_frame, facts_to_frame)
    store = PITStore(tmp_path)
    assert store.has_earnings() is False                              # MISSING: no parquet
    facts = [EarningsFact(symbol="RUN", fiscal_period="2026Q1", period_end=date(2026, 3, 31),
                          filing_date=date(2026, 5, 6), form="10-Q", actual_eps=1.2, source="edgar")]
    store.put_earnings(facts_to_frame(facts))
    assert store.has_earnings() is True                              # PRESENT
    assert facts_from_frame(store.get_earnings()) == facts           # exact round-trip, revenue -> None
    cal = [EarningsCalendarEntry(symbol="RUN", expected_date=date(2026, 5, 6),
                                 known_asof=date(2026, 4, 20), is_confirmed=True)]
    store.put_earnings_calendar(calendar_to_frame(cal))
    assert calendar_from_frame(store.get_earnings_calendar()) == cal
    assert store.get_earnings_calendar().iloc[0]["known_asof"] == date(2026, 4, 20)   # date parsed back


def test_short_interest_roundtrip_and_tri_state(tmp_path):
    # P5b: records persist via the short_interest.py frame converters; has_short_interest() is the
    # tri-state MISSING seam (absent=False, present-even-empty=True).
    from alpha.data.short_interest import ShortInterest, si_from_frame, si_to_frame
    store = PITStore(tmp_path)
    assert store.has_short_interest() is False                        # MISSING: no parquet
    records = [ShortInterest(symbol="RUN", settlement_date=date(2026, 6, 14),
                             publication_date=date(2026, 6, 25), shares_short=1.2e7, days_to_cover=6.0,
                             source="finra")]
    store.put_short_interest(si_to_frame(records))
    assert store.has_short_interest() is True                         # PRESENT
    assert si_from_frame(store.get_short_interest()) == records       # exact round-trip, optionals -> None
    store.put_short_interest(si_to_frame([]))
    assert store.has_short_interest() is True                         # PRESENT-BUT-EMPTY: checked, none


def test_offering_events_roundtrip_and_tri_state(tmp_path):
    from alpha.data.offerings import OfferingEvent, events_from_frame, events_to_frame
    store = PITStore(tmp_path)
    assert store.has_offering_events() is False                       # MISSING: no parquet
    events = [OfferingEvent(symbol="RUN", offering_id="333-1", event="announce", kind="shelf",
                            process_date=date(2026, 6, 9), form="S-3", source="edgar")]
    store.put_offering_events(events_to_frame(events))
    assert store.has_offering_events() is True                        # PRESENT
    assert events_from_frame(store.get_offering_events()) == events   # exact round-trip
    assert store.get_offering_events().iloc[0]["process_date"] == date(2026, 6, 9)   # date parsed back
