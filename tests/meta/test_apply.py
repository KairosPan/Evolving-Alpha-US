import pytest

from alpha.harness.loader import load_seeds
from alpha.harness.metatools import MetaTools
from alpha.harness.edit_log import EditLog
from alpha.refine.apply import try_apply_op, ALL_TOOLS
from alpha.refine.ops import RefineOp

SEEDS = "seeds"


def _tools():
    h = load_seeds(SEEDS)
    return MetaTools(h, EditLog()), h


def test_apply_patch_skill_succeeds():
    meta, h = _tools()
    sid = h.skills.all()[0].skill_id
    op = RefineOp(tool="patch_skill", args={"skill_id": sid, "notes": "taught note"}, rationale="r")
    rec, reason = try_apply_op(meta, h, op, allowed=ALL_TOOLS, min_retire_samples=5, min_promote_samples=3)
    assert reason is None and rec is not None and rec.tool == "patch_skill"
    assert h.skills.get(sid).notes == "taught note"


def test_apply_missing_rationale_rejected():
    meta, h = _tools()
    sid = h.skills.all()[0].skill_id
    op = RefineOp(tool="patch_skill", args={"skill_id": sid, "notes": "x"}, rationale="")
    rec, reason = try_apply_op(meta, h, op, allowed=ALL_TOOLS, min_retire_samples=5, min_promote_samples=3)
    assert rec is None and "rationale" in reason


def test_apply_immutable_doctrine_rejected_cleanly():
    meta, h = _tools()
    red = h.doctrine.immutable_core()[0].section
    op = RefineOp(tool="rewrite_doctrine", args={"section": red, "new_guidance": "x"}, rationale="r")
    rec, reason = try_apply_op(meta, h, op, allowed=ALL_TOOLS, min_retire_samples=5, min_promote_samples=3)
    assert rec is None and reason and "Immutable" in reason


def test_tool_not_in_allowed_rejected():
    meta, h = _tools()
    op = RefineOp(tool="rewrite_doctrine", args={"section": "x", "new_guidance": "y"}, rationale="r")
    rec, reason = try_apply_op(meta, h, op, allowed=frozenset({"patch_skill"}),
                               min_retire_samples=5, min_promote_samples=3)
    assert rec is None and "not in" in reason
