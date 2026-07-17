"""Operator MCP registry — the data-layer twin of alpha/data/registry.py (source_names). Offline.

Mirrors tests/data/test_registry.py + the connector-entry tests: server_names/get_server accessors,
frozen + extra=forbid on the spec, and the ships-EMPTY (mechanism-lands-dark) house invariant.
"""
import pytest

from alpha.mcp import registry
from alpha.mcp.registry import McpServerSpec, get_server, server_names


def _spec(**kw):
    base = dict(server_id="demo", command=["demo-server"], allowed_tools=["echo", "add"],
                env_keys=["DEMO_TOKEN"], description="demo")
    base.update(kw)
    return McpServerSpec(**base)


def test_ships_empty():
    # The channel is fully wired but no server is registered until an operator adds one (lands dark).
    assert server_names() == set()


def test_spec_frozen():
    s = _spec()
    with pytest.raises(Exception):
        s.server_id = "other"                              # frozen: operator config, never mutated


def test_spec_extra_forbid():
    with pytest.raises(Exception):
        McpServerSpec(server_id="x", command=["c"], bogus=1)


def test_spec_defaults():
    s = _spec()
    assert s.transport == "stdio" and s.description == "demo"
    bare = McpServerSpec(server_id="b", command=["c"])
    assert bare.allowed_tools == [] and bare.env_keys == []   # both default-empty


def test_server_names_and_get_server(monkeypatch):
    monkeypatch.setitem(registry._SERVERS, "demo", _spec())   # register one for the accessor probe
    assert "demo" in server_names()
    assert get_server("demo").server_id == "demo"
    assert get_server("absent") is None                       # soft miss, never raises
