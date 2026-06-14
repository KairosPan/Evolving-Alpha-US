import pytest
from alpha.harness.skill import Skill
from alpha.harness.memory import Lesson
from alpha.harness.doctrine import Doctrine
from alpha.harness.registry import SkillRegistry, MemoryStore
from alpha.harness.state import HarnessState
from alpha.harness.errors import ImmutableDoctrineError


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
