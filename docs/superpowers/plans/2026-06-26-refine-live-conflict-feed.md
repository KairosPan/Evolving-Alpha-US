# Refine-Live — Feed the §5 Conflict Queue (Persist Mode) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** An offline self-study run over the LIVE brain so real §5 conflicts populate the `ConflictQueue` (and the Conflicts UI): non-conflicting self-study (Refiner) edits evolve the live brain through the gate+breaker; edits contesting a teaching-owned element are held to the queue.

**Architecture:** Two additive changes — (1) thread `conflict_queue` through `InnerLoop.__init__` → `Refiner` in `_rebind` (mirrors the existing `episode_store` plumbing); (2) `scripts/refine_live.py` with `run_refine_live()` that loads the live brain under `LiveBrainStore.lock()`, runs the InnerLoop over a captured PIT window with a `ConflictQueue(ALPHA_CONFLICTS_DIR)`, and saves the evolved brain. Mirrors `scripts/save_evolution.py` + the workbench lock discipline.

**Tech Stack:** Python ≥3.11, pytest. Reuses `alpha/loop/inner_loop.py::InnerLoop`, `alpha/refine/refiner.py::Refiner` (already accepts `conflict_queue`), `alpha/meta/store.py::LiveBrainStore` (`.lock()`, `.load()`, `.save()`, `.edit_count()`), `alpha/meta/conflict_store.py::ConflictQueue`, `alpha/harness/manager.py::HarnessManager`, `alpha/harness/snapshot.py::SnapshotStore`. Test mirror: `tests/loop/test_inner_loop_episodes.py` (the working MockLLM-driven memory-refine pattern).

## Global Constraints

