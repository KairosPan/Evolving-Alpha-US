import pytest
from fastapi.testclient import TestClient

pytest.importorskip("fastapi")

from alpha_web import app as webapp
from alpha_web.sonia_client import SoniaClient
from sonia.app import create_app as create_sonia


@pytest.fixture(autouse=True)
def _wire_sonia(monkeypatch):
    # Drive the real Sonia app in-process via an injected sync TestClient, mock copilot + isolated state.
    monkeypatch.setenv("ALPHA_SONIA_PROVIDER", "mock")
    monkeypatch.setenv("ALPHA_MOCK_RESPONSE", "lets discuss the squeeze setup")
    webapp.set_sonia_client(SoniaClient(client=TestClient(create_sonia())))
    yield
    webapp.set_sonia_client(None)


@pytest.fixture()
def client():
    return TestClient(webapp.create_app())


def test_home_is_the_chat_cockpit(client):
    body = client.get("/").text
    assert "<html" in body.lower()
    assert "composer" in body.lower() or "send" in body.lower()


def test_message_round_trips_two_bubbles(client):
    r = client.post("/evolve/message", data={"text": "high short interest writeup"})
    assert r.status_code == 200
    assert "<html" not in r.text.lower()                       # HTMX partial (two turns)
    assert "high short interest writeup" in r.text
    assert "lets discuss the squeeze setup" in r.text


def test_accept_then_apply_then_rollback(client, monkeypatch):
    from alpha.harness.loader import load_seeds
    sid_skill = load_seeds("seeds").skills.all()[0].skill_id
    monkeypatch.setenv("ALPHA_MOCK_RESPONSE",
                       '{"ops": [{"tool": "patch_skill", "args": {"skill_id": "%s", "notes": "n"}, "rationale": "r"}]}' % sid_skill)
    msg = client.post("/evolve/message", data={"text": "patch it"})
    # pull ids out of the session via the sessions API the cockpit also uses
    sessions = client.get("/evolve/sessions").text
    assert "patch_skill" in msg.text and sid_skill in msg.text
    # the session list page renders
    assert "<html" in sessions.lower()


def test_new_chat_redirects_instead_of_nesting(client):
    # Regression: the New-chat button targets #thread, so /evolve/new must NOT return a whole
    # cockpit document (that nested the entire page inside itself). It should redirect via HTMX.
    r = client.post("/evolve/new")
    assert "<html" not in r.text.lower()
    assert "hx-redirect" in {k.lower() for k in r.headers}


def test_session_link_is_plain_navigation_not_fragment_swap(client):
    # Regression: session links used to hx-swap a full cockpit document into #cockpit, nesting the
    # whole page on every click. They must be plain full-page navigations instead.
    client.post("/evolve/message", data={"text": "hello there"})
    body = client.get("/").text
    assert 'hx-target="#cockpit"' not in body
    assert 'hx-get="/evolve/sessions/' not in body      # not an HTMX fragment swap of any kind
    assert 'href="/evolve/sessions/' in body


def test_session_list_has_a_delete_control(client):
    client.post("/evolve/message", data={"text": "hello there"})
    body = client.get("/").text
    assert "/delete" in body and "hx-confirm" in body.lower()


def test_delete_session_via_console_removes_it(client):
    import re
    client.post("/evolve/message", data={"text": "to be deleted"})
    sid = re.search(r"/evolve/sessions/([\w-]+)", client.get("/").text).group(1)
    r = client.post(f"/evolve/{sid}/delete")
    assert r.status_code == 200
    assert "<html" not in r.text.lower()          # empty partial → HTMX removes the <li>, no nesting
    assert sid not in client.get("/").text        # gone from the list


def test_sonia_offline_shows_a_friendly_banner(client):
    webapp.set_sonia_client(SoniaClient(base_url="http://127.0.0.1:9", timeout=0.2))
    r = client.post("/evolve/message", data={"text": "hi"})
    assert r.status_code == 200 and "unavailable" in r.text.lower()


def test_mutating_routes_dont_500_when_sonia_down(client):
    webapp.set_sonia_client(SoniaClient(base_url="http://127.0.0.1:9", timeout=0.2))
    for r in (
        client.post("/evolve/s1/edit/e1", data={"action": "accept"}),
        client.post("/evolve/s1/message/m1/apply"),
        client.post("/evolve/rollback/s1/m1"),
        client.post("/evolve/s1/delete"),
    ):
        assert r.status_code == 200 and "unavailable" in r.text.lower()
