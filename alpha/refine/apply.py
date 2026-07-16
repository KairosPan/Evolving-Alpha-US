# alpha/refine/apply.py
from __future__ import annotations

import re as _re
from typing import TYPE_CHECKING

from pydantic import ValidationError

from alpha.harness.connectors import ConnectorEntry
from alpha.harness.edit_log import EditProvenance, EditRecord
from alpha.harness.errors import HarnessError
from alpha.harness.memory import Lesson
from alpha.harness.metatools import MetaTools
from alpha.harness.skill import Skill
from alpha.harness.state import HarnessState
from alpha.harness.workflows import WorkflowEntry
from alpha.refine.ops import PASS_TOOLS, RefineOp
from alpha.trace import SCOPES, is_scope_wider, scope_rank

if TYPE_CHECKING:
    from alpha.memory.aggregate import TaskStats

ALL_TOOLS = frozenset().union(*PASS_TOOLS.values())

_SKILL_ID_SHAPE = _re.compile(r"^[a-z0-9]+(?:[_-][a-z0-9]+)*$")   # an id-shaped step ref (no spaces)

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
    if tool == "write_connector":
        return m.write_connector(ConnectorEntry.model_validate(args), rationale=r)
    if tool == "patch_connector":
        cid = args.pop("connector_id")
        return m.patch_connector(cid, args, rationale=r)
    if tool == "disable_connector":
        return m.disable_connector(args.pop("connector_id"), rationale=r)
    if tool == "write_workflow":
        entry = WorkflowEntry.model_validate(args)
        entry.content_hash = _workflow_hash(entry)            # stamp the content digest before upsert
        return m.write_workflow(entry, rationale=r)
    if tool == "patch_workflow":
        wid = args.pop("workflow_id")
        cur = m.h.workflows.get(wid)
        if cur is not None:                                   # unknown id -> patch_workflow raises KeyError
            merged = WorkflowEntry.model_validate({**cur.model_dump(), **args})   # coerce nested steps
            args["content_hash"] = _workflow_hash(merged)     # recompute on the updated entry
        return m.patch_workflow(wid, args, rationale=r)
    if tool == "retire_workflow":
        return m.retire_workflow(args.pop("workflow_id"), rationale=r)
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


def _is_taboo_less_trading_pattern(typ, domain, taboo) -> bool:
    """PC-9 predicate (魂骨宪法 §4 红线): a trading `type='pattern'` skill carrying no REAL red-line —
    i.e. a "do X" pattern with no non-blank "except when Y" taboo. Operational patterns (govern the
    agent's operation, not trading) and non-pattern skills (feature/failure_detector) are exempt. A
    `['']` blank entry does NOT count as a red-line (closes the blank-taboo loophole)."""
    return (typ == "pattern" and (domain or "trading") != "operational"
            and not any(isinstance(t, str) and t.strip() for t in (taboo or [])))


_MAX_INSTRUCTIONS = 2000
_LLM_ROLES = frozenset({"agent", "refiner", "sonia", "converse"})


def _connector_impl_resolves(entry: ConnectorEntry) -> bool:
    """A connector DECLARES a capability by referencing an operator-registered implementation by key;
    editing the declaration must never invent a capability that does not exist (data rung R1/R2). A
    data_source impl_ref must resolve in the data registry; an llm_role in the make_client roles; an
    mcp reference has no registry to resolve against yet (accepted)."""
    from alpha.data.registry import source_names       # lazy: keep refine independent of the data layer at import
    if entry.kind == "data_source":
        return entry.impl_ref in source_names()
    if entry.kind == "llm_role":
        return entry.impl_ref in _LLM_ROLES
    return True                                          # mcp: no registry to resolve against yet


def _env_keys_are_names(entry: ConnectorEntry) -> str | None:
    """env_keys must be env-var NAMES ONLY — never a `NAME=value` credential and never an oversized
    blob. A '=' or an over-64-char token is a value leak, refused at the waist."""
    for k in entry.env_keys:
        if "=" in k or len(k) > 64:
            return f"env_keys must be env-var NAMES only, never values (offending: {k[:20]!r}...)"
    return None


def _check_connector(entry: ConnectorEntry) -> str | None:
    """First failing structural-lint reason for a connector entry, or None if clean. Pure function of
    the entry so preview (deepcopy + throwaway log) == landing."""
    if not _connector_impl_resolves(entry):
        return f"impl_ref {entry.impl_ref!r} does not resolve for kind {entry.kind!r}"
    env_bad = _env_keys_are_names(entry)
    if env_bad is not None:
        return env_bad
    if len(entry.instructions) > _MAX_INSTRUCTIONS:
        return f"instructions too long ({len(entry.instructions)} > {_MAX_INSTRUCTIONS} chars)"
    return None


def _workflow_hash(entry: WorkflowEntry) -> str:
    """Canonical content digest of a workflow entry (excludes content_hash itself). Recomputed at the
    waist on every create/patch so the stored hash always reflects the landed content — a patch that
    changes content changes the hash. Uses the repo's edit-log/snapshot canonicalizer for stability."""
    from alpha.integrity import sha256_canonical_json    # lazy: mirror snapshot.py's canonicalizer
    body = entry.model_dump(mode="json")
    body.pop("content_hash", None)
    return sha256_canonical_json(body)


