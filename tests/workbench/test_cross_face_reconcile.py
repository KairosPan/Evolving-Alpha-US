"""Cross-face revert reconcile (2026-07-09 review major): both faces share ONE brain, so a restore
must heal derived state (sonia sessions' applied_seqs, else /propose 409s forever).

A7 (2026-07-13): the WORKER-staged leg of this flow is retired (the worker no longer proposes, so
there are no workbench staged edits to heal). The surviving live path — a legitimate landing
(user_direct via sonia /edit, or a Sonia teaching landing) recorded in a sonia session, then
reverted through the sonia /snapshots lever — still reconciles, and is what these tests now pin. The
pure reconcile helpers are unit-covered in tests/meta/test_reconcile.py."""
import pytest
pytest.importorskip("fastapi")

from fastapi.testclient import TestClient


def _env(tmp_path, monkeypatch):
    monkeypatch.setenv("ALPHA_LIVE_BRAIN_DIR", str(tmp_path / "brain"))
    monkeypatch.setenv("ALPHA_PROJECTS_DB", str(tmp_path / "state.db"))
    monkeypatch.setenv("ALPHA_WORKSPACE_DIR", str(tmp_path / "ws"))
    monkeypatch.setenv("ALPHA_SESSIONS_DIR", str(tmp_path / "sessions"))
    monkeypatch.setenv("ALPHA_SONIA_PROVIDER", "mock")
    monkeypatch.setenv("ALPHA_MOCK_RESPONSE", "prose")


def test_sonia_restore_heals_sonia_session(tmp_path, monkeypatch):
    _env(tmp_path, monkeypatch)
    from sonia.app import create_app as sonia_app
    sonia = TestClient(sonia_app())

    # land a legitimate user_direct edit (the User's own hand) → live seq 0 + a snapshot
    r = sonia.post("/edit", json={"tool": "process_memory",
                                  "args": {"lesson_id": "u1", "phases": ["trend"],
                                           "outcome": "win", "lesson": "user landed this"},
                                  "rationale": "direct edit"})
    assert r.status_code == 200 and r.json()["applied"] is True
    assert sonia.get("/healthz").json()["edit_count"] == 1
    snap = sonia.get("/snapshots").json()[0]            # the bare snapshot name (restore route wants it)

    # seed a sonia session asserting that same seq was applied through it
    from alpha.meta.models import Message, Session, new_message_id, new_session_id, now_iso
    from alpha.meta.store import SessionStore
    sstore = SessionStore(str(tmp_path / "sessions"))
    msg = Message(message_id=new_message_id(), role="assistant", created_at=now_iso(),
                  applied_seqs=[0])
    sess = Session(session_id=new_session_id(), created_at=now_iso(), messages=[msg])
    sstore.put(sess)

    # revert through the sonia /snapshots lever → the sweep heals the session's applied_seqs
    rr = sonia.post(f"/snapshots/{snap}/restore")
    assert rr.status_code == 200 and rr.json()["ok"] is True
    assert sonia.get("/healthz").json()["edit_count"] == 0
    assert sstore.get(sess.session_id).messages[0].applied_seqs == []   # cross-face heal


def test_snapshot_restore_rejects_traversal_names(tmp_path, monkeypatch):
    """NOTE: Starlette percent-decodes before routing, so an encoded ../ never reaches the
    handler ({name} can't contain '/') — the router 404s. The in-handler is_relative_to guard is
    unreachable defense-in-depth via HTTP; its store-level twin is pinned directly in
    tests/meta/test_proposal_store_guard.py. This test pins the routed behavior only."""
    _env(tmp_path, monkeypatch)
    from sonia.app import create_app as sonia_app
    sonia = TestClient(sonia_app())
    r = sonia.post("/snapshots/%2e%2e%2fbrain/restore")
    assert r.status_code == 404                            # router-level rejection
    r0 = sonia.post("/snapshots/anything/restore")
    assert r0.status_code == 400                           # no history dir yet → invalid
    (tmp_path / "brain" / "history").mkdir(parents=True)
    r2 = sonia.post("/snapshots/no-such-snapshot/restore")
    assert r2.status_code == 404                           # handler-level not-found
