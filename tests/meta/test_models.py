from alpha.meta.models import (
    LessonSource, Message, ProposedDirection, ProposedEdit, Session,
    new_session_id, new_edit_id,
)


def test_lesson_source_roundtrips():
    s = LessonSource(kind="text", title="t", text="body")
    assert LessonSource.model_validate(s.model_dump()) == s
    assert s.url is None


def test_proposed_edit_defaults_and_roundtrip():
    e = ProposedEdit(edit_id="e1", tool="write_skill", args={"skill_id": "x"})
    assert e.status == "proposed" and e.target_id is None and e.applied_seq is None
    assert ProposedEdit.model_validate(e.model_dump()) == e


def test_session_holds_nested_models_and_roundtrips():
    sess = Session(
        session_id="s1",
        messages=[Message(
            message_id="m1",
            role="assistant",
            directions=[ProposedDirection(direction_id="d1", title="lean into squeezes")],
            edits=[ProposedEdit(edit_id="e1", tool="patch_skill", args={"skill_id": "x"})],
        )],
    )
    assert sess.status == "open"
    again = Session.model_validate(sess.model_dump())
    assert again == sess and again.messages[0].edits[0].tool == "patch_skill"


def test_id_helpers_are_unique_and_sortable():
    a, b = new_session_id(), new_session_id()
    assert a != b and len(a) > 8
    assert new_edit_id() != new_edit_id()
