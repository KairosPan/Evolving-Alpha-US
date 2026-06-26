# alpha/refine/apply.py
from __future__ import annotations

from pydantic import ValidationError

from alpha.harness.edit_log import EditProvenance, EditRecord
from alpha.harness.errors import HarnessError
from alpha.harness.memory import Lesson
from alpha.harness.metatools import MetaTools
from alpha.harness.skill import Skill
from alpha.harness.state import HarnessState
from alpha.refine.ops import PASS_TOOLS, RefineOp

ALL_TOOLS = frozenset().union(*PASS_TOOLS.values())

_DISPATCH_ERRORS = (HarnessError, KeyError, ValueError, ValidationError, TypeError, AttributeError)


def _dispatch(meta: MetaTools, op: RefineOp) -> EditRecord:
    """Map an op to its MetaTools call. Defensive: force write_skill->incubating + strip stats;
    strip importance on process_memory (the create paths the Refiner already sanitizes)."""
    tool, args, r = op.tool, dict(op.args), op.rationale
    m = meta
    if tool == "write_skill":
        args.pop("stats", None)
        args["status"] = "incubating"
        return m.write_skill(Skill.from_seed(args), rationale=r)
    if tool == "patch_skill":
        sid = args.pop("skill_id")
        return m.patch_skill(sid, rationale=r, **args)
    if tool == "retire_skill":
        sid = args.pop("skill_id")
        perm = bool(args.pop("permanent", False))
        return m.retire_skill(sid, rationale=r, permanent=perm)
    if tool == "revive_skill":
        return m.revive_skill(args.pop("skill_id"), rationale=r)
    if tool == "promote_skill":
        return m.promote_skill(args.pop("skill_id"), rationale=r)
    if tool == "process_memory":
        args.pop("importance", None)
        return m.process_memory(Lesson.from_seed(args), rationale=r)
    if tool == "update_memory":
        lid = args.pop("lesson_id")
        return m.update_memory(lid, rationale=r, **args)
    if tool == "demote_memory":
        lid = args.pop("lesson_id")
        factor = float(args.pop("factor"))
        return m.demote_memory(lid, factor, rationale=r)
    if tool == "rewrite_doctrine":
        return m.rewrite_doctrine(args.pop("section"), args.pop("new_guidance"), rationale=r)
    raise ValueError(f"unknown tool: {tool}")


def _target_id(tool: str, args: dict) -> str | None:
    if tool in ("write_skill", "patch_skill", "retire_skill", "revive_skill", "promote_skill"):
        v = args.get("skill_id")
    elif tool in ("process_memory", "update_memory", "demote_memory"):
        v = args.get("lesson_id")
    elif tool == "rewrite_doctrine":
        v = args.get("section")
    else:
        v = None
    return str(v) if v is not None else None


def try_apply_op(meta: MetaTools, harness: HarnessState, op: RefineOp, *, allowed: frozenset[str],
                 min_retire_samples: int, min_promote_samples: int,
                 provenance: EditProvenance | None = None,
                 conflict_queue=None) -> tuple[EditRecord | None, str | None]:
    """Gate order: whitelist -> rationale -> empty-patch -> retire/promote evidence -> dispatch
    (dispatch errors -> clean reject reason). Returns (record, None) on apply | (None, reason)."""
    tid = _target_id(op.tool, op.args)
    if op.tool not in allowed:
        return None, "tool not in this pass or unknown"
    if not op.rationale or not op.rationale.strip():
        return None, "missing rationale"
    if op.tool in ("patch_skill", "update_memory") and not (set(op.args) - {"skill_id", "lesson_id"}):
        return None, "empty patch (no fields to change)"
    if op.tool == "retire_skill" and tid is not None:
        sk = harness.skills.get(tid)
        if sk is not None and sk.stats.n < min_retire_samples:
            return None, f"retire blocked: n={sk.stats.n} < min_retire_samples={min_retire_samples}"
    if op.tool == "promote_skill" and tid is not None:
        sk = harness.skills.get(tid)
        if sk is not None:
            if sk.stats.n < min_promote_samples:
                return None, f"promote blocked: n={sk.stats.n} < min_promote_samples={min_promote_samples}"
            if sk.stats.expectancy is None or sk.stats.expectancy <= 0:
                return None, "promote blocked: expectancy (advantage) not > 0"
    try:
        rec = _dispatch(meta, op)
    except _DISPATCH_ERRORS as e:
        return None, f"{type(e).__name__}: {e}"
    if provenance is not None:
        rec = meta.log.stamp_last(provenance)
    return rec, None
