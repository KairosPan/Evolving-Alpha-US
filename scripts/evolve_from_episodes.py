"""Forge evolution from episode evidence — charter-conformant since 2026-07-09.

Default mode "propose": forge_skills runs on a FORK of the live brain; the surviving delta ships
as an EvolutionProposal packet (-> $ALPHA_PROPOSALS_DIR) for the USER to adopt or discard in the
Sonia cockpit (/proposals). The live brain is byte-untouched; episode evidence is only READ.
Held conflicts still land in the ConflictQueue deliberately (user-adjudication signals about
live teaching-owned elements; resolution records intent only).

Mode "autonomous" (requires --autonomous AND ALPHA_UNSAFE_AUTONOMOUS=1) is the recorded
pre-pivot non-conformance escape hatch: lock -> load -> forge -> save on the live brain.

  python scripts/evolve_from_episodes.py [--asof YYYY-MM-DD]

Env vars (override defaults):
  ALPHA_LIVE_BRAIN_DIR   — path to the live brain directory (default ./state/brain)
  ALPHA_CONFLICTS_DIR    — path to the conflicts directory (default ./state/conflicts)
  ALPHA_EPISODES_DB      — path to the episodes SQLite DB (default ./state/brain.db)
  ALPHA_PROPOSALS_DIR    — path to the proposals directory (default ./state/proposals)
"""
from __future__ import annotations
import argparse, os
from datetime import date as Date

from alpha.harness.metatools import MetaTools
from alpha.memory.store import EpisodeStore
from alpha.meta.conflict_store import ConflictQueue
from alpha.meta.evolution import run_forked_evolution
from alpha.meta.proposal_store import ProposalQueue, proposals_dir
from alpha.meta.store import LiveBrainStore
from alpha.refine.forge import forge_skills
from alpha.settings import Settings, EVOLUTION_EPISODES_DB_DEFAULT

_UNSAFE_ENV = "ALPHA_UNSAFE_AUTONOMOUS"


def run_evolve_from_episodes(*, brain_dir: str, conflicts_dir: str, episodes_db: str,
                             asof: Date, mode: str = "propose",
                             proposals_root: "str | None" = None, **kwargs) -> dict:
    """One forge pass over episode evidence. mode="propose" (default, conformant): fork + packet.
    mode="autonomous": pre-pivot in-place forge, gated by $ALPHA_UNSAFE_AUTONOMOUS.
    Returns {"mode", "applied", "held", "rejected", ...} (applied = fork-applied in propose mode)."""
    bstore = LiveBrainStore(brain_dir)
    cq = ConflictQueue(conflicts_dir)

    if mode == "autonomous":
        if os.environ.get(_UNSAFE_ENV) != "1":
            raise RuntimeError(
                f"mode='autonomous' is the recorded pre-pivot non-conformance escape hatch "
                f"(forge edits land on the live brain with no human approver); set {_UNSAFE_ENV}=1 "
                f"to run it anyway")
        with bstore.lock():
            h, log = bstore.load()
            report = forge_skills(h, EpisodeStore.open(episodes_db), MetaTools(h, log),
                                  asof=asof, conflict_queue=cq, **kwargs)
            bstore.save(h, log)
        return {"mode": "autonomous", "applied": report.applied, "held": report.held,
                "rejected": report.rejected}

    box: dict = {}

    def runner(h, log):
        box["report"] = forge_skills(h, EpisodeStore.open(episodes_db), MetaTools(h, log),
                                     asof=asof, conflict_queue=cq, **kwargs)
        return h, log                       # forge mutates in place; no manager rebind involved

    root = proposals_root if proposals_root is not None else proposals_dir()
    prop = run_forked_evolution(bstore, runner, queue=ProposalQueue(root), kind="forge",
                                window={"asof": asof.isoformat()})
    report = box["report"]
    return {"mode": "propose", "proposal_id": prop.proposal_id if prop is not None else None,
            "n_delta": len(prop.records) if prop is not None else 0,
            "applied": report.applied, "held": report.held, "rejected": report.rejected,
            "proposals_dir": root}


def main() -> None:
    ap = argparse.ArgumentParser(
        description="Forge from episode evidence: propose an evolution packet (default) or, "
                    "unsafely, evolve the live brain in place.")
    ap.add_argument("--asof", type=Date.fromisoformat, default=Date.today(),
                    help="PIT date for episode evidence (default: today)")
    ap.add_argument("--autonomous", action="store_true",
                    help=f"pre-pivot in-place forge (requires {_UNSAFE_ENV}=1)")
    args = ap.parse_args()
    s = Settings.from_env()
    out = run_evolve_from_episodes(
        brain_dir=s.live_brain_dir,
        conflicts_dir=s.conflicts_dir,
        episodes_db=s.episodes_db or EVOLUTION_EPISODES_DB_DEFAULT,
        asof=args.asof,
        mode="autonomous" if args.autonomous else "propose",
    )
    if out["mode"] == "autonomous":
        print(f"{len(out['applied'])} promoted/retired (UNSAFE autonomous mode) · "
              f"{len(out['held'])} held · {len(out['rejected'])} rejected")
    elif out["proposal_id"] is not None:
        print(f"proposal {out['proposal_id']} staged: {out['n_delta']} surviving edit(s) "
              f"-> {out['proposals_dir']} — adopt or discard via the Sonia cockpit /proposals")
    else:
        print(f"no surviving edits — nothing proposed "
              f"({len(out['held'])} held · {len(out['rejected'])} rejected)")


if __name__ == "__main__":
    main()
