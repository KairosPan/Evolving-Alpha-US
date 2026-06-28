from __future__ import annotations
import json
from pydantic import BaseModel, Field
from alpha.llm.chat import ChatLLMClient, ChatMessage
from alpha.llm.extract import extract_json_object
from alpha.converse.registry import ToolRegistry


class ConversationResult(BaseModel):
    final_text: str = ""
    messages: list[ChatMessage] = Field(default_factory=list)
    tool_calls: list[dict] = Field(default_factory=list)   # [{"tool","args","result"}]
    hit_max_iters: bool = False


def _result_text(result) -> str:
    if hasattr(result, "model_dump_json"):
        return result.model_dump_json()
    try:
        return json.dumps(result, default=str)
    except TypeError:
        return str(result)


def _parse_tool_call(reply: str) -> dict | None:
    block = extract_json_object(reply)
    if not block:
        return None
    try:
        obj = json.loads(block)
    except json.JSONDecodeError:
        return None
    return obj if isinstance(obj, dict) and "tool" in obj else None


def run_conversation(registry: ToolRegistry, chat: ChatLLMClient, system: str,
                     messages: list[ChatMessage], *, max_iters: int = 8,
                     dispatch=None) -> ConversationResult:
    """Multi-turn tool-calling loop. Each iter: ask the model; if its reply is a tool call, dispatch
    it and feed the result back; otherwise the reply is the final answer. Bounded by max_iters.

    *dispatch* (name, args) -> result lets a caller (e.g. alpha.arena.ActivityPolicy) intercept every
    tool call at one choke point. Defaults to registry.call(name, **args) — byte-identical to before."""
    if dispatch is None:
        def dispatch(name, args):                 # default: the plain registry call
            return registry.call(name, **(args or {}))
    msgs = list(messages)
    calls: list[dict] = []
    for _ in range(max_iters):
        reply = chat.chat(system, msgs)
        call = _parse_tool_call(reply)
        if call is None:
            return ConversationResult(final_text=reply.strip(), messages=msgs, tool_calls=calls)
        name, args = call["tool"], call.get("args", {}) or {}
        try:
            result = dispatch(name, args)
        except KeyError:
            result = {"error": f"unknown tool: {name}"}
        except Exception as e:                       # a tool raising must not kill the conversation
            result = {"error": f"{type(e).__name__}: {e}"}
        calls.append({"tool": name, "args": args, "result": result})
        msgs.append(ChatMessage(role="assistant", text=reply))
        msgs.append(ChatMessage(role="user", text=f"[tool:{name} result]\n{_result_text(result)}"))
    return ConversationResult(
        final_text=(f"(I reached the {max_iters}-step tool-calling limit without finishing. "
                    "Try narrowing the request or asking again.)"),
        messages=msgs, tool_calls=calls, hit_max_iters=True)
