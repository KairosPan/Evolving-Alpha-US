from datetime import date
import pandas as pd
from alpha.harness.skill import Skill
from alpha.harness.doctrine import Doctrine
from alpha.harness.registry import SkillRegistry, MemoryStore
from alpha.harness.state import HarnessState
from alpha.data.source import FakeSource
from alpha.llm.client import MockLLMClient
from alpha.converse.agent import build_converse_registry, build_system_prompt, converse


def _h():
    skills = SkillRegistry.from_skills([
        Skill(skill_id="gap_and_go", name="Gap and Go", type="pattern", family="runner",
              phases=["trend"], status="active"),
    ])
    return HarnessState(doctrine=Doctrine(), skills=skills, memory=MemoryStore.from_lessons([]))


def _fake_source():
    cal = [date(2026, 6, d) for d in range(10, 14)]
    snaps, px, closes = {}, 10.0, []
    for d in cal:
        prev = px; px = px * 1.15; closes.append(px)
        snaps[d] = pd.DataFrame({"symbol": ["RUN"], "name": ["RUN"], "open": [prev], "high": [px],
                                 "low": [prev], "close": [px], "volume": [1], "prev_close": [prev]})
    bars = {"RUN": pd.DataFrame({"date": cal, "open": [10.0] + closes[:-1], "high": closes,
                                 "low": [10.0] + closes[:-1], "close": closes, "volume": [1] * len(cal)})}
    return FakeSource(calendar=cal, bars=bars, snapshots=snaps)


def _agent_llm():
    return MockLLMClient('{"regime_read": "trend frontside", "candidates": '
                         '[{"symbol": "RUN", "pattern": "gap_and_go", "confidence": 0.7}]}')


def test_registry_has_both_tools():
    reg = build_converse_registry(_h(), _agent_llm(), _fake_source())
    assert {s["name"] for s in reg.specs()} == {"decide", "propose_memory_edit"}


def test_system_prompt_lists_tools_and_convention():
    reg = build_converse_registry(_h(), _agent_llm(), _fake_source())
    sys = build_system_prompt(_h(), reg)
    assert "decide" in sys and "propose_memory_edit" in sys
    assert '"tool"' in sys


def test_system_prompt_advertises_tool_parameters():
    """The text protocol only shows the model what the prompt renders. propose_memory_edit takes a
    nested meta-tool call {tool, args, rationale} where tool is one of a fixed set — none of which a
    model can guess from the name+description alone. The prompt MUST advertise the parameter names and
    the valid meta-tool values, or the tool is uninvokable by a real LLM (it just guesses arg names)."""
    reg = build_converse_registry(_h(), _agent_llm(), _fake_source())
    sys = build_system_prompt(_h(), reg)
    # decide's date arg must be discoverable
    assert "date" in sys
    # propose_memory_edit's own keys + the valid meta-tool names it dispatches to
    assert "rationale" in sys
    for metatool in ("process_memory", "update_memory", "demote_memory"):
        assert metatool in sys, f"valid meta-tool {metatool!r} not advertised in system prompt"


def test_converse_calls_decide_for_date_then_finalizes():
    chat_llm = MockLLMClient(['{"tool": "decide", "args": {"date": "2026-06-12"}}',
                              "My read: RUN looks like a gap-and-go."])
    res = converse(_h(), "what's your read on RUN for 2026-06-12?",
                   agent_llm=_agent_llm(), chat_llm=chat_llm, source=_fake_source())
    assert res.hit_max_iters is False
    assert res.final_text == "My read: RUN looks like a gap-and-go."
    assert [c["tool"] for c in res.tool_calls] == ["decide"]
    assert res.tool_calls[0]["result"].candidates[0].symbol == "RUN"   # DecisionPackage (frozen pydantic; attr access)


def test_write_mode_none_registry_is_decide_only():
    """The bare converse() helper uses write_mode="none": it persists nothing and has no approval
    surface, so offering a stage tool would silently drop stagings at turn end."""
    reg = build_converse_registry(_h(), _agent_llm(), _fake_source(), write_mode="none")
    assert {s["name"] for s in reg.specs()} == {"decide"}
