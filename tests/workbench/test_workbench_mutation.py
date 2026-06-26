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


def _client(tmp_path, monkeypatch):
    monkeypatch.setenv("ALPHA_LIVE_BRAIN_DIR", str(tmp_path / "brain"))
    monkeypatch.setenv("ALPHA_PROJECTS_DIR", str(tmp_path / "projects"))
    monkeypatch.setenv("ALPHA_WORKSPACE_DIR", str(tmp_path / "ws"))
    from workbench.app import create_app, set_llms
    from alpha.llm.client import MockLLMClient
    set_llms(chat=MockLLMClient([
        '{"tool": "propose_memory_edit", "args": {"tool": "process_memory", "args": '
        '{"lesson_id": "m1", "phases": ["trend"], "outcome": "win", "lesson": "x"}, "rationale": "learned"}}',
        "Staged."]), agent=MockLLMClient("{}"),
        source=_fake_source())
    return TestClient(create_app())


def _stage_one(c):
    c.post("/converse", json={"text": "remember"})
    return c.get("/project").json()["staged_edits"][0]["edit_id"]


def test_approve_applies_through_gate(tmp_path, monkeypatch):
    c = _client(tmp_path, monkeypatch)
    eid = _stage_one(c)
    assert c.get("/healthz").json()["edit_count"] == 0
    r = c.post(f"/edits/{eid}/approve")
    assert r.status_code == 200 and r.json()["status"] == "approved"
    assert c.get("/healthz").json()["edit_count"] == 1            # the live brain gained the edit
    assert c.post(f"/edits/{eid}/approve").status_code == 404     # no longer pending


def test_reject_leaves_brain_unchanged(tmp_path, monkeypatch):
    c = _client(tmp_path, monkeypatch)
    eid = _stage_one(c)
    assert c.post(f"/edits/{eid}/reject").json()["status"] == "rejected"
    assert c.get("/healthz").json()["edit_count"] == 0


def test_rollback_after_approve(tmp_path, monkeypatch):
    c = _client(tmp_path, monkeypatch)
    eid = _stage_one(c); c.post(f"/edits/{eid}/approve")
    assert c.get("/healthz").json()["edit_count"] == 1
    assert c.post("/rollback").json()["ok"] is True
    assert c.get("/healthz").json()["edit_count"] == 0            # restored to the pre-approve snapshot
