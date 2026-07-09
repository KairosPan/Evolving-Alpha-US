import pytest
from fastapi.testclient import TestClient
from sonia.app import create_app


@pytest.fixture()
def client():
    return TestClient(create_app())


def _seed_and_propose(client, monkeypatch):
    """Chat, then call /propose so the assistant turn carries a proposed edit card.
    Returns (sid, mid, eid) where eid is the first proposed edit's id.
    Uses patch_skill so the propose succeeds (process_memory needs lesson_id + outcome fields)."""
    from alpha.harness.loader import load_seeds
    skid = load_seeds("seeds").skills.all()[0].skill_id

    # Chat turn — mock returns plain prose so chat stays prose-only
    monkeypatch.setenv("ALPHA_MOCK_RESPONSE", "let's discuss the skill")
    body = client.post("/chat", json={"text": "teach me"}).json()
    sid, mid = body["session_id"], body["assistant_message"]["message_id"]

    # /propose — mock returns a patch_skill op so the brain edit_count moves when applied
    monkeypatch.setenv(
        "ALPHA_MOCK_RESPONSE",
        '{"ops":[{"tool":"patch_skill","args":{"skill_id":"%s","notes":"tested by teaching"},'
        '"rationale":"r"}]}' % skid,
    )
    propose_body = client.post(f"/sessions/{sid}/messages/{mid}/propose").json()
    eid = propose_body["message"]["edits"][0]["edit_id"]
    return sid, mid, eid


def test_accept_then_apply_mutates_brain_and_snapshots(client, monkeypatch):
    sid, mid, eid = _seed_and_propose(client, monkeypatch)

    # accept the proposed edit
    client.post(f"/sessions/{sid}/edit/{eid}", json={"action": "accept"})

    # apply
    apply_resp = client.post(f"/sessions/{sid}/messages/{mid}/apply").json()
    assert apply_resp["applied"] == 1

    # brain mutated
    assert client.get("/healthz").json()["edit_count"] == 1

    # snapshot_before is set on the applied message
    sess = client.get(f"/sessions/{sid}").json()
    asst = next(m for m in sess["messages"] if m["message_id"] == mid)
    assert asst["snapshot_before"]


def test_apply_route_stamps_human_approver(client, monkeypatch):
    """Route-level pin (final review): reverting the route to `.apply(accepted)` without the
    human_approver kwarg must fail a test — the class-level pins alone don't cover the route."""
    import os
    from alpha.meta.store import LiveBrainStore

    sid, mid, eid = _seed_and_propose(client, monkeypatch)
    client.post(f"/sessions/{sid}/edit/{eid}", json={"action": "accept"})
    client.post(f"/sessions/{sid}/messages/{mid}/apply")

    _, log = LiveBrainStore(os.environ["ALPHA_LIVE_BRAIN_DIR"]).load()
    rec = log.records()[-1]
    assert rec.provenance.path == "teaching"
    assert rec.provenance.proposer == "sonia"
    assert rec.provenance.human_approver == "user"


def test_rollback_restores_pre_apply_brain(client, monkeypatch):
    sid, mid, eid = _seed_and_propose(client, monkeypatch)

    client.post(f"/sessions/{sid}/edit/{eid}", json={"action": "accept"})
    client.post(f"/sessions/{sid}/messages/{mid}/apply")
    assert client.get("/healthz").json()["edit_count"] == 1

    r = client.post(f"/sessions/{sid}/messages/{mid}/rollback")
    assert r.status_code == 200 and r.json()["ok"] is True
    assert client.get("/healthz").json()["edit_count"] == 0


def test_apply_with_no_accepted_edits_is_a_noop(client, monkeypatch):
    sid, mid, eid = _seed_and_propose(client, monkeypatch)

    # do NOT accept — leave the edit in "proposed" state
    apply_resp = client.post(f"/sessions/{sid}/messages/{mid}/apply").json()
    assert apply_resp["applied"] == 0
    assert client.get("/healthz").json()["edit_count"] == 0
