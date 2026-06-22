# tests/data/test_capture.py
"""capture_window must persist corporate actions into the PITStore, otherwise the OFFLINE firewall
(reverse-split / dilution veto in screen_decision) is silently blind on captured windows."""
from __future__ import annotations

from datetime import date

from alpha.data.capture import capture_window
from alpha.data.corp_actions import has_reverse_split_pending
from alpha.data.pit_store import PITStore
from alpha.data.snapshot_source import SnapshotSource


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
