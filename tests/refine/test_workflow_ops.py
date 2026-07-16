"""Workflow (W) write-waist ops routed through the ONE gate (try_apply_op).

Mirrors the connector op tests: create/patch/retire through MetaTools + the workflow lints
(description char cap + step-referential-integrity — a step ref that resolves to a RETIRED skill
is refused; unknown id-shaped refs and free-prose refs stay permissive) + content_hash (populated
on apply, recomputed on patch) + the worker-propose refusal (charter A7).
"""
from alpha.harness.state import HarnessState
from alpha.harness.doctrine import Doctrine
from alpha.harness.connectors import ConnectorRegistry
from alpha.harness.workflows import WorkflowRegistry  # noqa: F401
from alpha.harness.registry import MemoryStore, SkillRegistry
from alpha.harness.skill import Skill
from alpha.harness.metatools import MetaTools
from alpha.harness.edit_log import EditLog, EditProvenance
from alpha.refine.ops import RefineOp, PASS_TOOLS
from alpha.refine.apply import try_apply_op


def _h():
    # One ACTIVE skill (a valid step ref resolves) + one RETIRED skill (a step ref that must bounce).
    skills = SkillRegistry.from_skills([
        Skill.from_seed({"skill_id": "breakout_long", "name": "Breakout", "type": "feature"}),
        Skill.from_seed({"skill_id": "legacy_scan", "name": "Legacy", "type": "feature",
                         "status": "retired"}),
    ])
    return HarnessState(doctrine=Doctrine(entries=[]), skills=skills,
                        memory=MemoryStore.from_lessons([]), connectors=ConnectorRegistry.empty(),
                        workflows=WorkflowRegistry.empty())


def _args(**kw):
    a = dict(workflow_id="morning_scan", name="Morning Scan",
             description="scan gainers then rank",
             steps=[{"ref": "breakout_long", "note": "entry"}])
    a.update(kw)
    return a


def _apply(h, log, tool, args, rationale="because", **kw):
    return try_apply_op(MetaTools(h, log), h, RefineOp(tool=tool, args=args, rationale=rationale),
                        allowed=PASS_TOOLS["W"], min_retire_samples=0, min_promote_samples=0, **kw)


def test_write_workflow_creates_entry():
    h, log = _h(), EditLog()
    rec, reason = _apply(h, log, "write_workflow", _args())
    assert reason is None and rec is not None
    w = h.workflows.get("morning_scan")
    assert w is not None and w.name == "Morning Scan"
    assert rec.target_kind == "workflow" and rec.op == "create"
    assert w.content_hash                                    # populated on apply


def test_write_workflow_rejects_overlong_description():
    h, log = _h(), EditLog()
    rec, reason = _apply(h, log, "write_workflow", _args(description="x" * 201))
    assert rec is None and "description" in reason


def test_write_workflow_rejects_retired_skill_step():
    h, log = _h(), EditLog()
    rec, reason = _apply(h, log, "write_workflow",
                         _args(steps=[{"ref": "legacy_scan", "note": ""}]))
    assert rec is None and "step" in reason


def test_write_workflow_allows_unknown_id_shaped_ref():
    """An id-shaped ref with no matching skill is a future/free action ref — permissive."""
    h, log = _h(), EditLog()
    rec, reason = _apply(h, log, "write_workflow",
                         _args(steps=[{"ref": "future_skill_xyz", "note": ""}]))
    assert reason is None and rec is not None


def test_write_workflow_allows_free_prose_ref():
    """A ref with spaces is a free-prose action, not a skill id — permissive."""
    h, log = _h(), EditLog()
    rec, reason = _apply(h, log, "write_workflow",
                         _args(steps=[{"ref": "call the desk analyst", "note": ""}]))
    assert reason is None and rec is not None


def test_patch_workflow_updates_fields():
    h, log = _h(), EditLog()
    _apply(h, log, "write_workflow", _args())
    rec, reason = _apply(h, log, "patch_workflow",
                         {"workflow_id": "morning_scan", "name": "Renamed"})
    assert reason is None and h.workflows.get("morning_scan").name == "Renamed"


def test_patch_workflow_changes_content_hash():
    h, log = _h(), EditLog()
    _apply(h, log, "write_workflow", _args())
    before = h.workflows.get("morning_scan").content_hash
    assert before
    rec, reason = _apply(h, log, "patch_workflow",
                         {"workflow_id": "morning_scan", "description": "ranked scan of gap ups"})
    assert reason is None
    after = h.workflows.get("morning_scan").content_hash
    assert after and after != before                        # content change -> hash change


def test_patch_workflow_relint_rejects_retired_step():
    """A follow-up patch cannot smuggle a retired-skill step past the create-time lint."""
    h, log = _h(), EditLog()
    _apply(h, log, "write_workflow", _args())
    rec, reason = _apply(h, log, "patch_workflow",
                         {"workflow_id": "morning_scan", "steps": [{"ref": "legacy_scan"}]})
    assert rec is None and "step" in reason


def test_patch_workflow_unknown_id_rejected_cleanly():
    h, log = _h(), EditLog()
    rec, reason = _apply(h, log, "patch_workflow", {"workflow_id": "ghost", "name": "x"})
    assert rec is None and reason


def test_retire_workflow_sets_retired():
    h, log = _h(), EditLog()
    _apply(h, log, "write_workflow", _args())
    rec, reason = _apply(h, log, "retire_workflow", {"workflow_id": "morning_scan"})
    assert reason is None and h.workflows.get("morning_scan").status == "retired"


def test_workflow_op_refused_for_worker_proposer():
    h, log = _h(), EditLog()
    rec, reason = try_apply_op(MetaTools(h, log), h,
                               RefineOp(tool="write_workflow", args=_args(), rationale="x"),
                               allowed=PASS_TOOLS["W"], min_retire_samples=0, min_promote_samples=0,
                               provenance=EditProvenance(path="self_study", proposer="kairos"))
    assert rec is None and reason  # worker-propose refusal fires first (charter A7)
