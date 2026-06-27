"""Evolve the live brain from episode evidence (the forge runner): lock -> load -> forge -> save.
LLM-free — deterministic episode-evidence proposer (promote/retire) through the gate + conflict queue.

  python scripts/evolve_from_episodes.py [--asof YYYY-MM-DD]

Env vars (override defaults):
  ALPHA_LIVE_BRAIN_DIR   — path to the live brain directory (default ./state/brain)
  ALPHA_CONFLICTS_DIR    — path to the conflicts directory (default ./state/conflicts)
  ALPHA_EPISODES_DB      — path to the episodes SQLite DB (default ./state/brain.db)
"""
from __future__ import annotations
import argparse, os
from datetime import date as Date

from alpha.harness.metatools import MetaTools
from alpha.memory.store import EpisodeStore
from alpha.meta.conflict_store import ConflictQueue
from alpha.meta.store import LiveBrainStore
from alpha.refine.forge import forge_skills


def run_evolve_from_episodes(*, brain_dir: str, conflicts_dir: str, episodes_db: str,
                              asof: Date, **kwargs) -> dict:
    """Evolve the live brain via forge_skills (episode evidence) inside the brain file lock.
    Returns {"applied": [...], "held": [...], "rejected": [...]}."""
    bstore = LiveBrainStore(brain_dir)
    with bstore.lock():
        h, log = bstore.load()
        report = forge_skills(h, EpisodeStore.open(episodes_db), MetaTools(h, log),
                              asof=asof, conflict_queue=ConflictQueue(conflicts_dir), **kwargs)
        bstore.save(h, log)
    return {"applied": report.applied, "held": report.held, "rejected": report.rejected}


def main() -> None:
    ap = argparse.ArgumentParser(description="Evolve the live brain from episode evidence; feed the conflict queue.")
    ap.add_argument("--asof", type=Date.fromisoformat, default=Date.today(),
                    help="PIT date for episode evidence (default: today)")
    args = ap.parse_args()
    out = run_evolve_from_episodes(
        brain_dir=os.environ.get("ALPHA_LIVE_BRAIN_DIR", "./state/brain"),
        conflicts_dir=os.environ.get("ALPHA_CONFLICTS_DIR", "./state/conflicts"),
        episodes_db=os.environ.get("ALPHA_EPISODES_DB", "./state/brain.db"),
        asof=args.asof,
    )
    print(f"{len(out['applied'])} promoted/retired · {len(out['held'])} held · {len(out['rejected'])} rejected")


if __name__ == "__main__":
    main()
