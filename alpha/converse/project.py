from __future__ import annotations

from pydantic import BaseModel, Field

from alpha.llm.chat import ChatMessage
from alpha.meta.models import new_session_id, now_iso


class ProjectTurn(BaseModel):
    turn_id: str
    user_text: str
    final_text: str = ""
    tool_calls: list[dict] = Field(default_factory=list)   # JSON-safe (DecisionPackage results dumped)
    h_version: int | None = None                           # the SnapshotStore version this turn ran against
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


def new_project(title: str = "") -> Project:
    return Project(project_id=new_session_id(), created_at=now_iso(), title=title)


def new_turn(user_text: str) -> ProjectTurn:
    return ProjectTurn(turn_id=new_session_id(), user_text=user_text, created_at=now_iso())
