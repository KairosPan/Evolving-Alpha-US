# alpha/mcp/client.py
#
# A minimal stdio MCP client: spawn an operator-registered server, speak JSON-RPC 2.0 over its
# stdin/stdout (initialize -> tools/list -> tools/call), fail-soft on every call (never raise into
# the agent loop), and close() the child on teardown. Two disciplines are load-bearing:
#
#   * ENV WHITELIST (build_mcp_env) — the child sees a minimal PATH/HOME baseline plus EXACTLY the
#     spec's declared env_keys resolved from os.environ, NEVER the full parent env. Mirrors
#     LocalEnv / build_sandbox_env: a secret whose name the spec did not declare cannot enter,
#     regardless of its name (allowlist / default-deny).
#   * TRANSPORT SEAM — McpClient takes an injectable `transport` (a duck-typed object with
#     request(payload, timeout) and optional notify/close). Tests inject an IN-PROCESS
#     FakeMcpTransport and so spawn no subprocess and open no socket. The default _StdioTransport
#     spawns the real child.
#
# http transport is a flagged follow-up (registry.transport is a stdio-only Literal this round).
from __future__ import annotations

import json
import os
import threading
import time
from typing import Any

from alpha.mcp.registry import McpServerSpec

_PROTOCOL_VERSION = "2025-06-18"                 # MCP protocol revision advertised at initialize
_BASELINE_ENV_KEYS = ("PATH", "HOME")            # the minimal non-secret baseline every child needs
_DEFAULT_TIMEOUT = 30.0


def build_mcp_env(env_keys) -> dict[str, str]:
    """The env an MCP child may see — ALLOWLIST / default-deny (LocalEnv / build_sandbox_env
    discipline): a minimal PATH/HOME baseline plus EXACTLY the spec's declared env_keys resolved from
    os.environ. NEVER the full parent env — a secret whose NAME the spec did not declare never enters,
    which is what makes containment structural rather than a fragile denylist over secret-shaped names.
    A declared key absent from os.environ is simply omitted (fail-soft; the server sees it unset)."""
    out: dict[str, str] = {}
    for k in (*_BASELINE_ENV_KEYS, *env_keys):
        v = os.environ.get(k)
        if v is not None:
            out[k] = v
    return out


def _default_spawn(command: list[str], env: dict[str, str]):
    import subprocess
    return subprocess.Popen(
        command, env=env, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL, text=True, bufsize=1,
    )


class _StdioTransport:
    """Real stdio transport: spawn the child with the WHITELISTED env, then serve line-delimited
    JSON-RPC. A daemon reader thread drains stdout into a pending-by-id map so request() can wait for
    its own id under a per-call timeout while interleaved notifications / other ids are skipped. The
    `spawn` seam (default _default_spawn) is where a test could record the env argument, but the
    offline tests exercise the client through an injected FakeMcpTransport and never reach here."""

    def __init__(self, command: list[str], env: dict[str, str], *, spawn=None) -> None:
        spawn = spawn or _default_spawn
        self._proc = spawn(list(command), dict(env))
        self._pending: dict[Any, dict] = {}
        self._cv = threading.Condition()
        self._closed = False
        self._reader = threading.Thread(target=self._read_loop, daemon=True)
        self._reader.start()

    def _read_loop(self) -> None:
        stdout = self._proc.stdout
        if stdout is None:
            return
        for line in stdout:                                  # blocks until EOF (child exit / close)
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
            except Exception:
                continue                                     # skip non-JSON chatter, never crash the reader
            if isinstance(obj, dict) and obj.get("id") is not None:
                with self._cv:
                    self._pending[obj["id"]] = obj
                    self._cv.notify_all()

    def _write(self, payload: dict) -> None:
        stdin = self._proc.stdin
        if stdin is None:
            raise RuntimeError("MCP child stdin is closed")
        stdin.write(json.dumps(payload) + "\n")
        stdin.flush()

    def request(self, payload: dict, timeout: float) -> dict:
        rid = payload.get("id")
        self._write(payload)
        deadline = time.monotonic() + float(timeout)
        with self._cv:
            while rid not in self._pending:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise TimeoutError(f"MCP request {payload.get('method')!r} timed out after {timeout}s")
                self._cv.wait(remaining)
            return self._pending.pop(rid)

    def notify(self, payload: dict) -> None:
        self._write(payload)                                 # a notification has no id and no response

    def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        proc = self._proc
        for stream in (proc.stdin, proc.stdout):
            try:
                if stream is not None:
                    stream.close()
            except Exception:
                pass
        try:
            proc.terminate()
            try:
                proc.wait(timeout=5)
            except Exception:
                proc.kill()
        except Exception:
            pass


