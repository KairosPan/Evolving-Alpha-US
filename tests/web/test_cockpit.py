import pytest
from fastapi.testclient import TestClient
from alpha_web.app import create_app


@pytest.fixture()
def client():
    return TestClient(create_app())


def test_cockpit_is_home_and_shows_input_panel(client):
    body = client.get("/").text
    assert "Teach" in body and ("paste" in body.lower() or "url" in body.lower())


def test_seed_baseline_badge_shows_when_store_empty(client):
    body = client.get("/deck").text
    assert "seed baseline" in body.lower()


def test_ingest_text_returns_direction_cards(client, monkeypatch):
    monkeypatch.setenv("ALPHA_REFINER_PROVIDER", "mock")
    monkeypatch.setenv("ALPHA_MOCK_RESPONSE", '{"directions": [{"title": "lean into squeezes"}]}')
    r = client.post("/evolve/ingest", data={"text": "High short interest writeup"})
    assert r.status_code == 200 and "lean into squeezes" in r.text
    assert "<html" not in r.text.lower()        # partial only


def test_ingest_missing_key_shows_graceful_panel(client, monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.setenv("ALPHA_REFINER_PROVIDER", "anthropic")
    r = client.post("/evolve/ingest", data={"text": "x"})
    assert r.status_code == 200 and ("set your key" in r.text.lower() or "mock mode" in r.text.lower())


def test_direction_expands_to_edit_queue(client, monkeypatch):
    from alpha.harness.loader import load_seeds
    sid_skill = load_seeds("seeds").skills.all()[0].skill_id
    monkeypatch.setenv("ALPHA_REFINER_PROVIDER", "mock")
    monkeypatch.setenv("ALPHA_MOCK_RESPONSE", '{"directions": [{"title": "tighten"}]}')
    ingest = client.post("/evolve/ingest", data={"text": "writeup"})
    # grab the session + direction ids the server just created
    from alpha.meta.store import SessionStore
    import os
    store = SessionStore(os.environ["ALPHA_SESSIONS_DIR"])
    sess = store.list()[0]
    monkeypatch.setenv("ALPHA_MOCK_RESPONSE",
                       '{"ops": [{"tool": "patch_skill", "args": {"skill_id": "%s", "notes": "n"}, "rationale": "r"}]}' % sid_skill)
    r = client.post(f"/evolve/{sess.session_id}/direction",
                    data={"direction_id": sess.directions[0].direction_id, "comment": ""})
    assert r.status_code == 200 and "patch_skill" in r.text and sid_skill in r.text
    assert store.get(sess.session_id).edits                      # persisted


def _seed_session_with_one_edit(client, monkeypatch):
    from alpha.harness.loader import load_seeds
    sid_skill = load_seeds("seeds").skills.all()[0].skill_id
    monkeypatch.setenv("ALPHA_REFINER_PROVIDER", "mock")
    monkeypatch.setenv("ALPHA_MOCK_RESPONSE", '{"directions": [{"title": "t"}]}')
    client.post("/evolve/ingest", data={"text": "writeup"})
    import os
    from alpha.meta.store import SessionStore
    store = SessionStore(os.environ["ALPHA_SESSIONS_DIR"])
    sess = store.list()[0]
    monkeypatch.setenv("ALPHA_MOCK_RESPONSE",
                       '{"ops": [{"tool": "patch_skill", "args": {"skill_id": "%s", "notes": "n"}, "rationale": "r"}]}' % sid_skill)
    client.post(f"/evolve/{sess.session_id}/direction",
                data={"direction_id": sess.directions[0].direction_id, "comment": ""})
    return store, store.get(sess.session_id), sid_skill


def test_accept_marks_row_accepted(client, monkeypatch):
    store, sess, _ = _seed_session_with_one_edit(client, monkeypatch)
    eid = sess.edits[0].edit_id
    r = client.post(f"/evolve/{sess.session_id}/edit/{eid}", data={"action": "accept"})
    assert r.status_code == 200 and "accepted" in r.text
    assert store.get(sess.session_id).edits[0].status == "accepted"


def test_comment_reproposes_row_keeping_id(client, monkeypatch):
    store, sess, sid_skill = _seed_session_with_one_edit(client, monkeypatch)
    eid = sess.edits[0].edit_id
    monkeypatch.setenv("ALPHA_MOCK_RESPONSE",
                       '{"ops": [{"tool": "patch_skill", "args": {"skill_id": "%s", "notes": "revised"}, "rationale": "r2"}]}' % sid_skill)
    r = client.post(f"/evolve/{sess.session_id}/edit/{eid}", data={"action": "comment", "comment": "tighter"})
    assert r.status_code == 200 and "revised" in r.text
    assert store.get(sess.session_id).edits[0].edit_id == eid


def test_apply_mutates_live_brain_and_finalizes_session(client, monkeypatch):
    store, sess, sid_skill = _seed_session_with_one_edit(client, monkeypatch)
    eid = sess.edits[0].edit_id
    client.post(f"/evolve/{sess.session_id}/edit/{eid}", data={"action": "accept"})
    r = client.post(f"/evolve/{sess.session_id}/apply")
    assert r.status_code == 200 and "applied" in r.text.lower()
    final = store.get(sess.session_id)
    assert final.status == "applied" and final.applied_seqs == [0]
    # the live brain now reflects the edit
    from alpha.meta.store import LiveBrainStore
    import os
    h, _ = LiveBrainStore(os.environ["ALPHA_LIVE_BRAIN_DIR"]).load()
    assert h.skills.get(sid_skill).notes == "n"


def test_apply_on_already_applied_session_is_rejected(client, monkeypatch):
    store, sess, _ = _seed_session_with_one_edit(client, monkeypatch)
    sess.status = "applied"; store.put(sess)
    r = client.post(f"/evolve/{sess.session_id}/apply")
    assert r.status_code == 200 and "not open" in r.text.lower()
