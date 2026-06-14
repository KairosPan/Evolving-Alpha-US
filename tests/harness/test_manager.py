import pytest
from alpha.harness.skill import Skill
from alpha.harness.memory import Lesson
from alpha.harness.doctrine import Doctrine
from alpha.harness.registry import SkillRegistry, MemoryStore
from alpha.harness.state import HarnessState
from alpha.harness.snapshot import SnapshotStore
from alpha.harness.manager import HarnessManager


def _mgr(tmp_path):
    skills = SkillRegistry.from_skills([
        Skill(skill_id="a", name="A", type="pattern", family="runner", phases=["trend"], status="incubating"),
    ])
    memory = MemoryStore.from_lessons([])
    doctrine = Doctrine.from_seed_list([
        {"section": "trend", "regime": "trend", "immutable": False, "guidance": "ride leaders"},
    ])
    h = HarnessState(doctrine=doctrine, skills=skills, memory=memory)
    return HarnessManager(h, SnapshotStore(tmp_path))


def test_checkpoint_returns_version(tmp_path):
    mgr = _mgr(tmp_path)
    assert mgr.checkpoint("baseline") == 0
    assert mgr.latest_version() == 0


def test_rollback_restores_state_and_rebinds_tools(tmp_path):
    mgr = _mgr(tmp_path)
    v0 = mgr.checkpoint("baseline")                 # skill 'a' is incubating, log empty
    mgr.tools.promote_skill("a", rationale="beat OOS")    # incubating -> active (log has 1)
    mgr.tools.write_skill(Skill(skill_id="b", name="B", type="pattern", family="meme", phases=["flush"]),
                          rationale="new")
    assert mgr.harness.skills.get("a").status == "active"
    assert mgr.harness.skills.get("b") is not None
    assert len(mgr.log) == 2

    mgr.rollback_to(v0)
    assert mgr.harness.skills.get("a").status == "incubating"   # restored
    assert mgr.harness.skills.get("b") is None                  # post-checkpoint edit gone
    assert len(mgr.log) == 0                                    # log restored to v0

    # tools are rebound: a new edit acts on the restored harness and its log
    mgr.tools.promote_skill("a", rationale="re-promote on restored state")
    assert mgr.harness.skills.get("a").status == "active"
    assert len(mgr.log) == 1
    assert mgr.tools.h is mgr.harness and mgr.tools.log is mgr.log


def test_checkpoint_after_rollback_appends_new_version(tmp_path):
    mgr = _mgr(tmp_path)
    mgr.checkpoint("v0")
    mgr.tools.promote_skill("a", rationale="x")
    mgr.checkpoint("v1")
    mgr.rollback_to(0)
    assert mgr.checkpoint("v2-after-rollback") == 2   # version is disk-monotonic, not reset


def test_stale_tools_reference_operates_on_discarded_state(tmp_path):
    mgr = _mgr(tmp_path)
    v0 = mgr.checkpoint("v0")
    stale_tools = mgr.tools                  # cached BEFORE rollback
    mgr.tools.promote_skill("a", rationale="x")
    mgr.rollback_to(v0)
    # the stale reference still points at the discarded pre-rollback harness, not mgr.harness
    assert stale_tools.h is not mgr.harness
    stale_tools.write_skill(Skill(skill_id="ghost", name="G", type="pattern", family="meme", phases=["flush"]),
                            rationale="leaked")
    assert mgr.harness.skills.get("ghost") is None    # did NOT touch the live harness
