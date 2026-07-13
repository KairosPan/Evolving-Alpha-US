# alpha/refine/forge.py
from __future__ import annotations
from dataclasses import dataclass
from datetime import date as Date
from typing import Literal
from pydantic import BaseModel, Field
from alpha.harness.edit_log import EditProvenance
from alpha.harness.regime import phase_from_read
from alpha.harness.skill import Skill
from alpha.harness.state import HarnessState
from alpha.memory.aggregate import EpisodeStats, summarize
from alpha.refine.apply import try_apply_op
from alpha.refine.ops import RefineOp

BucketBy = Literal["phase", "narrative"]


@dataclass(frozen=True)
class _Proposal:
    """One forge proposal: the status op (promote/retire) plus an optional patch-on-promote patch.
    The patch is applied by forge_skills ONLY after the promote lands (a rejected promote never patches)."""
    op: RefineOp                        # promote_skill | retire_skill
    patch: RefineOp | None = None       # optional phase-narrowing patch_skill (P7 patch-on-promote)


def _best_promote_bucket(eps: list, skill_id: str, bucket_by: BucketBy, phase_of,
                         *, min_samples: int, min_winrate: float) -> tuple[EpisodeStats, object] | None:
    """The skill's best qualifying promotion bucket (P7 bucketed evidence), or None.

    Groups the skill's episodes by bucket — canonical phase (`phase_of(e.phase)`) for "phase", raw
    `e.narrative` for "narrative" — summarizes each, and returns the (stats, bucket_value) of the best
    bucket clearing the promote floor (n>=min_samples, win_rate>=min_winrate, mean_advantage>0),
    chosen deterministically by (win_rate, n, str(bucket)). Retire never buckets (see _propose)."""
    def bucket_of(e):
        return phase_of(e.phase or "") if bucket_by == "phase" else (e.narrative or "")
    groups: dict[object, list] = {}
    for e in eps:
        if e.skill_id == skill_id:
            groups.setdefault(bucket_of(e), []).append(e)
    best_key = None
    best: tuple[EpisodeStats, object] | None = None
    for bucket, group in groups.items():
        s = summarize(group, key=lambda e: e.skill_id)[skill_id]
        if s.n >= min_samples and s.win_rate >= min_winrate and s.mean_advantage > 0:
            key = (s.win_rate, s.n, str(bucket))
            if best_key is None or key > best_key:
                best_key, best = key, (s, bucket)
    return best


def _phase_patch(skill: Skill, bucket_phase: object) -> RefineOp | None:
    """A surgical phase-narrowing patch for a just-promoted skill — a `patch_skill` (not a wholesale
    `write_skill` replace). None if the winning bucket doesn't canonicalize to a real phase, or the
    skill is already scoped to exactly that phase (an empty/no-op patch the gate would reject)."""
    canon = phase_from_read(bucket_phase) if isinstance(bucket_phase, str) else None
    if canon is None:
        return None
    if skill.phases == [canon] and not skill.applies_all_phases:
        return None
    return RefineOp(tool="patch_skill",
                    args={"skill_id": skill.skill_id, "phases": [canon], "applies_all_phases": False},
                    rationale=f"forge patch-on-promote: scope to winning phase {canon!r} (episode evidence)")


def _propose(harness: HarnessState, episode_store, *, asof: Date,
             bucket_by: BucketBy | None = None, patch_on_promote: bool = False,
             promote_min_samples: int = 5, promote_min_winrate: float = 0.5,
             retire_min_samples: int = 5, retire_min_nukerate: float = 0.5,
             phase_of=phase_from_read) -> list[_Proposal]:
    """Deterministic per-skill episode-evidence proposer (PIT-masked via for_asof). Pure (reads only).

    Retire ALWAYS uses the GLOBAL per-skill aggregate — a demote must reflect broad failure and must
    never be diluted by bucketing. Promotion evidence is global when `bucket_by is None` (byte-identical
    to v1, same op order/rationale) or bucketed (best qualifying phase/narrative bucket) otherwise.
    `patch_on_promote` (with bucket_by="phase") attaches a phase-narrowing patch to each promote."""
    # for_asof's default limit (50) is a GLOBAL cap across all skills — too small for this offline
    # maintenance pass; limit=None = the no-cap convention shared with the recall/taboo aggregation sites.
    eps = episode_store.for_asof(asof, limit=None)
    global_stats = summarize(eps, key=lambda e: e.skill_id)
    out: list[_Proposal] = []
    for skill_id, gs in global_stats.items():                 # v1 iteration order (first-seen in recall)
        sk = harness.skills.get(skill_id)
        if sk is None:
            continue
        if sk.status == "incubating":
            if bucket_by is None:
                s, bucket = gs, None
            else:
                found = _best_promote_bucket(eps, skill_id, bucket_by, phase_of,
                                             min_samples=promote_min_samples, min_winrate=promote_min_winrate)
                if found is None:
                    continue
                s, bucket = found
            if s.n >= promote_min_samples and s.win_rate >= promote_min_winrate and s.mean_advantage > 0:
                rationale = (f"forge: episode evidence n={s.n} win_rate={s.win_rate:.2f} "
                             f"mean_adv={s.mean_advantage:+.2f}")
                if bucket is not None:
                    rationale += f" [{bucket_by}={bucket!r}]"
                op = RefineOp(tool="promote_skill", args={"skill_id": skill_id}, rationale=rationale)
                patch = _phase_patch(sk, bucket) if (patch_on_promote and bucket_by == "phase") else None
                out.append(_Proposal(op, patch))
        elif sk.status == "active" and gs.n >= retire_min_samples and gs.nuke_rate >= retire_min_nukerate:
            out.append(_Proposal(RefineOp(
                tool="retire_skill", args={"skill_id": skill_id, "permanent": False},
                rationale=(f"forge: episode evidence n={gs.n} nuke_rate={gs.nuke_rate:.2f} "
                           f"mean_adv={gs.mean_advantage:+.2f}"))))
    return out


