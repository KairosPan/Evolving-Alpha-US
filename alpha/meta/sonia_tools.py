"""Sonia's observe-tier tool registry: read-only brain browse (two-tier disclosure).

`_system` gives the model a budgeted INDEX of the brain; these seven `view_*`/`search_episodes`
tools let it pull the FULL detail of any single element on demand. All tools are `T0_OBSERVE` under a
fail-closed `ActivityPolicy` — Sonia's hands still only touch the brain-edit door via the separate
teach/propose chain (the extract_ops -> preview -> gated apply waist), never write from here.

Tool NAMES match apply.py::_REGISTERABLE_TOOLS exactly (view_doctrine/view_skill/view_lesson/
view_workflow/view_connector/view_subagent/search_episodes). Three market tools (market_snapshot/
daily_bars/latest_decisions) join ONLY when the alpaca connector is enabled and its env keys are set
(otherwise absent); they wrap a lazily-built RAW source in GuardedSource+AsOfGuard per call, fail-soft.

This module MAY import `alpha.arena` — the AST guard only walks `alpha/converse`, not `alpha/meta`.
"""
from __future__ import annotations

import os
from datetime import date, timedelta

from alpha.arena.contract import CapabilityTier
from alpha.arena.policy import ActivityPolicy
from alpha.converse.registry import ToolRegistry
from alpha.data.firewall import AsOfGuard
from alpha.data.source import GuardedSource


def _schema(name: str, desc: str, props: dict, required: list[str]) -> dict:
    return {"name": name, "description": desc,
            "parameters": {"type": "object", "properties": props, "required": required}}


def _dump(entry):
    # Every brain entry is a pydantic model; mode="json" keeps date fields (learned_asof) as ISO
    # strings so the loop can json.dumps the tool result. None (no such id) is a soft miss.
    return entry.model_dump(mode="json") if entry is not None else None


def _default_source_factory(impl_ref=None):
    # Lazy: importing make_source pulls the whole data stack (alpaca et al.), and building an
    # AlpacaSource reads env — so defer both to first tool DISPATCH, never registry build time.
    # Honor the connector's declared impl_ref (None -> env default) instead of hardcoding the default.
    from alpha.data.registry import make_source
    return make_source(impl_ref)                            # RAW source (caller wraps per contract)


def _market_snapshot_fn(source_factory):
    def market_snapshot(symbols) -> dict:
        # Mirror make_decide_for_date_tool: wrap the RAW source in GuardedSource(AsOfGuard(today))
        # per call (PIT-wrap is the caller's job). Fail-soft — never raise into the loop.
        try:
            today = date.today()
            guarded = GuardedSource(source_factory(), AsOfGuard(today))
            df = guarded.daily_snapshot(today)
            if symbols:
                df = df[df["symbol"].isin(list(symbols))]
            return {"ok": True, "asof": today.isoformat(), "snapshot": df.to_dict(orient="records")}
        except Exception as e:
            return {"ok": False, "error": str(e)}
    return market_snapshot


def _daily_bars_fn(source_factory):
    def daily_bars(symbol, days: int = 30) -> dict:
        try:
            today = date.today()
            start = today - timedelta(days=int(days))
            guarded = GuardedSource(source_factory(), AsOfGuard(today))
            df = guarded.daily_bars(symbol, start, today)
            return {"ok": True, "symbol": symbol, "bars": df.to_dict(orient="records")}
        except Exception as e:
            return {"ok": False, "error": str(e)}
    return daily_bars


def _latest_decisions_fn():
    def latest_decisions() -> dict:
        try:
            root = os.environ.get("ALPHA_WEB_DECISIONS_DIR")
            if not root:
                return {"ok": True, "decisions": None}       # no store configured -> soft absence
            from alpha.eval.decision_store import DecisionStore
            pkg = DecisionStore(root).latest()
            return {"ok": True, "decisions": pkg.model_dump(mode="json") if pkg is not None else None}
        except Exception as e:
            return {"ok": False, "error": str(e)}
    return latest_decisions


def _default_mcp_client_factory(spec):
    # Lazy: importing the client is cheap, but building it spawns the MCP child (stdio) and resolves
    # the whitelisted env — defer to first tool DISPATCH, never registry build time (mirrors the
    # market-source lazy pattern above). An injected factory (tests) short-circuits this entirely.
    from alpha.mcp.client import McpClient
    return McpClient(spec)


