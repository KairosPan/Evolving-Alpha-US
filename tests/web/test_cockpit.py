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


def test_assistant_markdown_is_rendered_not_a_wall_of_asterisks(client, monkeypatch):
    # Regression for the messy cockpit output: Sonia replies in markdown, so the bubble must show
    # real <strong>/<ol>, never literal ** markers run together into one paragraph.
    monkeypatch.setenv("ALPHA_MOCK_RESPONSE",
                       "Storage names:\n\n1. **PSTG** breakout\n2. **NTAP** pullback")
    r = client.post("/evolve/message", data={"text": "storage market"})
    assert r.status_code == 200
    assert "<strong>PSTG</strong>" in r.text
    assert "<ol>" in r.text and "<li>" in r.text
    assert "**PSTG**" not in r.text


def test_user_text_stays_literal_and_assistant_html_is_safe(client, monkeypatch):
    # User-typed text is shown verbatim (we don't markdown-render it); model-authored HTML is escaped.
    monkeypatch.setenv("ALPHA_MOCK_RESPONSE", "<script>alert(1)</script> and **safe bold**")
    r = client.post("/evolve/message", data={"text": "**user keeps stars**"})
    assert "**user keeps stars**" in r.text                 # user side: not turned into <strong>
    assert "<script>alert(1)</script>" not in r.text        # assistant side: never injected
    assert "<strong>safe bold</strong>" in r.text           # assistant markdown still renders


def test_message_renders_and_sessions_list_is_accessible(client, monkeypatch):
    # Chat is now prose-only (no inline edit cards from ops blocks).
    # Verify the message endpoint works and the session list page renders.
    msg = client.post("/evolve/message", data={"text": "patch it"})
    sessions = client.get("/evolve/sessions").text
    assert msg.status_code == 200
    # the session list page renders
    assert "<html" in sessions.lower()


def test_message_threads_session_id_back_to_composer(client):
    # Regression: after a message, the composer's hidden session_id must be updated to the (possibly
    # newly created) session. Otherwise every following message posts an empty session_id and Sonia
    # spawns a NEW session each time — splitting one conversation into many.
    import re
    r = client.post("/evolve/message", data={"text": "first turn"})
    assert r.status_code == 200
    assert "hx-swap-oob" in r.text                          # carries an out-of-band composer update
    m = re.search(r'id="composer-session"[^>]*value="([^"]+)"', r.text)
    assert m and m.group(1), "no session_id threaded back to the composer"
    assert 'id="composer-session"' in client.get("/").text  # composer carries the matching id


def test_consecutive_messages_stay_in_one_session(client):
    # End-to-end: with the threaded session_id (as the browser sends after the OOB swap), a second
    # message lands in the SAME session instead of starting a new one.
    import re
    r1 = client.post("/evolve/message", data={"text": "build me an agent"})
    sid = re.search(r'id="composer-session"[^>]*value="([^"]+)"', r1.text).group(1)
    r2 = client.post("/evolve/message", data={"text": "execute", "session_id": sid})
    sid2 = re.search(r'id="composer-session"[^>]*value="([^"]+)"', r2.text).group(1)
    assert sid2 == sid                                       # not split into a new session
    page = client.get(f"/evolve/sessions/{sid}").text
    assert "build me an agent" in page and "execute" in page


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
