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
from alpha.harness.skill import Skill, SkillStats
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
# Converse write-tool proposer — expects path="teaching", proposer="hermes"
#
# make_gated_write_tool creates a fresh EditLog per call, so we can't inspect it
# from outside. Instead we patch it to use a shared log, then assert provenance.
# ---------------------------------------------------------------------------

def test_converse_write_tool_applied_edit_has_hermes_provenance():
    """After propose_memory_edit, the record in the shared log must carry teaching/hermes."""
    import alpha.converse.tools as _ct
    from alpha.refine.apply import try_apply_op as _real_tap

    h = _bare_h()
    shared_log = EditLog()
    calls: list[dict] = []

    # Intercept try_apply_op to capture the provenance kwarg actually passed
    def _spy_tap(meta, harness, op, **kw):
        calls.append({"provenance": kw.get("provenance")})
        # Use a MetaTools backed by the shared log so we can inspect it
        meta2 = MetaTools(harness, shared_log)
        return _real_tap(meta2, harness, op, **kw)

    original = _ct.try_apply_op
    _ct.try_apply_op = _spy_tap
    try:
        _schema, propose = _ct.make_gated_write_tool(h)
        out = propose(tool="process_memory",
                      args={"lesson_id": "h-mem-1", "phases": ["trend"],
                            "outcome": "win", "lesson": "hermes taught this"},
                      rationale="teaching provenance test")
    finally:
        _ct.try_apply_op = original

    assert out["status"] == "applied", f"expected applied; got: {out}"
    assert len(calls) == 1, "spy not called"
    prov = calls[0]["provenance"]
    assert prov is not None, "provenance was None — implement it in make_gated_write_tool"
    assert prov.path == "teaching"
    assert prov.proposer == "hermes"
