"""Run the self-evolving InnerLoop over a captured PIT window against the LIVE brain, with a ConflictQueue:
non-conflicting self-study edits evolve the live brain (gate+breaker); edits contesting a teaching-owned
element are HELD to the queue (the Conflicts page). The 3rd live-brain writer — holds the brain file lock.

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
from alpha.meta.store import LiveBrainStore
from alpha.meta.conflict_store import ConflictQueue


def run_refine_live(source, start: Date, end: Date, *, brain_dir: str, conflicts_dir: str,
                    agent_llm_factory=None, refiner_llm_factory=None, horizon: int = 2,
                    agent_factory=None, loop_config: "LoopConfig | None" = None) -> dict:
    """Evolve the live brain via one InnerLoop pass over [start, end]; held conflicts -> ConflictQueue.
    Tests inject MockLLM factories + tmp dirs; the live path uses per-role make_client (temp=0).
    agent_factory: optional callable (HarnessState -> DecisionPolicy) for offline/test injection.
    loop_config: optional LoopConfig override (tests may set screen=False; production uses LoopConfig(horizon))."""
    agent_llm_factory = agent_llm_factory or (lambda: make_client("agent"))
    refiner_llm_factory = refiner_llm_factory or (lambda: make_client("refiner"))
    cfg = loop_config if loop_config is not None else LoopConfig(horizon=horizon)
    bstore = LiveBrainStore(brain_dir)
    cq = ConflictQueue(conflicts_dir)
    held_before = len(cq.all())
    with bstore.lock():                                   # 3rd writer — serialize vs Sonia/workbench
        h, log = bstore.load()                            # the LIVE brain (teaching-owned elements present)
        mgr = HarnessManager(h, SnapshotStore(tempfile.mkdtemp()), log=log)   # in-run breaker checkpoints
        loop = InnerLoop(mgr, source, start, end, agent_llm_factory(), refiner_llm_factory(),
                         config=cfg, conflict_queue=cq,
                         agent_factory=agent_factory)
        report = loop.run()
        bstore.save(mgr.harness, mgr.log)                 # persist the evolved brain
    held = len(cq.all()) - held_before
    return {"n_edits": report.n_edits, "held": held,
            "refines": len(report.refine_events), "brain_dir": brain_dir, "conflicts_dir": conflicts_dir}


def main() -> None:
    ap = argparse.ArgumentParser(description="Evolve the live brain over a PIT window; feed the conflict queue.")
    ap.add_argument("pit_root", help="PIT store root built by scripts/capture_window.py")
    ap.add_argument("start", type=Date.fromisoformat)
    ap.add_argument("end", type=Date.fromisoformat)
    ap.add_argument("--horizon", type=int, default=2)
    args = ap.parse_args()
    source = SnapshotSource(PITStore(Path(args.pit_root)))
    out = run_refine_live(source, args.start, args.end,
                          brain_dir=os.environ.get("ALPHA_LIVE_BRAIN_DIR", "./state/brain"),
                          conflicts_dir=os.environ.get("ALPHA_CONFLICTS_DIR", "./state/conflicts"),
                          horizon=args.horizon)
    print(f"{out['n_edits']} self-study edits applied · {out['held']} conflicts held "
          f"({out['refines']} refines) -> {out['conflicts_dir']}")


if __name__ == "__main__":
    main()
