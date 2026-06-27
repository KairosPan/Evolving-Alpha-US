# alpha/refine/forge.py
from __future__ import annotations
from datetime import date as Date
from pydantic import BaseModel, Field
from alpha.harness.edit_log import EditProvenance
from alpha.harness.state import HarnessState
from alpha.memory.aggregate import summarize
from alpha.refine.apply import try_apply_op
from alpha.refine.ops import RefineOp

def propose_skill_ops(harness: HarnessState, episode_store, *, asof: Date,
                      promote_min_samples: int = 5, promote_min_winrate: float = 0.5,
                      retire_min_samples: int = 5, retire_min_nukerate: float = 0.5) -> list[RefineOp]:
    """Deterministic per-skill episode-evidence proposer: promote strong incubating skills, soft-retire
    strong-negative active skills. PIT-masked via for_asof(asof). Pure (reads, never writes)."""
    # for_asof's default limit (50) is a GLOBAL cap across all skills — too small for this offline
    # maintenance pass, which must see a skill's full PIT-masked history (it keys promote/retire off n).
    # limit=None = the no-cap convention shared with the recall/taboo aggregation read sites.
    stats = summarize(episode_store.for_asof(asof, limit=None), key=lambda e: e.skill_id)
    ops: list[RefineOp] = []
    for skill_id, s in stats.items():
        sk = harness.skills.get(skill_id)
        if sk is None:
            continue
        if (sk.status == "incubating" and s.n >= promote_min_samples
                and s.win_rate >= promote_min_winrate and s.mean_advantage > 0):
            ops.append(RefineOp(tool="promote_skill", args={"skill_id": skill_id},
                                rationale=(f"forge: episode evidence n={s.n} win_rate={s.win_rate:.2f} "
                                           f"mean_adv={s.mean_advantage:+.2f}")))
        elif (sk.status == "active" and s.n >= retire_min_samples and s.nuke_rate >= retire_min_nukerate):
            ops.append(RefineOp(tool="retire_skill", args={"skill_id": skill_id, "permanent": False},
                                rationale=(f"forge: episode evidence n={s.n} nuke_rate={s.nuke_rate:.2f} "
                                           f"mean_adv={s.mean_advantage:+.2f}")))
    return ops


_FORGE_ALLOWED = frozenset({"promote_skill", "retire_skill"})


class ForgeReport(BaseModel):
    applied: list[str] = Field(default_factory=list)
    held: list[str] = Field(default_factory=list)
    rejected: list[tuple[str, str]] = Field(default_factory=list)   # (skill_id, reason)


def forge_skills(harness: HarnessState, episode_store, meta, *, asof: Date, conflict_queue=None,
                 min_promote_samples: int = 3, min_retire_samples: int = 5,
                 **proposer_kwargs) -> ForgeReport:
    """Apply the proposed promote/retire ops through the one gate: the episode evidence proposes, the gate
    independently confirms on the skill's own stats; a teaching-owned contest is HELD (§5)."""
    report = ForgeReport()
    for op in propose_skill_ops(harness, episode_store, asof=asof, **proposer_kwargs):
        sid = op.args["skill_id"]
        rec, reason = try_apply_op(meta, harness, op, allowed=_FORGE_ALLOWED,
                                   min_promote_samples=min_promote_samples,
                                   min_retire_samples=min_retire_samples,
                                   provenance=EditProvenance(path="self_study", proposer="forge"),
                                   conflict_queue=conflict_queue)
        if rec is not None:
            report.applied.append(sid)
        elif reason and reason.startswith("held_for_review"):
            report.held.append(sid)
        else:
            report.rejected.append((sid, reason or ""))
    return report