def _mcp_tool_fn(conn, spec, tool_name, make_client):
    """One dispatch fn for a single MCP tool. Owns the client lifecycle PER DISPATCH — build → list →
    call → close() in a finally — so no stdio child process / reader thread leaks across /chat turns
    (build_sonia_registry is rebuilt every turn and has NO teardown owner; a cached-across-turns client
    would orphan a child on each MCP dispatch). The live tools/list is the third leg of the capability
    intersection, enforced HERE at dispatch (a registered tool the live server does not currently offer
    fails soft). Efficiency note: this re-spawns per dispatch — acceptable for a rarely-called observe
    path; a pooled client with a real turn-end teardown owner is a follow-up (flagged)."""
    def mcp_tool(arguments=None) -> dict:
        client = None
        try:
            client = make_client(spec)                       # per dispatch: spawn (real) / wrap (fake)
            listed = client.list_tools()
            if not listed.get("ok"):
                return {"ok": False, "error": listed.get("error", "tools/list failed")}
            if tool_name not in (listed.get("tools") or []):
                return {"ok": False, "error": f"tool {tool_name!r} not offered by live server {conn.impl_ref!r}"}
            return client.call_tool(tool_name, arguments or {})
        except Exception as e:                               # belt-and-suspenders: never raise into the loop
            return {"ok": False, "error": str(e)}
        finally:
            if client is not None:
                client.close()                               # no leak: terminate the child every dispatch
    return mcp_tool


