# alpha/refine/forge.py
from __future__ import annotations
from datetime import date as Date
from alpha.harness.state import HarnessState
from alpha.memory.aggregate import summarize
from alpha.refine.ops import RefineOp

def propose_skill_ops(harness: HarnessState, episode_store, *, asof: Date,
                      promote_min_samples: int = 5, promote_min_winrate: float = 0.5,
                      retire_min_samples: int = 5, retire_min_nukerate: float = 0.5) -> list[RefineOp]:
    """Deterministic per-skill episode-evidence proposer: promote strong incubating skills, soft-retire
    strong-negative active skills. PIT-masked via for_asof(asof). Pure (reads, never writes)."""
    stats = summarize(episode_store.for_asof(asof), key=lambda e: e.skill_id)
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
