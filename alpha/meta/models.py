from __future__ import annotations

from datetime import datetime, timezone
from typing import Literal
from uuid import uuid4

from pydantic import BaseModel, Field


def new_session_id() -> str:
    return f"{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%f')}-{uuid4().hex[:4]}"


def new_edit_id() -> str:
    return uuid4().hex[:8]


def new_direction_id() -> str:
    return uuid4().hex[:6]


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


class Session(BaseModel):
    session_id: str
    created_at: str = ""
    channel: str = "teach"
    status: Literal["open", "applied", "discarded"] = "open"
    sources: list[LessonSource] = Field(default_factory=list)
    directions: list[ProposedDirection] = Field(default_factory=list)
    chosen_direction_id: str | None = None
    direction_comment: str = ""
    edits: list[ProposedEdit] = Field(default_factory=list)
    applied_seqs: list[int] = Field(default_factory=list)
    snapshot_before: str | None = None
    notes: list[str] = Field(default_factory=list)
