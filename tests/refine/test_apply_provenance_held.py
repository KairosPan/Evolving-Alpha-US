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


from alpha.harness.edit_log import EditLog as _EL


class _FakeQueue:
    def __init__(self): self.items = []
    def add(self, **kw): self.items.append(kw)


def test_self_study_contesting_teaching_is_held_not_applied():
    h = _h(); log = EditLog(); meta = MetaTools(h, log)
    # teaching first creates m1
    try_apply_op(meta, h, RefineOp(tool="process_memory",
                 args={"lesson_id": "m1", "phases": ["trend"], "outcome": "win", "lesson": "human says key"},
                 rationale="taught"), allowed=PASS_TOOLS["M"], min_retire_samples=5, min_promote_samples=3,
                 provenance=EditProvenance(path="teaching", proposer="sonia"))
    q = _FakeQueue()
    # self-study tries to demote the teaching-owned m1 -> HELD
    rec, reason = try_apply_op(meta, h, RefineOp(tool="demote_memory", args={"lesson_id": "m1", "factor": 0.5},
                 rationale="data weak"), allowed=PASS_TOOLS["M"], min_retire_samples=5, min_promote_samples=3,
                 provenance=EditProvenance(path="self_study", proposer="refiner"), conflict_queue=q)
    assert rec is None and reason.startswith("held_for_review")
    assert len(q.items) == 1                              # enqueued for the user
    assert h.memory.get("m1").importance.time_decay == 1.0  # NOT demoted (live H unchanged)


def test_no_conflict_queue_means_no_held_path():
    # without a conflict_queue the gate behaves as before (the op applies or rejects on its own merits)
    h = _h(); log = EditLog(); meta = MetaTools(h, log)
    try_apply_op(meta, h, RefineOp(tool="process_memory",
                 args={"lesson_id": "m1", "outcome": "win", "lesson": "x"}, rationale="t"),
                 allowed=PASS_TOOLS["M"], min_retire_samples=5, min_promote_samples=3,
                 provenance=EditProvenance(path="teaching", proposer="sonia"))
    rec, reason = try_apply_op(meta, h, RefineOp(tool="demote_memory", args={"lesson_id": "m1", "factor": 0.5},
                 rationale="r"), allowed=PASS_TOOLS["M"], min_retire_samples=5, min_promote_samples=3,
                 provenance=EditProvenance(path="self_study", proposer="refiner"))   # no queue
    assert reason is None and rec is not None             # applies (no held path without a queue)
