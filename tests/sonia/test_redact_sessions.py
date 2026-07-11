"""D1: sonia session persistence redacts pasted secrets; ProposedEdit payloads survive."""
from alpha.meta.models import Session, Message, Attachment
from alpha.meta.store import SessionStore

SECRET = "tok-pasted-secret-99999"


def test_session_put_redacts_text_and_attachments(tmp_path, monkeypatch):
    monkeypatch.setenv("PASTED_TOKEN", SECRET)
    store = SessionStore(root=tmp_path)
    s = Session(session_id="s1", created_at="2026-07-10T00:00:00Z", title="t",
                messages=[Message(message_id="m1", role="user", created_at="c",
                                  text=f"my key is {SECRET}",
                                  attachments=[Attachment(kind="file", name="f", mime="text/plain",
                                                          text=f"body {SECRET}")])])
    p = store.put(s)
    raw = p.read_text()
    assert SECRET not in raw and "[REDACTED:PASTED_TOKEN]" in raw
