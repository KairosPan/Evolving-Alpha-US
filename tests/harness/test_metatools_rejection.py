import pytest
from alpha.harness.skill import Skill
from alpha.harness.memory import Lesson
from alpha.harness.doctrine import Doctrine
from alpha.harness.registry import SkillRegistry, MemoryStore
from alpha.harness.state import HarnessState
from alpha.harness.metatools import MetaTools
from alpha.harness.errors import ImmutableDoctrineError, InvalidTransitionError


def _tools():
    skills = SkillRegistry.from_skills([
        Skill(skill_id="a", name="A", type="pattern", family="runner", phases=["trend"], status="active"),
    ])
    memory = MemoryStore.from_lessons([Lesson(lesson_id="l1", phases=["flush"], outcome="loss", lesson="x")])
    doctrine = Doctrine.from_seed_list([
        {"section": "core", "regime": "all", "immutable": True, "guidance": "stop discipline"},
    ])
    return MetaTools(HarnessState(doctrine=doctrine, skills=skills, memory=memory))


def test_rewrite_immutable_rejected_not_logged():
    mt = _tools()
    with pytest.raises(ImmutableDoctrineError):
        mt.rewrite_doctrine("core", "loosen the stop", rationale="bad idea")
    assert mt.h.doctrine.get("core").guidance == "stop discipline"   # unchanged
    assert len(mt.log) == 0                                          # NOT logged


def test_invalid_transition_rejected_not_logged():
    mt = _tools()
    with pytest.raises(InvalidTransitionError):
        mt.revive_skill("a", rationale="a is active not dormant")
    assert mt.h.skills.get("a").status == "active"
    assert len(mt.log) == 0


def test_forbidden_field_rejected_not_logged():
    mt = _tools()
    with pytest.raises(ValueError):
        mt.patch_skill("a", rationale="sneaky", stats={"n": 99})     # observation field
    assert mt.h.skills.get("a").stats.n == 0
    assert len(mt.log) == 0


def test_missing_target_rejected_not_logged():
    mt = _tools()
    with pytest.raises(KeyError):
        mt.patch_skill("ghost", rationale="hallucinated id", notes="x")
    assert len(mt.log) == 0


def test_duplicate_id_rejected_not_logged():
    mt = _tools()
    with pytest.raises(ValueError):
        mt.write_skill(Skill(skill_id="a", name="dup", type="pattern", family="runner", phases=["trend"]),
                       rationale="duplicate")
    assert mt.h.skills.get("a").name == "A"      # original unchanged
    assert len(mt.log) == 0


def test_missing_rationale_rejected_on_all_nine_tools():
    mt = _tools()
    new_skill = Skill(skill_id="z", name="Z", type="pattern", family="runner", phases=["trend"])
    new_lesson = Lesson(lesson_id="z", phases=["trend"], outcome="win", lesson="y")
    # rationale guard is the FIRST line of every tool, so even an otherwise-illegal edit
    # (e.g. revive/promote on an active skill) raises ValueError(rationale) and never mutates.
    calls = [
        lambda: mt.write_skill(new_skill, rationale=""),
        lambda: mt.patch_skill("a", rationale="", notes="x"),
        lambda: mt.retire_skill("a", rationale=""),
        lambda: mt.revive_skill("a", rationale=""),
        lambda: mt.promote_skill("a", rationale=""),
        lambda: mt.process_memory(new_lesson, rationale=""),
        lambda: mt.update_memory("l1", rationale="", lesson="x"),
        lambda: mt.demote_memory("l1", 0.5, rationale=""),
        lambda: mt.rewrite_doctrine("core", "y", rationale=""),
        lambda: mt.patch_skill("a", rationale="   ", notes="x"),   # blank/whitespace also rejected
    ]
    for call in calls:
        with pytest.raises(ValueError):
            call()
    assert mt.h.skills.get("a").notes == "" and mt.h.skills.get("z") is None
    assert mt.h.memory.get("z") is None
    assert len(mt.log) == 0


def test_invalid_demote_factor_rejected_not_logged():
    mt = _tools()
    for bad in (0.0, 1.5, -0.1):
        with pytest.raises(ValueError):
            mt.demote_memory("l1", bad, rationale="invalid factor")
    assert mt.h.memory.get("l1").importance.weight() == 1.0
    assert len(mt.log) == 0


def test_already_retired_rejected_not_logged():
    mt = _tools()
    mt.retire_skill("a", rationale="retire", permanent=True)     # active -> retired (1 record)
    with pytest.raises(InvalidTransitionError):
        mt.retire_skill("a", rationale="retire again")          # already retired -> reject
    assert mt.h.skills.get("a").status == "retired"
    assert len(mt.log) == 1                                      # only the first (real) retire logged


def test_atomic_patch_failure_not_logged():
    mt = _tools()
    with pytest.raises(Exception):
        mt.patch_skill("a", rationale="bad type", notes="changed", type="not_valid")
    assert mt.h.skills.get("a").notes == ""      # rolled back
    assert len(mt.log) == 0
