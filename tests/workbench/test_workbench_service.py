import pytest
pytest.importorskip("fastapi", reason="install: pip install -e '.[web,sonia]'")
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
    set_llms(chat=MockLLMClient([
        '{"tool": "propose_memory_edit", "args": {"tool": "process_memory", "args": '
        '{"lesson_id": "m1", "phases": ["trend"], "outcome": "win", "lesson": "x"}, "rationale": "learned"}}',
        "I cannot stage that."]),
        agent=MockLLMClient("{}"),
        source=_fake_source())
    return TestClient(create_app())


def test_healthz(tmp_path, monkeypatch):
    assert _client(tmp_path, monkeypatch).get("/healthz").json()["ok"] is True


def test_converse_stages_nothing(tmp_path, monkeypatch):
    # A7 (charter First Founding Principle: "Kairos does not propose at all"): the propose tool is
    # retired, so a model call to propose_memory_edit stages nothing — the turn still completes.
    c = _client(tmp_path, monkeypatch)
    r = c.post("/converse", json={"text": "remember this"}).json()
    assert r["assistant_text"] == "I cannot stage that."
    assert r["staged_edits"] == []
    proj = c.get("/project").json()
    assert proj["project_id"] == "default" and proj["staged_edits"] == []
