# alpha/refine/reflect.py
"""The self-learning channel — reflection→directions over the agent's OWN task runs (A3).

Deterministic (LLM-free), READ-ONLY over kind="task" episodes (PIT-masked via for_asof — the
kind="task" fence keeps it off every trade/verdict read, so verdict symmetry is preserved). It
reflects on operational-K task evidence and turns each reflection into a gate-vetted DIRECTION
(promote/retire of an OPERATIONAL skill — NEVER trading), routed through the one write-waist
(try_apply_op) inside a FORK so the surviving delta ships as an EvolutionProposal the USER
adjudicates. No new write path, no live H write.

Two-learning-paths invariants preserved here:
  - self-study forks-and-proposes (run_forked_evolution wraps this); it never auto-applies;
  - a direction contesting a teaching/user_direct-owned element is HELD (is_conflict, unchanged);
  - a direction the USER rejected is suppressed via negative constraints — never re-proposed.
"""
from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass, field
from datetime import date as Date

from alpha.harness.edit_log import EditProvenance
from alpha.harness.state import HarnessState
from alpha.memory.aggregate import TaskStats
from alpha.refine.apply import _target_id, try_apply_op
from alpha.refine.forge import _FORGE_ALLOWED
from alpha.refine.ops import RefineOp
from alpha.refine.task_forge import propose_task_skill_ops


@dataclass
class Reflection:
    """One human-readable observation about the agent's own task runs + the direction it suggests."""
    skill_id: str
    signal: str                      # "proven" | "underperforming"
    evidence: dict
    dominant_failure_kind: str | None
    rationale: str
    op: RefineOp
    stats: TaskStats


@dataclass
class ReflectReport:
    applied: list[str] = field(default_factory=list)
    held: list[str] = field(default_factory=list)
    rejected: list[tuple[str, str]] = field(default_factory=list)
    suppressed: list[str] = field(default_factory=list)   # negative-constraint-filtered directions
    reflections: list[Reflection] = field(default_factory=list)


def direction_signature(op: RefineOp) -> str:
    """The stable key of a direction (a verb on a target) for negative-constraint matching."""
    return f"{op.tool}:{_target_id(op.tool, op.args)}"


def signature_from_record(record: dict) -> str:
    """The same key computed from a landed/proposed EditRecord dict (tool + target_id)."""
    return f"{record.get('tool')}:{record.get('target_id')}"


def reflect_over_tasks(
    episode_store,
    harness: HarnessState,
    *,
    asof: Date,
    confirmed_ids: frozenset[str] = frozenset(),
    promote_min_samples: int = 3,
    promote_min_confirmed: int = 3,
    promote_min_success_rate: float = 0.5,
    retire_min_samples: int = 5,
    retire_min_failrate: float = 0.5,
) -> list[Reflection]:
    """Deterministic, read-only reflection over kind="task" episodes → candidate directions.

    Reuses the operational-only, confirmed-positive-floor candidate ops from task_forge (so the gate
    vets them identically) and wraps each in a Reflection carrying the human-readable "why" +
    the dominant failure_kind observed across that skill's task episodes.
    """
    task_eps = episode_store.for_asof(asof, kind="task", limit=None)   # PIT-masked, task-fenced
    fk: dict[str, Counter] = defaultdict(Counter)
    for e in task_eps:
        if getattr(e, "failure_kind", None):
            fk[e.skill_id][e.failure_kind] += 1

    pairs = propose_task_skill_ops(
        episode_store, harness, asof=asof, confirmed_ids=confirmed_ids,
        promote_min_samples=promote_min_samples, promote_min_confirmed=promote_min_confirmed,
        promote_min_success_rate=promote_min_success_rate,
        retire_min_samples=retire_min_samples, retire_min_failrate=retire_min_failrate)

    reflections: list[Reflection] = []
    for op, stats in pairs:
        sid = op.args["skill_id"]
        dom = None
        if fk.get(sid):
            dom = sorted(fk[sid].items(), key=lambda kv: (-kv[1], kv[0]))[0][0]   # deterministic tie-break
        signal = "proven" if op.tool == "promote_skill" else "underperforming"
        evidence = {"n": stats.n, "confirmed_n": stats.confirmed_n,
                    "confirmed_success_rate": round(stats.confirmed_success_rate, 4)}
        rationale = (f"reflection over {stats.n} task run(s) of '{sid}': confirmed "
                     f"{stats.confirmed_n} positive at {stats.confirmed_success_rate:.0%} → {op.tool}")
        reflections.append(Reflection(skill_id=sid, signal=signal, evidence=evidence,
                                      dominant_failure_kind=dom, rationale=rationale,
                                      op=op, stats=stats))
    return reflections


