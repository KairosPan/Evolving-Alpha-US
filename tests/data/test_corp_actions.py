# tests/data/test_corp_actions.py
from __future__ import annotations
from datetime import date
import pandas as pd
from alpha.data.corp_actions import known_corporate_actions, has_reverse_split_pending

CORP = pd.DataFrame({
    "symbol": ["RUN", "RUN"],
    "announce_date": [date(2026, 6, 9), date(2026, 6, 15)],
    "ex_date": [date(2026, 6, 20), date(2026, 6, 25)],
    "kind": ["reverse_split", "split"],
    "ratio": [0.1, 2.0],
})


def test_known_filters_by_announce_date_not_ex_date():
    # as_of just after the first announcement, before its ex-date
    known = known_corporate_actions(CORP, date(2026, 6, 10))
    assert list(known["kind"]) == ["reverse_split"]   # second not yet announced


def test_nothing_known_before_first_announcement():
    known = known_corporate_actions(CORP, date(2026, 6, 8))
    assert known.empty


def test_has_reverse_split_pending_pit():
    # known (announced) but ex-date still in the future => pending
    assert has_reverse_split_pending(CORP, "RUN", date(2026, 6, 10)) is True
    # before announcement => not pending (no lookahead to the ex-date)
    assert has_reverse_split_pending(CORP, "RUN", date(2026, 6, 8)) is False
    # after the ex-date => no longer "pending" (already executed)
    assert has_reverse_split_pending(CORP, "RUN", date(2026, 6, 21)) is False


def test_has_dilution_filing_announced_offering():
    from alpha.data.corp_actions import has_dilution_filing
    corp = pd.DataFrame({"symbol": ["DIL"], "announce_date": [date(2026, 6, 9)],
                         "ex_date": [date(2026, 6, 20)], "kind": ["atm"], "ratio": [None]})
    assert has_dilution_filing(corp, "DIL", date(2026, 6, 12)) is True     # announced by as_of -> overhang


def test_has_dilution_filing_pit_and_wrong_kind():
    from alpha.data.corp_actions import has_dilution_filing
    # DIL's shelf is announced AFTER as_of (PIT); OTHER's atm IS known (6/9<=6/12) but wrong symbol ->
    # exercises the symbol filter on a NON-empty known frame, not just the empty-frame short-circuit.
    corp = pd.DataFrame({"symbol": ["DIL", "OTHER"], "announce_date": [date(2026, 6, 20), date(2026, 6, 9)],
                         "ex_date": [date(2026, 7, 1), date(2026, 6, 20)],
                         "kind": ["shelf", "atm"], "ratio": [None, None]})
    assert has_dilution_filing(corp, "DIL", date(2026, 6, 12)) is False    # PIT + symbol filter (non-empty frame)
    split = pd.DataFrame({"symbol": ["DIL"], "announce_date": [date(2026, 6, 9)],
                          "ex_date": [date(2026, 6, 20)], "kind": ["reverse_split"], "ratio": [0.1]})
    assert has_dilution_filing(split, "DIL", date(2026, 6, 12)) is False   # not a dilution kind
