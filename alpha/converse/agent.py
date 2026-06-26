# alpha/converse/agent.py
from __future__ import annotations
from datetime import date, datetime
from alpha.harness.state import HarnessState
from alpha.state.market import MarketState
from alpha.universe.stock import StockSnapshot
from alpha.universe.universe import CandidateUniverse
from alpha.llm.chat import ChatMessage
from alpha.llm.config import make_client
from alpha.converse.registry import ToolRegistry
from alpha.converse.loop import run_conversation, ConversationResult
from alpha.converse.tools import make_decide_tool, make_gated_write_tool

# Phase 1A: a fixed default perception context for the no-arg `decide` tool. Building state from a
# live (source, date) is Phase 1B; here the conversational face proves the loop + tool plumbing.
def _default_state() -> MarketState:
    return MarketState(date=date(2026, 6, 12), gainer_count=1, gap_up_count=0, loser_count=0,
                       failed_breakout_count=0, max_runner_tier=1, echelon=[], breadth_raw=1.0,
                       sentiment_norm=0.6, as_of=datetime(2026, 6, 12, 16, 0))


def _default_universe() -> CandidateUniverse:
    return CandidateUniverse.from_stocks([StockSnapshot(symbol="RUN", name="Runner", status="gainer")])


def build_converse_registry(harness: HarnessState, agent_llm) -> ToolRegistry:
    reg = ToolRegistry()
    decide_schema, decide_fn = make_decide_tool(harness, agent_llm)
    reg.register("decide", decide_schema,
                 lambda: decide_fn(state=_default_state(), universe=_default_universe()))
    write_schema, write_fn = make_gated_write_tool(harness)
    reg.register("propose_memory_edit", write_schema, write_fn)
    return reg


def build_system_prompt(harness: HarnessState, registry: ToolRegistry) -> str:
    lines = [
        "You are evolving-alpha's conversational face. You share one brain (H) with the deterministic "
        "decider. You may use tools.",
        "",
        "TOOLS:",
    ]
    for s in registry.specs():
        lines.append(f"- {s['name']}: {s.get('description', '')}")
    lines += [
        "",
        "To CALL a tool, reply with a JSON object: {\"tool\": \"<name>\", \"args\": {...}}.",
        "To FINISH, reply with prose and no such JSON object.",
        "",
        f"DOCTRINE: {harness.doctrine.summary() if hasattr(harness.doctrine, 'summary') else ''}",
    ]
    return "\n".join(lines)


def converse(harness: HarnessState, user_text: str, *, agent_llm=None, chat_llm=None,
             max_iters: int = 8) -> ConversationResult:
    agent_llm = agent_llm if agent_llm is not None else make_client("agent")
    chat_llm = chat_llm if chat_llm is not None else make_client("converse")
    registry = build_converse_registry(harness, agent_llm)
    system = build_system_prompt(harness, registry)
    return run_conversation(registry, chat_llm, system, [ChatMessage(role="user", text=user_text)],
                            max_iters=max_iters)
