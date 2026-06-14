import pytest
from alpha.harness.skill import Skill, SkillStats
from alpha.harness.memory import Lesson
from alpha.harness.doctrine import Doctrine
from alpha.harness.registry import SkillRegistry, MemoryStore
from alpha.harness.state import HarnessState
from alpha.harness.metatools import MetaTools


def _tools():
    skills = SkillRegistry.from_skills([
        Skill(skill_id="a", name="A", type="pattern", family="runner", phases=["trend"], status="active"),
    ])
    memory = MemoryStore.from_lessons([Lesson(lesson_id="l1", phases=["flush"], outcome="loss", lesson="x")])
    doctrine = Doctrine.from_seed_list([
        {"section": "core", "regime": "all", "immutable": True, "guidance": "stop discipline"},
        {"section": "trend", "regime": "trend", "immutable": False, "guidance": "ride leaders"},
    ])
    return MetaTools(HarnessState(doctrine=doctrine, skills=skills, memory=memory))


def test_write_skill_clamps_status_and_stats():
    mt = _tools()
    sneaky = Skill(skill_id="b", name="B", type="pattern", family="runner", phases=["trend"],
                   status="active", stats=SkillStats(n=99, wins=99))
    rec = mt.write_skill(sneaky, rationale="codified from a winning sequence")
    stored = mt.h.skills.get("b")
    assert stored.status == "incubating"      # clamped, cannot mint active
    assert stored.stats.n == 0                # injected stats reset
    assert rec.op == "create" and rec.rationale == "codified from a winning sequence"
    assert rec.payload["before"] is None and rec.payload["after"]["status"] == "incubating"
    assert len(mt.log) == 1


def test_patch_skill_records_before_after():
    mt = _tools()
    rec = mt.patch_skill("a", rationale="tighten exit", exit_stop="lose VWAP")
    assert mt.h.skills.get("a").exit_stop == "lose VWAP"
    assert rec.payload["before"]["exit_stop"] == ""
    assert rec.payload["after"]["exit_stop"] == "lose VWAP"


def test_lifecycle_tools():
    mt = _tools()
    mt.retire_skill("a", rationale="alpha decayed")          # active -> dormant
    assert mt.h.skills.get("a").status == "dormant"
    mt.revive_skill("a", rationale="regime returned")        # dormant -> incubating
    mt.promote_skill("a", rationale="beat OOS")              # incubating -> active
    assert mt.h.skills.get("a").status == "active"
    assert [r.op for r in mt.log.records()] == ["retire", "revive", "promote"]


def test_memory_tools():
    mt = _tools()
    rec = mt.process_memory(Lesson(lesson_id="l2", phases=["trend"], outcome="win", lesson="y"),
                            rationale="new named analog")
    mt.update_memory("l1", rationale="sharpen", failure_signature="chased the top")
    mt.demote_memory("l1", 0.5, rationale="regime passed")
    assert mt.h.memory.get("l2") is not None
    assert rec.payload["before"] is None and rec.payload["after"]["lesson_id"] == "l2"
    assert mt.h.memory.get("l1").failure_signature == "chased the top"
    assert mt.h.memory.get("l1").importance.weight() == 0.5


def test_process_memory_clamps_importance():
    from alpha.harness.memory import Importance
    mt = _tools()
    sneaky = Lesson(lesson_id="big", phases=["trend"], outcome="loss", lesson="z",
                    importance=Importance(base=100.0))
    mt.process_memory(sneaky, rationale="cannot inject weight")
    assert mt.h.memory.get("big").importance.weight() == 1.0   # clamped to fresh Importance


def test_rewrite_doctrine_tool():
    mt = _tools()
    rec = mt.rewrite_doctrine("trend", "ride leaders; trim into blowoff", rationale="late cycle")
    assert mt.h.doctrine.get("trend").guidance == "ride leaders; trim into blowoff"
    assert rec.payload["old"] == "ride leaders"
    assert rec.payload["new"] == "ride leaders; trim into blowoff"
