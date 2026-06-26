from __future__ import annotations

import os
from fastapi.testclient import TestClient


def _client(tmp_path, monkeypatch):
    monkeypatch.setenv("ALPHA_CONFLICTS_DIR", str(tmp_path / "conflicts"))
    monkeypatch.setenv("ALPHA_LIVE_BRAIN_DIR", str(tmp_path / "brain"))
    monkeypatch.setenv("ALPHA_SESSIONS_DIR", str(tmp_path / "sessions"))
    monkeypatch.setenv("ALPHA_SONIA_PROVIDER", "mock")
    from sonia.app import create_app
    return TestClient(create_app())


def _seed_conflict(tmp_path):
    from alpha.meta.conflict_store import ConflictQueue
    q = ConflictQueue(str(tmp_path / "conflicts"))
    return q.add(op={"tool": "demote_memory", "args": {"lesson_id": "m1"}, "rationale": "data weak"},
                 provenance={"path": "self_study", "proposer": "refiner"},
                 contested={"target_id": "m1", "tool": "process_memory",
                            "provenance": {"path": "teaching", "proposer": "sonia"}})


def test_list_conflicts(tmp_path, monkeypatch):
    held = _seed_conflict(tmp_path)
    c = _client(tmp_path, monkeypatch)
    rows = c.get("/conflicts").json()
    assert len(rows) == 1 and rows[0]["conflict_id"] == held.conflict_id
    assert rows[0]["op"]["tool"] == "demote_memory" and rows[0]["provenance"]["path"] == "self_study"


def test_resolve_removes_conflict(tmp_path, monkeypatch):
    held = _seed_conflict(tmp_path)
    c = _client(tmp_path, monkeypatch)
    r = c.post(f"/conflicts/{held.conflict_id}/resolve", json={"decision": "keep_teaching"})
    assert r.status_code == 200 and r.json() == {"resolved": held.conflict_id, "decision": "keep_teaching"}
    assert c.get("/conflicts").json() == []                       # removed from the queue
    assert c.post(f"/conflicts/{held.conflict_id}/resolve", json={"decision": "keep_teaching"}).status_code == 404
