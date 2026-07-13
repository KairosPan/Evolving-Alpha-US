# A7 — Sonia-side proposer over worker traces (closes G7)

> Spec date 2026-07-13. Closes the named deviation **G7** (charter-conformance spec
> `2026-07-09-charter-conformance-live-governance.md` §5.4). Baseline: local `main` @ `be76466`,
> 1775 offline tests, lint 0, tcb-check 0.

## 0. The deviation being closed

The 2026-07-09 arc killed the worker's self-**LANDING** (`write_mode="apply"` raises), but the
worker still **PROPOSES** staged edits: the arena/converse face registers `propose_memory_edit`
(→ a `StagedEdit`), and `workbench /edits/{id}/approve` lands it stamped `proposer="kairos"`. The
charter's **First Founding Principle** is stronger:

> *only two hands may send it there: a Sonia proposal that passes deliberation → user approval →
> Applier, or the User's own direct edit … Kairos does not propose and does not self-edit.*

So a `proposer="kairos"` edit reaching the gate — even user-approved — is forbidden. §5.4 recorded
this as out-of-scope-then, needing "a Sonia-side proposer over worker traces." A7 delivers it.

## 1. The two hands (the invariant A7 makes executable)

Exactly two origins may send an edit to the one write-waist (`try_apply_op`):

| Hand | path / proposer | How it reaches the gate |
|---|---|---|
| **Sonia proposal** | `teaching` / `sonia`; or self-study `self_study` / `forge`\|`refiner` surfaced through Sonia's `/proposals` and user-adopted | Sonia teach `/edit`+preview→apply; or a fork-and-propose run (refine/forge/**reflect**) → `EvolutionProposal` → `adopt_proposal` |
| **User direct edit** | `user_direct` / `user` (with `human_approver`) | Sonia `POST /edit` |

**Refused: the worker.** `proposer ∈ {kairos, hermes}` (the worker face, current + pre-rename
name) may never send to the gate. `kairos`/`hermes` stay in the `EditProvenance` Literal for
**read-compat** (persisted brains still deserialize) — the refusal is a *write*-origin gate, not a
vocabulary removal.

## 2. Part 1 — the Sonia-side proposer over worker traces (ALREADY BUILT by A3; A7 pins it)

