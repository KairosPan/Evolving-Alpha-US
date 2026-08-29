"""FastMCP adapter: register the pure toolset onto a stdio MCP server.

The whole SDK surface lives here - `alpaca_kit/mcp/tools.py` stays SDK-free and offline-
testable, and this module only translates. Registration passes name= and description=
EXPLICITLY: `build_tools` returns closures wrapped by `_soft`, and a lambda body carries no
docstring at all, so letting FastMCP infer from `fn.__name__`/`fn.__doc__` would ship every
tool to the model nameless-by-luck and description-less. Parameter schemas are inferred from
each fn's signature, which `functools.wraps` keeps pointing at the real body (via __wrapped__)
rather than at _soft's **kwargs.

Pinned against mcp 1.28.1: FastMCP.add_tool(fn, name=, description=, ...).
"""
from __future__ import annotations

from mcp.server.fastmcp import FastMCP

from alpaca_kit.mcp.tools import Tool, build_tools


def build_server(tools: dict[str, Tool] | None = None) -> FastMCP:
    """A FastMCP server with every Tool registered under its own name."""
    server = FastMCP("alpaca-kit")
    for t in (build_tools() if tools is None else tools).values():
        server.add_tool(t.fn, name=t.name, description=t.description)
    return server
