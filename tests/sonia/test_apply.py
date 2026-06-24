import pytest
from fastapi.testclient import TestClient
from alpha.harness.loader import load_seeds
from sonia.app import create_app


@pytest.fixture()
def client():
    return TestClient(create_app())


def _seed_one_edit(client, monkeypatch):
    sid_skill = load_seeds("seeds").skills.all()[0].skill_id
    monkeypatch.setenv("ALPHA_MOCK_RESPONSE",
                       '{"ops": [{"tool": "patch_skill", "args": {"skill_id": "%s", "notes": "taught"}, "rationale": "r"}]}' % sid_skill)
    body = client.post("/chat", json={"text": "patch it"}).json()
    sid = body["session_id"]
    mid = body["assistant_message"]["message_id"]
    eid = body["assistant_message"]["edits"][0]["edit_id"]
    return sid, mid, eid, sid_skill


def test_accept_then_apply_mutates_brain_and_snapshots(client, monkeypatch):
    sid, mid, eid, sid_skill = _seed_one_edit(client, monkeypatch)
    assert client.post(f"/sessions/{sid}/edit/{eid}", json={"action": "accept"}).json()["status"] == "accepted"
    r = client.post(f"/sessions/{sid}/messages/{mid}/apply").json()
    assert r["applied"] == 1
    assert client.get("/healthz").json()["edit_count"] == 1            # live brain mutated
    assert client.get(f"/sessions/{sid}").json()["messages"][1]["snapshot_before"]


def test_rollback_restores_pre_apply_brain(client, monkeypatch):
    sid, mid, eid, _ = _seed_one_edit(client, monkeypatch)
    client.post(f"/sessions/{sid}/edit/{eid}", json={"action": "accept"})
    client.post(f"/sessions/{sid}/messages/{mid}/apply")
    assert client.post(f"/sessions/{sid}/messages/{mid}/rollback").json()["ok"] is True
    assert client.get("/healthz").json()["edit_count"] == 0            # rolled back


def test_apply_with_no_accepted_edits_is_a_noop(client, monkeypatch):
    sid, mid, _eid, _ = _seed_one_edit(client, monkeypatch)            # never accept
    assert client.post(f"/sessions/{sid}/messages/{mid}/apply").json()["applied"] == 0
    assert client.get("/healthz").json()["edit_count"] == 0
