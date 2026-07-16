import pytest
from alpha.harness.subagents import SubagentEntry, SubagentRegistry
from alpha.harness.state import HarnessState
from alpha.harness.doctrine import Doctrine
from alpha.harness.registry import MemoryStore, SkillRegistry


def _entry(sid="research", **kw):
    base = dict(subagent_id=sid, name="Research Analyst",
                description="Dispatch for deep multi-source research on a single ticker.",
                system_prompt="You are a focused research analyst.",
                tools=["read", "search"], skills_preload=["skill_x"])
    base.update(kw)
    return SubagentEntry(**base)


def test_entry_rejects_unknown_field():
    with pytest.raises(Exception):
        SubagentEntry(subagent_id="x", name="X", bogus=1)


def test_entry_defaults():
    e = _entry()
    assert e.llm_role == "inherit"
    assert e.max_tier == "T0_OBSERVE"
    assert e.max_turns == 8
    assert e.status == "active"
    assert e.domain == "trading"
    assert e.tools == ["read", "search"]
    assert e.skills_preload == ["skill_x"]


def test_entry_empty_defaults():
    e = SubagentEntry(subagent_id="s", name="S")
    assert e.description == "" and e.system_prompt == "" and e.notes == ""
    assert e.tools == [] and e.skills_preload == []
    assert e.llm_role == "inherit" and e.max_tier == "T0_OBSERVE" and e.max_turns == 8


def test_registry_dup_id_raises():
    with pytest.raises(ValueError):
        SubagentRegistry.from_subagents([_entry(), _entry()])


def test_registry_get_all_len_bool():
    r = SubagentRegistry.from_subagents([_entry()])
    assert r.get("research").name == "Research Analyst" and r.get("absent") is None
    assert len(r) == 1 and r.all()[0].subagent_id == "research"
    assert bool(SubagentRegistry.empty()) is True and len(SubagentRegistry.empty()) == 0


def test_registry_upsert_replaces():
    r = SubagentRegistry.empty()
    r.upsert(_entry())
    r.upsert(_entry(name="Research Analyst v2"))
    assert len(r) == 1 and r.get("research").name == "Research Analyst v2"


def _minimal_h(**kw):
    return HarnessState(doctrine=Doctrine(), skills=SkillRegistry.from_skills([]),
                        memory=MemoryStore.from_lessons([]), **kw)


def test_harness_roundtrip_carries_subagents():
    h = _minimal_h(subagents=SubagentRegistry.from_subagents([_entry()]))
    d = h.to_dict()
    assert d["subagents"][0]["subagent_id"] == "research"
    assert d["subagents"][0]["tools"] == ["read", "search"]
    h2 = HarnessState.from_dict(d)
    a = h2.subagents.get("research")
    assert a.llm_role == "inherit" and a.max_turns == 8 and a.status == "active"


def test_legacy_dump_without_subagents_yields_empty():
    h = _minimal_h()
    d = h.to_dict()
    d.pop("subagents")
    h2 = HarnessState.from_dict(d)
    assert len(h2.subagents) == 0
