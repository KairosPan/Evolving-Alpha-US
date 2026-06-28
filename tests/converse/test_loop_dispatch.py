from alpha.converse.loop import run_conversation
from alpha.converse.registry import ToolRegistry


class _Chat:
    def __init__(self, replies): self._r = list(replies)
    def chat(self, system, messages): return self._r.pop(0)


def test_dispatch_callable_intercepts_tool_calls():
    reg = ToolRegistry()
    reg.register("look", {"name": "look"}, lambda: {"raw": "registry"})
    seen = []
    def dispatch(name, args):
        seen.append((name, args))
        return {"via": "policy"}
    chat = _Chat(['{"tool": "look", "args": {}}', "done"])
    res = run_conversation(reg, chat, "sys", [], max_iters=3, dispatch=dispatch)
    assert seen == [("look", {})]
    assert res.tool_calls[0]["result"] == {"via": "policy"}
    assert res.final_text == "done"


def test_default_dispatch_is_registry_call():
    reg = ToolRegistry()
    reg.register("look", {"name": "look"}, lambda: {"raw": "registry"})
    chat = _Chat(['{"tool": "look", "args": {}}', "done"])
    res = run_conversation(reg, chat, "sys", [], max_iters=3)
    assert res.tool_calls[0]["result"] == {"raw": "registry"}
