import pytest

pytest.importorskip("fastapi")

from alpha.harness.loader import load_seeds
from alpha_web import drawer
from fastapi.testclient import TestClient

from alpha_web import app as webapp
from alpha_web.sonia_client import SoniaClient
from sonia.app import create_app as create_sonia


# ── view-model units ─────────────────────────────────────────────────────────

def test_pending_view_none_session_is_empty():
    v = drawer.pending_view(None)
    assert v.session_id == "" and v.groups == [] and v.pending_count == 0


def test_pending_view_groups_by_message_and_counts_actionable():
    session = {"session_id": "s1", "messages": [
        {"message_id": "m1", "edits": [
            {"edit_id": "e1", "status": "accepted"},
            {"edit_id": "e2", "status": "proposed"}]},
        {"message_id": "m2", "edits": []},                     # no edits → skipped
        {"message_id": "m3", "edits": [{"edit_id": "e3", "status": "applied"}]},
    ]}
    v = drawer.pending_view(session)
    assert [g.message_id for g in v.groups] == ["m1", "m3"]
    assert v.groups[0].accepted == 1 and v.groups[0].applied is False
    assert v.groups[1].applied is True and v.groups[1].accepted == 0
    assert v.pending_count == 2                                 # e1 accepted + e2 proposed; e3 applied excluded


def test_brain_view_mirrors_six_components_in_rail_order():
    v = drawer.brain_view(load_seeds("seeds"))
    assert [c.key for c in v.components] == \
        ["doctrine", "memory", "workflow", "skills", "connector", "subagent"]


def test_brain_view_live_have_counts_stubs_do_not():
    state = load_seeds("seeds")
    v = drawer.brain_view(state)
    by_key = {c.key: c for c in v.components}
    assert by_key["skills"].count == len(state.skills.all())
    assert by_key["skills"].items == state.skills.all()
    assert by_key["skills"].is_stub is False and by_key["skills"].path == "/skills"
    for k in ("workflow", "connector", "subagent"):
        assert by_key[k].is_stub is True
        assert by_key[k].count is None and by_key[k].items == [] and by_key[k].blurb


# ── route integration ─────────────────────────────────────────────────────────

@pytest.fixture(autouse=True)
def _wire_sonia(monkeypatch):
    # Drive the real Sonia app in-process via an injected sync TestClient; mock copilot + isolated state.
    monkeypatch.setenv("ALPHA_SONIA_PROVIDER", "mock")
    monkeypatch.setenv("ALPHA_MOCK_RESPONSE", "lets discuss the squeeze setup")
    webapp.set_sonia_client(SoniaClient(client=TestClient(create_sonia())))
    yield
    webapp.set_sonia_client(None)


@pytest.fixture()
def client():
    return TestClient(webapp.create_app())


def test_home_renders_drawer_shell_and_six_brain_components(client):
    body = client.get("/").text
    assert 'id="agent-drawer"' in body
    assert 'id="pending"' in body and 'id="brain-panel"' in body
    assert 'class="drawer-resizer"' in body           # drag-resize hook (JS wired in Task 4)
    assert "drawer-collapse" in body                  # collapse hook
    panel = body.split('id="brain-panel"', 1)[1]      # isolate the brain panel from the left-rail nav
    for label in ("Doctrine", "Memory", "Workflow", "Skill", "Connector", "Subagent"):
        assert label in panel
    assert "read-only" in panel                       # stub marker
    assert "→ open full page" in panel                # live-component full-page link


def test_message_lands_edits_in_the_drawer_with_a_chip_not_inline(client, monkeypatch):
    sid_skill = load_seeds("seeds").skills.all()[0].skill_id
    monkeypatch.setenv("ALPHA_MOCK_RESPONSE",
        '{"ops":[{"tool":"patch_skill","args":{"skill_id":"%s","notes":"n"},"rationale":"r"}]}' % sid_skill)
    r = client.post("/evolve/message", data={"text": "patch it"})
    assert r.status_code == 200
    assert 'id="pending"' in r.text and 'hx-swap-oob="true"' in r.text     # drawer refreshes OOB
    assert 'id="brain-panel"' in r.text
    head = r.text.split('id="pending"', 1)[0]                              # chat turns + composer, before the OOB drawer
    assert "change-chip" in head                                          # bubble points at the drawer
    assert "edit-card" not in head                                        # …and no inline cards in the bubble
    assert "edit-card" in r.text and "patch_skill" in r.text              # the edit lives in the drawer's pending section


def test_apply_reflects_in_brain_panel_and_rollback_reverts(client, monkeypatch):
    import re
    monkeypatch.setenv("ALPHA_MOCK_RESPONSE",
        '{"ops":[{"tool":"process_memory",'
        '"args":{"lesson_id":"les-test-1","lesson":"NEW-TEST-LESSON","outcome":"principle"},'
        '"rationale":"teach test"}]}')
    m = client.post("/evolve/message", data={"text": "remember this"})
    sid = re.search(r'id="composer-session"[^>]*value="([^"]+)"', m.text).group(1)
    eid = re.search(r"/edit/([\w-]+)", m.text).group(1)
    # before apply: only proposed — not in the live brain mirror yet (the proposed edit card, which
    # DOES echo the lesson text, lives in #pending; check only the brain-panel portion)
    assert "NEW-TEST-LESSON" not in m.text.split('id="brain-panel"', 1)[1]
    # accept: the Apply form only appears once an edit is accepted, so scrape mid from THIS response
    acc = client.post(f"/evolve/{sid}/edit/{eid}", data={"action": "accept"})
    mid = re.search(r"/message/([\w-]+)/apply", acc.text).group(1)
    ap = client.post(f"/evolve/{sid}/message/{mid}/apply")
    assert 'id="brain-panel"' in ap.text and 'hx-swap-oob="true"' in ap.text
    assert "NEW-TEST-LESSON" in ap.text.split('id="brain-panel"', 1)[1]    # brain mirror reflects the applied lesson
    # rollback reverts the brain. The edit card stays status=applied (Sonia rollback restores the
    # brain snapshot, not edit status), so it still echoes the text in #pending — assert on the mirror.
    rb = client.post(f"/evolve/rollback/{sid}/{mid}")
    assert "NEW-TEST-LESSON" not in rb.text.split('id="brain-panel"', 1)[1]  # gone from the live brain


def test_drawer_mutations_stay_unavailable_when_sonia_down(client):
    webapp.set_sonia_client(SoniaClient(base_url="http://127.0.0.1:9", timeout=0.2))
    for r in (
        client.post("/evolve/s1/edit/e1", data={"action": "accept"}),
        client.post("/evolve/s1/message/m1/apply"),
        client.post("/evolve/rollback/s1/m1"),
    ):
        assert r.status_code == 200 and "unavailable" in r.text.lower()


import pathlib


def test_cockpit_js_wires_the_drawer_controls():
    js = pathlib.Path("alpha_web/static/cockpit.js").read_text("utf-8")
    assert "drawer-resizer" in js            # drag-to-resize handler
    assert "--drawer-w" in js                # sets the width custom property
    assert "drawer-collapse" in js           # collapse toggle
    assert "acc-toggle" in js                # delegated accordion handler
    assert "data-flash" in js or "change-chip" in js   # chip → drawer flash
