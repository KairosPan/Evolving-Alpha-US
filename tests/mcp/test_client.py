"""Minimal stdio MCP client — driven ENTIRELY through an in-process FakeMcpTransport: these tests
spawn no subprocess and open no socket. Cover the JSON-RPC handshake (initialize -> tools/list ->
tools/call), fail-soft-on-timeout, and the env ALLOWLIST discipline (build_mcp_env + the _StdioTransport
spawn seam that records the env argument).
"""
import io

from alpha.mcp import client
from alpha.mcp.client import McpClient, build_mcp_env
from alpha.mcp.registry import McpServerSpec


class FakeMcpTransport:
    """In-process JSON-RPC seam: answers initialize/tools/list/tools/call from canned data, records
    every request payload, spawns nothing. `raise_on` simulates a per-call timeout (transport raises);
    `error_on` returns a JSON-RPC error object for the named method."""

    def __init__(self, *, tools=None, call_result=None, raise_on=(), error_on=()):
        self.tools = list(tools or [])
        self.call_result = call_result if call_result is not None else {"content": [{"type": "text", "text": "ok"}]}
        self.raise_on = set(raise_on)
        self.error_on = set(error_on)
        self.requests = []
        self.notifications = []
        self.closed = False

    def request(self, payload, timeout):
        self.requests.append(payload)
        method, rid = payload.get("method"), payload.get("id")
        if method in self.raise_on:
            raise TimeoutError(f"simulated timeout on {method} (timeout={timeout})")
        if method in self.error_on:
            return {"jsonrpc": "2.0", "id": rid, "error": {"code": -32000, "message": f"boom {method}"}}
        if method == "initialize":
            result = {"protocolVersion": "2025-06-18", "capabilities": {}, "serverInfo": {"name": "fake"}}
        elif method == "tools/list":
            result = {"tools": [{"name": n} for n in self.tools]}
        elif method == "tools/call":
            result = self.call_result
        else:
            result = {}
        return {"jsonrpc": "2.0", "id": rid, "result": result}

    def notify(self, payload):
        self.notifications.append(payload)

    def close(self):
        self.closed = True


def _spec(**kw):
    base = dict(server_id="demo", command=["demo-server"], allowed_tools=["echo"], env_keys=["DEMO_TOKEN"])
    base.update(kw)
    return McpServerSpec(**base)


def test_handshake_happy_path():
    t = FakeMcpTransport(tools=["echo", "add"], call_result={"content": [{"type": "text", "text": "hi"}]})
    c = McpClient(_spec(), transport=t)
    assert c.initialize()["ok"] is True
    listed = c.list_tools()
    assert listed["ok"] is True and listed["tools"] == ["echo", "add"]
    called = c.call_tool("echo", {"msg": "hi"})
    assert called["ok"] is True and called["result"] == {"content": [{"type": "text", "text": "hi"}]}
    # JSON-RPC shape: every request is 2.0 with an id; tools/call carried name + arguments.
    methods = [r["method"] for r in t.requests]
    assert methods[0] == "initialize" and "tools/list" in methods and "tools/call" in methods
    assert all(r["jsonrpc"] == "2.0" and "id" in r for r in t.requests)
    call_req = next(r for r in t.requests if r["method"] == "tools/call")
    assert call_req["params"] == {"name": "echo", "arguments": {"msg": "hi"}}
    # initialize is idempotent — a second call sends no new initialize request.
    before = methods.count("initialize")
    c.initialize()
    assert [r["method"] for r in t.requests].count("initialize") == before


def test_initialized_notification_sent_after_initialize():
    t = FakeMcpTransport(tools=["echo"])
    McpClient(_spec(), transport=t).initialize()
    assert t.notifications and t.notifications[0]["method"] == "notifications/initialized"


def test_call_timeout_is_fail_soft():
    t = FakeMcpTransport(tools=["echo"], raise_on={"tools/call"})
    c = McpClient(_spec(), transport=t)
    out = c.call_tool("echo", {})
    assert out["ok"] is False and "error" in out             # caught, never raised into the loop


def test_list_timeout_is_fail_soft():
    t = FakeMcpTransport(raise_on={"tools/list"})
    out = McpClient(_spec(), transport=t).list_tools()
    assert out["ok"] is False and "error" in out


def test_server_error_is_fail_soft():
    t = FakeMcpTransport(tools=["echo"], error_on={"tools/call"})
    out = McpClient(_spec(), transport=t).call_tool("echo", {})
    assert out["ok"] is False and "boom" in out["error"]


def test_close_terminates_transport():
    t = FakeMcpTransport()
    McpClient(_spec(), transport=t).close()
    assert t.closed is True


# ── env ALLOWLIST discipline (LocalEnv / build_sandbox_env twin) ──────────────────────────────────

def test_build_mcp_env_is_allowlist(monkeypatch):
    monkeypatch.setenv("DECLARED_KEY", "v1")
    monkeypatch.setenv("UNDECLARED_SECRET", "v2")
    monkeypatch.setenv("PATH", "/usr/bin")
    env = build_mcp_env(["DECLARED_KEY", "ABSENT_KEY"])
    assert env["DECLARED_KEY"] == "v1"
    assert "UNDECLARED_SECRET" not in env                    # not declared -> never enters (default-deny)
    assert "ABSENT_KEY" not in env                           # declared but unset -> omitted (fail-soft)
    assert set(env) - {"PATH", "HOME"} == {"DECLARED_KEY"}   # only baseline + declared keys


class _FakeProc:
    def __init__(self):
        self.stdin = io.StringIO()
        self.stdout = io.StringIO("")                        # EOF immediately -> reader thread exits at once
        self.terminated = False

    def terminate(self):
        self.terminated = True

    def wait(self, timeout=None):
        return 0

    def kill(self):
        pass


def test_stdio_transport_spawns_with_whitelisted_env_only(monkeypatch):
    # The spawn seam records the env argument — NO real subprocess. Asserts the child sees ONLY the
    # declared key + PATH/HOME baseline, and an undeclared secret is stripped regardless of its name.
    monkeypatch.setenv("MY_MCP_TOKEN", "secret-value")
    monkeypatch.setenv("SNEAKY_API_KEY", "should-not-pass")
    monkeypatch.setenv("PATH", "/usr/bin")
    captured = {}

    def _spawn(command, env):
        captured["command"], captured["env"] = command, env
        return _FakeProc()

    t = client._StdioTransport(["my-server"], build_mcp_env(["MY_MCP_TOKEN"]), spawn=_spawn)
    assert captured["command"] == ["my-server"]
    env = captured["env"]
    assert env.get("MY_MCP_TOKEN") == "secret-value"
    assert "SNEAKY_API_KEY" not in env                       # undeclared secret never reaches the child
    assert set(env) <= {"PATH", "HOME", "MY_MCP_TOKEN"}      # baseline + declared only
    t.close()
