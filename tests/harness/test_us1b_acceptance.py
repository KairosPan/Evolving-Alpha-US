"""US-1b acceptance: the harness is editable through the 9 meta-tools with an audited EditLog,
the immutable core is protected on the edit path, and rejected edits never touch H or the log."""
import pytest
from alpha.harness.skill import Skill
from alpha.harness.memory import Lesson
from alpha.harness.doctrine import Doctrine
from alpha.harness.registry import SkillRegistry, MemoryStore
from alpha.harness.state import HarnessState
from alpha.harness.metatools import MetaTools
from alpha.harness.errors import ImmutableDoctrineError


def _tools():
    skills = SkillRegistry.from_skills([
        Skill(skill_id="a", name="A", type="pattern", family="runner", phases=["trend"], status="incubating"),
    ])
    memory = MemoryStore.from_lessons([])
    doctrine = Doctrine.from_seed_list([
        {"section": "core", "regime": "all", "immutable": True, "guidance": "stop discipline"},
        {"section": "trend", "regime": "trend", "immutable": False, "guidance": "ride leaders"},
    ])
    return MetaTools(HarnessState(doctrine=doctrine, skills=skills, memory=memory))


def test_full_edit_cycle_audited():
    mt = _tools()
    mt.promote_skill("a", rationale="beat OOS")
    mt.write_skill(Skill(skill_id="b", name="B", type="failure_detector", family="meme", phases=["flush"]),
                   rationale="codified a blowoff detector")
    mt.process_memory(Lesson(lesson_id="m1", phases=["flush"], outcome="loss", lesson="don't chase tops"),
                      rationale="named analog")
    mt.rewrite_doctrine("trend", "ride leaders; trim into blowoff", rationale="late cycle")
    # 4 successful edits, all audited with rationale
    assert len(mt.log) == 4
    assert all(r.rationale for r in mt.log.records())
    assert mt.h.skills.get("a").status == "active"
    assert mt.h.skills.get("b").status == "incubating"      # write clamps to incubating
    assert mt.h.doctrine.get("trend").guidance.endswith("blowoff")


def test_immutable_core_protected_and_unlogged():
    mt = _tools()
    with pytest.raises(ImmutableDoctrineError):
        mt.rewrite_doctrine("core", "loosen", rationale="bad")
    assert mt.h.doctrine.get("core").guidance == "stop discipline"
    assert len(mt.log) == 0
