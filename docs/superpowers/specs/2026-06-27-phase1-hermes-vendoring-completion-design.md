> **Status:** APPROVED (2026-06-27) — design brainstormed and approved by the user; entering implementation planning. Completes the two named-open §8/Phase-1 follow-ups (the §8 spec reframe + the deferred narrow-waist vendoring) and the one deferred Phase-1 substrate piece (SQLite/FTS5 session persistence). Scope confirmed by the user: **reference-vendor the clean leaf + parity test; REPLACE the JSON ProjectStore with SQLite + FTS5 (CJK trigram); reframe spec §8/§9.**
>
> **Parent spec:** `docs/superpowers/specs/2026-06-25-evolving-alpha-hermes-rebase-architecture-design.md` (§8 "Narrow-waist vendor boundary", §9 "Phased rollout"). **Phase-0 inputs:** `spikes/2026-06-26-hermes-vendor-feasibility/{FINDINGS,COUPLING}.md` (pinned Hermes SHA `5add283ec8e7a33110a9051179208bd50bda427c`).

# Phase-1 Hermes-Vendoring — Completion (Design)

## 1. Context & goal

The Hermes re-base's phased rollout (Phases 0–4 in the parent spec §9) is **functionally shipped** and on `origin/main`: the Phase-0 vendor-feasibility spike (NUANCED GO), the Phase-1 B-WIDE conversational face (1A reimplemented the registry + turn loop; 1B added decide-for-date), the Phase-2 project workspace, the Phase-3 two-paths self-evolution, and the Phase-4 PIT memory system.

Three pieces tied to **§8 (the narrow-waist vendor boundary)** and the **Phase-1 done-criteria** remain open (recorded in the `hermes-rebase-design` memory and the parent spec):

