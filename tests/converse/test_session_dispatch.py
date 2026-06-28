# tests/converse/test_session_dispatch.py
from alpha.converse.session import converse_project
from alpha.converse.sqlite_store import SqliteProjectStore
from alpha.harness.loader import load_seeds


class _Chat:
    def __init__(self, replies): self._r = list(replies)
    def chat(self, system, messages): return self._r.pop(0)


def test_converse_project_routes_through_injected_dispatch(tmp_path):
    # a factory whose dispatch fail-closes any tool name (proving the LIVE path uses dispatch)
    seen = {}
    def factory(h, agent_llm, source, *, read_only, write_mode):
        from alpha.converse.registry import ToolRegistry
        reg = ToolRegistry()
        reg.register("decide", {"name": "decide"}, lambda **a: {"unreached": True})
        def dispatch(name, args):
            seen["called"] = (name, args)
            return {"error": "fail-closed (test)"}
        return reg, dispatch
    store = SqliteProjectStore.open(str(tmp_path / "state.db"))
    chat = _Chat(['{"tool": "decide", "args": {"date": "2026-01-05"}}', "done"])
    proj = converse_project("p1", "hi", harness=load_seeds("seeds"), store=store,
                            agent_llm=None, chat_llm=chat, source=None,
                            registry_factory=factory)
    assert seen["called"] == ("decide", {"date": "2026-01-05"})         # dispatch was used
    assert proj.turns[-1].tool_calls[0]["result"] == {"error": "fail-closed (test)"}
    assert proj.turns[-1].final_text == "done"


def test_converse_project_default_factory_unchanged(tmp_path):
    store = SqliteProjectStore.open(str(tmp_path / "s.db"))
    chat = _Chat(["just talking"])                                       # no tool call
    proj = converse_project("p2", "hello", harness=load_seeds("seeds"), store=store,
                            agent_llm=None, chat_llm=chat, source=None)   # no factory
    assert proj.turns[-1].final_text == "just talking"
