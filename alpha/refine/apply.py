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
from alpha.trace import SCOPES, is_scope_wider, scope_rank

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


def _derive_confirmed_task_ids(log) -> frozenset[str]:
    """Externally-confirmed task episode ids from DURABLE records only (A2 / kairos-mining §2.3).

    A confirmation == a gated EditRecord stamped with `human_approver` whose `evidence_ref` lists
    the confirmed task episode ids under `confirmed_episode_ids`. task_forge (and any self-study
    proposer) cannot stamp `human_approver` — that is written only at human-approval time — so this
    set is forgery-resistant AT THE WAIST: the gate derives the confirmed-positive count itself
    instead of trusting the proposer's `confirmed_ids`/`task_stats`."""
    out: set[str] = set()
    for rec in log.records():
        p = rec.provenance
        # Harvest ONLY from a HUMAN-approval path (teaching approve / user_direct edit). A
        # self_study record carrying human_approver — e.g. laundered via adopt_proposal's post-gate
        # direct save, which bypasses the waist's leg-1 check — is NOT a valid confirmation source:
        # its evidence_ref was authored by the proposer, so trusting it would re-open the self-write
        # channel. This path-filter is the load-bearing leg (leg-1 alone can't see the bypass).
        if (p is not None and p.human_approver and p.evidence_kind == "task"
                and p.path in ("teaching", "user_direct") and p.evidence_ref):
            for eid in (p.evidence_ref.get("confirmed_episode_ids") or []):
                out.add(str(eid))
    return frozenset(out)


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


def _landed_scope(op: RefineOp) -> str | None:
    """The scope this edit would land at, ONLY IF the op explicitly declares one (op.args['scope']).
    None = undeclared -> A8's scope-mismatch gate is a byte-identical no-op (legacy / pre-label ops).
    A garbage value also returns None (the dispatch's Scope-Literal validation rejects it later)."""
    s = op.args.get("scope")
    return s if s in SCOPES else None


def _evidence_scope(provenance: EditProvenance | None) -> str:
    """The effective scope of the cited evidence for the scope-mismatch gate — derived
    CONSERVATIVELY (A8 governance decision, user-ratified): the NARROWEST scope observed in the
    cited evidence (provenance.evidence_ref['evidence_scopes' | 'evidence_scope']), or 'per-session'
    (narrowest) when unknown, so a wide edit off narrow/absent evidence bounces. The STORED default
    scope label stays agent-global (A4); the GATE never reads it — it reads the cited evidence."""
    ref = provenance.evidence_ref if provenance is not None else None
    scopes: list[str] = []
    if isinstance(ref, dict):
        raw = ref.get("evidence_scopes")
        if isinstance(raw, (list, tuple)):
            scopes = [s for s in raw if s in SCOPES]
        elif ref.get("evidence_scope") in SCOPES:
            scopes = [ref["evidence_scope"]]
    if not scopes:
        return "per-session"
    return min(scopes, key=scope_rank)


