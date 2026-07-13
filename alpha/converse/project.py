from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

from alpha.llm.chat import ChatMessage
from alpha.meta.models import new_session_id, now_iso
from alpha.trace import AttributionTuple


class StagedEdit(BaseModel):
    """A converse-face brain edit proposed for the user's approval (preview/approve flow)."""
    edit_id: str
    op: dict                                   # {"tool","args","rationale"} — the RefineOp seed
    summary: str = ""
    valid: bool = False                        # passed the dry-run gate
    reason: str | None = None                  # dry-run / apply reject reason
    preview: dict = Field(default_factory=dict)
    status: Literal["pending", "approved", "rejected"] = "pending"
    snapshot_before: str = ""
    applied_seq: int | None = None


class ProjectTurn(BaseModel):
    turn_id: str
    user_text: str
    final_text: str = ""
    tool_calls: list[dict] = Field(default_factory=list)   # JSON-safe (DecisionPackage results dumped)
    h_version: int | None = None                           # the SnapshotStore version this turn ran against
    attribution: AttributionTuple | None = None            # A4: body-version × model-id × kernel-version
    created_at: str = ""


class Project(BaseModel):
    """One persisted conversation/workspace engagement. ONE shared brain — h_pin (optional) only changes
    which H-version this project READS; never a private brain copy."""
    project_id: str
    created_at: str = ""
    title: str = ""
    h_pin: int | None = None
    messages: list[ChatMessage] = Field(default_factory=list)
    turns: list[ProjectTurn] = Field(default_factory=list)
    staged_edits: list[StagedEdit] = Field(default_factory=list)


def new_project(title: str = "") -> Project:
    return Project(project_id=new_session_id(), created_at=now_iso(), title=title)


def new_turn(user_text: str) -> ProjectTurn:
    return ProjectTurn(turn_id=new_session_id(), user_text=user_text, created_at=now_iso())
