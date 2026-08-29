"""The FastMCP adapter: every Tool in the dict reaches the wire under its own name.

Offline by construction - building a server registers callables, it never runs them, so no
key, no network and no PIT bed is touched. `anyio` ships with the mcp SDK; `list_tools` is
async, so the test drives it through anyio.run rather than adding an asyncio marker.
"""
from __future__ import annotations

import pytest

pytest.importorskip("mcp", reason="install: pip install -e . (mcp SDK)")

from alpaca_kit.mcp.server import build_server  # noqa: E402
from alpaca_kit.mcp.tools import Tool  # noqa: E402


def _canned() -> dict[str, Tool]:
    return {
        "ping": Tool(name="ping", description="pong", fn=lambda: {"ok": True}),
        "echo": Tool(name="echo", description="echo x", fn=lambda x: {"ok": True, "x": x}),
    }


def _listed(server):
    import anyio

    return anyio.run(server.list_tools)


def test_build_server_registers_every_tool():
    listed = _listed(build_server(_canned()))
    assert {t.name for t in listed} == {"ping", "echo"}


def test_registered_tools_carry_their_descriptions():
    # The tool closures are wrapped and carry no __doc__, so the adapter MUST pass description=
    # explicitly; without it every tool ships to the model description-less.
    listed = _listed(build_server(_canned()))
    assert {t.name: t.description for t in listed} == {"ping": "pong", "echo": "echo x"}


def test_build_server_defaults_to_the_real_toolset():
    # No tools argument -> build_tools(); `earnings` is the keyless tool registered under every
    # env, so this holds whether or not the operator has APCA keys or a PIT bed.
    listed = _listed(build_server())
    names = {t.name for t in listed}
    assert "earnings" in names
    assert all(t.description for t in listed)


def test_real_tool_schemas_expose_their_parameters():
    # _soft wraps each body in a **kwargs closure; if the SDK read THAT signature every tool
    # would ship with an empty schema. functools.wraps must keep the real parameters visible.
    listed = _listed(build_server())
    earnings = next(t for t in listed if t.name == "earnings")
    assert "symbol" in earnings.inputSchema.get("properties", {})


def test_the_full_keyed_toolset_registers():
    # The keyless test env never exercises the account lambdas (no __name__, no params) or the
    # operator-gated order tools, yet those are exactly what the dsh profile boots. Build the
    # widest toolset offline with injected factories and pin that every one reaches the wire
    # named, described, and with its parameters intact.
    from alpaca_kit.mcp.tools import build_tools

    env = {"APCA_API_KEY_ID": "k", "APCA_API_SECRET_KEY": "s",
           "ALPHA_PIT_ROOT": "/tmp/no-such-bed", "ALPACA_KIT_ENABLE_ORDERS": "1"}
    tools = build_tools(env, source_factory=lambda: None, trading_factory=lambda: None,
                        edgar_factory=lambda: None)
    listed = _listed(build_server(tools))
    assert {t.name for t in listed} == set(tools)
    assert {t.name: t.description for t in listed} == {n: t.description for n, t in tools.items()}
    by_name = {t.name: t for t in listed}
    assert "qty" in by_name["place_order"].inputSchema.get("properties", {})
    assert by_name["account"].inputSchema.get("properties", {}) == {}