def build_sonia_registry(h, *, source_factory=None, mcp_client_factory=None) -> tuple[ToolRegistry, ActivityPolicy]:
    """Read-only brain-browse tools over H (all T0_OBSERVE), plus three market tools ONLY when the
    alpaca connector is enabled and its env keys are present, plus namespaced MCP tools for each
    enabled+resolvable kind="mcp" connector. Returns (registry, fail-closed policy).

    Each fn is called by the loop as `fn(**args)` (registry.call), so its single param name IS the
    schema arg name the model must emit. Results are fail-soft dicts ({"ok": bool, ...}); an unknown
    id returns the entry as None rather than raising. `source_factory` (default: lazy make_source)
    supplies the RAW market source; a per-call GuardedSource(AsOfGuard(today)) does the PIT wrap.
    `mcp_client_factory` (default: lazy McpClient) builds an MCP client from a server spec — tests
    inject a FakeMcpTransport-backed factory so no subprocess spawns."""
    reg = ToolRegistry()
    tiers: dict[str, CapabilityTier] = {}

    def _add(name, desc, fn, props, required, *, tier: CapabilityTier = CapabilityTier.T0_OBSERVE):
        reg.register(name, _schema(name, desc, props, required), fn)
        tiers[name] = tier                                   # brain-browse tools default T0; MCP passes conn.tier

    _add("view_doctrine", "Full guidance text of one doctrine section, by section id.",
         lambda section: {"ok": True, "entry": _dump(h.doctrine.get(section))},
         {"section": {"type": "string", "description": "doctrine section id"}}, ["section"])
    _add("view_skill", "Full detail of one K skill, by skill id.",
         lambda skill_id: {"ok": True, "skill": _dump(h.skills.get(skill_id))},
         {"skill_id": {"type": "string"}}, ["skill_id"])
    _add("view_lesson", "Full text of one M memory lesson, by lesson id.",
         lambda lesson_id: {"ok": True, "lesson": _dump(h.memory.get(lesson_id))},
         {"lesson_id": {"type": "string"}}, ["lesson_id"])
    _add("view_workflow", "Full detail of one workflow, by workflow id.",
         lambda workflow_id: {"ok": True, "workflow": _dump(h.workflows.get(workflow_id))},
         {"workflow_id": {"type": "string"}}, ["workflow_id"])
    _add("view_connector", "Full detail of one connector (data source / integration), by connector id.",
         lambda connector_id: {"ok": True, "connector": _dump(h.connectors.get(connector_id))},
         {"connector_id": {"type": "string"}}, ["connector_id"])
    _add("view_subagent", "Full detail of one subagent, by subagent id.",
         lambda subagent_id: {"ok": True, "subagent": _dump(h.subagents.get(subagent_id))},
         {"subagent_id": {"type": "string"}}, ["subagent_id"])
    _add("search_episodes",
         "NOT YET WIRED to the EpisodeStore — always returns zero hits regardless of brain.db "
         "contents. Do NOT infer that episodic memory is empty from an empty result.",
         # Placeholder: episodic search is not yet wired to the EpisodeStore (recorded follow-up).
         # It returns no hits even when brain.db is full, so the model must not over-trust an empty
         # result as evidence of absence. The `note` makes the un-wired state explicit in the result.
         lambda query: {"ok": True, "hits": [], "note": "episodic search not yet wired"},
         {"query": {"type": "string"}}, ["query"])

    # Market tools ride the alpaca connector declaration: register ONLY when the entry exists, is
    # enabled, AND every named env key is present — so a missing .env.alpaca leaves them simply
    # absent (never a boot error). Names match apply.py::_REGISTERABLE_TOOLS exactly (Task 7 pin).
    conn = h.connectors.get("alpaca")
    if conn is not None and conn.enabled and all(os.environ.get(k) for k in conn.env_keys):
        # Honor the connector's declared impl_ref (not the env default) unless a test injects a source.
        make = source_factory if source_factory is not None else (lambda: _default_source_factory(conn.impl_ref))
        _add("market_snapshot", "Latest daily snapshot (price/volume) for one or more symbols.",
             _market_snapshot_fn(make),
             {"symbols": {"type": "array", "items": {"type": "string"},
                          "description": "ticker symbols"}}, ["symbols"])
        _add("daily_bars", "Recent daily OHLCV bars for one symbol (default last 30 days).",
             _daily_bars_fn(make),
             {"symbol": {"type": "string"},
              "days": {"type": "integer", "description": "lookback days (default 30)"}}, ["symbol"])
        _add("latest_decisions", "The most recent persisted DecisionPackage, if a run produced one.",
             _latest_decisions_fn(), {}, [])

    # MCP connectors (Body component C): for each ENABLED kind="mcp" connector whose env_keys are all
    # present AND whose impl_ref resolves in the operator MCP registry, register namespaced observe
    # tools mcp_<connector_id>_<tool>. Registered NAMES = intersection(connector.capabilities,
    # spec.allowed_tools) — capabilities is an ENFORCED allowlist (empty / no overlap -> register
    # nothing, fail-closed). The server's LIVE tools/list is the third leg, enforced at DISPATCH so
    # registration never spawns the child (lazy client, mirrors _default_source_factory). All T0.
    from alpha.mcp.registry import get_server, server_names as _mcp_server_names
    _mcp_servers = _mcp_server_names()
    for conn in h.connectors.all():
        if conn.kind != "mcp" or not conn.enabled:
            continue
        if not all(os.environ.get(k) for k in conn.env_keys):
            continue                                         # env keys missing -> absent (never a boot error)
        if conn.impl_ref not in _mcp_servers:
            continue                                         # unresolvable server -> absent
        spec = get_server(conn.impl_ref)
        if spec is None:                                     # defensive (impl_ref was in server_names)
            continue
        allowed = set(spec.allowed_tools)
        registerable = [t for t in conn.capabilities if t in allowed]   # ENFORCED intersection, order-stable
        if not registerable:
            continue                                         # empty capabilities / no overlap -> nothing
        try:
            conn_tier = CapabilityTier[conn.tier]            # "T0_OBSERVE" -> enum; the tier gate participates
        except KeyError:
            continue                                         # unrecognized tier string -> register nothing (fail-closed)
        make_client = mcp_client_factory if mcp_client_factory is not None else _default_mcp_client_factory
        for tool_name in registerable:
            _add(f"mcp_{conn.connector_id}_{tool_name}",
                 f"MCP tool {tool_name!r} on server {conn.impl_ref!r} ({conn.name}). Fail-soft.",
                 _mcp_tool_fn(conn, spec, tool_name, make_client),
                 {"arguments": {"type": "object",
                                "description": f"arguments object for MCP tool {tool_name!r}"}},
                 [], tier=conn_tier)                         # respect the operator-declared connector tier (not hardcoded T0)

    return reg, ActivityPolicy(reg, tiers)


def render_tool_specs(reg: ToolRegistry) -> str:
    """Render the registry as a TEXT tool-calling protocol block for the system prompt.

    The conversation loop is a TEXT protocol: the model can only call a tool whose ARG NAMES it can
    see, so advertise each tool's name + typed args (a real-LLM guessing arg names 500s otherwise)."""
    lines = ["TOOLS (read-only brain browse — call one to fetch full detail before you answer):"]
    for s in reg.specs():
        params = s.get("parameters") or {}
        props = params.get("properties") or {}
        required = set(params.get("required") or [])
        parts = []
        for pname, pspec in props.items():
            bit = pname if pname in required else f"{pname}?"
            ptype = pspec.get("type")
            if ptype:
                bit += f": {ptype}"
            parts.append(bit)
        lines.append(f"- {s['name']}({', '.join(parts)}): {s.get('description', '')}")
    lines += ["",
              'To CALL a tool, reply with ONLY a JSON object: {"tool": "<name>", "args": {...}}.',
              "To FINISH, reply with prose (optionally your single directions block) and no tool JSON."]
    return "\n".join(lines)