def try_apply_op(meta: MetaTools, harness: HarnessState, op: RefineOp, *, allowed: frozenset[str],
                 min_retire_samples: int, min_promote_samples: int,
                 provenance: EditProvenance | None = None,
                 conflict_queue=None,
                 task_stats: "TaskStats | None" = None,
                 min_task_samples: int = 3,
                 min_task_success_rate: float = 0.5,
                 min_task_confirmed_samples: int = 3,
                 task_recall=None, asof=None,
                 normalize=None) -> tuple[EditRecord | None, str | None]:
    """Gate order: stamp coherence -> whitelist -> rationale -> empty-patch -> set-once/create guards ->
    scope-mismatch (A8) -> domain-aware separation -> [task branch: operational-M reject -> gate-side re-derivation ->
    task floor (PC-8) -> conflict] -> trade floors -> conflict -> dispatch
    (dispatch errors -> clean reject reason). Returns (record, None) on apply | (None, reason).

    `task_recall` (read-only EpisodeStore) + `asof` (keyword-only, A2): when both are threaded in on
    a task-evidenced op, the gate re-derives `task_stats` ITSELF from `task_recall.for_asof(asof,
    kind="task")` with `confirmed_ids` from durable EditLog records — the caller-supplied `task_stats`
    is then ignored (kairos-mining §2.3). Both absent (the default) → byte-identical to the dormant
    P-C build. Enforcement semantics are unchanged; this only wires the branch's evidence source.

    `normalize` (keyword-only) selects the create-path phase vocabulary; None → resolved FROM THE H
    being edited (`harness.vocabulary`), never the process env, so pack identity rides with the harness
    (a growth-H edit keeps its scale-typed tokens; a momo-H edit stays momo even under a divergent
    ALPHA_SEED_PACK). Enforcement is unchanged — this only picks the create-path normalizer (P0.5 / P0.3 §5)."""
    if normalize is None:                       # resolve the create-path vocabulary from the H being
        from alpha.harness.loader import normalizer_for   # edited (h.vocabulary), NOT the process env
        normalize = normalizer_for(harness.vocabulary)
    tid = _target_id(op.tool, op.args)
    # Two-hands invariant (A7; charter First Founding Principle — "only two hands may send it
    # there"): the worker (Kairos, pre-rename hermes) does NOT propose. An op stamped
    # proposer="kairos"|"hermes" is refused at the waist, before any content check — only a Sonia
    # proposal (sonia / self-study forge|refiner surfaced through /proposals) or the User's direct
    # edit (user) may reach the gate. The names stay in the EditProvenance Literal for read-compat
    # (persisted brains still deserialize); this is a WRITE-origin gate, not a vocabulary removal.
    if provenance is not None and provenance.proposer in ("kairos", "hermes"):
        return None, ("worker proposals retired (charter A7): Kairos does not propose; only a Sonia "
                      "proposal or the User's direct edit may send to the gate")
    # Stamp coherence (charter drill roster, extended 2026-07-08): a direct edit not carrying
    # the user-authored stamp is refused at the waist, before any content check.
    if provenance is not None and provenance.path == "user_direct" and (
            provenance.proposer != "user" or not provenance.human_approver):
        return None, "user_direct requires proposer='user' with human_approver (unstamped direct edit refused)"
    # A2 review-fix (leg 1): human_approver is a HUMAN act — it may ride only a user_direct or
    # teaching edit. A self-study op may not self-stamp it, or a proposer could forge the external
    # confirmation the confirmed-positive floor counts. Refused at the waist, before any durable
    # record, like a mis-stamped user_direct. (The legit user-adopted self_study record carries
    # human_approver via adopt_proposal's POST-gate direct save, which never reaches this waist;
    # leg 2 in _derive_confirmed_task_ids fences that path out of the confirmed-derivation.)
    if provenance is not None and provenance.human_approver and provenance.path not in ("user_direct", "teaching"):
        return None, "human_approver may only ride a user_direct or teaching edit (self-study cannot self-approve)"
    if op.tool not in allowed:
        return None, "tool not in this pass or unknown"
    if not op.rationale or not op.rationale.strip():
        return None, "missing rationale"
    if op.tool in ("patch_skill", "update_memory") and not (set(op.args) - {"skill_id", "lesson_id"}):
        return None, "empty patch (no fields to change)"
    # PC-4: set-once relabel guard — domain is immutable once an element is created; all provenances.
    if op.tool in ("patch_skill", "update_memory") and "domain" in op.args:
        return None, "domain is set-once; cannot be relabeled"
    # A8 scope-mismatch static gate (charter *The External Channel* — "live from day one"): an edit
    # landing at a scope WIDER than its cited evidence's scope fails and bounces to Sonia. ADDITIVE +
    # fail-closed: fires ONLY when the op explicitly declares a landed scope (op.args['scope']); an
    # undeclared/legacy op -> byte-identical pass. user_direct is exempt (the user's own hand carries
    # agent-global authority; forgoes the packet counsel, charter *Applier*). Evidence scope defaults
    # to the NARROWEST cited, or per-session when unknown (A8 governance decision; see the A8 spec).
    landed = _landed_scope(op)
    if landed is not None and (provenance is None or provenance.path != "user_direct"):
        evidence = _evidence_scope(provenance)
        if is_scope_wider(landed, evidence):
            return None, (f"scope-mismatch: landed scope '{landed}' wider than evidence scope "
                          f"'{evidence}' (bounces to Sonia)")
    # PC-5: domain-aware separation gate — task-evidenced ops may only target operational H.
    # Placed before the trade floors so operational targets (stats.n==0/expectancy=None) aren't
    # wrongly rejected by the retire/promote floor before we can route them.
    if provenance is not None and provenance.evidence_kind == "task":
        # A2 item 2: operational-M is out of scope — the task signal targets K + operational
        # doctrine only (arena-spec §5), NEVER M (Lessons). Reject every task-evidenced memory op,
        # closing the create-path gap where process_memory(domain="operational") slipped through.
        if _target_kind(op.tool) == "memory":
            return None, "separation: operational-M out of scope (task evidence targets K + operational-doctrine only)"
        domain = _element_domain(harness, op.tool, tid, op.args)
        if domain != "operational":
            return None, f"separation: task-evidence may only target operational H (target domain={domain})"
        # A2 item 3 + before-live (a): gate-side re-derivation. With a read-only PIT-pinned task
        # recall handle threaded in, the gate recomputes task_stats ITSELF from durable records and
        # IGNORES the caller's task_stats (mirrors the verdict recall_store split so the gate can
        # never become a self-write channel). task_recall=None → byte-identical (caller-supplied).
        if task_recall is not None:
            if asof is None:
                return None, "task floor: asof required to re-derive task evidence (fails closed)"
            from alpha.memory.aggregate import summarize_task   # lazy: respect the refine<->memory cycle
            eps = task_recall.for_asof(asof, kind="task", limit=None)
            confirmed = _derive_confirmed_task_ids(meta.log)
            task_stats = summarize_task(eps, key=lambda e: e.skill_id, confirmed_ids=confirmed).get(tid)
        # Operational target: short-circuit the trade floors entirely.
        # PC-8 (Task 17): gate-side task floor — authority lives at the waist.
        # None fails closed; the caller MUST supply (or the gate MUST derive) task evidence.
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
        # A2 item 1: conflict routing — an operational task op contesting a teaching- or
        # user_direct-owned element is HELD for adjudication, not silently applied. The task branch
        # used to short-circuit past the trade path's conflict check at the tail of this function.
        if conflict_queue is not None:
            from alpha.refine.conflict import is_conflict
            if is_conflict(meta.log, op, provenance):
                contested = meta.log.latest_for(_target_kind(op.tool), tid) if tid else None
                conflict_queue.add(op=op.model_dump(),
                                   provenance=provenance.model_dump() if provenance else None,
                                   contested=contested.model_dump() if contested else None)
                return None, "held_for_review: self-study contests a teaching- or user-owned element"
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
