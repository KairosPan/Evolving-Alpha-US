"""DecisionStore: persist daily DecisionPackages as <root>/<date>.json (atomic), read back by date.
The web console reads these so /decisions browses the real packages a run produced."""
from __future__ import annotations

from datetime import date

from alpha.eval.decision import Candidate, DecisionPackage
from alpha.eval.decision_store import DecisionStore


def _pkg(d, syms=("AAA",)):
    return DecisionPackage(date=d, candidates=[Candidate(symbol=s, pattern="gap_and_go") for s in syms])


def test_put_get_roundtrip(tmp_path):
    store = DecisionStore(tmp_path)
    store.put(_pkg(date(2026, 1, 5), ("AAA", "BBB")))
    got = store.get(date(2026, 1, 5))
    assert got is not None and got.date == date(2026, 1, 5)
    assert [c.symbol for c in got.candidates] == ["AAA", "BBB"]


def test_dates_sorted_latest_len(tmp_path):
    store = DecisionStore(tmp_path)
    for d in (date(2026, 1, 7), date(2026, 1, 5), date(2026, 1, 6)):
        store.put(_pkg(d))
    assert store.dates() == [date(2026, 1, 5), date(2026, 1, 6), date(2026, 1, 7)]
    assert store.latest().date == date(2026, 1, 7)
    assert len(store) == 3


def test_missing_is_none(tmp_path):
    store = DecisionStore(tmp_path / "empty")     # dir need not exist yet
    assert store.get(date(2026, 1, 1)) is None
    assert store.latest() is None
    assert store.dates() == [] and len(store) == 0


def test_put_overwrites_same_date(tmp_path):
    store = DecisionStore(tmp_path)
    store.put(_pkg(date(2026, 1, 5), ("AAA",)))
    store.put(_pkg(date(2026, 1, 5), ("CCC",)))
    assert [c.symbol for c in store.get(date(2026, 1, 5)).candidates] == ["CCC"]
    assert len(store) == 1


def test_atomic_no_tmp_and_ignores_strays(tmp_path):
    store = DecisionStore(tmp_path)
    store.put(_pkg(date(2026, 1, 5)))
    assert not list(tmp_path.glob("*.tmp"))            # no truncated temp left behind
    (tmp_path / "notes.txt").write_text("x")           # non-decision files don't appear as dates
    (tmp_path / "not-a-date.json").write_text("{}")
    assert store.dates() == [date(2026, 1, 5)]
