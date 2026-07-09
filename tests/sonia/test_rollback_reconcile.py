"""Revert reconciles derived state (charter conformance 2026-07-09): after /rollback, session
records stop asserting the reverted seqs — applied_seqs cleared, edit statuses reset — so the
teaching turn is recoverable (/propose no longer 409s forever)."""
import pytest
from fastapi.testclient import TestClient

from sonia.app import create_app


@pytest.fixture()
def client():
    return TestClient(create_app())


def _seed_propose_accept_apply(client, monkeypatch):
    from alpha.harness.loader import load_seeds
    skid = load_seeds("seeds").skills.all()[0].skill_id

    monkeypatch.setenv("ALPHA_MOCK_RESPONSE", "prose turn")
    body = client.post("/chat", json={"text": "teach me"}).json()
    sid, mid = body["session_id"], body["assistant_message"]["message_id"]

    monkeypatch.setenv(
        "ALPHA_MOCK_RESPONSE",
        '{"ops":[{"tool":"patch_skill","args":{"skill_id":"%s","notes":"taught"},'
        '"rationale":"r"}]}' % skid)
    eid = client.post(f"/sessions/{sid}/messages/{mid}/propose").json()["message"]["edits"][0]["edit_id"]
    client.post(f"/sessions/{sid}/edit/{eid}", json={"action": "accept"})
    client.post(f"/sessions/{sid}/messages/{mid}/apply")
    return sid, mid


def test_rollback_clears_applied_seqs_and_resets_edit_status(client, monkeypatch):
    sid, mid = _seed_propose_accept_apply(client, monkeypatch)
    assert client.get("/healthz").json()["edit_count"] == 1

    client.post(f"/sessions/{sid}/messages/{mid}/rollback")
    assert client.get("/healthz").json()["edit_count"] == 0

    sess = client.get(f"/sessions/{sid}").json()
    msg = next(m for m in sess["messages"] if m["message_id"] == mid)
    assert msg["applied_seqs"] == []                       # the dead-end assertion is gone
    edit = msg["edits"][0]
    assert edit["status"] == "accepted" and edit["applied_seq"] is None
    assert edit["apply_reason"] == "rolled back"


def test_propose_is_recoverable_after_rollback(client, monkeypatch):
    sid, mid = _seed_propose_accept_apply(client, monkeypatch)
    client.post(f"/sessions/{sid}/messages/{mid}/rollback")

    monkeypatch.setenv("ALPHA_MOCK_RESPONSE", '{"no_edit": true, "reason": "nothing new"}')
    r = client.post(f"/sessions/{sid}/messages/{mid}/propose")
    assert r.status_code == 200                            # was a permanent 409 before the fix