def _check_workflow(entry: WorkflowEntry, h: HarnessState) -> str | None:
    """First failing structural-lint reason for a workflow entry, or None if clean. Pure function of
    the (entry, H) so preview == landing. Step referential-integrity is PERMISSIVE (taboo-lint's
    block-known-bad posture): only an id-shaped ref that resolves to a RETIRED skill is rejected;
    free-prose refs (with spaces) and unknown id-shaped refs (possibly future skills) are allowed."""
    if len(entry.description) > 200:
        return "description exceeds 200 chars (the index budget)"
    for st in entry.steps:
        if _SKILL_ID_SHAPE.match(st.ref):                     # looks like a skill id -> must not be retired
            sk = h.skills.get(st.ref)
            if sk is not None and sk.status == "retired":
                return f"step ref {st.ref!r} resolves to a retired skill"
    return None


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
    elif tool in ("write_connector", "patch_connector", "disable_connector"):
        v = args.get("connector_id")
    elif tool in ("write_workflow", "patch_workflow", "retire_workflow"):
        v = args.get("workflow_id")
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
    # PC-9 (red-line lint, kairos-mining §1.4/§2.4/§4.4): a trading `type='pattern'` skill MUST carry
    # >=1 non-blank taboo — a "do X" with no red-line ("except when Y") violates the 魂骨宪法 (§4 红线).
    # Enforced at CREATE (write_skill) AND at any PATCH that touches `type`/`taboo` — because both are
    # freely patchable through the K pass, a create-only gate is defeated by a follow-up patch that
    # (a) flips an exempt feature to a pattern or (b) strips the taboo from an already-passed pattern
    # (review-confirmed 2026-07-13). A patch touching NEITHER field is not re-linted (a pre-existing
    # taboo-less pattern is a separate grandfathering concern, not this patch's doing). Operational
    # patterns route through the task branch (returned above) and are exempt; domain is set-once so a
    # patch cannot relabel it. The 6 seed trading patterns all carry a taboo -> zero valid-op breakage.
    if op.tool == "write_skill":
        if _is_taboo_less_trading_pattern(op.args.get("type"), op.args.get("domain", "trading"),
                                          op.args.get("taboo")):
            return None, "red-line: a new trading pattern skill must carry >=1 taboo entry (魂骨宪法 §4)"
    elif op.tool == "patch_skill" and tid is not None and ("type" in op.args or "taboo" in op.args):
        existing = harness.skills.get(tid)
        if existing is not None and _is_taboo_less_trading_pattern(
                op.args.get("type", existing.type), existing.domain,
                op.args.get("taboo", existing.taboo)):
            return None, "red-line: patch would leave a trading pattern skill with no taboo (魂骨宪法 §4)"
    # Connector (C) structural lints (data rung R1/R2): impl_ref must resolve, env_keys must be
    # env-var NAMES only, instructions within the char cap. Enforced at CREATE and at any PATCH
    # (a create-only lint is defeated by a follow-up patch — the PC-9 pattern). Pure function of the
    # (merged) entry so preview == landing. A malformed op / unknown patch target bounces cleanly at
    # dispatch (_DISPATCH_ERRORS), so the lint only runs when it can build the entry to check.
    if op.tool == "write_connector":
        try:
            entry = ConnectorEntry.model_validate(op.args)
        except _DISPATCH_ERRORS as e:
            return None, f"{type(e).__name__}: {e}"
        bad = _check_connector(entry)
        if bad is not None:
            return None, bad
    elif op.tool == "patch_connector":
        cur = harness.connectors.get(op.args.get("connector_id"))
        if cur is not None:      # unknown id -> let dispatch raise KeyError -> clean reject
            fields = {k: v for k, v in op.args.items() if k != "connector_id"}
            try:
                merged = cur.model_copy(update=fields)
            except _DISPATCH_ERRORS as e:
                return None, f"{type(e).__name__}: {e}"
            bad = _check_connector(merged)
            if bad is not None:
                return None, bad
    # Workflow (W) structural lints (data rung R1/R2): description within the index budget +
    # step referential-integrity (a step ref that resolves to a RETIRED skill bounces; unknown/free
    # refs stay permissive). Enforced at CREATE and at any PATCH (the PC-9 create-only-defeat pattern).
    # Pure function of the (merged) entry + H so preview == landing.
    if op.tool == "write_workflow":
        try:
            entry = WorkflowEntry.model_validate(op.args)
        except _DISPATCH_ERRORS as e:
            return None, f"{type(e).__name__}: {e}"
        bad = _check_workflow(entry, harness)
        if bad is not None:
            return None, bad
    elif op.tool == "patch_workflow":
        cur = harness.workflows.get(op.args.get("workflow_id"))
        if cur is not None:      # unknown id -> let dispatch raise KeyError -> clean reject
            fields = {k: v for k, v in op.args.items() if k != "workflow_id"}
            try:
                merged = WorkflowEntry.model_validate({**cur.model_dump(), **fields})   # coerce nested steps
            except _DISPATCH_ERRORS as e:
                return None, f"{type(e).__name__}: {e}"
            bad = _check_workflow(merged, harness)
            if bad is not None:
                return None, bad
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
