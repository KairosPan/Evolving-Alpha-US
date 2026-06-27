import pytest
pytest.importorskip("fastapi")
from datetime import date
import pandas as pd
from fastapi.testclient import TestClient
from alpha_web.workbench_client import WorkbenchClient


def _wb_tc(tmp_path, monkeypatch):
    monkeypatch.setenv("ALPHA_LIVE_BRAIN_DIR", str(tmp_path / "brain"))
    monkeypatch.setenv("ALPHA_PROJECTS_DB", str(tmp_path / "state.db"))
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


def _web_client(tmp_path, monkeypatch):
    from alpha_web.app import app, set_workbench_client
    set_workbench_client(WorkbenchClient(client=_wb_tc(tmp_path, monkeypatch)))
    return TestClient(app)


def test_workbench_page_renders(tmp_path, monkeypatch):
    tc = _web_client(tmp_path, monkeypatch)
    tc.post("/workbench/say", data={"text": "remember"})              # stage a proposal
    r = tc.get("/workbench")
    assert r.status_code == 200 and "Workbench" in r.text and "process_memory" in r.text


def test_workbench_approve_empty_200(tmp_path, monkeypatch):
    tc = _web_client(tmp_path, monkeypatch)
    tc.post("/workbench/say", data={"text": "remember"})
    # fetch the edit id via the workbench project directly for robustness:
    from alpha_web.app import _workbench
    pid = _workbench().get_project()["staged_edits"][0]["edit_id"]
    r = tc.post(f"/workbench/edits/{pid}/approve")
    assert r.status_code == 200 and r.text == ""                      # empty-200 row removal


def test_approve_error_banner_escapes_eid_xss(monkeypatch):
    # The approve-error branch reflects path param `eid` into a raw text/html fragment via html.escape.
    # A workbench client that RAISES on approve_edit triggers the error banner.
    # The reflected eid MUST be HTML-escaped (reflected-XSS guard), not interpolated raw.
    import urllib.parse
    from fastapi.testclient import TestClient
    from alpha_web.app import app, set_workbench_client

    class _BrokenClient:
        def approve_edit(self, eid):
            raise RuntimeError("workbench unavailable")

    set_workbench_client(_BrokenClient())
    tc = TestClient(app)
    payload = '"><img src=x onerror=alert(1)>'
    r = tc.post(f"/workbench/edits/{urllib.parse.quote(payload, safe='')}/approve")
    assert r.status_code == 200
    assert '"><img' not in r.text and "<img src=x" not in r.text      # no attribute-breakout / live tag
    assert "&lt;img" in r.text                                         # reflected, but escaped (inert)
