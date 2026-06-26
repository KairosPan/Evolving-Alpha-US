import pytest
pytest.importorskip("fastapi")
from datetime import date
import pandas as pd
from fastapi.testclient import TestClient
from alpha_web.workbench_client import WorkbenchClient


def _wb_tc(tmp_path, monkeypatch):
    monkeypatch.setenv("ALPHA_LIVE_BRAIN_DIR", str(tmp_path / "brain"))
    monkeypatch.setenv("ALPHA_PROJECTS_DIR", str(tmp_path / "projects"))
    monkeypatch.setenv("ALPHA_WORKSPACE_DIR", str(tmp_path / "ws"))
    from workbench.app import create_app, set_llms
    from alpha.llm.client import MockLLMClient
    from alpha.data.source import FakeSource
    cal = [date(2026, 6, 10)]
    snaps = {cal[0]: pd.DataFrame({"symbol": ["RUN"], "name": ["RUN"], "open": [1.0], "high": [1.0],
                                   "low": [1.0], "close": [1.0], "volume": [1], "prev_close": [1.0]})}
    bars = {"RUN": pd.DataFrame({"date": cal, "open": [1.0], "high": [1.0], "low": [1.0],
                                 "close": [1.0], "volume": [1]})}
    source = FakeSource(calendar=cal, bars=bars, snapshots=snaps)
    set_llms(chat=MockLLMClient([
        '{"tool": "propose_memory_edit", "args": {"tool": "process_memory", "args": '
        '{"lesson_id": "m1", "outcome": "win", "lesson": "x"}, "rationale": "learned"}}', "Staged."]),
        agent=MockLLMClient("{}"),
        source=source)
    return TestClient(create_app())


def test_workbench_client_converse_and_approve(tmp_path, monkeypatch):
    wc = WorkbenchClient(client=_wb_tc(tmp_path, monkeypatch))
    r = wc.converse("remember")
    eid = r["staged_edits"][0]["edit_id"]
    assert wc.approve_edit(eid)["status"] == "approved"
    assert wc.get_project()["project_id"] == "default"
