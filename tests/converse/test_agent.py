from datetime import date, datetime
from alpha.harness.skill import Skill
from alpha.harness.doctrine import Doctrine
from alpha.harness.registry import SkillRegistry, MemoryStore
from alpha.harness.state import HarnessState
from alpha.llm.client import MockLLMClient
from alpha.converse.agent import build_converse_registry, build_system_prompt, converse


def _h():
    skills = SkillRegistry.from_skills([
        Skill(skill_id="gap_and_go", name="Gap and Go", type="pattern", family="runner",
              phases=["trend"], status="active"),
    ])
    return HarnessState(doctrine=Doctrine(), skills=skills, memory=MemoryStore.from_lessons([]))


def test_registry_has_both_tools():
    reg = build_converse_registry(_h(), MockLLMClient("{}"))
    names = {s["name"] for s in reg.specs()}
    assert names == {"decide", "propose_memory_edit"}


def test_system_prompt_lists_tools_and_convention():
    reg = build_converse_registry(_h(), MockLLMClient("{}"))
    sys = build_system_prompt(_h(), reg)
    assert "decide" in sys and "propose_memory_edit" in sys
    assert '"tool"' in sys  # documents the tool-call JSON convention


def test_converse_calls_decide_then_finalizes():
    # the conversational (converse-role) LLM drives a 2-step turn:
    #   reply 1 -> call decide ; reply 2 -> final prose
    chat_llm = MockLLMClient(['{"tool": "decide", "args": {}}', "My read: RUN looks like a gap-and-go."])
    # the day-agent LLM that `decide` invokes returns a canned DecisionPackage
    agent_llm = MockLLMClient('{"regime_read": "trend frontside", "candidates": '
                              '[{"symbol": "RUN", "pattern": "gap_and_go", "confidence": 0.7}]}')
    # decide() needs a state+universe; for 1A the tool is called with no args, so converse() must
    # supply them — assert the loop reached a final answer after one decide call.
    res = converse(_h(), "what's your read on RUN today?", agent_llm=agent_llm, chat_llm=chat_llm)
    assert res.hit_max_iters is False
    assert res.final_text == "My read: RUN looks like a gap-and-go."
    assert [c["tool"] for c in res.tool_calls] == ["decide"]
    # DecisionPackage is a frozen pydantic model — not dict-subscriptable; use attribute access
    assert res.tool_calls[0]["result"].candidates[0].symbol == "RUN"
