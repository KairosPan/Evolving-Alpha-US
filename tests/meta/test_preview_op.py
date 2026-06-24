from alpha.harness.loader import load_seeds
from alpha.meta.agent import preview_op
from alpha.refine.ops import RefineOp


def test_preview_op_dry_runs_without_mutating_live_brain():
    h = load_seeds("seeds")
    sid = h.skills.all()[0].skill_id
    op = RefineOp(tool="patch_skill", args={"skill_id": sid, "notes": "from preview"}, rationale="r")
    edit = preview_op(h, op)
    assert edit.status == "proposed" and edit.target_id == sid
    assert edit.payload["after"] == {"notes": "from preview"}
    assert h.skills.get(sid).notes != "from preview"          # live brain NOT mutated


def test_preview_op_failed_op_becomes_failed_card():
    h = load_seeds("seeds")
    op = RefineOp(tool="patch_skill", args={"skill_id": "nope", "notes": "x"}, rationale="r")
    edit = preview_op(h, op)
    assert edit.status == "failed" and edit.apply_reason
