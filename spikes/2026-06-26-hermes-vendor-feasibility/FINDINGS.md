# Phase 0 Findings — Hermes vendor feasibility

Pinned Hermes SHA: 5add283ec8e7a33110a9051179208bd50bda427c

## Vendorability (from COUPLING.md)

Vendor feasibility is driven by the **EAGER** footprint (imports that execute on `import`, module top-level only), not the total static footprint. The total for all three targets is identical (503 files / 432 055 LOC) because lazy/function-level imports pull in the entire monolith when those code paths run — this number is misleading for vendorability and is shown only for context.

| target | eager files | eager LOC | drags `agent/`? | verdict |
|---|---|---|---|---|
| `tools/registry.py` | 1 | 589 | No | liftable (eager leaf) |
| `hermes_state.py` | 7 | 8 825 | Yes | eager-coupled — investigate/sever or reimplement |
| `agent/conversation_loop.py` | 28 | 20 906 | Yes | drags-monolith — do NOT vendor; reimplement |

## Integration proof (Tasks 3–5)

- registry + turn loop (`spike_loop.py`): PASS
- `decide` tool returns a typed `DecisionPackage` through the registry: PASS
- gated write tool routes a `RefineOp` through `try_apply_op` (valid op applied, `rewrite_doctrine` rejected): PASS

All 7 spike tests green; 555 main-suite tests unaffected.

## GO / NO-GO for Strategy C (narrow-waist vendor)

**NUANCED GO** — literal "lift the whole module set" is NOT viable (the deep code is one 2 579-file daily-moving monolith), but the narrow waist IS achievable via a hybrid disposition:

1. **Reimplement the turn loop** — `agent/conversation_loop.py` has an eager footprint of 28 files and drags the entire `agent/` package; it is the wrong thing to vendor. The spike's `spike_loop.py` (≈70 LOC) is a complete, proven reimplementation of the thin tool-calling contract, and Tasks 3–5 show it routes both a `decide` tool and a gated write tool correctly. This path is already done.

2. **`tools/registry.py` is a clean optional leaf-vendor** — eager footprint = 1 file / 589 LOC, no `agent/` drag. Its 503-file total only materializes if you load Hermes's own tools; we register our own (Tasks 4–5 prove this). It is small enough that reimplementing is equally valid.

3. **`hermes_state.py` is a follow-up investigate-or-reimplement** — eager coupling to `agent/` via 7 files / 8 825 LOC is real but modest. If the SQLite/FTS5 session-store value is needed in Phase 1, the right move is to audit those 7 eager files for severability; the default posture is reimplement-the-schema (the schema is the stable contract, not the implementation).

The fallback ("reimplement against Hermes's tool schema") is already demonstrated by `spike_loop.py` + all 7 passing integration tests. Strategy C is viable on this narrower, more precise basis.

## §8 vendor-tracking recommendation

**Hard-pin SHA `5add283ec8e7a33110a9051179208bd50bda427c`; do not track upstream.**

Justification: the reachable static footprint is 503 files / 432 055 LOC — the entire Hermes monolith. Even though we vendor little-to-no deep code (only the optional leaf `registry.py` at 1 file / 589 LOC, everything else reimplemented), a periodic rebase would require re-running coupling measurements across 2 579 Python files each cycle to confirm that the leaf's eager surface has not grown or that the schema contracts have not shifted. That cost is not justified by the benefit. The single stable artifact we depend on is the **tool-calling schema** (JSON-serialisable name/schema/fn triples), which is captured in the spike's own tests. Pin the SHA, document the schema version, and only bump deliberately if a specific upstream change is needed — at which point re-run the coupling measurement suite as a gating check.

Only `registry.py` (eager leaf, 589 LOC, no `agent/` drag) would be a low-churn vendor candidate worth tracking; everything else is reimplement-and-don't-track.

## What Phase 1 should vendor vs reimplement

| module | disposition | rationale |
|---|---|---|
| `agent/conversation_loop.py` | **Reimplement** (already done: `spike_loop.py`) | Eager 28 files, drags `agent/`; thin loop is trivial to own |
| `hermes_state.py` | **Reimplement the schema** (SQLite/FTS5 session store) | Eager 7 files, drags `agent/`; schema is the stable surface; audit severability only if store features are urgently needed |
| `tools/registry.py` | **Optional leaf-vendor or reimplement** | Eager 1 file / 589 LOC, no `agent/` drag; small enough either way; if vendored, pin to SHA above |
| Hermes tool-calling JSON schema | **Adopt (not vendor)** | The schema contract (name / JSON-schema / callable) is the narrow waist; Tasks 4–5 prove it is stable and sufficient |
