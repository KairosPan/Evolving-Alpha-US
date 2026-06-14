"""US-1c acceptance: a full checkpoint -> edit -> rollback cycle restores H + log exactly,
rebinds the meta-tools, survives a process boundary (fresh manager from the same store), and
preserves the immutable-core guard across persistence."""
import pytest
from alpha.harness.skill import Skill
from alpha.harness.memory import Lesson
from alpha.harness.doctrine import Doctrine
from alpha.harness.registry import SkillRegistry, MemoryStore
from alpha.harness.state import HarnessState
from alpha.harness.snapshot import SnapshotStore
from alpha.harness.manager import HarnessManager
from alpha.harness.errors import ImmutableDoctrineError


def _state():
    skills = SkillRegistry.from_skills([
        Skill(skill_id="a", name="A", type="pattern", family="runner", phases=["trend"], status="incubating"),
    ])
    doctrine = Doctrine.from_seed_list([
        {"section": "core", "regime": "all", "immutable": True, "guidance": "stop discipline"},
    ])
    return HarnessState(doctrine=doctrine, skills=skills, memory=MemoryStore.from_lessons([]))


def test_checkpoint_edit_rollback_cycle(tmp_path):
    store = SnapshotStore(tmp_path)
    mgr = HarnessManager(_state(), store)
    good = mgr.checkpoint("good")
    # a "bad" refine: promote + add a skill
    mgr.tools.promote_skill("a", rationale="maybe overfit")
    mgr.tools.write_skill(Skill(skill_id="junk", name="J", type="pattern", family="meme", phases=["flush"]),
                          rationale="noise")
    assert mgr.harness.skills.get("junk") is not None and len(mgr.log) == 2
    # roll back the bad refine
    mgr.rollback_to(good)
    assert mgr.harness.skills.get("a").status == "incubating"
    assert mgr.harness.skills.get("junk") is None
    assert len(mgr.log) == 0
    with pytest.raises(ImmutableDoctrineError):
        mgr.harness.doctrine.get("core").guidance = "loosen"


def test_reload_from_store_across_fresh_manager(tmp_path):
    store = SnapshotStore(tmp_path)
    mgr = HarnessManager(_state(), store)
    mgr.tools.promote_skill("a", rationale="promote")
    v = mgr.checkpoint("active-state")
    # a brand-new manager over the same store loads the persisted state (simulated restart)
    mgr2 = HarnessManager(_state(), SnapshotStore(tmp_path))
    mgr2.rollback_to(v)
    assert mgr2.harness.skills.get("a").status == "active"
    assert mgr2.tools.h is mgr2.harness
