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
        '{"lesson_id": "m1", "outcome": "win", "lesson": "x"}, "rationale": "learned"}}',
        "I cannot stage that."]),
        agent=MockLLMClient("{}"),
        source=source)
    return TestClient(create_app())


def test_workbench_client_converse_stages_nothing(tmp_path, monkeypatch):
    # A7 (charter First Founding Principle: "Kairos does not propose at all"): converse stages no
    # H edit, and the approve endpoint is retired (410 → the sync client raises).
    import httpx
    wc = WorkbenchClient(client=_wb_tc(tmp_path, monkeypatch))
    r = wc.converse("remember")
    assert r["staged_edits"] == []
    assert wc.get_project()["project_id"] == "default"
    with pytest.raises(httpx.HTTPStatusError):
        wc.approve_edit("any-id")                                     # retired → 410


def _web_client(tmp_path, monkeypatch):
    from alpha_web.app import app, set_workbench_client
    set_workbench_client(WorkbenchClient(client=_wb_tc(tmp_path, monkeypatch)))
    return TestClient(app)


def test_workbench_page_renders_with_no_proposals(tmp_path, monkeypatch):
    tc = _web_client(tmp_path, monkeypatch)
    tc.post("/workbench/say", data={"text": "remember"})              # A7: stages nothing
    r = tc.get("/workbench")
    assert r.status_code == 200 and "Workbench" in r.text
    assert "No pending proposals" in r.text                           # the empty-state copy
    assert "process_memory" not in r.text                             # no staged edit rendered


def test_workbench_approve_proxy_never_500s(tmp_path, monkeypatch):
    # The worker cannot stage, so the approve endpoint is retired (410). The alpha_web proxy must
    # still return 200 (an "unavailable" banner), never a 500 — HTMX degrades gracefully.
    tc = _web_client(tmp_path, monkeypatch)
    tc.post("/workbench/say", data={"text": "remember"})
    r = tc.post("/workbench/edits/any-id/approve")
    assert r.status_code == 200 and "could not approve" in r.text


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
