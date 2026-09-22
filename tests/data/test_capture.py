# tests/data/test_capture.py
"""capture_window must persist corporate actions into the PITStore, otherwise the OFFLINE firewall
(reverse-split / dilution veto in screen_decision) is silently blind on captured windows."""
from __future__ import annotations

from datetime import date

import pytest

from alpaca_kit.pit.capture import capture_window
from alpaca_kit.feeds.corp_actions import has_reverse_split_pending
from alpaca_kit.pit.pit_store import PITStore
from alpaca_kit.pit.snapshot_source import SnapshotSource


def test_capture_window_stores_corp_actions(fake_source, tmp_path):
    store = PITStore(tmp_path)
    capture_window(fake_source, store, date(2026, 6, 10), date(2026, 6, 12), ["RUN", "FLOP"])
    corp = store.get_corp_actions()
    assert corp is not None and list(corp["symbol"]) == ["RUN"]          # RUN reverse_split captured
    # the offline source can now answer the announce-keyed firewall query for the pending split
    known = SnapshotSource(store).corporate_actions_known(date(2026, 6, 12))
    assert has_reverse_split_pending(known, "RUN", date(2026, 6, 12)) is True


def test_capture_window_scopes_corp_actions_to_captured_symbols(fake_source, tmp_path):
    # RUN's reverse split must NOT leak into a store that only captured FLOP (no bars/snapshots for RUN).
    store = PITStore(tmp_path)
    capture_window(fake_source, store, date(2026, 6, 10), date(2026, 6, 12), ["FLOP"])
    corp = store.get_corp_actions()
    assert corp is None or corp.empty or "RUN" not in set(corp["symbol"])


def test_source_that_cannot_check_corp_actions_writes_no_artifact(tmp_path):
    # corp_actions_available() False -> NO corp_actions.parquet, so the replay reports MISSING (the guard
    # could not check) instead of an empty frame that reads back as "checked, clean".
    import pandas as pd
    from alpaca_kit.source import FakeSource
    cal = [date(2026, 6, 10), date(2026, 6, 11)]
    bars = {"RUN": pd.DataFrame({"date": cal, "open": [1.0, 2.0], "high": [2.0, 3.0], "low": [1.0, 2.0],
                                 "close": [1.5, 2.5], "volume": [10, 20]})}
    blind = FakeSource(calendar=cal, bars=bars, snapshots={}, corp_actions_available=False)
    store = PITStore(tmp_path)
    capture_window(blind, store, cal[0], cal[-1], ["RUN"])
    assert not (tmp_path / "corp_actions.parquet").exists()
    assert store.get_bars("RUN") is not None and store.has_snapshot(cal[1])
    assert SnapshotSource(store).corp_actions_available() is False


def test_source_without_the_probe_still_writes_corp_actions(fake_source, tmp_path):
    # A legacy source lacking corp_actions_available defaults True (GuardedSource's posture) -> written.
    class _Legacy:
        def __getattr__(self, name):
            if name == "corp_actions_available":
                raise AttributeError(name)
            return getattr(fake_source, name)
    store = PITStore(tmp_path)
    capture_window(_Legacy(), store, date(2026, 6, 10), date(2026, 6, 12), ["RUN"])
    assert store.has_corp_actions() and list(store.get_corp_actions()["symbol"]) == ["RUN"]


def test_end_to_end_bought_files_capture_then_guarded_replay(tmp_path):
    """A bought Massive-shaped directory -> capture_window -> a PIT bed with bars, derived snapshots, the
    union calendar and CHECKSUMS (no corp_actions.parquet) -> replay_days yields the bars through the
    guard, which refuses a read past the day."""
    import json
    from alpaca_kit.feeds.massive_files import MassiveFilesSource
    from alpaca_kit.firewall import LookaheadError
    from alpaca_kit.pit.integrity_check import verify_checksums
    from alpaca_kit.replay import replay_days
    t0, day_ms = 1781064000000, 86_400_000                          # 2026-06-10T04:00Z = midnight ET
    vendor = tmp_path / "massive"
    (vendor / "ACME").mkdir(parents=True)
    (vendor / "ACME" / "2026-06-10_2026-06-12.json").write_text(json.dumps({
        "ticker": "ACME", "adjusted": False, "status": "OK", "results": [
            {"t": t0, "o": 10.0, "h": 12.0, "l": 9.5, "c": 11.0, "v": 1000, "vw": 10.5, "n": 3},
            {"t": t0 + day_ms, "o": 12.5, "h": 15.0, "l": 12.0, "c": 14.0, "v": 3000, "vw": 13.0, "n": 3},
            {"t": t0 + 2 * day_ms, "o": 16.0, "h": 18.0, "l": 15.0, "c": 17.0, "v": 5000, "vw": 16.5, "n": 3},
        ]}))
    bed = tmp_path / "bed"
    start, end = date(2026, 6, 10), date(2026, 6, 12)
    capture_window(MassiveFilesSource(vendor), PITStore(bed), start, end, ["ACME"])

    store = PITStore(bed)
    assert store.get_calendar() == [start, date(2026, 6, 11), end]                  # the bought window
    assert list(store.get_bars("ACME").columns) == ["date", "open", "high", "low", "close", "volume"]
    snap = store.get_snapshot(date(2026, 6, 11))
    assert snap is not None and float(snap.iloc[0]["prev_close"]) == 11.0            # derived from bars
    assert (bed / "CHECKSUMS").exists() and verify_checksums(bed, fail_closed=True) == []
    assert not (bed / "corp_actions.parquet").exists()                              # honestly MISSING

    days = list(replay_days(pit_root=str(bed), start=start, end=end))
    assert [d for d, _ in days] == [start, date(2026, 6, 11), end]
    day, guarded = days[1]
    bars = guarded.daily_bars("ACME", start, day)
    assert list(bars["close"]) == [11.0, 14.0]
    assert guarded.corp_actions_available() is False
    with pytest.raises(LookaheadError):
        guarded.daily_bars("ACME", start, end)                                       # end > as_of
