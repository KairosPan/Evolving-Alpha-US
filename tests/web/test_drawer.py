import pathlib

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
    assert v.last_applied == ""                                 # no applied groups → empty string


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
    assert v.last_applied == "m3"                               # m3 is the only (and last) applied group


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


# NOTE: test_message_lands_edits_in_the_drawer_with_a_chip_not_inline and
# test_apply_reflects_in_brain_panel_and_rollback_reverts were removed in Task 3
# (chat is now prose-only and no longer seeds edit cards via ops blocks).
# They will be replaced in Task 4 when /propose can seed edits into the drawer.

def test_message_oob_updates_drawer_and_brain_panel(client, monkeypatch):
    # Chat is prose-only: the drawer and brain panel still refresh OOB after every message,
    # even without edit cards (the pending section is empty).
    r = client.post("/evolve/message", data={"text": "discuss setup"})
    assert r.status_code == 200
    assert 'id="pending"' in r.text and 'hx-swap-oob="true"' in r.text     # drawer refreshes OOB
    assert 'id="brain-panel"' in r.text


def test_drawer_mutations_stay_unavailable_when_sonia_down(client):
    webapp.set_sonia_client(SoniaClient(base_url="http://127.0.0.1:9", timeout=0.2))
    for r in (
        client.post("/evolve/s1/edit/e1", data={"action": "accept"}),
        client.post("/evolve/s1/message/m1/apply"),
        client.post("/evolve/rollback/s1/m1"),
    ):
        assert r.status_code == 200 and "unavailable" in r.text.lower()


def test_cockpit_js_wires_the_drawer_controls():
    js = (pathlib.Path(__file__).resolve().parents[2] / "alpha_web" / "static" / "cockpit.js").read_text("utf-8")
    assert "drawer-resizer" in js            # drag-to-resize handler
    assert "--drawer-w" in js                # sets the width custom property
    assert "drawer-collapse" in js           # collapse toggle
    assert "acc-toggle" in js                # delegated accordion handler
    assert "data-flash" in js or "change-chip" in js   # chip → drawer flash
