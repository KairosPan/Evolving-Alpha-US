"""Task 9 — Sonia's observe loop: respond() reroutes through run_conversation with a T0-only
ActivityPolicy over seven read-only brain-browse tools. Offline: scripted `_Chat` returns a canned
tool-call JSON then a prose finish (the same shape as the arena's test_policy scripted client)."""
import json
from pathlib import Path

from alpha.harness.edit_log import EditLog
from alpha.harness.loader import load_seeds
from alpha.harness.metatools import MetaTools
from alpha.meta.models import Message, Session, new_message_id, now_iso
from alpha.meta.sonia_agent import SoniaAgent
from alpha.meta.sonia_tools import build_sonia_registry

SEEDS = Path(__file__).resolve().parents[2] / "seeds"   # momo pack lives at seeds/, not seeds/momo

# The seven tool NAMES must match apply.py::_REGISTERABLE_TOOLS exactly (Task 7 pinned this set).
_VIEW_TOOLS = {"view_doctrine", "view_skill", "view_lesson", "view_workflow",
               "view_connector", "view_subagent", "search_episodes"}


class _Chat:
    """Scripted chat: pops canned replies in order. Duck-types ChatLLMClient.chat(system, messages)."""

    def __init__(self, replies):
        self._r = list(replies)

    def chat(self, system, messages):
        return self._r.pop(0)


def _sess():
    return Session(session_id="s1", created_at=now_iso())


def _umsg(text):
    return Message(message_id=new_message_id(), role="user", created_at=now_iso(),
                   text=text, origin="user")


def test_registry_registers_seven_view_tools_at_t0():
    h = load_seeds(SEEDS)
    reg, pol = build_sonia_registry(h)
    names = {s["name"] for s in reg.specs()}
    assert _VIEW_TOOLS <= names
    # every registered tool is T0-tiered (the fail-closed policy would refuse an untiered one)
    for name in names:
        assert pol.tiers[name].name == "T0_OBSERVE"


def test_view_connector_tool_returns_the_alpaca_seed():
    h = load_seeds(SEEDS)
    reg, pol = build_sonia_registry(h)
    out = pol.dispatch("view_connector", {"connector_id": "alpaca"})
    assert out["ok"] and out["connector"]["connector_id"] == "alpaca"
    # unknown id fails SOFT (ok=True, entry None) — never raises out of the loop
    miss = pol.dispatch("view_connector", {"connector_id": "does-not-exist"})
    assert miss["ok"] and miss["connector"] is None


def test_view_workflow_and_subagent_soft_on_empty_momo_registry():
    h = load_seeds(SEEDS)                                   # momo pack has no workflows/subagents
    reg, pol = build_sonia_registry(h)
    assert pol.dispatch("view_workflow", {"workflow_id": "x"}) == {"ok": True, "workflow": None}
    assert pol.dispatch("view_subagent", {"subagent_id": "x"}) == {"ok": True, "subagent": None}


def test_respond_uses_a_tool_then_finishes():
    h = load_seeds(SEEDS)
    # turn 1: model asks to view the alpaca connector; turn 2: prose answer citing what it saw
    chat = _Chat([json.dumps({"tool": "view_connector", "args": {"connector_id": "alpaca"}}),
                  "Alpaca is your data connector."])
    agent = SoniaAgent(MetaTools(h, EditLog()), chat, registry_factory=build_sonia_registry)
    msg = agent.respond(_sess(), _umsg("what data do we have?"))
    assert "Alpaca" in msg.text                             # final prose after the tool turn
    assert msg.directions == []


def test_respond_still_parses_directions_without_tools():
    # CRITICAL interplay: a reply whose ONLY JSON block is {"directions": ...} has no "tool" key,
    # so the loop treats it as the final answer and parse_directions(final_text) still fires.
    h = load_seeds(SEEDS)
    chat = _Chat(['Here is a thought.\n{"directions": [{"title": "T", "summary": "S"}]}'])
    agent = SoniaAgent(MetaTools(h, EditLog()), chat, registry_factory=build_sonia_registry)
    msg = agent.respond(_sess(), _umsg("ideas?"))
    assert msg.directions and msg.directions[0].title == "T"
    assert "T" not in msg.text or msg.text.startswith("Here is a thought")   # block stripped from prose


def test_respond_without_factory_is_single_shot():
    # Back-compat: no registry_factory -> the old single chat() call, no tool loop.
    h = load_seeds(SEEDS)
    chat = _Chat(["Just prose, no tools."])
    agent = SoniaAgent(MetaTools(h, EditLog()), chat)
    msg = agent.respond(_sess(), _umsg("hi"))
    assert msg.text == "Just prose, no tools."


def test_system_prompt_advertises_tool_arg_names():
    # The loop is a TEXT protocol: a real LLM can only call a tool whose ARG NAMES it can see.
    h = load_seeds(SEEDS)
    reg, _ = build_sonia_registry(h)
    agent = SoniaAgent(MetaTools(h, EditLog()), _Chat([]), registry_factory=build_sonia_registry)
    system = agent._system(reg)
    assert "view_connector(connector_id" in system            # arg name is rendered
    assert '{"tool"' in system                                # call protocol is spelled out
