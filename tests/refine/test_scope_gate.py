"""A8 part (b): the gate-level scope-mismatch refusal (charter *The External Channel*).

An edit landing at a scope WIDER than its cited evidence's scope fails the static policy gate and
bounces. The gate is ADDITIVE/byte-identical until an op explicitly declares a landed scope, and
uses a CONSERVATIVE evidence-scope default (narrowest observed, per-session when unknown)."""
from __future__ import annotations

from alpha.harness.doctrine import Doctrine
from alpha.harness.edit_log import EditLog, EditProvenance
from alpha.harness.metatools import MetaTools
from alpha.harness.registry import MemoryStore, SkillRegistry
from alpha.harness.state import HarnessState
from alpha.refine.apply import ALL_TOOLS, try_apply_op
from alpha.refine.ops import RefineOp


def _fresh() -> tuple[MetaTools, HarnessState]:
    h = HarnessState(doctrine=Doctrine(), skills=SkillRegistry.from_skills([]),
                     memory=MemoryStore.from_lessons([]))
    return MetaTools(h, EditLog()), h


def _lesson_op(lesson_id: str, *, scope: str | None = None) -> RefineOp:
    args = {"lesson_id": lesson_id, "outcome": "principle", "lesson": "hold VWAP or exit"}
    if scope is not None:
        args["scope"] = scope
    return RefineOp(tool="process_memory", args=args, rationale="a lesson")


def _apply(op, provenance):
    meta, h = _fresh()
    return try_apply_op(meta, h, op, allowed=ALL_TOOLS, min_retire_samples=0, min_promote_samples=0,
                        provenance=provenance)


def test_wider_than_evidence_bounces():
    # Declares agent-global, cites per-session evidence -> WIDER -> refused.
    prov = EditProvenance(path="teaching", proposer="sonia",
                          evidence_ref={"evidence_scopes": ["per-session"]})
    rec, reason = _apply(_lesson_op("l1", scope="agent-global"), prov)
    assert rec is None
    assert "scope-mismatch" in reason and "agent-global" in reason and "per-session" in reason


def test_within_scope_passes():
    prov = EditProvenance(path="teaching", proposer="sonia",
                          evidence_ref={"evidence_scopes": ["per-session"]})
    rec, reason = _apply(_lesson_op("l2", scope="per-session"), prov)
    assert rec is not None and reason is None


def test_unknown_evidence_defaults_narrow_so_wide_edit_bounces():
    # The user-ratified conservative default: no evidence_ref -> evidence treated as per-session
    # (narrowest), so a declared agent-global edit bounces (the gate has teeth, not vacuous).
    prov = EditProvenance(path="teaching", proposer="sonia")
    rec, reason = _apply(_lesson_op("l3", scope="agent-global"), prov)
    assert rec is None and "scope-mismatch" in reason
    # ... and a per-session landing off unknown evidence is within scope -> passes.
    rec2, reason2 = _apply(_lesson_op("l4", scope="per-session"), prov)
    assert rec2 is not None and reason2 is None


def test_user_direct_is_exempt():
    # The user's own hand carries agent-global authority and forgoes the packet counsel (charter).
    prov = EditProvenance(path="user_direct", proposer="user", human_approver="user")
    rec, reason = _apply(_lesson_op("l5", scope="agent-global"), prov)
    assert rec is not None and reason is None


def test_no_declared_scope_is_byte_identical():
    # An op that declares NO landed scope lands exactly as before A8 (the gate never fires).
    prov = EditProvenance(path="teaching", proposer="sonia")
    rec, reason = _apply(_lesson_op("l6"), prov)   # no scope arg
    assert rec is not None and reason is None
