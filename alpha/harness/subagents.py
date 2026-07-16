"""Subagent (A) — the sixth Body component: a specialized dispatch persona. STATE ONLY this arc:
`description` is the dispatch routing signal, `system_prompt` the body, `tools`/`max_tier` the
restriction surface. Dispatch mechanics (the G pass) stay deferred — PASS_TOOLS["G"] is
reserved-empty; these entries are dispatch-READY, carry no executable content (data rung R1/R2)."""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from alpha.trace import DEFAULT_SCOPE, Scope


class SubagentEntry(BaseModel):
    model_config = ConfigDict(extra="forbid", validate_assignment=True)

    subagent_id: str
    name: str
    description: str = ""                            # the ONLY dispatch-routing signal
    system_prompt: str = ""
    llm_role: str = "inherit"                        # agent/refiner/sonia/converse, or "inherit"
    tools: list[str] = Field(default_factory=list)
    max_tier: str = "T0_OBSERVE"
    skills_preload: list[str] = Field(default_factory=list)
    max_turns: int = 8
    domain: Literal["trading", "operational"] = "trading"
    scope: Scope = DEFAULT_SCOPE
    status: Literal["active", "retired"] = "active"
    notes: str = ""


class SubagentRegistry:
    """Id-keyed registry (house style: mirrors WorkflowRegistry/ConnectorRegistry). Always truthy."""

    def __init__(self, entries: dict[str, SubagentEntry]) -> None:
        self._entries = dict(entries)

    @classmethod
    def empty(cls) -> "SubagentRegistry":
        return cls({})

    @classmethod
    def from_subagents(cls, entries: list[SubagentEntry]) -> "SubagentRegistry":
        d: dict[str, SubagentEntry] = {}
        for e in entries:
            if e.subagent_id in d:
                raise ValueError(f"duplicate subagent_id: {e.subagent_id}")
            d[e.subagent_id] = e
        return cls(d)

    def get(self, subagent_id: str) -> "SubagentEntry | None":
        return self._entries.get(subagent_id)

    def all(self) -> list[SubagentEntry]:
        return list(self._entries.values())

    def upsert(self, entry: SubagentEntry) -> None:
        self._entries[entry.subagent_id] = entry

    def __len__(self) -> int:
        return len(self._entries)

    def __bool__(self) -> bool:
        return True
