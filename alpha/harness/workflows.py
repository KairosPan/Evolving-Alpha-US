"""Workflow (W) — the fifth Body component: a named multi-step playbook, SKILL-SHAPED per the
unanimous mainstream verdict (no first-class workflow type in Claude Code / Codex / Hermes). Steps
reference skills by id (or free-prose actions); side-effectful flows are human-triggered by default
(`user_only`). Declarative this arc — no executor; the entry is prompt-visible and teachable/
evolvable through the write-waist (data rung R1/R2, carries no executable content)."""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from alpha.trace import DEFAULT_SCOPE, Scope


class WorkflowStep(BaseModel):
    model_config = ConfigDict(extra="forbid")

    ref: str                                        # skill id or free-prose action
    note: str = ""


class WorkflowEntry(BaseModel):
    model_config = ConfigDict(extra="forbid", validate_assignment=True)

    workflow_id: str
    name: str
    description: str = ""                            # <=200 chars — the index line
    steps: list[WorkflowStep] = Field(default_factory=list)
    arg_hints: list[str] = Field(default_factory=list)
    user_only: bool = True                          # side-effectful flows are human-triggered
    phases: list[str] = Field(default_factory=list)
    domain: Literal["trading", "operational"] = "trading"
    scope: Scope = DEFAULT_SCOPE
    status: Literal["active", "retired"] = "active"
    content_hash: str = ""


class WorkflowRegistry:
    """Id-keyed registry (house style: mirrors SkillRegistry/ConnectorRegistry). Always truthy."""

    def __init__(self, entries: dict[str, WorkflowEntry]) -> None:
        self._entries = dict(entries)

    @classmethod
    def empty(cls) -> "WorkflowRegistry":
        return cls({})

    @classmethod
    def from_workflows(cls, entries: list[WorkflowEntry]) -> "WorkflowRegistry":
        d: dict[str, WorkflowEntry] = {}
        for e in entries:
            if e.workflow_id in d:
                raise ValueError(f"duplicate workflow_id: {e.workflow_id}")
            d[e.workflow_id] = e
        return cls(d)

    def get(self, workflow_id: str) -> "WorkflowEntry | None":
        return self._entries.get(workflow_id)

    def all(self) -> list[WorkflowEntry]:
        return list(self._entries.values())

    def upsert(self, entry: WorkflowEntry) -> None:
        self._entries[entry.workflow_id] = entry

    def __len__(self) -> int:
        return len(self._entries)

    def __bool__(self) -> bool:
        return True
