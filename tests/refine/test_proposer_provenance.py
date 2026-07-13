# tests/refine/test_proposer_provenance.py
"""TDD: verify each proposer threads the correct EditProvenance through try_apply_op.

RED before implementation (provenance will be None because proposers don't pass it yet).
GREEN after implementation.
"""
from __future__ import annotations

from alpha.harness.doctrine import Doctrine
from alpha.harness.edit_log import EditLog, EditProvenance
from alpha.harness.metatools import MetaTools
from alpha.harness.registry import MemoryStore, SkillRegistry
from alpha.harness.state import HarnessState
from alpha.llm.client import MockLLMClient
from alpha.refine.ops import RefineOp, PASS_TOOLS
from alpha.refine.refiner import Refiner, RefinerConfig


# ---------------------------------------------------------------------------
# shared helpers
# ---------------------------------------------------------------------------

def _bare_h():
    return HarnessState(doctrine=Doctrine(),
                        skills=SkillRegistry.from_skills([]),
                        memory=MemoryStore.from_lessons([]))


# ---------------------------------------------------------------------------
# Refiner proposer — expects path="self_study", proposer="refiner"
# ---------------------------------------------------------------------------

def test_refiner_applied_edit_has_self_study_provenance():
    """After _apply_op, the EditLog record must carry self_study/refiner provenance."""
    h = _bare_h()
    log = EditLog()
    meta = MetaTools(h, log)
    r = Refiner(h, MockLLMClient("{}"), meta, RefinerConfig())

    op = RefineOp(tool="process_memory",
                  args={"lesson_id": "r-mem-1", "phases": ["trend"],
                        "outcome": "win", "lesson": "refiner learned this"},
                  rationale="self-study evidence")
    ok, edit = r._apply_op(op, "M", PASS_TOOLS["M"])

    assert ok is True, f"expected applied; got: {edit}"
    last = log.records()[-1]
    assert last.provenance is not None, "provenance should be stamped (was None — implement it)"
    assert last.provenance.path == "self_study"
    assert last.provenance.proposer == "refiner"


# ---------------------------------------------------------------------------
# Worker proposer — RETIRED by A7 (charter First Founding Principle: "Kairos does not propose at
# all"). The stage tool is gone AND a kairos-stamped op is refused at the gate (the two-hands seam).
# ---------------------------------------------------------------------------

def test_worker_stage_tool_is_retired():
    """A7: the worker face no longer exposes a memory-edit staging tool."""
    import alpha.converse.tools as _ct
    assert not hasattr(_ct, "make_propose_edit_tool")


def test_gate_refuses_kairos_stamped_op():
    """A7 two-hands seam: even if a kairos-stamped op is assembled, try_apply_op refuses it before
    any content check — the worker (Kairos) may never send to the gate."""
    from alpha.harness.edit_log import EditLog
    from alpha.refine.apply import try_apply_op
    from alpha.refine.ops import PASS_TOOLS

    h = _bare_h()
    log = EditLog()
    op = RefineOp(tool="process_memory",
                  args={"lesson_id": "h-mem-1", "phases": ["trend"],
                        "outcome": "win", "lesson": "kairos tried to propose"},
                  rationale="worker proposal attempt")
    rec, reason = try_apply_op(MetaTools(h, log), h, op, allowed=PASS_TOOLS["M"],
                               min_retire_samples=5, min_promote_samples=3,
                               provenance=EditProvenance(path="teaching", proposer="kairos",
                                                         human_approver="user"))
    assert rec is None and "Kairos does not propose" in (reason or "")
    assert not any(l.lesson_id == "h-mem-1" for l in h.memory.all()), "live H must be untouched"
