# alpha/refine/apply.py
from __future__ import annotations

from typing import TYPE_CHECKING

from pydantic import ValidationError

from alpha.harness.edit_log import EditProvenance, EditRecord
from alpha.harness.errors import HarnessError
from alpha.harness.memory import Lesson
from alpha.harness.metatools import MetaTools
from alpha.harness.skill import Skill
from alpha.harness.state import HarnessState
from alpha.refine.ops import PASS_TOOLS, RefineOp

if TYPE_CHECKING:
    from alpha.memory.aggregate import TaskStats

ALL_TOOLS = frozenset().union(*PASS_TOOLS.values())

_DISPATCH_ERRORS = (HarnessError, KeyError, ValueError, ValidationError, TypeError, AttributeError)


def _dispatch(meta: MetaTools, op: RefineOp, *, normalize) -> EditRecord:
    """Map an op to its MetaTools call. Defensive: force write_skill->incubating + strip stats;
    strip importance on process_memory (the create paths the Refiner already sanitizes).

    `normalize` selects the phase vocabulary for the create paths (write_skill/process_memory);
    `try_apply_op` resolves it from the H being edited (`h.vocabulary`) — never the process env —
    so a live growth-H edit keeps its scale-typed tokens instead of dropping them (P0.5 / P0.3 §5)."""
    tool, args, r = op.tool, dict(op.args), op.rationale
    m = meta
    if tool == "write_skill":
        args.pop("stats", None)
        args["status"] = "incubating"
        return m.write_skill(Skill.from_seed(args, normalize=normalize), rationale=r)
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
        return m.process_memory(Lesson.from_seed(args, normalize=normalize), rationale=r)
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


def _target_kind(tool: str) -> str:
    from alpha.refine.conflict import _KIND
    return _KIND.get(tool, "")


def _element_domain(h: HarnessState, tool: str, tid: str | None, args: dict) -> str | None:
    """Return the domain of the op's target element for the domain-aware separation gate.

    Create tools (write_skill, process_memory) declare domain in args; all others look up
    the existing element.  Returns None when the target is missing or has no domain attr
    (fail-closed: None != "operational" → rejected).
    """
    if tool in ("write_skill", "process_memory"):
        return args.get("domain", "trading")   # create: domain declared in args
    if tid is None:
        return None
    kind = _target_kind(tool)
    if kind == "skill":
        el = h.skills.get(tid)
    elif kind == "memory":
        el = h.memory.get(tid)
    elif kind == "doctrine":
        el = h.doctrine.get(tid)
    else:
        el = None
    return getattr(el, "domain", None) if el is not None else None


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
                 conflict_queue=None,
                 task_stats: "TaskStats | None" = None,
                 min_task_samples: int = 3,
                 min_task_success_rate: float = 0.5,
                 min_task_confirmed_samples: int = 3,
                 normalize=None) -> tuple[EditRecord | None, str | None]:
    """Gate order: stamp coherence -> whitelist -> rationale -> empty-patch -> set-once/create guards ->
    domain-aware separation -> task floor (PC-8) -> trade floors -> conflict -> dispatch
    (dispatch errors -> clean reject reason). Returns (record, None) on apply | (None, reason).

    `normalize` (keyword-only) selects the create-path phase vocabulary; None → resolved FROM THE H
    being edited (`harness.vocabulary`), never the process env, so pack identity rides with the harness
    (a growth-H edit keeps its scale-typed tokens; a momo-H edit stays momo even under a divergent
    ALPHA_SEED_PACK). Enforcement is unchanged — this only picks the create-path normalizer (P0.5 / P0.3 §5)."""
    if normalize is None:                       # resolve the create-path vocabulary from the H being
        from alpha.harness.loader import normalizer_for   # edited (h.vocabulary), NOT the process env
        normalize = normalizer_for(harness.vocabulary)
    tid = _target_id(op.tool, op.args)
    # Stamp coherence (charter drill roster, extended 2026-07-08): a direct edit not carrying
    # the user-authored stamp is refused at the waist, before any content check.
    if provenance is not None and provenance.path == "user_direct" and (
            provenance.proposer != "user" or not provenance.human_approver):
        return None, "user_direct requires proposer='user' with human_approver (unstamped direct edit refused)"
    if op.tool not in allowed:
        return None, "tool not in this pass or unknown"
    if not op.rationale or not op.rationale.strip():
        return None, "missing rationale"
    if op.tool in ("patch_skill", "update_memory") and not (set(op.args) - {"skill_id", "lesson_id"}):
        return None, "empty patch (no fields to change)"
    # PC-4: set-once relabel guard — domain is immutable once an element is created; all provenances.
    if op.tool in ("patch_skill", "update_memory") and "domain" in op.args:
        return None, "domain is set-once; cannot be relabeled"
    # PC-5: domain-aware separation gate — task-evidenced ops may only target operational H.
    # Placed before the trade floors so operational targets (stats.n==0/expectancy=None) aren't
    # wrongly rejected by the retire/promote floor before we can route them.
    if provenance is not None and provenance.evidence_kind == "task":
        domain = _element_domain(harness, op.tool, tid, op.args)
        if domain != "operational":
            return None, f"separation: task-evidence may only target operational H (target domain={domain})"
        # Operational target: short-circuit the trade floors entirely.
        # PC-8 (Task 17): gate-side task floor — authority lives at the waist.
        # None fails closed; the caller MUST supply precomputed task evidence.
        if task_stats is None:
            return None, "task floor: task_stats required for operational ops (fails closed)"
        if task_stats.n < min_task_samples:
            return None, (f"task floor: n={task_stats.n} < min_task_samples={min_task_samples}")
        if task_stats.confirmed_n < min_task_confirmed_samples:
            return None, (f"task floor: confirmed_n={task_stats.confirmed_n} "
                          f"< min_task_confirmed_samples={min_task_confirmed_samples}")
        if task_stats.confirmed_success_rate < min_task_success_rate:
            return None, (f"task floor: confirmed_success_rate={task_stats.confirmed_success_rate:.3f} "
                          f"< min_task_success_rate={min_task_success_rate}")
        try:
            rec = _dispatch(meta, op, normalize=normalize)
        except _DISPATCH_ERRORS as e:
            return None, f"{type(e).__name__}: {e}"
        rec = meta.log.stamp_last(provenance)
        return rec, None
    # PC-4: create-path mislabel guard — only a task-evidenced create may mint domain="operational".
    if op.tool in ("write_skill", "process_memory") and op.args.get("domain") == "operational":
        if provenance is None or provenance.evidence_kind != "task":
            return None, "create may not mint operational under trade evidence"
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
    if conflict_queue is not None:
        from alpha.refine.conflict import is_conflict
        if is_conflict(meta.log, op, provenance):
            contested = meta.log.latest_for(_target_kind(op.tool), tid) if tid else None
            conflict_queue.add(op=op.model_dump(), provenance=provenance.model_dump() if provenance else None,
                               contested=contested.model_dump() if contested else None)
            return None, "held_for_review: self-study contests a teaching- or user-owned element"
    try:
        rec = _dispatch(meta, op, normalize=normalize)
    except _DISPATCH_ERRORS as e:
        return None, f"{type(e).__name__}: {e}"
    if provenance is not None:
        rec = meta.log.stamp_last(provenance)
    return rec, None