- **Python `>=3.11`**, pytest. The existing suite (currently **644 passed**) must stay green — both changes are additive (`conflict_queue=None` default → today's behavior; `save_evolution.py` and every existing InnerLoop test unchanged).
- **Persist mode:** non-conflicting self-study edits apply through `try_apply_op` (the one gate) + the InnerLoop breaker, and are **saved** to the live brain; conflicting edits (self-study contesting a teaching-owned element) are **held** to the queue, never auto-applied.
- **Lock:** `run_refine_live` wraps its whole `load → run → save` in `LiveBrainStore.lock()` (the 3rd live-brain writer, after Sonia + workbench). A busy lock → `RuntimeError` (the existing primitive; fail loud).
- **Offline operator script:** LLM/source/window errors propagate (no never-500 softening). The CLI mirrors `save_evolution.py`: `refine_live.py <pit_root> <start> <end> [--horizon N]`; env `ALPHA_LIVE_BRAIN_DIR` (default `./state/brain`), `ALPHA_CONFLICTS_DIR` (default `./state/conflicts`). LLMs default to `make_client("agent")`/`make_client("refiner")`.
- English; mirror `scripts/save_evolution.py` + `tests/loop/test_inner_loop_episodes.py`.

## File Structure

- Modify: `alpha/loop/inner_loop.py` (`InnerLoop.__init__` +`conflict_queue=None`; `_rebind` passes it to `Refiner`).
- Create: `scripts/refine_live.py` (`run_refine_live(...)` core + `main()` CLI).
- Tests: `tests/loop/test_inner_loop_conflict_queue.py` (threading unit test), `tests/scripts/test_refine_live.py` (offline end-to-end).

---

### Task 1: Thread `conflict_queue` through `InnerLoop` → `Refiner`

**Files:**
- Modify: `alpha/loop/inner_loop.py`
- Test: `tests/loop/test_inner_loop_conflict_queue.py`

**Interfaces:**
- Consumes: `Refiner(harness, llm, meta, cfg, conflict_queue=…)` (already exists, §5).
- Produces: `InnerLoop(..., episode_store=None, conflict_queue=None)` — stores `self._conflict_queue`; `_rebind()` builds the Refiner with it. Consumed by Task 2.

- [ ] **Step 1: Write the failing test**

```python
# tests/loop/test_inner_loop_conflict_queue.py
from datetime import date
import pandas as pd
from alpha.harness.loader import load_seeds
from alpha.harness.manager import HarnessManager
from alpha.harness.snapshot import SnapshotStore
from alpha.data.source import FakeSource
from alpha.llm.client import MockLLMClient
from alpha.loop.inner_loop import InnerLoop
from pathlib import Path
import tempfile

SEEDS = Path(__file__).resolve().parents[2] / "seeds"

def _src():
    cal = [date(2026, 6, 10)]
    snaps = {cal[0]: pd.DataFrame({"symbol": ["RUN"], "name": ["RUN"], "open": [1.0], "high": [1.0],
                                   "low": [1.0], "close": [1.0], "volume": [1], "prev_close": [1.0]})}
    bars = {"RUN": pd.DataFrame({"date": cal, "open": [1.0], "high": [1.0], "low": [1.0], "close": [1.0], "volume": [1]})}
    return FakeSource(calendar=cal, bars=bars, snapshots=snaps)

def _loop(conflict_queue):
    mgr = HarnessManager(load_seeds(SEEDS), SnapshotStore(tempfile.mkdtemp()))
    return InnerLoop(mgr, _src(), date(2026, 6, 10), date(2026, 6, 10),
                     MockLLMClient("{}"), MockLLMClient("{}"), conflict_queue=conflict_queue)

def test_conflict_queue_reaches_the_refiner():
    sentinel = object()
    loop = _loop(sentinel)
    assert loop._refiner._conflict_queue is sentinel

def test_conflict_queue_defaults_none():
    loop = _loop(None)
    assert loop._refiner._conflict_queue is None
```

- [ ] **Step 2: Run to verify it fails**

Run: `python -m pytest tests/loop/test_inner_loop_conflict_queue.py -v`
Expected: FAIL — `InnerLoop.__init__() got an unexpected keyword argument 'conflict_queue'`.

- [ ] **Step 3: Implement** — `alpha/loop/inner_loop.py`:

In `__init__`, add the param after `episode_store=None`:
```python
                 episode_store=None, conflict_queue=None) -> None:
```
and store it (next to `self._episode_store = episode_store`):
```python
        self._conflict_queue = conflict_queue
```
In `_rebind()`, change the Refiner construction:
```python
        self._refiner = Refiner(h, self._refiner_llm, self._mgr.tools, self._refiner_cfg,
                                conflict_queue=self._conflict_queue)
```

- [ ] **Step 4: Run to verify it passes + full suite green**

Run: `python -m pytest tests/loop/test_inner_loop_conflict_queue.py -v && python -m pytest -q`
Expected: 2 PASS; full suite green (additive default `None`).

- [ ] **Step 5: Commit**

```bash
git add alpha/loop/inner_loop.py tests/loop/test_inner_loop_conflict_queue.py
git commit -m "feat(loop): thread conflict_queue through InnerLoop -> Refiner"
```

---

### Task 2: `scripts/refine_live.py` — run the InnerLoop over the live brain, feed the queue

**Files:**
- Create: `scripts/refine_live.py`
- Test: `tests/scripts/test_refine_live.py`

**Interfaces:**
- Consumes: `InnerLoop(..., conflict_queue=…)` (T1), `LiveBrainStore` (`.lock()/.load()/.save()/.edit_count()`), `ConflictQueue`, `HarnessManager`, `SnapshotStore`.
- Produces: `run_refine_live(source, start, end, *, brain_dir, conflicts_dir, agent_llm_factory=None, refiner_llm_factory=None, horizon=2) -> dict` (returns `{"n_edits", "held", "applied_seqs"}` or similar summary) + a `main()` CLI mirroring `save_evolution.py`.

- [ ] **Step 1: Read the mirrors** — read `scripts/save_evolution.py` (the `run_evolution`/`main` shape + the MockLLM-factory seam) and `tests/loop/test_inner_loop_episodes.py` (the WORKING agent+refiner `MockLLMClient` scripts + the window/horizon that actually triggers a memory refine, and how a `process_memory`/`demote_memory` op is emitted by the scripted refiner and parsed by `parse_ops`). The e2e test below reuses that exact agent+refiner script, only changing the seed (teaching-owned) + adding the `conflict_queue`.

- [ ] **Step 2: Write the failing test**

```python
# tests/scripts/test_refine_live.py
from datetime import date
from pathlib import Path
import importlib

from alpha.harness.doctrine import Doctrine
from alpha.harness.registry import SkillRegistry, MemoryStore
from alpha.harness.state import HarnessState
from alpha.harness.edit_log import EditLog, EditProvenance
from alpha.harness.memory import Lesson
from alpha.meta.store import LiveBrainStore
from alpha.meta.conflict_store import ConflictQueue
from alpha.llm.client import MockLLMClient
# reuse the working refine-driving fixtures from the episodes test
from tests.loop.test_inner_loop_episodes import (              # mirror: agent+refiner scripts + source
    <SOURCE_FACTORY>, <AGENT_SCRIPT>, <REFINER_SCRIPT_BUILDER>, <START>, <END>, <HORIZON>,
)   # implementer: import the actual names from that file (see Step 1)

def _seed_teaching_brain(brain_dir, lesson_id="m_teach"):
    """A live brain whose EditLog records a TEACHING-owned memory -> a self-study op contesting it is held."""
    h = HarnessState(doctrine=Doctrine(),
                     skills=SkillRegistry.from_skills([]),
                     memory=MemoryStore.from_lessons([Lesson.from_seed(
                         {"lesson_id": lesson_id, "phases": ["trend"], "outcome": "win", "lesson": "taught"})]))
    log = EditLog()
    log.append("process_memory", "memory", lesson_id, "create")
    log.stamp_last(EditProvenance(path="teaching", proposer="sonia"))
    LiveBrainStore(brain_dir).save(h, log)
    return lesson_id

def test_refine_live_feeds_conflicts_and_persists(tmp_path):
    brain_dir = tmp_path / "brain"; conflicts_dir = tmp_path / "conflicts"
    lid = _seed_teaching_brain(brain_dir)
    refine_live = importlib.import_module("scripts.refine_live")
    # a scripted refiner that proposes (a) demote_memory on the teaching-owned lesson -> HELD, and
    # (b) a non-conflicting process_memory for a NEW lesson -> applies. (Build via the episodes-test helper.)
    out = refine_live.run_refine_live(
        <SOURCE_FACTORY>(), <START>, <END>, brain_dir=str(brain_dir), conflicts_dir=str(conflicts_dir),
        agent_llm_factory=lambda: MockLLMClient(<AGENT_SCRIPT>),
        refiner_llm_factory=lambda: MockLLMClient(<REFINER_SCRIPT_BUILDER>(contest_lesson=lid)),
        horizon=<HORIZON>)
    held = ConflictQueue(str(conflicts_dir)).all()
    assert any(c.op.get("args", {}).get("lesson_id") == lid for c in held)    # the contesting op was held
    assert LiveBrainStore(str(brain_dir)).edit_count() > 1                    # a non-conflicting edit persisted
```

> **Implementer note:** the `<…>` placeholders are the actual fixtures from `tests/loop/test_inner_loop_episodes.py` — import or replicate that file's source factory, agent MockLLM script, and refiner MockLLM script (adapting the refiner script to emit a `demote_memory` op on `m_teach` PLUS one non-conflicting `process_memory` op). If those fixtures are not importable (local funcs), replicate the minimal window+scripts inline by reading that test. The point of the test is: after `run_refine_live`, the contesting op is in the `ConflictQueue` AND a non-conflicting self-study edit is in the SAVED live brain. Keep it fully offline (MockLLM + FakeSource + tmp dirs).

- [ ] **Step 3: Run to verify it fails**

Run: `python -m pytest tests/scripts/test_refine_live.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'scripts.refine_live'` (create `tests/scripts/__init__.py` if needed — check how `tests/` packages are set up).

- [ ] **Step 4: Implement** — `scripts/refine_live.py` (mirror `save_evolution.py`):

```python
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
                    agent_llm_factory=None, refiner_llm_factory=None, horizon: int = 2) -> dict:
    """Evolve the live brain via one InnerLoop pass over [start, end]; held conflicts -> ConflictQueue.
    Tests inject MockLLM factories + tmp dirs; the live path uses per-role make_client (temp=0)."""
    agent_llm_factory = agent_llm_factory or (lambda: make_client("agent"))
    refiner_llm_factory = refiner_llm_factory or (lambda: make_client("refiner"))
    bstore = LiveBrainStore(brain_dir)
    cq = ConflictQueue(conflicts_dir)
    held_before = len(cq.all())
    with bstore.lock():                                   # 3rd writer — serialize vs Sonia/workbench
        h, log = bstore.load()                            # the LIVE brain (teaching-owned elements present)
        mgr = HarnessManager(h, SnapshotStore(tempfile.mkdtemp()), log=log)   # in-run breaker checkpoints
        loop = InnerLoop(mgr, source, start, end, agent_llm_factory(), refiner_llm_factory(),
                         config=LoopConfig(horizon=horizon), conflict_queue=cq)
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
```

> **Implementer note:** confirm `report` (a `LoopReport`) exposes `n_edits` and `refine_events` — `scripts/save_evolution.py` already reads both, so they exist. If a field name differs, read `alpha/loop/inner_loop.py`'s `LoopReport` and adapt the summary dict (do NOT change `LoopReport`).

- [ ] **Step 5: Run to verify it passes + full suite green**

Run: `python -m pytest tests/scripts/test_refine_live.py -v && python -m pytest -q`
Expected: PASS; full suite green.

- [ ] **Step 6: Commit**

```bash
git add scripts/refine_live.py tests/scripts/test_refine_live.py
git commit -m "feat(scripts): refine_live — evolve the live brain + feed the conflict queue, under the lock"
```

---

## Self-Review

**Spec coverage:**
- Thread `conflict_queue` InnerLoop→Refiner (mirror episode_store) → Task 1. ✓
- `scripts/refine_live.py` over the live brain, under the lock, persist + held → Task 2. ✓
- Persist mode (non-conflicting edits saved; conflicts held) → Task 2 (gate+breaker via the InnerLoop, save back). ✓
- Lock = 3rd writer → Task 2 (`bstore.lock()` around load→run→save). ✓
- Offline fail-loud operator script → Task 2 (no try/except softening; CLI mirrors save_evolution). ✓
- Tests: threading unit + offline e2e (teaching-owned seed → contesting op held + non-conflicting edit persisted) → Tasks 1 + 2. ✓
- Out of scope (UI trigger, dedup, auto-apply-on-accept) → not built. ✓

**Placeholder scan:** Task 1 is fully exact-code. Task 2's `run_refine_live`/`main` are exact code; the e2e test's `<…>` tokens are explicitly the real fixtures from `tests/loop/test_inner_loop_episodes.py` (Step 1 names that file to read), with the precise assertion contract spelled out — an instruction to reuse a named existing fixture, not a vague placeholder.

**Type consistency:** `InnerLoop(..., conflict_queue=…)` (T1) is called by `run_refine_live` (T2). `LiveBrainStore.lock()/load()/save()/edit_count()` and `ConflictQueue.all()` are the real signatures used in both the impl and the e2e test. `HarnessManager(h, store, log=log)` matches the real ctor. `run_refine_live(source, start, end, *, brain_dir, conflicts_dir, agent_llm_factory, refiner_llm_factory, horizon)` is the single signature used by both `main()` and the test. The held-conflict assertion reads `HeldConflict.op["args"]["lesson_id"]` — matching the `{"tool","args","rationale"}` op dump the gate enqueues.