class McpClient:
    """Fail-soft JSON-RPC 2.0 client over an injectable transport. Every public method returns a dict
    {"ok": bool, ...} and NEVER raises into the caller (the agent loop). initialize() is idempotent and
    is called implicitly by list_tools/call_tool, so a caller can just dispatch. When no `transport` is
    injected the default _StdioTransport spawns the server with build_mcp_env(spec.env_keys)."""

    def __init__(self, spec: McpServerSpec, *, transport=None, timeout: float = _DEFAULT_TIMEOUT) -> None:
        self._spec = spec
        self._timeout = float(timeout)
        self._transport = transport if transport is not None else _StdioTransport(
            list(spec.command), build_mcp_env(spec.env_keys))
        self._id = 0
        self._initialized = False

    def _next_id(self) -> int:
        self._id += 1
        return self._id

    def _rpc(self, method: str, params: dict | None = None, *, timeout: float | None = None) -> dict:
        req: dict[str, Any] = {"jsonrpc": "2.0", "id": self._next_id(), "method": method}
        if params is not None:
            req["params"] = params
        try:
            resp = self._transport.request(req, self._timeout if timeout is None else float(timeout))
        except Exception as e:                                # timeout / transport error -> fail-soft
            return {"ok": False, "error": f"{type(e).__name__}: {e}"}
        if not isinstance(resp, dict):
            return {"ok": False, "error": "malformed JSON-RPC response (not an object)"}
        if resp.get("error") is not None:
            return {"ok": False, "error": str(resp["error"])}
        return {"ok": True, "result": resp.get("result")}

    def initialize(self) -> dict:
        if self._initialized:
            return {"ok": True, "result": None}
        out = self._rpc("initialize", {"protocolVersion": _PROTOCOL_VERSION, "capabilities": {},
                                        "clientInfo": {"name": "alpha-mcp", "version": "0"}})
        if out["ok"]:
            self._initialized = True
            notify = getattr(self._transport, "notify", None)
            if callable(notify):                             # best-effort per the MCP handshake
                try:
                    notify({"jsonrpc": "2.0", "method": "notifications/initialized"})
                except Exception:
                    pass
        return out

    def list_tools(self, *, timeout: float | None = None) -> dict:
        init = self.initialize()
        if not init["ok"]:
            return {"ok": False, "error": init.get("error", "initialize failed")}
        out = self._rpc("tools/list", {}, timeout=timeout)
        if not out["ok"]:
            return out
        result = out.get("result") or {}
        raw = result.get("tools") or []
        names = [t.get("name") for t in raw if isinstance(t, dict) and t.get("name")]
        return {"ok": True, "tools": names, "raw": raw}

    def call_tool(self, name: str, arguments: dict | None = None, *, timeout: float | None = None) -> dict:
        init = self.initialize()
        if not init["ok"]:
            return {"ok": False, "error": init.get("error", "initialize failed")}
        out = self._rpc("tools/call", {"name": name, "arguments": arguments or {}}, timeout=timeout)
        if not out["ok"]:
            return out
        return {"ok": True, "result": out.get("result")}

    def close(self) -> None:
        close = getattr(self._transport, "close", None)
        if callable(close):
            try:
                close()
            except Exception:
                pass
