"""Regression (found by the 2026-07-09 conformance review, verified by execution): a lesson with
a date-typed learned_asof landed through the gate used to crash every json.dumps consumer of
to_dict (LiveBrainStore.save, SnapshotStore, proposal packets). to_dict must be json-mode."""
import json
from datetime import date

from alpha.harness.doctrine import Doctrine
from alpha.harness.edit_log import EditLog
from alpha.harness.metatools import MetaTools
from alpha.harness.registry import MemoryStore, SkillRegistry
from alpha.harness.state import HarnessState
from alpha.refine.apply import try_apply_op
from alpha.refine.ops import PASS_TOOLS, RefineOp


def _bare_h():
    return HarnessState(doctrine=Doctrine(), skills=SkillRegistry.from_skills([]),
                        memory=MemoryStore.from_lessons([]))


def test_learned_asof_brain_survives_json_round_trip():
    h = _bare_h()
    log = EditLog()
    op = RefineOp(tool="process_memory",
                  args={"lesson_id": "d-1", "phases": ["trend"], "outcome": "win",
                        "lesson": "dated lesson", "learned_asof": "2026-07-09"},
                  rationale="PIT-keyed lesson")
    rec, reason = try_apply_op(MetaTools(h, log), h, op, allowed=PASS_TOOLS["M"],
                               min_retire_samples=5, min_promote_samples=3)
    assert rec is not None, reason
    assert h.memory.get("d-1").learned_asof == date(2026, 7, 9)

    text = json.dumps({"harness": h.to_dict(), "log": log.to_dict()})   # used to raise TypeError
    data = json.loads(text)
    h2 = HarnessState.from_dict(data["harness"])
    log2 = EditLog.from_dict(data["log"])
    assert h2.memory.get("d-1").learned_asof == date(2026, 7, 9)
    assert len(log2) == 1