def reflect_task_skills(
    harness: HarnessState,
    episode_store,
    meta,
    *,
    asof: Date,
    confirmed_ids: frozenset[str] = frozenset(),
    negative_signatures: frozenset[str] = frozenset(),
    conflict_queue=None,
    task_recall=None,
    min_task_samples: int = 3,
    min_task_success_rate: float = 0.5,
    min_task_confirmed_samples: int = 3,
    promote_min_samples: int = 3,
    promote_min_confirmed: int = 3,
    promote_min_success_rate: float = 0.5,
    retire_min_samples: int = 5,
    retire_min_failrate: float = 0.5,
) -> ReflectReport:
    """Route each reflection's direction through the one gate (try_apply_op). Negative-constraint
    signatures are SUPPRESSED (never sent to the gate — a user-rejected direction is not re-proposed).

    Same gate call as forge_task_skills: self_study/forge/evidence_kind="task" provenance, the
    confirmed-positive floor, the operational-domain gate, and the conflict→held check all apply
    unchanged. `task_recall`+`asof` let the gate re-derive confirmed evidence from durable records.
    """
    report = ReflectReport()
    reflections = reflect_over_tasks(
        episode_store, harness, asof=asof, confirmed_ids=confirmed_ids,
        promote_min_samples=promote_min_samples, promote_min_confirmed=promote_min_confirmed,
        promote_min_success_rate=promote_min_success_rate,
        retire_min_samples=retire_min_samples, retire_min_failrate=retire_min_failrate)
    report.reflections = reflections

    for r in reflections:
        op = r.op
        sid = op.args["skill_id"]
        if direction_signature(op) in negative_signatures:
            report.suppressed.append(sid)                 # the negative constraint bites HERE
            continue
        sk = harness.skills.get(sid)
        provenance = EditProvenance(path="self_study", proposer="forge", evidence_kind="task",
                                    evidence_ref={"domain": getattr(sk, "domain", None)})
        rec, reason = try_apply_op(
            meta, harness, op, allowed=_FORGE_ALLOWED,
            min_promote_samples=promote_min_samples, min_retire_samples=retire_min_samples,
            provenance=provenance, conflict_queue=conflict_queue, task_stats=r.stats,
            min_task_samples=min_task_samples, min_task_success_rate=min_task_success_rate,
            min_task_confirmed_samples=min_task_confirmed_samples,
            task_recall=task_recall, asof=asof)
        if rec is not None:
            report.applied.append(sid)
        elif reason and reason.startswith("held_for_review"):
            report.held.append(sid)
        else:
            report.rejected.append((sid, reason or ""))
    return report


def record_directions_from_proposal(store, proposal, *, reason: str = "user_discard") -> int:
    """Human-rejection mining: turn each direction a DISCARDED proposal carried into a negative
    constraint (keyed by signature) so the detector never re-proposes it. Returns the count added."""
    count = 0
    for rec in getattr(proposal, "records", []) or []:
        tool = rec.get("tool")
        if not tool:
            continue
        tid = rec.get("target_id")
        store.add(signature=signature_from_record(rec), tool=str(tool),
                  target_id=str(tid) if tid is not None else "", reason=reason,
                  source_proposal_id=getattr(proposal, "proposal_id", ""))
        count += 1
    return count


def reflections_summary(reflections: list[Reflection]) -> list[dict]:
    """JSON-safe digest of the reflections, for the EvolutionProposal window (cockpit surfacing)."""
    return [{"skill_id": r.skill_id, "signal": r.signal, "rationale": r.rationale,
             "dominant_failure_kind": r.dominant_failure_kind, "evidence": r.evidence}
            for r in reflections]
