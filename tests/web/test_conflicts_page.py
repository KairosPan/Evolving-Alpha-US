import os

import pytest

pytest.importorskip("fastapi", reason="install: pip install -e '.[web,sonia]'")

from fastapi.testclient import TestClient

from alpha_web.sonia_client import SoniaClient


def _sonia_tc(tmp_path, monkeypatch):
    monkeypatch.setenv("ALPHA_CONFLICTS_DIR", str(tmp_path / "conflicts"))
    monkeypatch.setenv("ALPHA_LIVE_BRAIN_DIR", str(tmp_path / "brain"))
    monkeypatch.setenv("ALPHA_SESSIONS_DIR", str(tmp_path / "sessions"))
    monkeypatch.setenv("ALPHA_SONIA_PROVIDER", "mock")
    from sonia.app import create_app
    return TestClient(create_app())


def _seed(tmp_path):
    from alpha.meta.conflict_store import ConflictQueue
    return ConflictQueue(str(tmp_path / "conflicts")).add(
        op={"tool": "demote_memory", "args": {"lesson_id": "m1"}, "rationale": "weak"},
        provenance={"path": "self_study", "proposer": "refiner"},
        contested={"target_id": "m1"},
    )


def test_sonia_client_list_and_resolve(tmp_path, monkeypatch):
    held = _seed(tmp_path)
    sc = SoniaClient(client=_sonia_tc(tmp_path, monkeypatch))
    assert sc.list_conflicts()[0]["conflict_id"] == held.conflict_id
    assert sc.resolve_conflict(held.conflict_id, "keep_teaching")["resolved"] == held.conflict_id
    assert sc.list_conflicts() == []


def _web_client(tmp_path, monkeypatch):
    from alpha_web.app import app, set_sonia_client
    set_sonia_client(SoniaClient(client=_sonia_tc(tmp_path, monkeypatch)))
    return TestClient(app)


def test_conflicts_page_renders_held(tmp_path, monkeypatch):
    held = _seed(tmp_path)
    r = _web_client(tmp_path, monkeypatch).get("/conflicts")
    assert r.status_code == 200
    assert "Conflicts" in r.text                                  # nav label
    assert held.conflict_id in r.text and "self_study" in r.text  # the held conflict is rendered
    assert "demote_memory" in r.text


def test_conflicts_page_empty_state(tmp_path, monkeypatch):
    r = _web_client(tmp_path, monkeypatch).get("/conflicts")      # no conflicts seeded
    assert r.status_code == 200 and "Conflicts" in r.text         # renders an empty state, no 500


def test_resolve_returns_empty_200_and_removes(tmp_path, monkeypatch):
    held = _seed(tmp_path)
    tc = _web_client(tmp_path, monkeypatch)
    r = tc.post(f"/conflicts/{held.conflict_id}/resolve", data={"decision": "accept_self_study"})
    assert r.status_code == 200 and r.text == ""                 # empty -> htmx outerHTML-swaps the row away
    assert tc.get("/conflicts").json() if False else True        # (page is HTML; assert via the queue below)
    from alpha.meta.conflict_store import ConflictQueue
    assert ConflictQueue(str(tmp_path / "conflicts")).all() == []   # actually resolved in Sonia's queue
