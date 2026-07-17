# alpha/mcp/registry.py
#
# Operator registry of MCP servers — the data-layer twin of alpha/data/registry.py (source_names).
# A kind="mcp" ConnectorEntry references a server here by key (impl_ref -> server_id); the connector
# write-waist lint (alpha/refine/apply.py::_connector_impl_resolves) resolves that key against
# server_names(), so an entry can never invent a server the operator never registered (data R1/R2).
#
# Add a server (operator-only, out of the agent's reach):
#   1. Construct an McpServerSpec(server_id=..., command=[...], allowed_tools=[...], env_keys=[...]).
#   2. Register one line in _SERVERS keyed by server_id.
#   3. A ConnectorEntry(kind="mcp", impl_ref=<server_id>) now resolves at the waist.
#
# Ships EMPTY: the mechanism lands dark (house pattern — the connector Literal accepts "mcp" and the
# whole channel is wired, but no server is registered until an operator adds one).
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class McpServerSpec(BaseModel):
    """Operator-registered MCP server: WHAT may be spawned and WHICH tools it may expose. Frozen +
    extra=forbid — a spec is operator config, never agent-editable, and never carries a credential
    VALUE (env_keys are variable NAMES only, resolved from os.environ at spawn time). `allowed_tools`
    is the operator's hard ceiling on the server's tool surface; the connector's own `capabilities`
    narrows it further (the enforced intersection lives in the sonia_tools MCP gate)."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    server_id: str
    transport: Literal["stdio"] = "stdio"          # only stdio this round (http is a flagged follow-up)
    command: list[str]                             # argv to spawn (operator-authored, never agent-editable)
    allowed_tools: list[str] = Field(default_factory=list)   # operator ceiling on the tool surface
    env_keys: list[str] = Field(default_factory=list)        # env-var NAMES only, never values
    description: str = ""


# Module-level registry — SHIPS EMPTY (mechanism lands dark, mirrors alpha.data.registry._SOURCES).
_SERVERS: dict[str, McpServerSpec] = {}


def server_names() -> set[str]:
    """Public accessor for the registered MCP server_ids — used by the connector write-waist lint to
    resolve a kind="mcp" connector's impl_ref. Callers must NOT import the private `_SERVERS`."""
    return set(_SERVERS)


def get_server(server_id: str) -> "McpServerSpec | None":
    """The spec for `server_id`, or None if unregistered (soft miss — mirrors ConnectorRegistry.get).
    The MCP gate calls this only AFTER confirming membership via server_names(), so None is defensive."""
    return _SERVERS.get(server_id)
