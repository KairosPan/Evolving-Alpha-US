import pytest
from alpha.harness.skill import Skill
from alpha.harness.memory import Lesson
from alpha.harness.registry import SkillRegistry, MemoryStore


def _skill(sid, family="runner", phases=("trend",), status="active", type_="pattern"):
    return Skill(skill_id=sid, name=sid, type=type_, family=family, phases=list(phases), status=status)


def test_skill_registry_queries():
    reg = SkillRegistry.from_skills([
        _skill("a", family="runner", phases=["trend"], status="active"),
        _skill("b", family="swing", phases=["recovery"], status="incubating", type_="feature"),
    ])
    assert reg.get("a").skill_id == "a"
    assert len(reg) == 2 and bool(reg) is True
    assert [s.skill_id for s in reg.by_status("active")] == ["a"]
    assert [s.skill_id for s in reg.by_type("feature")] == ["b"]
    assert [s.skill_id for s in reg.by_phase("trend")] == ["a"]
    assert [s.skill_id for s in reg.by_family("swing")] == ["b"]


def test_skill_registry_applies_all_phases():
    s = _skill("z", phases=[])
    s.applies_all_phases = True
    reg = SkillRegistry.from_skills([s])
    assert [x.skill_id for x in reg.by_phase("flush")] == ["z"]   # applies_all matches any phase


def test_duplicate_skill_id_rejected():
    with pytest.raises(ValueError):
        SkillRegistry.from_skills([_skill("dup"), _skill("dup")])


def test_memory_store_queries():
    store = MemoryStore.from_lessons([
        Lesson(lesson_id="l1", phases=["flush"], family="meme", outcome="loss", lesson="x"),
        Lesson(lesson_id="l2", phases=["trend"], family="runner", outcome="win", lesson="y"),
    ])
    assert store.get("l1").lesson_id == "l1"
    assert [l.lesson_id for l in store.by_phase("flush")] == ["l1"]
    assert [l.lesson_id for l in store.by_family("runner")] == ["l2"]
    assert [l.lesson_id for l in store.by_outcome("loss")] == ["l1"]
    assert len(store) == 2 and bool(store) is True
