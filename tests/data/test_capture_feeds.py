"""P5 capture-window persistence of the new feeds (spec 2026-07-13-p5-consume-path-activations-design §3).

capture_window persists the OPTIONAL P5 feeds — earnings (facts + calendar), FINRA short interest, EDGAR
offering-lifecycle events, and free float — into the PITStore so a captured window replays them offline,
and write_checksums (called last, walks the whole tree) auto-covers the new parquets. Additive /
default-off: a source with no feeds -> none of the parquets are written -> byte-identical capture, and the
CHECKSUMS manifest is identical to a pre-P5 capture.
"""
from __future__ import annotations

from datetime import date

import pandas as pd

from alpha.data.capture import capture_window
from alpha.data.earnings import EarningsCalendarEntry, EarningsFact
from alpha.data.float_shares import FloatFact
from alpha.data.integrity_check import MANIFEST_NAME, verify_checksums
from alpha.data.offerings import OfferingEvent, is_dilution_overhang
from alpha.data.pit_store import PITStore
from alpha.data.short_interest import ShortInterest
from alpha.data.snapshot_source import SnapshotSource
from alpha.data.source import FakeSource

_CAL = [date(2026, 6, 10), date(2026, 6, 11), date(2026, 6, 12)]
_END = date(2026, 6, 12)


def _bars(sym):
    return pd.DataFrame({"date": _CAL, "open": [10., 11., 12.], "high": [10., 11., 12.],
                         "low": [10., 11., 12.], "close": [10., 11., 12.], "volume": [1, 1, 1]})


def _feeds_source():
    """RUN carries all four feeds (knowable by the window end); OFFSCREEN is a non-captured symbol whose
    records must NOT leak into a store that only captured RUN."""
    return FakeSource(
        calendar=_CAL, bars={"RUN": _bars("RUN"), "OFFSCREEN": _bars("OFFSCREEN")},
        snapshots={}, corp_actions_available=True,
        earnings=[EarningsFact(symbol="RUN", fiscal_period="2026Q1", period_end=date(2026, 3, 31),
                               filing_date=date(2026, 6, 1), actual_eps=1.2),
                  EarningsFact(symbol="OFFSCREEN", fiscal_period="2026Q1", period_end=date(2026, 3, 31),
                               filing_date=date(2026, 6, 1))],
        earnings_calendar=[EarningsCalendarEntry(symbol="RUN", expected_date=date(2026, 6, 20),
                                                 known_asof=date(2026, 6, 2)),
                           EarningsCalendarEntry(symbol="OFFSCREEN", expected_date=date(2026, 6, 20),
                                                 known_asof=date(2026, 6, 2))],
        short_interest=[ShortInterest(symbol="RUN", settlement_date=date(2026, 5, 31),
                                      publication_date=date(2026, 6, 10), shares_short=3e6,
                                      days_to_cover=4.0),
                        ShortInterest(symbol="OFFSCREEN", settlement_date=date(2026, 5, 31),
                                      publication_date=date(2026, 6, 10), shares_short=1e6)],
        offering_events=[OfferingEvent(symbol="RUN", offering_id="S3-1", event="announce", kind="shelf",
                                       process_date=date(2026, 6, 5)),
                         OfferingEvent(symbol="OFFSCREEN", offering_id="S3-9", event="announce",
                                       kind="shelf", process_date=date(2026, 6, 5))],
        float_facts=[FloatFact(symbol="RUN", free_float=30e6, knowable_date=date(2026, 6, 1)),
                     FloatFact(symbol="OFFSCREEN", free_float=99e6, knowable_date=date(2026, 6, 1))])


# ── feeds present -> persisted + PIT-replayable + CHECKSUMS-covered ──────────────────────────────
def test_capture_persists_all_four_feeds_and_they_replay_pit(tmp_path):
    store = PITStore(tmp_path)
    capture_window(_feeds_source(), store, _CAL[0], _END, ["RUN"])
    assert store.has_earnings() and store.has_short_interest()
    assert store.has_offering_events() and store.has_float()

    snap = SnapshotSource(store)
    assert [f.symbol for f in snap.earnings_known("RUN", _END)] == ["RUN"]
    assert snap.earnings_calendar(_END)[0].symbol == "RUN"
    si = snap.short_interest_known("RUN", _END)
    assert si and si[0].days_to_cover == 4.0
    assert snap.float_known("RUN", _END)[0].free_float == 30e6
    # the offering-lifecycle reducer replays offline: RUN's active announce is still an overhang.
    assert is_dilution_overhang(snap.offering_events_known("RUN", _END), "RUN", _END) is True


def test_capture_scopes_feeds_to_captured_symbols(tmp_path):
    store = PITStore(tmp_path)
    capture_window(_feeds_source(), store, _CAL[0], _END, ["RUN"])       # OFFSCREEN not captured
    snap = SnapshotSource(store)
    assert snap.earnings_known("OFFSCREEN", _END) == []
    assert snap.short_interest_known("OFFSCREEN", _END) == []
    assert snap.offering_events_known("OFFSCREEN", _END) == []
    assert snap.float_known("OFFSCREEN", _END) == []
    assert all(e.symbol == "RUN" for e in snap.earnings_calendar(_END))  # calendar scoped too


def test_capture_checksums_cover_the_new_feeds(tmp_path):
    store = PITStore(tmp_path)
    capture_window(_feeds_source(), store, _CAL[0], _END, ["RUN"])
    manifest = (tmp_path / MANIFEST_NAME).read_text()
    for parquet in ("earnings_facts.parquet", "earnings_calendar.parquet", "short_interest.parquet",
                    "offering_events.parquet", "float_shares.parquet"):
        assert parquet in manifest                                       # the feed is in the manifest
    assert verify_checksums(tmp_path, fail_closed=True) == []            # and re-hashes clean


# ── feeds absent -> byte-identical capture (no feed parquets, identical manifest) ────────────────
def _bare_source():
    return FakeSource(calendar=_CAL, bars={"RUN": _bars("RUN")}, snapshots={}, corp_actions_available=True)


def test_no_feeds_writes_no_feed_parquets(tmp_path):
    store = PITStore(tmp_path)
    capture_window(_bare_source(), store, _CAL[0], _END, ["RUN"])
    assert not store.has_earnings() and not store.has_short_interest()
    assert not store.has_offering_events() and not store.has_float()
    assert verify_checksums(tmp_path, fail_closed=True) == []


def test_no_feeds_manifest_omits_the_feed_parquets(tmp_path):
    store = PITStore(tmp_path)
    capture_window(_bare_source(), store, _CAL[0], _END, ["RUN"])
    manifest = (tmp_path / MANIFEST_NAME).read_text()
    for parquet in ("earnings_facts.parquet", "short_interest.parquet", "offering_events.parquet",
                    "float_shares.parquet"):
        assert parquet not in manifest
