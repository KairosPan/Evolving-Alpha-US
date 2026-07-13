"""A8 part (c): the teaching /apply staleness pin — what was previewed is what lands.

/propose pins the previewed brain-content hash on the message; /apply refuses (409, re-preview) if
the live brain moved between preview and apply. Byte-identical when previewed_hash is empty."""
import os

import pytest
from fastapi.testclient import TestClient

from alpha.meta.store import SessionStore
from sonia.app import create_app


@pytest.fixture()
def client():
    return TestClient(create_app())


def _propose_patch(client, monkeypatch):
    """Chat + /propose a patch_skill edit; returns (sid, mid, eid). Mirrors test_apply."""
    from alpha.harness.loader import load_seeds
    skid = load_seeds("seeds").skills.all()[0].skill_id
    monkeypatch.setenv("ALPHA_MOCK_RESPONSE", "let's discuss the skill")
    body = client.post("/chat", json={"text": "teach me"}).json()
    sid, mid = body["session_id"], body["assistant_message"]["message_id"]
    monkeypatch.setenv(
        "ALPHA_MOCK_RESPONSE",
        '{"ops":[{"tool":"patch_skill","args":{"skill_id":"%s","notes":"t"},"rationale":"r"}]}' % skid)
    resp = client.post(f"/sessions/{sid}/messages/{mid}/propose").json()
    eid = resp["message"]["edits"][0]["edit_id"]
    return sid, mid, eid


def test_propose_pins_the_previewed_hash(client, monkeypatch):
    sid, mid, _eid = _propose_patch(client, monkeypatch)
    sess = client.get(f"/sessions/{sid}").json()
    asst = next(m for m in sess["messages"] if m["message_id"] == mid)
    assert asst["previewed_hash"]                         # the pin is set on a successful propose


def test_apply_against_unchanged_brain_lands(client, monkeypatch):
    sid, mid, eid = _propose_patch(client, monkeypatch)
    client.post(f"/sessions/{sid}/edit/{eid}", json={"action": "accept"})
    r = client.post(f"/sessions/{sid}/messages/{mid}/apply")
    assert r.status_code == 200 and r.json()["applied"] == 1
    assert client.get("/healthz").json()["edit_count"] == 1


def test_apply_refuses_when_brain_moved_since_preview(client, monkeypatch):
    sid, mid, eid = _propose_patch(client, monkeypatch)
    client.post(f"/sessions/{sid}/edit/{eid}", json={"action": "accept"})
    # the brain moves between preview and apply: a user-direct edit lands a new lesson
    direct = client.post("/edit", json={"tool": "process_memory",
                                        "args": {"lesson_id": "moved", "outcome": "principle",
                                                 "lesson": "the base shifted"},
                                        "rationale": "shift the base"})
    assert direct.status_code == 200
    assert client.get("/healthz").json()["edit_count"] == 1

    r = client.post(f"/sessions/{sid}/messages/{mid}/apply")
    assert r.status_code == 409 and "stale" in r.json()["error"]
    assert client.get("/healthz").json()["edit_count"] == 1     # the stale edit did NOT land


def test_empty_pin_is_byte_identical_legacy(client, monkeypatch):
    """A message with no pin (legacy, or a card built outside /propose) applies unchanged."""
    sid, mid, eid = _propose_patch(client, monkeypatch)
    # simulate a legacy message: clear the pin on the persisted session
    sstore = SessionStore(os.environ["ALPHA_SESSIONS_DIR"])
    sess = sstore.get(sid)
    for m in sess.messages:
        if m.message_id == mid:
            m.previewed_hash = ""
    sstore.put(sess)
    client.post(f"/sessions/{sid}/edit/{eid}", json={"action": "accept"})
    r = client.post(f"/sessions/{sid}/messages/{mid}/apply")
    assert r.status_code == 200 and r.json()["applied"] == 1
