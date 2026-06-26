# tests/refine/test_apply_provenance_held.py
from alpha.harness.doctrine import Doctrine
from alpha.harness.registry import SkillRegistry, MemoryStore
from alpha.harness.state import HarnessState
from alpha.harness.metatools import MetaTools
from alpha.harness.edit_log import EditLog, EditProvenance
from alpha.refine.apply import try_apply_op
from alpha.refine.ops import RefineOp, PASS_TOOLS


def _h():
    return HarnessState(doctrine=Doctrine(), skills=SkillRegistry.from_skills([]),
                        memory=MemoryStore.from_lessons([]))


def test_apply_stamps_provenance_on_the_record():
    h = _h(); log = EditLog(); meta = MetaTools(h, log)
    op = RefineOp(tool="process_memory", args={"lesson_id": "m1", "phases": ["trend"],
                  "outcome": "win", "lesson": "x"}, rationale="learned")
    p = EditProvenance(path="teaching", proposer="sonia")
    rec, reason = try_apply_op(meta, h, op, allowed=PASS_TOOLS["M"],
                               min_retire_samples=5, min_promote_samples=3, provenance=p)
    assert reason is None and rec is not None and rec.provenance == p
    assert log.records()[-1].provenance == p


def test_apply_without_provenance_is_unchanged():
    h = _h(); log = EditLog(); meta = MetaTools(h, log)
    op = RefineOp(tool="process_memory", args={"lesson_id": "m2", "phases": ["trend"],
                  "outcome": "win", "lesson": "y"}, rationale="learned")
    rec, reason = try_apply_op(meta, h, op, allowed=PASS_TOOLS["M"],
                               min_retire_samples=5, min_promote_samples=3)   # no provenance
    assert reason is None and rec is not None and rec.provenance is None
