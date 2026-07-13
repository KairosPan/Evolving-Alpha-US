from __future__ import annotations

from datetime import datetime, timezone
from typing import Literal
from uuid import uuid4

from pydantic import BaseModel, Field

from alpha.trace import MessageOrigin


def new_session_id() -> str:
    return f"{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%f')}-{uuid4().hex[:4]}"


def new_edit_id() -> str:
    return uuid4().hex[:8]


def new_direction_id() -> str:
    return uuid4().hex[:6]


def new_message_id() -> str:
    return uuid4().hex[:8]


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class LessonSource(BaseModel):
    kind: Literal["text", "url"]
    url: str | None = None
    title: str = ""
    text: str
    fetched_at: str = ""


class ProposedDirection(BaseModel):
    direction_id: str
    title: str
    summary: str = ""
    rationale: str = ""
    target_kinds: list[str] = Field(default_factory=list)   # advisory hint: {doctrine,skills,memory}


class ProposedEdit(BaseModel):
    edit_id: str
    tool: str
    target_kind: str = ""
    target_id: str | None = None
    op: str = ""
    summary: str = ""
    payload: dict | None = None
    rationale: str = ""
    args: dict = Field(default_factory=dict)
    status: Literal["proposed", "accepted", "rejected", "applied", "failed"] = "proposed"
    user_comment: str = ""
    apply_reason: str = ""
    applied_seq: int | None = None


class Attachment(BaseModel):
    kind: Literal["file", "url"]
    name: str = ""
    mime: str = ""
    text: str = ""


class Message(BaseModel):
    message_id: str
    role: Literal["user", "assistant"]
    created_at: str = ""
    text: str = ""
    origin: MessageOrigin | None = None   # principal-origin stamp (A4); None = legacy/unstamped
    attachments: list[Attachment] = Field(default_factory=list)
    directions: list[ProposedDirection] = Field(default_factory=list)
    edits: list[ProposedEdit] = Field(default_factory=list)
    snapshot_before: str | None = None
    applied_seqs: list[int] = Field(default_factory=list)
    proposal_note: str = ""          # set when a /propose pass yielded no edit (the visible reason)
    previewed_hash: str = ""         # A8 staleness pin: the brain-content hash the preview was dry-run
                                     # against; /apply refuses (re-preview) if the live brain moved


class Session(BaseModel):
    session_id: str
    created_at: str = ""
    title: str = ""
    channel: str = "teach"
    status: Literal["open", "discarded"] = "open"
    messages: list[Message] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)
