# alpha/converse/agent.py
from __future__ import annotations
from datetime import date, datetime
from alpha.harness.state import HarnessState
from alpha.llm.chat import ChatMessage
from alpha.llm.config import make_client
from alpha.data.registry import make_source
from alpha.converse.registry import ToolRegistry
from alpha.converse.loop import run_conversation, ConversationResult
from alpha.converse.tools import make_decide_for_date_tool
from alpha.agent.retrieval import select_for_prompt


def build_converse_registry(harness: HarnessState, agent_llm, source,
                            *, read_only: bool = False, write_mode: str = "stage",
                            conflict_queue=None, provenance=None) -> ToolRegistry:
    """The worker face registers no H-mutation tool (charter First Founding Principle: "Kairos does
    not propose at all"). make_gated_write_tool (live landing) was retired 2026-07-09; the STAGING
    tool (propose_memory_edit) was retired by A7 2026-07-13 — H evolves over worker TRACES via the
    Sonia-side proposer (reflect.py → /proposals), not by the worker proposing.

    write_mode is kept for signature stability: "apply" still RAISES (never silently downgrade); any
    other value ("stage"/"none") registers no brain-edit tool. conflict_queue/provenance are accepted
    for signature stability (they no longer route a worker propose path)."""
    reg = ToolRegistry()
    decide_schema, decide_fn = make_decide_for_date_tool(harness, agent_llm, source)
    reg.register("decide", decide_schema, decide_fn)
    mode = "none" if read_only else write_mode
    if mode == "apply":
        raise ValueError("write_mode='apply' was retired (charter conformance 2026-07-09): "
                         "the worker face never lands its own edit — and A7 retired staging too")
    return reg


def _render_tool_spec(spec: dict) -> str:
    """Render one tool as `name(arg[?]: type one of {...} — desc, ...): description`.

    The conversation loop is a TEXT protocol — the model can only call a tool whose argument names it
    can see. Rendering just name+description (the old behaviour) left tools with non-obvious args (e.g.
    decide's required `date`) uninvokable: a real LLM just guesses arg names and every call 500s on a
    TypeError. So advertise the parameters: names, required-ness, types, enums and any per-arg description."""
    params = spec.get("parameters") or {}
    props = params.get("properties") or {}
    required = set(params.get("required") or [])
    parts = []
    for pname, pspec in props.items():
        bit = pname if pname in required else f"{pname}?"
        ptype = pspec.get("type")
        if ptype:
            bit += f": {ptype}"
        enum = pspec.get("enum")
        if enum:
            bit += " one of {" + "|".join(str(v) for v in enum) + "}"
        pdesc = pspec.get("description")
        if pdesc:
            bit += f" — {pdesc}"
        parts.append(bit)
    sig = ", ".join(parts)
    return f"- {spec['name']}({sig}): {spec.get('description', '')}"


def build_system_prompt(harness: HarnessState, registry: ToolRegistry, *,
                        asof: date | datetime | None = None) -> str:
    lines = [
        "You are Kairos, this system's conversational face. You share one brain (H) with the deterministic "
        "decider. You may use tools.",
        "",
        "TOOLS:",
    ]
    for s in registry.specs():
        lines.append(_render_tool_spec(s))
    selection = select_for_prompt(harness, phase_prior=None, asof=asof)
    if selection.lessons:
        lines += ["", "RECALLED LESSONS:"]
        for lesson in selection.lessons:
            lines.append(f"- {lesson.lesson}")
    lines += [
        "",
        "To CALL a tool, reply with a JSON object: {\"tool\": \"<name>\", \"args\": {...}}.",
        "To FINISH, reply with prose and no such JSON object.",
        "",
        f"DOCTRINE: {harness.doctrine.summary() if hasattr(harness.doctrine, 'summary') else ''}",
    ]
    return "\n".join(lines)


def converse(harness: HarnessState, user_text: str, *, agent_llm=None, chat_llm=None, source=None,
             max_iters: int = 8, asof: date | datetime | None = None) -> ConversationResult:
    agent_llm = agent_llm if agent_llm is not None else make_client("agent")
    chat_llm = chat_llm if chat_llm is not None else make_client("converse")
    source = source if source is not None else make_source()
    # write_mode="none": this bare helper persists nothing and has no approval surface — a stage
    # tool here would silently drop its stagings at turn end (stated, not silent: no tool at all).
    # The persisted staging flow lives in converse_project (workbench).
    registry = build_converse_registry(harness, agent_llm, source, write_mode="none")
    system = build_system_prompt(harness, registry, asof=asof)
    return run_conversation(registry, chat_llm, system, [ChatMessage(role="user", text=user_text)],
                            max_iters=max_iters)
