from alpha.converse.registry import ToolRegistry
from alpha.converse.loop import run_conversation
from alpha.llm.chat import ChatMessage
from alpha.llm.client import MockLLMClient


def _reg():
    reg = ToolRegistry()
    reg.register("echo", {"name": "echo"}, lambda msg: f"got:{msg}")
    return reg


def test_dispatches_tool_then_finalizes():
    # turn 1: model calls echo; turn 2: model gives a prose final answer
    llm = MockLLMClient(['{"tool": "echo", "args": {"msg": "hi"}}', "all done"])
    res = run_conversation(_reg(), llm, "sys", [ChatMessage(role="user", text="go")])
    assert res.final_text == "all done"
    assert res.hit_max_iters is False
    assert len(res.tool_calls) == 1
    assert res.tool_calls[0]["tool"] == "echo" and res.tool_calls[0]["result"] == "got:hi"


def test_no_tool_call_is_immediate_final():
    llm = MockLLMClient(["just prose, no json"])
    res = run_conversation(_reg(), llm, "sys", [ChatMessage(role="user", text="hi")])
    assert res.final_text == "just prose, no json"
    assert res.tool_calls == []


def test_unknown_tool_is_reported_not_raised():
    llm = MockLLMClient(['{"tool": "ghost", "args": {}}', "done"])
    res = run_conversation(_reg(), llm, "sys", [ChatMessage(role="user", text="go")])
    assert res.tool_calls[0]["result"] == {"error": "unknown tool: ghost"}
    assert res.final_text == "done"


def test_respects_max_iters():
    # model always emits a tool call -> never finalizes -> budget exhausts
    llm = MockLLMClient(['{"tool": "echo", "args": {"msg": "x"}}'])
    res = run_conversation(_reg(), llm, "sys", [ChatMessage(role="user", text="go")], max_iters=3)
    assert res.hit_max_iters is True
    assert len(res.tool_calls) == 3
    # On exhaustion the turn must NOT silently yield empty prose: a fallback final_text is returned
    # (callers render res.final_text directly) while hit_max_iters stays True for programmatic detection.
    assert res.final_text != ""
    assert "3" in res.final_text
