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


def test_chat_is_graceful_when_copilot_unavailable(client, monkeypatch):
    monkeypatch.delenv("ALPHA_SONIA_PROVIDER", raising=False)        # default openai_compat
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    body = client.post("/chat", json={"text": "hi"}).json()
    assert "couldn't respond" in body["assistant_message"]["text"].lower()
    assert body["user_message"]["text"] == "hi"                      # user turn preserved


def test_chat_never_returns_edit_cards_now(client, monkeypatch):
    from alpha.harness.loader import load_seeds
    sid = load_seeds("seeds").skills.all()[0].skill_id
    monkeypatch.setenv("ALPHA_MOCK_RESPONSE",
                       '{"ops": [{"tool": "patch_skill", "args": {"skill_id": "%s"}, "rationale": "r"}]}' % sid)
    body = client.post("/chat", json={"text": "patch it"}).json()
    assert body["assistant_message"]["edits"] == []      # chat is prose-only; edits come from /propose


def _seed_turn(client, mock, monkeypatch):
    """Create a session with one user+assistant turn; return (sid, assistant message_id)."""
    monkeypatch.setenv("ALPHA_MOCK_RESPONSE", mock)
    body = client.post("/chat", json={"text": "teach me"}).json()
    return body["session_id"], body["assistant_message"]["message_id"]


def test_propose_crystallizes_ops_into_edit_cards(client, monkeypatch):
    from alpha.harness.loader import load_seeds
    skid = load_seeds("seeds").skills.all()[0].skill_id
    sid, mid = _seed_turn(client, "let's discuss", monkeypatch)
    monkeypatch.setenv("ALPHA_MOCK_RESPONSE",
        '{"ops":[{"tool":"patch_skill","args":{"skill_id":"%s","notes":"n"},"rationale":"r"}]}' % skid)
    body = client.post(f"/sessions/{sid}/messages/{mid}/propose").json()
    edits = body["message"]["edits"]
    assert len(edits) == 1 and edits[0]["status"] == "proposed" and edits[0]["tool"] == "patch_skill"
    assert body["message"]["proposal_note"] == ""
    # read-only: proposing does not mutate the live brain
    assert client.get("/healthz").json()["edit_count"] == 0


def test_propose_no_edit_sets_a_visible_note(client, monkeypatch):
    sid, mid = _seed_turn(client, "let's discuss", monkeypatch)
    monkeypatch.setenv("ALPHA_MOCK_RESPONSE", '{"no_edit": true, "reason": "still clarifying the window"}')
    body = client.post(f"/sessions/{sid}/messages/{mid}/propose").json()
    assert body["message"]["edits"] == []
    assert body["message"]["proposal_note"] == "still clarifying the window"


def test_propose_redline_op_becomes_a_failed_card(client, monkeypatch):
    sid, mid = _seed_turn(client, "let's discuss", monkeypatch)
    monkeypatch.setenv("ALPHA_MOCK_RESPONSE",
        '{"ops":[{"tool":"patch_skill","args":{"skill_id":"missing"},"rationale":"r"}]}')
    body = client.post(f"/sessions/{sid}/messages/{mid}/propose").json()
    assert body["message"]["edits"][0]["status"] == "failed" and body["message"]["edits"][0]["apply_reason"]


def test_propose_on_missing_message_is_404(client):
    sid = client.post("/sessions/new").json()["session_id"]
    assert client.post(f"/sessions/{sid}/messages/nope/propose").status_code == 404
