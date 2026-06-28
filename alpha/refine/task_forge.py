# alpha/refine/task_forge.py
"""Deterministic task-signal proposer — the operational-K twin of forge.propose_skill_ops.

Reads kind="task" episodes from the episode store, aggregates via summarize_task, and proposes
promote_skill / retire_skill ops ONLY for domain="operational" K-skills (NEVER for trading).
Every op is routed through try_apply_op stamped with EditProvenance(evidence_kind="task"),
satisfying the one-write-waist invariant and the PC-9 pinning requirement (verdict 5).
"""
from __future__ import annotations

from datetime import date as Date

from alpha.harness.edit_log import EditProvenance
from alpha.harness.state import HarnessState
from alpha.memory.aggregate import TaskStats, summarize_task
from alpha.refine.apply import try_apply_op
from alpha.refine.forge import ForgeReport, _FORGE_ALLOWED
from alpha.refine.ops import RefineOp


def propose_task_skill_ops(
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
) -> list[tuple[RefineOp, TaskStats]]:
    """Deterministic per-skill task-episode proposer for operational K.

    Reads kind="task" episodes PIT-masked by `asof`, aggregates via summarize_task, and
    proposes:
      - promote_skill  for operational incubating skills meeting the confirmed-positive floor.
      - retire_skill   for operational active skills with strong confirmed-failure signal.

    NEVER proposes for domain="trading" skills — domain is checked against the harness element,
    not the episode. The gate (try_apply_op) re-enforces the floor independently; the proposer-
    side floor here is a pre-filter to avoid sending noise to the gate.

    Returns a list of (RefineOp, TaskStats) pairs so the caller can pass the task evidence to
    try_apply_op without re-computing it.
    """
    # Pass limit=None: the no-cap convention shared with all full-history aggregation callers.
    task_eps = episode_store.for_asof(asof, kind="task", limit=None)
    stats = summarize_task(task_eps, key=lambda e: e.skill_id, confirmed_ids=confirmed_ids)
    pairs: list[tuple[RefineOp, TaskStats]] = []
    for skill_id, s in stats.items():
        sk = harness.skills.get(skill_id)
        if sk is None:
            continue
        # Domain gate: ONLY operational K can be evolved via task evidence.
        if sk.domain != "operational":
            continue
        # Promote: incubating + meets confirmed-positive floor.
        if (sk.status == "incubating"
                and s.n >= promote_min_samples
                and s.confirmed_n >= promote_min_confirmed
                and s.confirmed_success_rate >= promote_min_success_rate):
            op = RefineOp(
                tool="promote_skill",
                args={"skill_id": skill_id},
                rationale=(f"task_forge: n={s.n} confirmed_n={s.confirmed_n} "
                           f"confirmed_success_rate={s.confirmed_success_rate:.2f}"),
            )
            pairs.append((op, s))
        # DEFERRED: retire-on-task (spec §3.5) requires a confirmed-FAILURE gate floor; the
        # Task-17 gate only added a confirmed-POSITIVE promote floor, which a failing skill can
        # never pass — so a retire op here is always rejected. Emit nothing for retire until a
        # retire-specific task floor ships, to avoid dead, always-rejected ops in ForgeReport.
    return pairs


def forge_task_skills(
    harness: HarnessState,
    episode_store,
    meta,
    *,
    asof: Date,
    confirmed_ids: frozenset[str] = frozenset(),
    conflict_queue=None,
    min_task_samples: int = 3,
    min_task_success_rate: float = 0.5,
    min_task_confirmed_samples: int = 3,
    promote_min_samples: int = 3,
    promote_min_confirmed: int = 3,
    promote_min_success_rate: float = 0.5,
    retire_min_samples: int = 5,
    retire_min_failrate: float = 0.5,
) -> ForgeReport:
    """Apply proposed task-evidence ops through the one gate (try_apply_op).

    Every op is stamped EditProvenance(path="self_study", proposer="forge", evidence_kind="task"),
    enforcing the PC-9 pinning invariant (verdict 5): an op from this path ALWAYS carries
    evidence_kind="task". The gate independently re-enforces the task floor from the precomputed
    task_stats, so the proposer-side floor is a pre-filter only.
    """
    report = ForgeReport()
    pairs = propose_task_skill_ops(
        episode_store, harness,
        asof=asof,
        confirmed_ids=confirmed_ids,
        promote_min_samples=promote_min_samples,
        promote_min_confirmed=promote_min_confirmed,
        promote_min_success_rate=promote_min_success_rate,
        retire_min_samples=retire_min_samples,
        retire_min_failrate=retire_min_failrate,
    )
    for op, task_stats in pairs:
        sid = op.args["skill_id"]
        sk = harness.skills.get(sid)
        domain = sk.domain
        # PINNING (verdict 5): evidence_kind is ALWAYS "task" for this proposer.
        provenance = EditProvenance(
            path="self_study",
            proposer="forge",
            evidence_kind="task",
            evidence_ref={"domain": domain},
        )
        rec, reason = try_apply_op(
            meta, harness, op,
            allowed=_FORGE_ALLOWED,
            min_promote_samples=promote_min_samples,
            min_retire_samples=retire_min_samples,
            provenance=provenance,
            conflict_queue=conflict_queue,
            task_stats=task_stats,
            min_task_samples=min_task_samples,
            min_task_success_rate=min_task_success_rate,
            min_task_confirmed_samples=min_task_confirmed_samples,
        )
        if rec is not None:
            report.applied.append(sid)
        elif reason and reason.startswith("held_for_review"):
            report.held.append(sid)
        else:
            report.rejected.append((sid, reason or ""))
    return report