1. **The §8 spec reframe.** §8's table and §9's done-criteria still describe a literal "vendor these Hermes modules" plan. The Phase-0 spike disproved the literal lift (Hermes is a 2 579-file daily-moving monolith; every target's *total* import footprint is the whole 503-file/432k-LOC monolith) and reframed Strategy C as **"reimplement-the-thin-parts + selective leaf-vendor."** The spec was never updated to match.

2. **The actual narrow-waist vendoring.** The spike proved `tools/registry.py` is a **clean eager leaf** (eager footprint = 1 file / 589 LOC, no `agent/` drag) and the single "low-churn vendor candidate worth tracking" — but Phase-1A *reimplemented* the registry (the 28-LOC `alpha/converse/registry.py`) and the vendor was deferred. The pinned Hermes clone lives at `spikes/.../​_hermes/` but is **gitignored** (never committed).

3. **The deferred Phase-1 SQLite session persistence.** Phase-1's done-criterion ("persist messages to SQLite") was explicitly deferred ("SQLite session persistence (reimplement `hermes_state`)"). The conversational face persists projects as **JSON** today (`alpha/converse/store.py::ProjectStore`).

**Goal:** close all three as three independent, additively-sequenced deliverables (D1/D2/D3), bringing the implementation and the spec into agreement with the Phase-0 reality and finishing the deferred Phase-1 substrate.

### 1.1 Explicitly out of scope (now)

- **Wiring the vendored Hermes registry into the live code path.** The spike found the registry's *lazy* imports drag the monolith when certain code paths run; eager import is clean (eager=1) but actively using Hermes's registry in the hot path is a heavier dependency than a 28-LOC concept warrants. We **reference-vendor** it (committed, pinned, audited) and keep the reimplementation as the active path, with a parity test proving the reimpl honors the vendored schema contract. (User-chosen.)
- **Migrating Sonia's `SessionStore`** (`alpha/meta/store.py`, the teaching channel). Phase-1's "SQLite sessions" is the **B-WIDE conversational face** = the `Project`/`ProjectStore` substrate only. Sonia is untouched.
- **`hermes_state.py` code-level vendoring.** Per the spike, its 7-eager-file `agent/` coupling means **reimplement the schema** (the stable contract), not lift the code. D2 reimplements the schema; it does not vendor `hermes_state.py`.
- **Tracking Hermes upstream.** §8 is resolved to a **hard pin** (D3); no rebase cadence.
- **Vision, GEPA/Forge, fast self-study sub-tier, live-order tools** — all remain deferred per the parent spec.

---

## 2. Deliverables overview

The three deliverables touch **disjoint files** and have no ordering dependency; they can be implemented and reviewed in parallel.

| | Deliverable | Active-path behavior change | Blast radius |
|---|---|---|---|
| **D1** | Reference-vendor `tools/registry.py` + contract-parity test | **None** (reimpl stays active) | new `third_party/`; +1 test file |
| **D2** | Replace JSON `ProjectStore` with `SqliteProjectStore` (`state.db` + FTS5 trigram) | persistence backend swap (interface-identical) | `alpha/converse/`, `workbench/app.py`, `scripts/`, converse+workbench tests |
| **D3** | Reframe parent spec §8/§9 + update `PROJECT_STATE.md` | none (docs) | `docs/` |

---

## 3. D1 — Reference-vendor the clean leaf + parity test

### 3.1 Vendored tree

New committed directory `third_party/hermes/`:

- `tools/registry.py` — the 589-LOC eager-leaf file, **verbatim** from the pinned SHA (copied from `spikes/.../_hermes/tools/registry.py`).
- `LICENSE` — Hermes's MIT license (copied from `spikes/.../_hermes/LICENSE`).
- `PROVENANCE.md` — records: upstream repo URL (`NousResearch/hermes-agent`), the pinned SHA `5add283ec8e7a33110a9051179208bd50bda427c`, *what* is vendored (only `tools/registry.py`), *why* it is reference-only (the active code path is `alpha/converse/registry.py`; this is the audit/provenance anchor and the schema source-of-truth), and the **§8 policy: hard-pin, do not track upstream** (re-run the spike's coupling measurement as a gating check before any deliberate bump).

`third_party/hermes/_hermes/` (the full gitignored clone) stays gitignored and out of the commit.

### 3.2 Contract-parity test

`tests/converse/test_registry_parity.py` asserts the active `alpha/converse/registry.py` faithfully implements the vendored registry's **tool-calling schema contract**:

- a tool is a `(name, JSON-schema dict, callable)` triple;
- registration is keyed by name; dispatch is by name; an unknown name is a reported/raised error (per our loop's convention);
- `specs()` returns the list of per-tool JSON schemas the provider consumes.

**Importability decision (resolved in the plan, not assumed):** the spike measured the leaf at eager=1, so `third_party/hermes/tools/registry.py` *should* import standalone. The first plan task confirms this. **If** relative imports prevent standalone import, the test instead compares the reimpl against a **captured golden schema snapshot** extracted from the vendored file (committed alongside as `tests/converse/_registry_contract_golden.json`), and `PROVENANCE.md` notes that the file is retained as reference source rather than an importable module. Either way the parity guarantee holds; the plan picks the branch after the importability check.

### 3.3 No active-path change

`alpha/converse/registry.py` is unchanged. D1 adds files and a test only.

---

## 4. D2 — Replace JSON `ProjectStore` with SQLite + FTS5

### 4.1 Interface contract (unchanged)

`SqliteProjectStore` exposes the **exact methods `converse_project` and `workbench` already call** on the JSON store:

- `get(project_id) -> Project | None`
- `put(project) -> None` (today returns a `Path`; the SQLite store returns `None` — see §4.5)
- `delete(project_id) -> None` (idempotent)
- `list() -> list[Project]` (newest-first)

The `Project` pydantic model (`alpha/converse/project.py`: `project_id`, `created_at`, `title`, `h_pin`, `messages: list[ChatMessage]`, `turns: list[ProjectTurn]`, `staged_edits: list[StagedEdit]`) stays the **round-trip contract** — all seven fields must round-trip. Because the model is unchanged, `converse_project`'s body is untouched; only the store *type* and its construction site change.

### 4.2 Schema (`state.db`)

```sql
CREATE TABLE IF NOT EXISTS projects (
  project_id   TEXT PRIMARY KEY,
  created_at   TEXT NOT NULL,          -- from Project.created_at (set at new_project)
  title        TEXT NOT NULL,
  h_pin        INTEGER,
  turns        TEXT NOT NULL,          -- JSON: list[ProjectTurn]
  staged_edits TEXT NOT NULL);         -- JSON: list[StagedEdit]
CREATE TABLE IF NOT EXISTS messages (
  project_id TEXT NOT NULL, seq INTEGER NOT NULL, role TEXT NOT NULL, text TEXT NOT NULL,
  PRIMARY KEY (project_id, seq));
CREATE VIRTUAL TABLE IF NOT EXISTS messages_fts USING fts5(text, tokenize='trigram', content='');
```

- **Messages are normalized rows** (not a JSON blob) so FTS5 can index them — this is the substantive reason the store isn't just "JSON-in-a-cell." `turns`/`staged_edits` stay JSON cells (no search requirement; keeps the model round-trip trivial).
- **No `updated_at` / no wall-clock read.** `list()` matches the JSON store's *exact* ordering — `ORDER BY project_id DESC` (the JSON `ProjectStore.list()` sorts `key=project_id, reverse=True`). Storing `created_at`/`title` verbatim from the model keeps the store a pure, clock-free serializer — no persistence-layer time side effect, so nothing about verdict reproducibility is touched.

### 4.3 `put` / `get` / `search` behavior

- `put(project)`: single transaction — upsert the `projects` envelope; `DELETE` then re-`INSERT` this project's `messages` rows from `project.messages` (idx = list position); refresh the FTS index for those rows (mirrors `EpisodeStore`'s add-and-index pattern). Atomic per `put`.
- `get(id)`: reconstruct the `Project` — envelope columns + ordered `messages` rows → `ChatMessage`s + JSON-decoded turns/staged_edits.
- `search(query) -> list[...]`: FTS5 query over `messages_fts`, returning matching `(project_id, seq, role, text)` (and/or the owning projects). This is the new capability the FTS5 table exists for; no current UI consumes it yet, but it is part of the chosen scope and is tested.
- `delete(id)`: remove envelope + messages + FTS rows. Idempotent.

### 4.4 Construction sites + factory

- `workbench/app.py::_project_store()` switches from `ProjectStore(ALPHA_PROJECTS_DIR)` to `SqliteProjectStore.open(ALPHA_PROJECTS_DB)` (default e.g. `./state/projects/state.db`).
- `SqliteProjectStore` mirrors `EpisodeStore`'s constructors: `.open(path, *, create_if_missing=True)` and `.in_memory()` (the latter for tests).
- The traversal-guard concern in the JSON `_path` **disappears** — `project_id` is a bound SQL parameter, never a filename.

### 4.5 Replace = remove the JSON store

After the migration script (§4.6) and the test-fixture rewire (§5), `alpha/converse/store.py` (JSON `ProjectStore`) is **deleted**. Any remaining importer is updated to `SqliteProjectStore`. `converse_project`'s `store: ProjectStore` annotation becomes `store: SqliteProjectStore` (or a shared `ProjectStoreProtocol` if a second backend is ever wanted — not now; YAGNI → concrete type). The `put` return type changes `Path -> None`; callers ignore the return today (`converse_project` discards it), so this is safe — confirmed in the plan.

### 4.6 One-time migration

`scripts/migrate_projects_to_sqlite.py`: read every `*.json` under a source `ALPHA_PROJECTS_DIR`, validate into `Project`, `put` into the target `state.db`. Idempotent (upsert). Tested against a fixture dir. Low-stakes (this is a single-user research tool; on-disk project state is minimal), but included for safety and because "replace" implies no data left behind.

### 4.7 Verification gates (resolved in the plan)

- **Trigram tokenizer availability.** `tokenize='trigram'` needs SQLite ≥ 3.34. The plan's first D2 task probes the runtime `sqlite3` (a tiny `CREATE VIRTUAL TABLE ... tokenize='trigram'` in `:memory:`); **if unavailable**, fall back to the default `unicode61` tokenizer and record the downgrade in a module comment + the spec. A guard test documents which tokenizer is active.
- **Durability.** One transaction per `put` (SQLite's default atomic commit) replaces the JSON `_atomic_write`+`os.replace`. Equivalent crash-safety for the single-writer pattern.

---

## 5. Testing strategy

TDD throughout (write the failing test first), matching the repo's discipline.

- **D1:** `test_registry_parity.py` (contract parity, per §3.2) + a provenance-presence assertion (LICENSE + pinned-SHA string committed under `third_party/hermes/`).
- **D2:**
  - New `tests/converse/test_sqlite_store.py`: round-trip fidelity (`put`→`get` reproduces a `Project` with messages/turns/staged_edits/h_pin), `list()` newest-first, idempotent `delete`, `in_memory()` isolation, FTS `search()` returns the right messages, trigram-availability guard.
  - New `tests/converse/test_migrate_projects.py`: JSON dir → `state.db` import fidelity + idempotency.
  - **Existing 28 converse + 5 workbench tests stay green** — the ones that construct a `ProjectStore` are pointed at `SqliteProjectStore` via a shared fixture (interface-identical). No test logic changes beyond the store constructor.
- **D3:** doc-only; the spec self-review pass (placeholders / internal consistency / §8-table-matches-spike).
- **Whole-suite gate:** `676 → 676 + N` green; the only existing-code behavior change is the persistence backend swap (D2), verified by the unchanged converse/workbench suites passing against SQLite.

---

## 6. Orchestration

The build follows the project's established path: **this spec → `writing-plans` (implementation plan) → execute via a Workflow.** After the plan exists:

- D1/D2/D3 fan out in **parallel** (disjoint files → no worktree isolation needed).
- Each deliverable: TDD implement → run its own tests → **adversarial review** (an independent agent tries to refute correctness, the interface-identity claim, FTS/migration fidelity, and test-vacuity) → fold findings.
- A final stage runs the **full suite + the verification gates** (trigram probe, leaf importability, no-stray-JSON-store) and synthesizes a GO/NO-GO with the new test count.

---

## 7. Risks & open questions

1. **Leaf importability for the parity test** — mitigated by the §3.2 golden-snapshot fallback, decided by an explicit plan task (not assumed).
2. **Trigram tokenizer unavailable on the runtime** — mitigated by the §4.7 probe + `unicode61` fallback.
3. **Hidden `ProjectStore` importer** — the grep found only two consumers (`converse_project`, `workbench`); the plan re-greps before deleting `store.py` so no importer is orphaned.
4. **`put` return-type change (`Path -> None`)** — current callers discard the return; confirmed in the plan before changing the annotation.
5. **No current consumer of `search()`** — accepted: FTS is in the chosen scope; it ships tested, ready for a future "search conversations" UI. Flagged so it isn't mistaken for dead code.
6. **Vendored file drift vs. active reimpl** — the parity test is the guard; if Hermes is ever deliberately bumped, the §8 policy (re-run coupling measurement) + the parity test catch a contract shift.

---

## 8. Done-criteria

- `third_party/hermes/{tools/registry.py, LICENSE, PROVENANCE.md}` committed; parity test green.
- `SqliteProjectStore` (+ FTS5) replaces the JSON store; migration script + tests green; converse + workbench suites green against SQLite; the JSON `store.py` removed with no orphaned importers.
- Parent spec §8 table + §9 Phase-1 done-criteria reframed to the spike's reality; the pin-vs-rebase "Open" resolved to hard-pin; closed items moved to `PROJECT_STATE.md`.
- Full suite green; verification gates (trigram, importability) recorded.
