"""Task B: the MCP gate in build_sonia_registry — mirrors the alpaca gate (tests/meta/test_sonia_loop.py).

A kind="mcp" connector registers namespaced observe-tier tools ONLY when enabled AND its env_keys are
present AND its impl_ref resolves in the operator MCP registry; the registered NAME set is the ENFORCED
intersection(capabilities, spec.allowed_tools); the live tools/list is the third leg, enforced at
dispatch. Everything is driven through an in-process FakeMcpTransport — no subprocess, no socket.
"""
from pathlib import Path

import pytest

from alpha.harness.connectors import ConnectorEntry, ConnectorRegistry
from alpha.harness.doctrine import Doctrine
from alpha.harness.loader import load_seeds
from alpha.harness.registry import MemoryStore, SkillRegistry
from alpha.harness.state import HarnessState
from alpha.mcp import registry as mcp_registry
from alpha.mcp.client import McpClient
from alpha.mcp.registry import McpServerSpec
from alpha.meta.sonia_tools import build_sonia_registry

SEEDS = Path(__file__).resolve().parents[2] / "seeds"


class FakeMcpTransport:
    """In-process JSON-RPC seam (same shape as tests/mcp/test_client.py's)."""

    def __init__(self, *, tools=None, call_result=None, error_on=()):
        self.tools = list(tools or [])
        self.call_result = call_result if call_result is not None else {"content": [{"type": "text", "text": "ok"}]}
        self.error_on = set(error_on)

    def request(self, payload, timeout):
        method, rid = payload.get("method"), payload.get("id")
        if method in self.error_on:
            return {"jsonrpc": "2.0", "id": rid, "error": {"code": -1, "message": "boom"}}
        if method == "tools/list":
            result = {"tools": [{"name": n} for n in self.tools]}
        elif method == "tools/call":
            result = self.call_result
        else:
            result = {}
        return {"jsonrpc": "2.0", "id": rid, "result": result}

    def notify(self, payload):
        pass

    def close(self):
        pass


def _mcp_conn(**kw):
    base = dict(connector_id="demo", name="Demo MCP", kind="mcp", impl_ref="demo",
                capabilities=["echo", "add"], env_keys=["DEMO_TOKEN"], instructions="demo server.")
    base.update(kw)
    return ConnectorEntry(**base)


def _h(*connectors):
    return HarnessState(doctrine=Doctrine(), skills=SkillRegistry.from_skills([]),
                        memory=MemoryStore.from_lessons([]),
                        connectors=ConnectorRegistry.from_connectors(list(connectors)))


def _factory(transport):
    return lambda spec: McpClient(spec, transport=transport)


@pytest.fixture
def demo_server(monkeypatch):
    # allowed_tools is the operator ceiling (superset of the connector's capabilities, plus "danger").
    monkeypatch.setitem(mcp_registry._SERVERS, "demo",
                        McpServerSpec(server_id="demo", command=["demo-server"],
                                      allowed_tools=["echo", "add", "danger"], env_keys=["DEMO_TOKEN"]))


@pytest.fixture
def token(monkeypatch):
    monkeypatch.setenv("DEMO_TOKEN", "test-value")


def _mcp_names(reg):
    return {s["name"] for s in reg.specs() if s["name"].startswith("mcp_")}


def test_no_mcp_entry_no_mcp_tools():
    reg, _ = build_sonia_registry(_h())
    assert _mcp_names(reg) == set()


def test_registered_when_enabled_keys_and_server_resolve(demo_server, token):
    t = FakeMcpTransport(tools=["echo", "add"])
    reg, pol = build_sonia_registry(_h(_mcp_conn()), mcp_client_factory=_factory(t))
    assert _mcp_names(reg) == {"mcp_demo_echo", "mcp_demo_add"}
    for name in _mcp_names(reg):
        assert pol.tiers[name].name == "T0_OBSERVE"          # default connector tier
    out = pol.dispatch("mcp_demo_echo", {"arguments": {"msg": "hi"}})
    assert out["ok"] is True and out["result"] == {"content": [{"type": "text", "text": "ok"}]}


def test_mcp_tool_respects_connector_tier_gate(demo_server, token):
    # A side-effecting MCP server declared at a higher tier must NOT masquerade as observe: the
    # connector-declared tier flows to the ActivityPolicy tier gate, so in Sonia's autonomous
    # read-only loop (no confirm callable) a T4 tool is BLOCKED, not silently run under an observe label.
    t = FakeMcpTransport(tools=["echo"])
    reg, pol = build_sonia_registry(_h(_mcp_conn(capabilities=["echo"], tier="T4_CONFIRM")),
                                    mcp_client_factory=_factory(t))
    assert pol.tiers["mcp_demo_echo"].name == "T4_CONFIRM"   # respected, not hardcoded T0
    out = pol.dispatch("mcp_demo_echo", {"arguments": {}})
    assert out.get("needs_confirmation") is True and "confirmation" in out.get("error", "")


