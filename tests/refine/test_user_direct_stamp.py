# tests/refine/test_user_direct_stamp.py
"""Charter drill (roster extended 2026-07-08): a seeded direct edit whose provenance lacks the
user-authored stamp must be refused at the waist — path="user_direct" requires proposer="user"
AND a human_approver. Mis-stamped ops are rejected BEFORE dispatch and never logged."""
from alpha.harness.doctrine import Doctrine
from alpha.harness.registry import SkillRegistry, MemoryStore
from alpha.harness.state import HarnessState
from alpha.harness.metatools import MetaTools
from alpha.harness.edit_log import EditLog, EditProvenance
from alpha.refine.apply import try_apply_op, ALL_TOOLS
from alpha.refine.ops import RefineOp


def _h():
    return HarnessState(doctrine=Doctrine(), skills=SkillRegistry.from_skills([]),
                        memory=MemoryStore.from_lessons([]))


def _apply(provenance):
    h = _h(); log = EditLog(); meta = MetaTools(h, log)
    op = RefineOp(tool="process_memory", args={"lesson_id": "m1", "phases": ["trend"],
                  "outcome": "win", "lesson": "x"}, rationale="direct edit")
    rec, reason = try_apply_op(meta, h, op, allowed=ALL_TOOLS,
                               min_retire_samples=0, min_promote_samples=0, provenance=provenance)
    return rec, reason, log


def test_user_direct_with_wrong_proposer_is_refused_and_unlogged():
    rec, reason, log = _apply(EditProvenance(path="user_direct", proposer="refiner",
                                             human_approver="user"))
    assert rec is None and "user_direct requires" in reason
    assert len(log.records()) == 0


def test_user_direct_without_human_approver_is_refused_and_unlogged():
    rec, reason, log = _apply(EditProvenance(path="user_direct", proposer="user"))
    assert rec is None and "user_direct requires" in reason
    assert len(log.records()) == 0


def test_properly_stamped_user_direct_lands():
    rec, reason, log = _apply(EditProvenance(path="user_direct", proposer="user",
                                             human_approver="user"))
    assert reason is None and rec is not None
    assert rec.provenance.path == "user_direct"
