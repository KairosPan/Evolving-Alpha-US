from alpha.meta.models import (Attachment, Message, Session, new_message_id, now_iso)


def test_attachment_and_message_roundtrip():
    a = Attachment(kind="file", name="notes.md", text="hello")
    m = Message(message_id="m1", role="user", text="teach", attachments=[a])
    back = Message.model_validate_json(m.model_dump_json())
    assert back.attachments[0].name == "notes.md" and back.role == "user"
    assert back.edits == [] and back.directions == [] and back.snapshot_before is None


def test_session_thread_roundtrip_and_defaults():
    s = Session(session_id="s1", title="t", messages=[Message(message_id="m1", role="assistant")])
    back = Session.model_validate_json(s.model_dump_json())
    assert back.title == "t" and back.messages[0].role == "assistant"
    assert Session(session_id="s2").messages == [] and Session(session_id="s2").title == ""


def test_id_and_time_helpers():
    assert len(new_message_id()) == 8 and new_message_id() != new_message_id()
    assert "T" in now_iso()
