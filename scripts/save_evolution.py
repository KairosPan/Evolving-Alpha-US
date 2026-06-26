"""Run the self-evolving InnerLoop over a captured PIT window and dump the edit trajectory — how the
Refiner changed H (doctrine / skills / memory) — as JSON the console's Evolution page renders.

  python scripts/capture_window.py 2026-01-02 2026-03-31 snap AAPL MSFT NVDA TSLA AMD
  export DEEPSEEK_API_KEY=...   # agent + refiner both default to openai_compat/deepseek-v4-pro
  python scripts/save_evolution.py snap 2026-01-02 2026-03-31 evolution.json
  ALPHA_WEB_EVOLUTION=evolution.json python -m alpha_web
"""
from __future__ import annotations

import argparse
import json
import tempfile
from datetime import date as Date
from pathlib import Path

from alpha.data.pit_store import PITStore
from alpha.data.snapshot_source import SnapshotSource
from alpha.harness.loader import load_seeds
from alpha.harness.manager import HarnessManager
from alpha.harness.snapshot import SnapshotStore
from alpha.llm.config import make_client
from alpha.loop.inner_loop import InnerLoop, LoopConfig

SEEDS_DIR = Path(__file__).resolve().parents[1] / "seeds"


def evolution_view(edit_dicts: list[dict], report, start: Date, end: Date) -> dict:
    """Assemble the Evolution view dict: the run window, a summary of the inner loop, and the
    append-only edit records (EditRecord.model_dump()) in sequence."""
    return {
        "window": {"start": start.isoformat(), "end": end.isoformat()},
        "summary": {
            "refines": len(report.refine_events),
            "breaker_trips": len(report.breaker_events),
            "frozen_from": report.frozen_from.isoformat() if report.frozen_from is not None else None,
            "n_edits": report.n_edits,
        },
        "edits": edit_dicts,
    }


def run_evolution(source, start: Date, end: Date, *, seeds_dir: Path = SEEDS_DIR,
                  agent_llm_factory=None, refiner_llm_factory=None, horizon: int = 2) -> dict:
    """Run the InnerLoop (agent + Refiner) over [start, end] and return the Evolution view dict.
    Tests inject MockLLM factories; the live path uses per-role make_client (temp=0)."""
    agent_llm_factory = agent_llm_factory or (lambda: make_client("agent"))
    refiner_llm_factory = refiner_llm_factory or (lambda: make_client("refiner"))
    mgr = HarnessManager(load_seeds(seeds_dir), SnapshotStore(tempfile.mkdtemp()))
    loop = InnerLoop(mgr, source, start, end, agent_llm_factory(), refiner_llm_factory(),
                     config=LoopConfig(horizon=horizon))
    report = loop.run()
    return evolution_view(mgr.log.to_dict(), report, start, end)


def main() -> None:
    ap = argparse.ArgumentParser(description="Dump the inner-loop edit trajectory for the console.")
    ap.add_argument("pit_root", help="PIT store root built by scripts/capture_window.py")
    ap.add_argument("start", type=Date.fromisoformat)
    ap.add_argument("end", type=Date.fromisoformat)
    ap.add_argument("out", help="output JSON path (point ALPHA_WEB_EVOLUTION here)")
    ap.add_argument("--horizon", type=int, default=2)
    args = ap.parse_args()

    source = SnapshotSource(PITStore(Path(args.pit_root)))
    evo = run_evolution(source, args.start, args.end, horizon=args.horizon)
    Path(args.out).write_text(json.dumps(evo, indent=2, default=str), encoding="utf-8")
    print(f"wrote {evo['summary']['n_edits']} edits ({evo['summary']['refines']} refines) -> {args.out}")


if __name__ == "__main__":
    main()
