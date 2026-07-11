"""Self-study evolution over a captured PIT window — charter-conformant since 2026-07-09.

Default mode "propose": the InnerLoop runs with FULL autonomy on a FORK of the live brain (trial
semantics: gate, breaker, in-fork rollbacks all fork-internal), the live brain and the live
episode DB are byte-untouched, and the surviving edit delta ships as an EvolutionProposal packet
(-> $ALPHA_PROPOSALS_DIR) for the USER to adopt or discard in the Sonia cockpit (/proposals).
Held self-study-vs-teaching conflicts still land in the ConflictQueue DELIBERATELY — they contest
LIVE teaching-owned elements (computed against live state at fork time) and are pure
user-adjudication signals; resolution records intent only, never auto-applies.

Mode "autonomous" (requires --autonomous AND ALPHA_UNSAFE_AUTONOMOUS=1) is the recorded
pre-pivot non-conformance escape hatch: edits land on the live brain with no human approver and
the breaker may machine-revert the live brain mid-run. Experiments only.

  python scripts/capture_window.py 2026-01-02 2026-03-31 snap AAPL MSFT NVDA TSLA AMD
  export DEEPSEEK_API_KEY=...                       # agent + refiner default to deepseek-v4-pro
  ALPHA_LIVE_BRAIN_DIR=./state/brain ALPHA_CONFLICTS_DIR=./state/conflicts \
    python scripts/refine_live.py snap 2026-01-02 2026-03-31
"""
from __future__ import annotations
import argparse, os, tempfile
from datetime import date as Date
from pathlib import Path

from alpha.data.pit_store import PITStore
from alpha.data.snapshot_source import SnapshotSource
from alpha.harness.manager import HarnessManager
from alpha.harness.snapshot import SnapshotStore
from alpha.llm.config import make_client
from alpha.loop.inner_loop import InnerLoop, LoopConfig
from alpha.memory.store import EpisodeStore
from alpha.meta.evolution import run_forked_evolution
from alpha.meta.proposal_store import ProposalQueue, proposals_dir
from alpha.meta.store import LiveBrainStore
from alpha.meta.conflict_store import ConflictQueue
from alpha.settings import Settings, EVOLUTION_EPISODES_DB_DEFAULT

_UNSAFE_ENV = "ALPHA_UNSAFE_AUTONOMOUS"


def run_refine_live(source, start: Date, end: Date, *, brain_dir: str, conflicts_dir: str,
                    agent_llm_factory=None, refiner_llm_factory=None, horizon: int = 2,
                    agent_factory=None, loop_config: "LoopConfig | None" = None,
                    episodes_db: "str | None" = None, mode: str = "propose",
                    proposals_root: "str | None" = None) -> dict:
    """One self-study pass over [start, end]. mode="propose" (default, conformant): fork + packet,
    no live writes. mode="autonomous": pre-pivot in-place evolution, gated by $ALPHA_UNSAFE_AUTONOMOUS.
    Tests inject MockLLM factories + tmp dirs; the live path uses per-role make_client (temp=0)."""
    agent_llm_factory = agent_llm_factory or (lambda: make_client("agent"))
    refiner_llm_factory = refiner_llm_factory or (lambda: make_client("refiner"))
    cfg = loop_config if loop_config is not None else LoopConfig(horizon=horizon)
    bstore = LiveBrainStore(brain_dir)
    cq = ConflictQueue(conflicts_dir)
    held_before = len(cq.all())

    def _loop(h, log, *, episode_store, recall_store):
        mgr = HarnessManager(h, SnapshotStore(tempfile.mkdtemp()), log=log)
        loop = InnerLoop(mgr, source, start, end, agent_llm_factory(), refiner_llm_factory(),
                         config=cfg, conflict_queue=cq, episode_store=episode_store,
                         recall_store=recall_store, agent_factory=agent_factory)
        report = loop.run()
        return mgr, report

    if mode == "autonomous":
        if os.environ.get(_UNSAFE_ENV) != "1":
            raise RuntimeError(
                f"mode='autonomous' is the recorded pre-pivot non-conformance escape hatch "
                f"(agent edits land on the live brain with no human approver); set {_UNSAFE_ENV}=1 "
                f"to run it anyway")
        episode_store = EpisodeStore.open(episodes_db) if episodes_db else None
        with bstore.lock():                               # serialize vs Sonia/workbench
            h, log = bstore.load()
            mgr, report = _loop(h, log, episode_store=episode_store, recall_store=episode_store)
            bstore.save(mgr.harness, mgr.log)             # persist the evolved brain (UNSAFE path)
        return {"mode": "autonomous", "n_edits": report.n_edits,
                "held": len(cq.all()) - held_before, "refines": len(report.refine_events),
                "brain_dir": brain_dir, "conflicts_dir": conflicts_dir}

    # propose (default): the fork writes NO live episodes — a discarded fork must die with its
    # session; recall/taboo still READ the live DB (the compare_harnesses read-handle pattern).
    recall = EpisodeStore.open(episodes_db) if episodes_db else None
    box: dict = {}

    def runner(h, log):
        mgr, box["report"] = _loop(h, log, episode_store=None, recall_store=recall)
        return mgr.harness, mgr.log       # FINAL handles — in-fork breaker rollbacks rebind them

    root = proposals_root if proposals_root is not None else proposals_dir()
    prop = run_forked_evolution(bstore, runner, queue=ProposalQueue(root), kind="refine",
                                window={"start": start.isoformat(), "end": end.isoformat()})
    report = box.get("report")
    return {"mode": "propose", "proposal_id": prop.proposal_id if prop is not None else None,
            "n_delta": len(prop.records) if prop is not None else 0,
            "held": len(cq.all()) - held_before,
            "refines": len(report.refine_events) if report is not None else 0,
            "brain_dir": brain_dir, "conflicts_dir": conflicts_dir, "proposals_dir": root}


def main() -> None:
    ap = argparse.ArgumentParser(
        description="Self-study over a PIT window: propose an evolution packet (default) or, "
                    "unsafely, evolve the live brain in place.")
    ap.add_argument("pit_root", help="PIT store root built by scripts/capture_window.py")
    ap.add_argument("start", type=Date.fromisoformat)
    ap.add_argument("end", type=Date.fromisoformat)
    ap.add_argument("--horizon", type=int, default=2)
    ap.add_argument("--autonomous", action="store_true",
                    help=f"pre-pivot in-place evolution (requires {_UNSAFE_ENV}=1)")
    args = ap.parse_args()
    s = Settings.from_env()
    source = SnapshotSource(PITStore(Path(args.pit_root)))
    out = run_refine_live(source, args.start, args.end,
                          brain_dir=s.live_brain_dir,
                          conflicts_dir=s.conflicts_dir,
                          horizon=args.horizon,
                          episodes_db=s.episodes_db or EVOLUTION_EPISODES_DB_DEFAULT,
                          mode="autonomous" if args.autonomous else "propose")
    if out["mode"] == "autonomous":
        print(f"{out['n_edits']} self-study edits applied (UNSAFE autonomous mode) · "
              f"{out['held']} conflicts held ({out['refines']} refines) -> {out['conflicts_dir']}")
    elif out["proposal_id"] is not None:
        print(f"proposal {out['proposal_id']} staged: {out['n_delta']} surviving edit(s) "
              f"({out['refines']} refines, {out['held']} conflicts held) -> {out['proposals_dir']} "
              f"— adopt or discard via the Sonia cockpit /proposals")
    else:
        print(f"no surviving edits — nothing proposed "
              f"({out['refines']} refines ran, {out['held']} conflicts held)")


if __name__ == "__main__":
    main()
