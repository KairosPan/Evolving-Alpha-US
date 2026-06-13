# tests/test_harness.py
from youzi.harness.skill import Skill
from youzi.harness.registry import SkillRegistry
from youzi.harness.memory_store import MemoryStore
from youzi.harness.memory_item import Lesson
from youzi.harness.doctrine import Doctrine, DoctrineEntry
from youzi.harness.cycle import StateMachine
from youzi.harness.harness import HarnessState


def _h():
    skills = SkillRegistry.from_skills([
        Skill.from_seed({"skill_id": "a", "name_cn": "甲", "type": "pattern",
                         "applicable_regime": ["主升"], "trigger": "t", "entry": "e",
                         "exit_stop": "x", "status": "active"}),
        Skill.from_seed({"skill_id": "b", "name_cn": "乙", "type": "pattern",
                         "applicable_regime": ["主升"], "trigger": "t", "entry": "e",
                         "exit_stop": "x", "status": "dormant"}),
    ])
    mem = MemoryStore.from_lessons([
        Lesson.from_seed({"lesson_id": "l1", "regime": "all", "outcome": "principle",
                          "lesson": "计划交易"})])
    doc = Doctrine(entries=[DoctrineEntry.from_seed(
        {"section": "主升作战", "regime": "主升", "immutable": False, "guidance": "持有龙头"})])
    cyc = StateMachine.from_seed_list([{"phase": "主升", "you_see": [], "transitions": []}])
    return HarnessState(doctrine=doc, skills=skills, memory=mem, cycle=cyc)


def test_active_skills_for_phase_excludes_dormant():
    h = _h()
    got = h.active_skills_for("主升")
    assert {s.skill_id for s in got} == {"a"}   # 只 active, 排除 dormant


def test_harness_holds_all_four_components():
    h = _h()
    assert h.skills.get("a") is not None
    assert h.memory.get("l1") is not None
    assert [e.section for e in h.doctrine.for_regime("主升")] == ["主升作战"]
    assert h.cycle.get("主升") is not None
