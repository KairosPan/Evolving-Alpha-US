import pytest
from fastapi.testclient import TestClient
from sonia.app import create_app


@pytest.fixture()
def client():
    return TestClient(create_app())


def test_healthz_reports_seed_brain(client):
    r = client.get("/healthz")
    assert r.status_code == 200 and r.json() == {"ok": True, "brain_live": False, "edit_count": 0}


def test_new_then_list_sessions(client):
    sid = client.post("/sessions/new").json()["session_id"]
    assert any(s["session_id"] == sid for s in client.get("/sessions").json())


def test_delete_session_removes_from_list_and_is_idempotent(client):
    sid = client.post("/sessions/new").json()["session_id"]
    assert any(s["session_id"] == sid for s in client.get("/sessions").json())
    r = client.post(f"/sessions/{sid}/delete")
    assert r.status_code == 200 and r.json()["deleted"] == sid
    assert all(s["session_id"] != sid for s in client.get("/sessions").json())
    assert client.post(f"/sessions/{sid}/delete").status_code == 200      # idempotent


def test_chat_appends_two_turns_and_persists(client):
    r = client.post("/chat", json={"text": "high short interest writeup"})
    body = r.json()
    assert r.status_code == 200
    assert body["user_message"]["text"] == "high short interest writeup"
    assert body["assistant_message"]["role"] == "assistant" and body["assistant_message"]["text"]
    loaded = client.get(f"/sessions/{body['session_id']}").json()
    assert [m["role"] for m in loaded["messages"]] == ["user", "assistant"]
    assert loaded["title"]                                         # derived from first user message


def test_chat_with_ops_returns_edit_cards(client, monkeypatch):
    from alpha.harness.loader import load_seeds
    sid = load_seeds("seeds").skills.all()[0].skill_id
    monkeypatch.setenv("ALPHA_MOCK_RESPONSE",
                       '{"ops": [{"tool": "patch_skill", "args": {"skill_id": "%s", "notes": "n"}, "rationale": "r"}]}' % sid)
    body = client.post("/chat", json={"text": "patch it"}).json()
    assert body["assistant_message"]["edits"][0]["status"] == "proposed"


def test_chat_is_graceful_when_copilot_unavailable(client, monkeypatch):
    monkeypatch.delenv("ALPHA_SONIA_PROVIDER", raising=False)        # default openai_compat
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    body = client.post("/chat", json={"text": "hi"}).json()
    assert "couldn't respond" in body["assistant_message"]["text"].lower()
    assert body["user_message"]["text"] == "hi"                      # user turn preserved
