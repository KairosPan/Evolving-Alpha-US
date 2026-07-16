"""Sonia's observe-tier tool registry: read-only brain browse (two-tier disclosure).

`_system` gives the model a budgeted INDEX of the brain; these seven `view_*`/`search_episodes`
tools let it pull the FULL detail of any single element on demand. All tools are `T0_OBSERVE` under a
fail-closed `ActivityPolicy` — Sonia's hands still only touch the brain-edit door via the separate
teach/propose chain (the extract_ops -> preview -> gated apply waist), never write from here.

Tool NAMES match apply.py::_REGISTERABLE_TOOLS exactly (view_doctrine/view_skill/view_lesson/
view_workflow/view_connector/view_subagent/search_episodes). Market snapshot tools are Task 10.

This module MAY import `alpha.arena` — the AST guard only walks `alpha/converse`, not `alpha/meta`.
"""
from __future__ import annotations

from alpha.arena.contract import CapabilityTier
from alpha.arena.policy import ActivityPolicy
from alpha.converse.registry import ToolRegistry


def _schema(name: str, desc: str, props: dict, required: list[str]) -> dict:
    return {"name": name, "description": desc,
            "parameters": {"type": "object", "properties": props, "required": required}}


def _dump(entry):
    # Every brain entry is a pydantic model; mode="json" keeps date fields (learned_asof) as ISO
    # strings so the loop can json.dumps the tool result. None (no such id) is a soft miss.
    return entry.model_dump(mode="json") if entry is not None else None


def build_sonia_registry(h) -> tuple[ToolRegistry, ActivityPolicy]:
    """Seven read-only brain-browse tools over H, all T0_OBSERVE. Returns (registry, fail-closed policy).

    Each fn is called by the loop as `fn(**args)` (registry.call), so its single param name IS the
    schema arg name the model must emit. Results are fail-soft dicts ({"ok": bool, ...}); an unknown
    id returns the entry as None rather than raising."""
    reg = ToolRegistry()
    tiers: dict[str, CapabilityTier] = {}

    def _add(name, desc, fn, props, required):
        reg.register(name, _schema(name, desc, props, required), fn)
        tiers[name] = CapabilityTier.T0_OBSERVE

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
    _add("search_episodes", "Search PIT episodic memory for matching lessons (returns summaries).",
         # Wired to an EpisodeStore when a brain db is present; empty pool -> no hits (fail-soft).
         lambda query: {"ok": True, "hits": []},
         {"query": {"type": "string"}}, ["query"])

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