def test_mcp_unknown_tier_string_registers_nothing(demo_server, token):
    # Fail-closed: a connector carrying an unrecognized tier string registers no tool (never a
    # tool without a tier the policy can gate).
    reg, _ = build_sonia_registry(_h(_mcp_conn(capabilities=["echo"], tier="T9_BOGUS")),
                                  mcp_client_factory=_factory(FakeMcpTransport(tools=["echo"])))
    assert _mcp_names(reg) == set()


def test_mcp_dispatch_closes_client_no_leak(demo_server, token):
    # No orphaned child across turns: every dispatch owns the client lifecycle and closes it.
    class _CountingTransport(FakeMcpTransport):
        closes = 0
        def close(self):
            type(self).closes += 1

    t = _CountingTransport(tools=["echo"])
    reg, pol = build_sonia_registry(_h(_mcp_conn(capabilities=["echo"])), mcp_client_factory=_factory(t))
    assert _CountingTransport.closes == 0                    # registration never touches the child
    pol.dispatch("mcp_demo_echo", {"arguments": {}})
    pol.dispatch("mcp_demo_echo", {"arguments": {}})
    assert _CountingTransport.closes == 2                    # one close per dispatch — nothing leaks


def test_absent_when_disabled(demo_server, token):
    t = FakeMcpTransport(tools=["echo", "add"])
    reg, _ = build_sonia_registry(_h(_mcp_conn(enabled=False)), mcp_client_factory=_factory(t))
    assert _mcp_names(reg) == set()


def test_absent_when_env_key_missing(demo_server, monkeypatch):
    monkeypatch.delenv("DEMO_TOKEN", raising=False)
    t = FakeMcpTransport(tools=["echo", "add"])
    reg, _ = build_sonia_registry(_h(_mcp_conn()), mcp_client_factory=_factory(t))
    assert _mcp_names(reg) == set()


def test_absent_when_impl_ref_not_in_registry(token):
    # No demo_server fixture -> "demo" is not a registered server.
    t = FakeMcpTransport(tools=["echo", "add"])
    reg, _ = build_sonia_registry(_h(_mcp_conn()), mcp_client_factory=_factory(t))
    assert _mcp_names(reg) == set()


def test_capabilities_intersect_allowed_tools_enforced(demo_server, token):
    # Connector asks for "echo" (in allowed) + "secret" (NOT in allowed) — only echo registers. And
    # "danger" (in allowed + live) is NOT requested by capabilities, so it never registers either.
    t = FakeMcpTransport(tools=["echo", "add", "danger", "secret"])
    reg, _ = build_sonia_registry(_h(_mcp_conn(capabilities=["echo", "secret"])),
                                  mcp_client_factory=_factory(t))
    assert _mcp_names(reg) == {"mcp_demo_echo"}


def test_empty_capabilities_registers_nothing(demo_server, token):
    t = FakeMcpTransport(tools=["echo", "add"])
    reg, _ = build_sonia_registry(_h(_mcp_conn(capabilities=[])), mcp_client_factory=_factory(t))
    assert _mcp_names(reg) == set()                          # fail-closed on empty allowlist


def test_dispatch_fail_soft_on_server_error(demo_server, token):
    t = FakeMcpTransport(tools=["echo", "add"], error_on={"tools/call"})
    reg, pol = build_sonia_registry(_h(_mcp_conn()), mcp_client_factory=_factory(t))
    out = pol.dispatch("mcp_demo_echo", {"arguments": {}})
    assert out["ok"] is False and "error" in out


def test_dispatch_fail_soft_when_tool_not_offered_live(demo_server, token):
    # Registered from capabilities ∩ allowed_tools, but the LIVE server currently offers only "add" —
    # a dispatch of the registered-but-unoffered echo fails soft (the third intersection leg at dispatch).
    t = FakeMcpTransport(tools=["add"])
    reg, pol = build_sonia_registry(_h(_mcp_conn()), mcp_client_factory=_factory(t))
    assert "mcp_demo_echo" in _mcp_names(reg)                # registered on the static intersection
    out = pol.dispatch("mcp_demo_echo", {"arguments": {}})
    assert out["ok"] is False and "not offered" in out["error"]


def test_alpaca_and_mcp_coexist(demo_server, token, monkeypatch):
    # Regression: adding an MCP connector does not disturb the alpaca market-tool gate (byte-identical).
    for k in ("APCA_API_KEY_ID", "APCA_API_SECRET_KEY"):
        monkeypatch.setenv(k, "test-value")
    from alpha.data.source import FakeSource
    h = load_seeds(SEEDS)                                    # carries the enabled alpaca connector
    h.connectors.upsert(_mcp_conn())
    t = FakeMcpTransport(tools=["echo", "add"])
    reg, pol = build_sonia_registry(h, source_factory=lambda: FakeSource(calendar=[], bars={}, snapshots={}),
                                    mcp_client_factory=_factory(t))
    names = {s["name"] for s in reg.specs()}
    assert {"market_snapshot", "daily_bars", "latest_decisions"} <= names   # alpaca gate intact
    assert {"mcp_demo_echo", "mcp_demo_add"} <= names                        # mcp gate added alongside
