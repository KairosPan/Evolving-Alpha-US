# tests/scripts/test_capture_window_wiring.py
"""capture_window's main() must build its source via the registry (make_source), so ALPHA_DATA_SOURCE
selects the vendor — verified offline by patching make_source to a FakeSource."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))
import capture_window as cw  # noqa: E402

from alpha.data.pit_store import PITStore  # noqa: E402


def test_main_builds_source_via_make_source(monkeypatch, tmp_path, fake_source):
    monkeypatch.setattr(cw, "make_source", lambda *a, **k: fake_source)
    monkeypatch.setattr(sys, "argv",
                        ["capture_window.py", "2026-06-10", "2026-06-12", str(tmp_path), "RUN", "FLOP"])
    cw.main()
    store = PITStore(tmp_path)
    assert store.get_bars("RUN") is not None                       # capture ran through the patched source
    assert list(store.get_corp_actions()["symbol"]) == ["RUN"]     # incl. the corp-action wiring