A3 landed exactly this: `alpha/refine/reflect.py` runs forge-style detectors over `kind="task"`
episodes (the worker's own task traces, PIT-masked via `for_asof`), and
`scripts/reflect_from_tasks.py` wraps it in `run_forked_evolution` → an `EvolutionProposal`
(`kind="reflect"`, → `$ALPHA_PROPOSALS_DIR`) the USER adopts or discards in the Sonia cockpit
(`/proposals`). Zero live H write; the surviving records carry `self_study`/`forge` provenance
(never `kairos`), so they are the **Sonia proposal** hand reading **worker** evidence.

A7 does **not** rebuild this — "A7 is about WHO proposes, not a new mechanism." A7 adds a test that
frames it as the two-hands answer: worker trace → proposal in `/proposals`, zero live write, records
are gate-**acceptable** (forge, not kairos).

## 3. Part 2 — retire the worker's propose origination (three layers, defense-in-depth)

### 3.1 The seam (LOAD-BEARING) — `alpha/refine/apply.py::try_apply_op` (TCB)
A stamp-coherence refusal, grouped with the existing `user_direct`/`human_approver` checks, before
the whitelist and any content check:

```python
# A7 (charter First Founding Principle — "only two hands may send it there"): the worker (Kairos,
# pre-rename hermes) does not propose. An op stamped proposer="kairos"|"hermes" is refused at the
# waist — only a Sonia proposal (sonia/forge/refiner) or the User's direct edit (user) may land.
if provenance is not None and provenance.proposer in ("kairos", "hermes"):
    return None, "worker proposals retired (charter A7): Kairos does not propose; ..."
```

This alone satisfies the acceptance ("no worker-originated `StagedEdit` reaches the gate") — any
kairos-stamped op is refused regardless of which caller assembles it. TCB edit: minimal-additive,
regen `tcb.lock`, accounted in §6.

### 3.2 The write-scope authority — `alpha/meta/teach_surface.py` (the "one-place" A8 anticipated)
Remove the `kairos` teach face: `TEACH_FACES=("sonia",)`, `_TEACH_SCOPES={"sonia": ALL_TOOLS}`.
`teach_scope("kairos")`/`teach_provenance("kairos")` now raise `ValueError` (unknown face). Sonia's
full-scope leg is byte-unchanged.

### 3.3 The tool — `converse/tools.py`, `converse/agent.py`, `arena/builder.py`
- `tools.py`: delete `make_propose_edit_tool` + `_MEMORY_EDIT_PARAMS` (the only worker H-edit tool).
- `agent.py::build_converse_registry`: register only `decide` — no `propose_memory_edit`, any mode.
  `write_mode` kept for signature stability; `"apply"` still raises (retired 2026-07-09); `"stage"`
  now registers no brain-edit tool. Docstring: the worker face is compute-use-only for H.
- `arena/builder.py`: drop `tiers["propose_memory_edit"]`. `decide/read/write/shell/recall` intact.

### 3.4 The orphaned landing — `workbench/app.py::approve_edit`
With no propose tool, `staged_edits` is always empty, so the approval path is unreachable for a
worker edit; the gate (§3.1) refuses it even if smuggled. `approve_edit` no longer references the
removed `kairos` scope — it returns a `410` "worker proposals retired (charter A7)". `reject_edit`
and `rollback` become inert-but-harmless (empty `staged_edits` → `404`/nothing-to-roll-back) and are
left structurally intact. The `StagedEdit` model, `session.py` §6b materialization (never fires —
no `{"staged": True}` result), `reconcile_staged_edits`, and the `workbench.html` proposals section
are left in place but **inert** (byte-identical where not the propose path); the alpha_web proxy and
template render "no proposals". Removed unused imports: `teach_provenance`, `teach_scope`,
`assert_approvable`, `StagedEditNotApproved`.

## 4. What the worker KEEPS (unchanged)
`decide` (T0), `read_file` (T1), `write_file` (T2), `shell` (T2), `recall` (T0). Full computer-use;
only the H-mutation **propose** path is retired. Workbench `/converse`, `/project`, `/rollback`,
`reject_edit` endpoints remain (the last two inert).

## 5. G7 closure proof
1. Worker cannot **originate**: no `propose_memory_edit` tool in any registry (§3.3) → no `StagedEdit`.
2. Worker cannot **land**: `try_apply_op` refuses `proposer∈{kairos,hermes}` (§3.1) → the one gate,
   the one channel, both faces converge here (CLAUDE.md write-waist).
3. Worker cannot **derive scope**: `teach_scope("kairos")` raises (§3.2).
4. The two legitimate hands are unchanged: Sonia (sonia/forge/refiner via /proposals+adopt or teach)
   and User (user_direct) still land. The Sonia-side proposer over worker traces (reflect) is the
   answer to "who proposes over worker evidence" (§2).

## 6. TCB accounting
Only `alpha/refine/apply.py` (TCB row: the gate) changes. Minimal-additive: one stamp-coherence
refusal, no signature change, no new dependency. Regen: `python scripts/gen_tcb_lock.py`; the new
hash replaces the `apply.py` row. `teach_surface.py`, `converse/*`, `arena/builder.py`,
`workbench/app.py` are **not** TCB members (checked against `tcb.lock`). No other TCB file changes.

## 7. Tests (TDD)
**New (pin the invariant):**
- gate refuses `proposer="kairos"` and `"hermes"`; accepts `sonia`/`user`/`forge`/`refiner`.
- worker registry (`build_converse_registry`, `build_arena`) has no `propose_memory_edit`; keeps
  decide/read/write/shell.
- Sonia-side proposer (reflect over worker task episodes) → `/proposals`, zero live write, records
  gate-acceptable (forge) — the "two hands" framing (reuses A3's `test_reflect_propose`).

**Retired/updated (were pinning the G7 behavior):** `test_propose_edit_tool.py` (subject gone),
`test_proposer_provenance.py` (kairos dry-run leg), `test_registry_provenance.py` (stage→no propose
tool), `test_converse_project_stage.py` (no staged edit), `test_teach_surface.py` (sonia-only +
kairos unknown + approve_edit retired), `test_workbench_mutation.py` (stage→approve→rollback →
retirement + gate-refuses-kairos), `test_builder.py` (no propose tier), plus any web/workbench test
asserting a staged/approve surface.

## 8. Out of scope / deliberately not done
- The staged-edit **data plumbing** (`StagedEdit`, materialization, reconcile, the workbench
  proposals UI) is left inert, not ripped out — a full UI teardown is disproportionate to G7 and
  risks the 1775 baseline; "byte-identical where not the propose path" (task) argues for the
  surgical cut. A future arc may repurpose the workbench approval surface to review **Sonia**
  proposals (the legitimate hand), at which point the inert plumbing is the seam to reuse.
- `hermes` is refused at the gate for completeness though it has 0 production write callers.
- Charter/DEVELOPMENT-PLAN/manuscript edits are reported, not made (see the report).