def propose_skill_ops(harness: HarnessState, episode_store, *, asof: Date,
                      promote_min_samples: int = 5, promote_min_winrate: float = 0.5,
                      retire_min_samples: int = 5, retire_min_nukerate: float = 0.5,
                      bucket_by: BucketBy | None = None) -> list[RefineOp]:
    """Deterministic per-skill episode-evidence proposer: promote strong incubating skills, soft-retire
    strong-negative active skills. PIT-masked via for_asof(asof). Pure (reads, never writes).

    `bucket_by` (P7): None (default) aggregates promotion evidence GLOBALLY per skill — byte-identical
    to v1. "phase"/"narrative" promotes on a skill's best qualifying phase/narrative bucket instead, so
    a skill that only works in one regime/narrative earns a promotion its diluted global average denies.
    Retire stays global regardless. Patch-on-promote is a forge_skills-level concern (see forge_skills)."""
    return [p.op for p in _propose(harness, episode_store, asof=asof, bucket_by=bucket_by,
                                   promote_min_samples=promote_min_samples, promote_min_winrate=promote_min_winrate,
                                   retire_min_samples=retire_min_samples, retire_min_nukerate=retire_min_nukerate)]


_FORGE_ALLOWED = frozenset({"promote_skill", "retire_skill"})


class ForgeReport(BaseModel):
    applied: list[str] = Field(default_factory=list)
    held: list[str] = Field(default_factory=list)
    rejected: list[tuple[str, str]] = Field(default_factory=list)   # (skill_id, reason)


def forge_skills(harness: HarnessState, episode_store, meta, *, asof: Date, conflict_queue=None,
                 min_promote_samples: int = 3, min_retire_samples: int = 5,
                 bucket_by: BucketBy | None = None, patch_on_promote: bool = False,
                 **proposer_kwargs) -> ForgeReport:
    """Apply the proposed promote/retire ops through the one gate: the episode evidence proposes, the gate
    independently confirms on the skill's own stats; a teaching-owned contest is HELD (§5).

    P7 (default-off): `bucket_by` scopes promotion evidence to a phase/narrative bucket; `patch_on_promote`
    (with bucket_by="phase") lands a surgical phase-narrowing `patch_skill` AFTER a promote lands — a
    rejected promote never patches. The widened `allowed` set includes patch_skill only when
    patch_on_promote is on (the module constant _FORGE_ALLOWED is unchanged, so task_forge is unaffected)."""
    report = ForgeReport()
    allowed = _FORGE_ALLOWED | ({"patch_skill"} if patch_on_promote else frozenset())

    def _apply(op: RefineOp) -> tuple[object, str | None]:
        return try_apply_op(meta, harness, op, allowed=allowed,
                            min_promote_samples=min_promote_samples, min_retire_samples=min_retire_samples,
                            provenance=EditProvenance(path="self_study", proposer="forge"),
                            conflict_queue=conflict_queue)

    for p in _propose(harness, episode_store, asof=asof, bucket_by=bucket_by,
                      patch_on_promote=patch_on_promote, **proposer_kwargs):
        sid = p.op.args["skill_id"]
        rec, reason = _apply(p.op)
        if rec is None:
            if reason and reason.startswith("held_for_review"):
                report.held.append(sid)
            else:
                report.rejected.append((sid, reason or ""))
            continue
        report.applied.append(sid)
        if p.patch is not None:                               # patch-on-promote: only after promote landed
            prec, preason = _apply(p.patch)
            if prec is not None:
                report.applied.append(sid)
            elif preason and preason.startswith("held_for_review"):
                report.held.append(sid)
            else:
                report.rejected.append((sid, preason or ""))
    return report
