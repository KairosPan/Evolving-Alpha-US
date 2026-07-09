"""Cross-face revert reconcile (2026-07-09 review major): both faces share ONE brain, so a
restore issued through the SONIA service must also heal WORKBENCH staged edits (and the sonia
/snapshots restore lever must exist for landings with no session message, e.g. user-direct)."""
import pytest
pytest.importorskip("fastapi")
from datetime import date

import pandas as pd
from fastapi.testclient import TestClient

from alpha.data.source import FakeSource


def _fake_source():
    cal = [date(2026, 6, 10)]
    snaps = {cal[0]: pd.DataFrame({"symbol": ["RUN"], "name": ["RUN"], "open": [1.0], "high": [1.0],
                                   "low": [1.0], "close": [1.0], "volume": [1], "prev_close": [1.0]})}
    bars = {"RUN": pd.DataFrame({"date": cal, "open": [1.0], "high": [1.0], "low": [1.0],
                                 "close": [1.0], "volume": [1]})}
    return FakeSource(calendar=cal, bars=bars, snapshots=snaps)


def _env(tmp_path, monkeypatch):
    monkeypatch.setenv("ALPHA_LIVE_BRAIN_DIR", str(tmp_path / "brain"))
    monkeypatch.setenv("ALPHA_PROJECTS_DB", str(tmp_path / "state.db"))
    monkeypatch.setenv("ALPHA_WORKSPACE_DIR", str(tmp_path / "ws"))
    monkeypatch.setenv("ALPHA_SESSIONS_DIR", str(tmp_path / "sessions"))
    monkeypatch.setenv("ALPHA_SONIA_PROVIDER", "mock")
    monkeypatch.setenv("ALPHA_MOCK_RESPONSE", "prose")


def _workbench_client():
    from workbench.app import create_app, set_llms
    from alpha.llm.client import MockLLMClient
    set_llms(chat=MockLLMClient([
        '{"tool": "propose_memory_edit", "args": {"tool": "process_memory", "args": '
        '{"lesson_id": "m1", "phases": ["trend"], "outcome": "win", "lesson": "x"}, "rationale": "learned"}}',
        "Staged."]), agent=MockLLMClient("{}"), source=_fake_source())
    return TestClient(create_app())


def test_sonia_snapshot_restore_heals_workbench_staged_edit(tmp_path, monkeypatch):
    _env(tmp_path, monkeypatch)
    wb = _workbench_client()

    # stage + approve through the workbench: the live brain gains the edit
    wb.post("/converse", json={"text": "remember"})
    eid = wb.get("/project").json()["staged_edits"][0]["edit_id"]
    wb.post(f"/edits/{eid}/approve")
    assert wb.get("/healthz").json()["edit_count"] == 1

    # revert through SONIA's snapshot lever (the approve snapshot lives in the shared history)
    from sonia.app import create_app as sonia_app
    sonia = TestClient(sonia_app())
    snaps = sonia.get("/snapshots").json()
    assert f"approve-{eid}" in snaps
    r = sonia.post(f"/snapshots/approve-{eid}/restore")
    assert r.status_code == 200 and r.json()["ok"] is True
    assert wb.get("/healthz").json()["edit_count"] == 0

    # the WORKBENCH staged edit was healed by the sonia-side sweep (cross-face reconcile)
    se = wb.get("/project").json()["staged_edits"][0]
    assert se["status"] == "pending" and se["applied_seq"] is None
    assert se["reason"] == "rolled back"


def test_snapshot_restore_rejects_traversal_names(tmp_path, monkeypatch):
    _env(tmp_path, monkeypatch)
    from sonia.app import create_app as sonia_app
    sonia = TestClient(sonia_app())
    r = sonia.post("/snapshots/%2e%2e%2fbrain/restore")
    assert r.status_code in (400, 404)
