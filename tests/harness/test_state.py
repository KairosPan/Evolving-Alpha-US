import pytest
from alpha.harness.skill import Skill
from alpha.harness.memory import Lesson
from alpha.harness.doctrine import Doctrine
from alpha.harness.registry import SkillRegistry, MemoryStore
from alpha.harness.state import HarnessState
from alpha.harness.errors import ImmutableDoctrineError


def _state_with_operational():
    """HarnessState that includes operational-domain Skill and Lesson (PC-3 round-trip pin)."""
    skills = SkillRegistry.from_skills([
        Skill(skill_id="trade_s", name="Trade Skill", type="pattern",
              family="runner", phases=["trend"], status="active", domain="trading"),
        Skill(skill_id="op_s", name="Op Skill", type="pattern",
              family="runner", phases=["trend"], status="active", domain="operational"),
    ])
    memory = MemoryStore.from_lessons([
        Lesson(lesson_id="l_trade", phases=["trend"], outcome="win",
               lesson="trade lesson", domain="trading"),
        Lesson(lesson_id="l_op", phases=["trend"], outcome="win",
               lesson="op lesson", domain="operational"),
    ])
    doctrine = Doctrine.from_seed_list([
        {"section": "core", "regime": "all", "immutable": True, "guidance": "stop discipline"},
    ])
    return HarnessState(doctrine=doctrine, skills=skills, memory=memory)


def _state():
    skills = SkillRegistry.from_skills([
        Skill(skill_id="a", name="A", type="pattern", family="runner", phases=["trend"], status="active"),
        Skill(skill_id="b", name="B", type="pattern", family="runner", phases=["trend"], status="incubating"),
    ])
    memory = MemoryStore.from_lessons([Lesson(lesson_id="l1", phases=["trend"], outcome="win", lesson="x")])
    doctrine = Doctrine.from_seed_list([
        {"section": "core", "regime": "all", "immutable": True, "guidance": "stop discipline"},
    ])
    return HarnessState(doctrine=doctrine, skills=skills, memory=memory)


def test_active_skills_for_phase():
    st = _state()
    assert [s.skill_id for s in st.active_skills_for("trend")] == ["a"]   # 'b' is incubating


def test_roundtrip_preserves_immutable_guard():
    st = _state()
    d = st.to_dict()
    st2 = HarnessState.from_dict(d)
    assert len(st2.skills) == 2 and len(st2.memory) == 1
    core = st2.doctrine.get("core")
    assert core.immutable is True
    with pytest.raises(ImmutableDoctrineError):       # guard restored after rebuild
        core.guidance = "tampered"


def test_vocabulary_defaults_momo_and_survives_roundtrip():
    """P0.5: the pack vocabulary rides ON the H. Default is 'momo'; an explicit stamp survives
    to_dict() -> from_dict()."""
    assert _state().vocabulary == "momo"                 # default when unstamped
    st = _state()
    st.vocabulary = "growth"
    d = st.to_dict()
    assert d["vocabulary"] == "growth"                   # serialised (not silently dropped)
    assert HarnessState.from_dict(d).vocabulary == "growth"


def test_legacy_dump_without_vocabulary_defaults_momo():
    """A pre-P0.5 brain.json / snapshot carries no `vocabulary` key -> loads as momo (byte-identical
    to the old behaviour, no migration needed)."""
    legacy = _state().to_dict()
    legacy.pop("vocabulary")                             # simulate an old dump
    assert HarnessState.from_dict(legacy).vocabulary == "momo"


def test_domain_survives_harness_roundtrip():
    """PC-3 Fork-E pin: Skill.domain and Lesson.domain survive to_dict() → from_dict()."""
    st = _state_with_operational()
    d = st.to_dict()
    st2 = HarnessState.from_dict(d)

    skills_by_id = {s.skill_id: s for s in st2.skills.all()}
    assert skills_by_id["trade_s"].domain == "trading"
    assert skills_by_id["op_s"].domain == "operational"

    lessons_by_id = {l.lesson_id: l for l in st2.memory.all()}
    assert lessons_by_id["l_trade"].domain == "trading"
    assert lessons_by_id["l_op"].domain == "operational"

    # Also pin that 'domain' key appears in the serialised dicts (not silently dropped)
    skill_dicts = {s["skill_id"]: s for s in d["skills"]}
    assert skill_dicts["op_s"]["domain"] == "operational"
    lesson_dicts = {l["lesson_id"]: l for l in d["memory"]}
    assert lesson_dicts["l_op"]["domain"] == "operational"
