"""Self-learning channel — reflect on the agent's OWN task runs, propose directions (A3).

Default mode "propose" (charter-conformant): reflect_task_skills runs on a FORK of the live brain
over kind="task" episode evidence; the surviving delta ships as an EvolutionProposal (kind="reflect",
-> $ALPHA_PROPOSALS_DIR) for the USER to adopt or discard in the Sonia cockpit (/proposals). The
live brain is byte-untouched; episodes are only READ. A direction the user previously DISCARDED is
suppressed via the negative-constraint store — never re-proposed. Held conflicts land in the
ConflictQueue (user-adjudication signals about live teaching-owned elements).

Mode "autonomous" (requires --autonomous AND ALPHA_UNSAFE_AUTONOMOUS=1) is the recorded pre-pivot
non-conformance escape hatch, mirroring the sibling self-study scripts.

  python scripts/reflect_from_tasks.py [--asof YYYY-MM-DD]

Env vars (override defaults):
  ALPHA_LIVE_BRAIN_DIR      — live brain directory (default ./state/brain)
  ALPHA_CONFLICTS_DIR       — conflicts directory (default ./state/conflicts)
  ALPHA_EPISODES_DB         — episodes SQLite DB (default ./state/brain.db)
  ALPHA_PROPOSALS_DIR       — proposals directory (default ./state/proposals)
  ALPHA_NEG_CONSTRAINTS_DIR — rejected-direction constraints (default ./state/neg_constraints)
"""
from __future__ import annotations

import argparse
import os
from datetime import date as Date

from alpha.harness.metatools import MetaTools
from alpha.memory.store import EpisodeStore
from alpha.meta.body_git import make_brain_store
from alpha.meta.conflict_store import ConflictQueue
from alpha.meta.evolution import run_forked_evolution
from alpha.meta.negative_constraint import NegativeConstraintStore
from alpha.meta.proposal_store import ProposalQueue, proposals_dir
from alpha.refine.apply import _derive_confirmed_task_ids
from alpha.refine.reflect import reflect_over_tasks, reflect_task_skills, reflections_summary
from alpha.settings import EVOLUTION_EPISODES_DB_DEFAULT, Settings

_UNSAFE_ENV = "ALPHA_UNSAFE_AUTONOMOUS"


def run_reflect_from_tasks(*, brain_dir: str, conflicts_dir: str, episodes_db: str,
                           neg_constraints_dir: str, asof: Date, mode: str = "propose",
                           proposals_root: "str | None" = None) -> dict:
    """One reflection→directions pass over task-episode evidence. mode="propose" (default,
    conformant): fork + EvolutionProposal packet. mode="autonomous": pre-pivot in-place, gated."""
    bstore = make_brain_store(brain_dir, git=Settings.from_env().body_git)
    cq = ConflictQueue(conflicts_dir)
    neg = NegativeConstraintStore(neg_constraints_dir)
    neg_signatures = neg.signatures()

    if mode == "autonomous":
        if os.environ.get(_UNSAFE_ENV) != "1":
            raise RuntimeError(
                f"mode='autonomous' is the recorded pre-pivot non-conformance escape hatch "
                f"(reflect directions land on the live brain with no human approver); set "
                f"{_UNSAFE_ENV}=1 to run it anyway")
        with bstore.lock():
            h, log = bstore.load()
            confirmed = _derive_confirmed_task_ids(log)
            report = reflect_task_skills(h, EpisodeStore.open(episodes_db), MetaTools(h, log),
                                         asof=asof, confirmed_ids=confirmed,
                                         negative_signatures=neg_signatures, conflict_queue=cq,
                                         task_recall=EpisodeStore.open(episodes_db))
            bstore.save(h, log)
        return {"mode": "autonomous", "applied": report.applied, "held": report.held,
                "rejected": report.rejected, "suppressed": report.suppressed}

    # propose (default): reflect on a fork; ship the surviving delta as a packet.
    live_h, live_log = bstore.load()
    confirmed = _derive_confirmed_task_ids(live_log)
    pre = reflect_over_tasks(EpisodeStore.open(episodes_db), live_h, asof=asof,
                             confirmed_ids=confirmed)     # read-only view for the proposal window

    box: dict = {}

    def runner(h, log):
        box["report"] = reflect_task_skills(
            h, EpisodeStore.open(episodes_db), MetaTools(h, log), asof=asof,
            confirmed_ids=_derive_confirmed_task_ids(log), negative_signatures=neg_signatures,
            conflict_queue=cq, task_recall=EpisodeStore.open(episodes_db))
        return h, log

    root = proposals_root if proposals_root is not None else proposals_dir()
    prop = run_forked_evolution(bstore, runner, queue=ProposalQueue(root), kind="reflect",
                                window={"asof": asof.isoformat(),
                                        "reflections": reflections_summary(pre)})
    report = box["report"]
    return {"mode": "propose", "proposal_id": prop.proposal_id if prop is not None else None,
            "n_delta": len(prop.records) if prop is not None else 0,
            "applied": report.applied, "held": report.held, "rejected": report.rejected,
            "suppressed": report.suppressed, "proposals_dir": root}


def main() -> None:
    ap = argparse.ArgumentParser(
        description="Reflect on the agent's own task runs: propose evolution directions (default) "
                    "or, unsafely, evolve the live brain in place.")
    ap.add_argument("--asof", type=Date.fromisoformat, default=Date.today(),
                    help="PIT date for task-episode evidence (default: today)")
    ap.add_argument("--autonomous", action="store_true",
                    help=f"pre-pivot in-place reflect (requires {_UNSAFE_ENV}=1)")
    args = ap.parse_args()
    s = Settings.from_env()
    out = run_reflect_from_tasks(
        brain_dir=s.live_brain_dir,
        conflicts_dir=s.conflicts_dir,
        episodes_db=s.episodes_db or EVOLUTION_EPISODES_DB_DEFAULT,
        neg_constraints_dir=s.neg_constraints_dir,
        asof=args.asof,
        mode="autonomous" if args.autonomous else "propose",
    )
    if out["mode"] == "autonomous":
        print(f"{len(out['applied'])} promoted/retired (UNSAFE autonomous mode) · "
              f"{len(out['held'])} held · {len(out['suppressed'])} suppressed · "
              f"{len(out['rejected'])} rejected")
    elif out["proposal_id"] is not None:
        print(f"reflect proposal {out['proposal_id']} staged: {out['n_delta']} direction(s) "
              f"-> {out['proposals_dir']} — adopt or discard via the Sonia cockpit /proposals")
    else:
        print(f"no surviving directions — nothing proposed ({len(out['held'])} held · "
              f"{len(out['suppressed'])} suppressed · {len(out['rejected'])} rejected)")


if __name__ == "__main__":
    main()
