# Feed the §5 Conflict Queue Live (Refine-Live, Persist Mode) Design

> Status: **APPROVED** (brainstormed 2026-06-26). Next: writing-plans.
> Scope: wire an offline self-study run over the LIVE brain so real conflicts populate the §5 `ConflictQueue` (and the Conflicts UI), while non-conflicting self-study edits actually evolve the live brain.

## Goal

§5 built the conflict mechanism (`try_apply_op(conflict_queue=…)`, `Refiner(conflict_queue=…)`) and the §5-UI follow-up gave you a Conflicts page — but nothing ever feeds the queue: the only `InnerLoop` caller (`inner_loop.py:117`) constructs the `Refiner` without a `conflict_queue`, and `save_evolution.py` runs the loop over a fresh-seeded brain in a tempdir (no teaching-owned elements → no conflicts can arise). This closes that loop: an **offline self-study run over the live brain** (which carries Sonia's teaching-owned elements) with a `ConflictQueue` at `ALPHA_CONFLICTS_DIR`, so the Refiner's edits that contest teaching-owned elements are held + surfaced for adjudication, and its non-conflicting edits evolve the live brain.

## Confirmed decisions (from brainstorming)

1. **Persist mode (real autonomous evolution).** Non-conflicting self-study edits are applied through the gate (+ the capability-floor breaker) and **saved back to the live brain**; conflicting edits (self-study contesting a teaching-owned element) are **held** to the queue, never auto-applied. This is the full "two learning paths" operating on the live brain.
2. **A producer script** (`scripts/refine_live.py`), mirroring `save_evolution.py` — offline, deliberate, costs agent+refiner LLM calls. NOT a console button (a UI trigger is deferred).
3. **Holds the brain file lock.** The run is the THIRD live-brain writer (after Sonia and workbench); it wraps its load→run→save in `LiveBrainStore.lock()` to serialize against them.

## Architecture

Two additive changes, no new modules:

### 1. Thread `conflict_queue` through `InnerLoop` → `Refiner`

`alpha/loop/inner_loop.py`:
- `InnerLoop.__init__(..., episode_store=None, conflict_queue=None)` — add the param beside the existing `episode_store` (the §6 precedent), store `self._conflict_queue = conflict_queue`.
- `_rebind()` — change `self._refiner = Refiner(h, self._refiner_llm, self._mgr.tools, self._refiner_cfg)` to pass `conflict_queue=self._conflict_queue`.

`Refiner.__init__` already accepts `conflict_queue` (§5) and threads it to `try_apply_op` in `_apply_op`. Purely additive: default `None` → today's behavior; `save_evolution.py` and every existing `InnerLoop` test are unchanged.

### 2. `scripts/refine_live.py` (mirror `save_evolution.py`)

Loads the live brain, runs the InnerLoop over a captured PIT window with a `ConflictQueue`, saves the evolved brain back — all under the lock:

```python
bstore = LiveBrainStore(os.environ.get("ALPHA_LIVE_BRAIN_DIR", "./state/brain"))
cq = ConflictQueue(os.environ.get("ALPHA_CONFLICTS_DIR", "./state/conflicts"))
held_before = len(cq.all())
with bstore.lock():                                  # 3rd writer — serialize vs Sonia/workbench
    h, log = bstore.load()                           # the LIVE brain (carries teaching-owned elements)
    mgr = HarnessManager(h, SnapshotStore(tempfile.mkdtemp()), log=log)   # SnapshotStore = in-run breaker checkpoints
    loop = InnerLoop(mgr, source, start, end, agent_llm, refiner_llm,
                     config=LoopConfig(horizon=horizon), conflict_queue=cq)
    report = loop.run()
    bstore.save(mgr.harness, mgr.log)                # persist the evolved brain
held = len(cq.all()) - held_before
print(f"{report.n_edits} self-study edits applied · {held} conflicts held -> {ALPHA_CONFLICTS_DIR}")
```

CLI (mirrors `save_evolution.py`): `refine_live.py <pit_root> <start> <end> [--horizon N]`. The source is `SnapshotSource(PITStore(pit_root))` from a `capture_window` run; agent+refiner LLMs default to `make_client("agent")`/`make_client("refiner")` (temp=0). A `run_refine_live(source, start, end, *, brain_dir, conflicts_dir, agent_llm_factory, refiner_llm_factory, horizon)` core function (testable with injected MockLLM factories + tmp dirs) under the thin `main()`.

## Data flow

```
capture_window ──► PIT source ──┐
                                 ▼
  LiveBrainStore.load() ──► HarnessManager ──► InnerLoop(conflict_queue=cq)
   (teaching-owned H)             │                   │
                                  │            Refiner proposes ops
                                  │             ├─ non-conflicting ─► try_apply_op (gate + breaker) ─► applied to H
                                  │             └─ contests teaching ─► HELD ─► ConflictQueue ─► Conflicts UI
                                  ▼
                         LiveBrainStore.save(evolved H, log)
```

## Error handling / safety

- **Lock:** `bstore.lock()` (the existing primitive) serializes against Sonia/workbench; a busy lock → `RuntimeError` after the bounded timeout (fail loud).
- **Gate + breaker:** non-conflicting self-study edits still pass the one gate (`try_apply_op` — rationale/evidence floors/red-lines) and the InnerLoop's capability-floor breaker (rolls back bad batches mid-run). This is the protection against bad autonomous edits on the live brain.
- **Conflicts never auto-apply:** a held op is enqueued and NOT applied (§5 semantics); the live brain only gains the self-study edits that did NOT contest teaching.
- **Offline batch, not a server:** LLM/source/window errors propagate (fail the run loudly) rather than being swallowed — this is a deliberate operator-run script.

## Testing (all offline, deterministic)

- **InnerLoop threading** (`tests/loop/`): construct an `InnerLoop(..., conflict_queue=<sentinel>)` and assert the rebound `Refiner._conflict_queue is <sentinel>` (and that `conflict_queue=None` — the default — leaves it `None`). Non-vacuous, no run needed.
- **End-to-end refine-live** (`tests/scripts/` or `tests/loop/`): a tmp `ALPHA_LIVE_BRAIN_DIR` pre-seeded with a brain whose EditLog records a **teaching-owned** memory (a `process_memory` record stamped `provenance.path="teaching"`); a `FakeSource` window; a scripted agent MockLLM + a scripted refiner MockLLM that proposes (a) one op contesting the teaching-owned memory (e.g. `demote_memory` on it) and (b) one non-conflicting op. After `run_refine_live`: assert the contesting op is in the `ConflictQueue` (`cq.all()` grew) AND the non-conflicting edit landed in the **saved** live brain (`LiveBrainStore(dir).edit_count()` rose / the lesson is present). This proves the full persist + held split end-to-end.
- Existing `save_evolution`/InnerLoop tests stay green (additive `conflict_queue=None`).

## Out of scope (deferred)

- A console/Sonia/workbench button to trigger refine-live (it's an offline operator script for now).
- De-duplicating re-surfaced conflicts across repeated runs (the queue appends; adjudication clears).
- Resolving a held conflict by auto-applying the self-study op (§5-accepted: accept = record intent only).
- Per-narrative-line regime reads / any new Refiner behavior — this only WIRES the existing Refiner to the live brain + queue.

## Why this shape

- It reuses everything: the §5 conflict mechanism, the §6 `episode_store` threading pattern, the workbench `LiveBrainStore.lock()`, and the `save_evolution.py` producer shape. The net new surface is one `InnerLoop` param + one script.
- Persist mode makes the self-study path real on the live brain while keeping teaching-owned territory under your adjudication — exactly the §5 "two learning paths, one gated brain, conflicts → user" doctrine, now actually running.
