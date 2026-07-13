"""A7 (charter First Founding Principle: "Kairos does not propose at all"): the worker face's
stage -> approve -> land -> rollback lifecycle is RETIRED. The worker cannot stage an H edit (no
propose tool), the approve endpoint refuses (410), and the gate refuses proposer="kairos". Only a
Sonia proposal (/proposals) or the User's direct edit (Sonia /edit) may land."""
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
    monkeypatch.setenv("ALPHA_PROJECTS_DB", str(tmp_path / "state.db"))
    monkeypatch.setenv("ALPHA_WORKSPACE_DIR", str(tmp_path / "ws"))
    from workbench.app import create_app, set_llms
    from alpha.llm.client import MockLLMClient
    # The model tries to stage a memory edit; after A7 the tool is gone so nothing stages.
    set_llms(chat=MockLLMClient([
        '{"tool": "propose_memory_edit", "args": {"tool": "process_memory", "args": '
        '{"lesson_id": "m1", "phases": ["trend"], "outcome": "win", "lesson": "x"}, "rationale": "learned"}}',
        "I cannot stage that."]), agent=MockLLMClient("{}"),
        source=_fake_source())
    return TestClient(create_app())


def test_worker_converse_stages_nothing(tmp_path, monkeypatch):
    c = _client(tmp_path, monkeypatch)
    r = c.post("/converse", json={"text": "remember"}).json()
    assert r["staged_edits"] == []
    assert c.get("/healthz").json()["edit_count"] == 0        # live brain untouched (no landing)


def test_approve_endpoint_is_retired(tmp_path, monkeypatch):
    # A7: the worker-propose approval landing is retired — the endpoint refuses (no kairos edit lands).
    c = _client(tmp_path, monkeypatch)
    c.post("/converse", json={"text": "remember"})
    r = c.post("/edits/does-not-exist/approve")
    assert r.status_code == 410
    body = r.json()
    assert body["status"] == "retired" and "does not propose" in body["error"]
    assert c.get("/healthz").json()["edit_count"] == 0


def test_rollback_has_nothing_to_roll_back(tmp_path, monkeypatch):
    # With no worker landing, the workbench rollback lever finds nothing to revert (inert-harmless).
    c = _client(tmp_path, monkeypatch)
    c.post("/converse", json={"text": "remember"})
    assert c.post("/rollback").status_code == 404


def test_create_app_fails_fast_when_brain_inside_workspace(tmp_path, monkeypatch):
    """Boot assert (structural invariant): LocalEnv is not a kernel boundary, so a server whose
    brain dir sits inside the shell workspace must refuse to start, not mutate-then-trip."""
    monkeypatch.setenv("ALPHA_WORKSPACE_DIR", str(tmp_path / "ws"))
    monkeypatch.setenv("ALPHA_LIVE_BRAIN_DIR", str(tmp_path / "ws" / "brain"))
    from workbench.app import create_app
    with pytest.raises(RuntimeError, match="inside workspace"):
        create_app()
