"""Connector (C) — the fourth Body component: a DECLARATION of an external data/tool connection
the agent may draw on. An entry references an operator-registered implementation by key (impl_ref
into alpha.data.registry) and names required env vars — it carries NO URL, NO credential value,
NO executable content, so editing an entry can never grant a capability (data rung R1/R2)."""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from alpha.trace import DEFAULT_SCOPE, Scope


class ConnectorEntry(BaseModel):
    model_config = ConfigDict(extra="forbid", validate_assignment=True)

    connector_id: str
    name: str
    kind: Literal["data_source", "llm_role", "mcp"]
    impl_ref: str                                   # registry key (make_source / make_client / MCP id)
    capabilities: list[str] = Field(default_factory=list)
    env_keys: list[str] = Field(default_factory=list)   # env-var NAMES only, never values
    instructions: str = ""                          # the ONLY field ever prompt-rendered
    pit_key: str = ""                               # per-connector PIT contract note
    enabled: bool = True
    required: bool = False
    tier: str = "T0_OBSERVE"
    domain: Literal["trading", "operational"] = "trading"
    scope: Scope = DEFAULT_SCOPE
    notes: str = ""


class ConnectorRegistry:
    """Id-keyed registry (house style: mirrors SkillRegistry/MemoryStore). Always truthy."""

    def __init__(self, entries: dict[str, ConnectorEntry]) -> None:
        self._entries = dict(entries)                         # copy (mirrors Workflow/SubagentRegistry)

    @classmethod
    def empty(cls) -> "ConnectorRegistry":
        return cls({})

    @classmethod
    def from_connectors(cls, entries: list[ConnectorEntry]) -> "ConnectorRegistry":
        d: dict[str, ConnectorEntry] = {}
        for e in entries:
            if e.connector_id in d:
                raise ValueError(f"duplicate connector_id: {e.connector_id}")
            d[e.connector_id] = e
        return cls(d)

    def get(self, connector_id: str) -> "ConnectorEntry | None":
        return self._entries.get(connector_id)

    def all(self) -> list[ConnectorEntry]:
        return list(self._entries.values())

    def upsert(self, entry: ConnectorEntry) -> None:
        self._entries[entry.connector_id] = entry

    def __len__(self) -> int:
        return len(self._entries)

    def __bool__(self) -> bool:
        return True
