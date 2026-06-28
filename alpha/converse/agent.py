# alpha/converse/agent.py
from __future__ import annotations
from datetime import date, datetime
from alpha.harness.state import HarnessState
from alpha.llm.chat import ChatMessage
from alpha.llm.config import make_client
from alpha.data.registry import make_source
from alpha.converse.registry import ToolRegistry
from alpha.converse.loop import run_conversation, ConversationResult
from alpha.converse.tools import make_decide_for_date_tool, make_gated_write_tool, make_propose_edit_tool
from alpha.agent.retrieval import select_for_prompt


def build_converse_registry(harness: HarnessState, agent_llm, source,
                            *, read_only: bool = False, write_mode: str = "apply",
                            conflict_queue=None, provenance=None) -> ToolRegistry:
    reg = ToolRegistry()
    decide_schema, decide_fn = make_decide_for_date_tool(harness, agent_llm, source)
    reg.register("decide", decide_schema, decide_fn)
    mode = "none" if read_only else write_mode
    if mode == "apply":
        write_schema, write_fn = make_gated_write_tool(
            harness, conflict_queue=conflict_queue, provenance=provenance)
        reg.register("propose_memory_edit", write_schema, write_fn)
    elif mode == "stage":
        write_schema, write_fn = make_propose_edit_tool(harness)
        reg.register("propose_memory_edit", write_schema, write_fn)
    return reg


def build_system_prompt(harness: HarnessState, registry: ToolRegistry, *,
                        asof: date | datetime | None = None) -> str:
    lines = [
        "You are evolving-alpha's conversational face. You share one brain (H) with the deterministic "
        "decider. You may use tools.",
        "",
        "TOOLS:",
    ]
    for s in registry.specs():
        lines.append(f"- {s['name']}: {s.get('description', '')}")
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
    registry = build_converse_registry(harness, agent_llm, source)
    system = build_system_prompt(harness, registry, asof=asof)
    return run_conversation(registry, chat_llm, system, [ChatMessage(role="user", text=user_text)],
                            max_iters=max_iters)
