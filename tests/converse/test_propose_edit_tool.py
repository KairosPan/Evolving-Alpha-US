import copy
from alpha.harness.doctrine import Doctrine
from alpha.harness.registry import SkillRegistry, MemoryStore
from alpha.harness.state import HarnessState
from alpha.converse.tools import make_propose_edit_tool


def _h():
    return HarnessState(doctrine=Doctrine(), skills=SkillRegistry.from_skills([]),
                        memory=MemoryStore.from_lessons([]))


def test_propose_stages_without_mutating_live():
    h = _h(); before = copy.deepcopy(h.to_dict())
    schema, fn = make_propose_edit_tool(h)
    out = fn(tool="process_memory", args={"lesson_id": "m1", "phases": ["trend"], "outcome": "win", "lesson": "x"},
             rationale="learned this")
    assert out["staged"] is True and out["valid"] is True and out["edit_id"]
    assert out["op"]["tool"] == "process_memory"
    assert h.to_dict() == before                     # live brain untouched (dry-run only)


def test_propose_invalid_reports_reason():
    h = _h()
    _schema, fn = make_propose_edit_tool(h)
    out = fn(tool="process_memory", args={"lesson_id": "m1", "outcome": "win", "lesson": "x"}, rationale="")
    assert out["staged"] is True and out["valid"] is False and out["reason"]   # missing rationale -> gate reject
