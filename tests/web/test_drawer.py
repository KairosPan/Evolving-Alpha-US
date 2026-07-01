import pytest

pytest.importorskip("fastapi")

from alpha.harness.loader import load_seeds
from alpha_web import drawer


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
