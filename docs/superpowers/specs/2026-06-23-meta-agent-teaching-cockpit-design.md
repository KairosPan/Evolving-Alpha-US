# Meta-Agent Teaching Cockpit — Design

**Date:** 2026-06-23
**Status:** Approved (brainstorm). Next: implementation plan.
**Topic:** Turn the web console's Evolution page into an interactive *meta-agent cockpit* where the
human teaches the co-pilot from curated content, the agent proposes evolution choices, the human
gives feedback, and accepted edits accumulate into a persistent live brain — each round a *session*.

---

## 1. Goal & framing

The user wants to **teach** the agent ("我可以教我的 agent 怎么做") and have it **self-learn** from
its own task sessions ("他也能从任务 session 中自学到"). One evolving brain, two channels.

This spec covers **v1: the teaching channel only**, on the **trading brain**. The two channels and the
general meta-agent are explicit roadmap follow-ups (§11).

The pivotal reuse insight: the existing autonomous **Refiner** already turns *evidence* (a task
trajectory + credit + failure-signatures) into *edits* to the brain `H = (doctrine, skills, memory)`
via 9 typed meta-tools, logged as `EditRecord`s. Teaching keeps that **exact same apply path** and
only swaps the *proposal source*: human-curated content instead of realized market outcomes. So this
is an additive subsystem, not a fork of the brain logic.

### Decisions locked during brainstorm

| # | Decision |
|---|----------|
| Domain | Trading brain now (`H = doctrine/skills/memory`); general meta-agent → roadmap. |
| Channels | Teaching (human→agent) in v1; self-learning (agent→itself) → roadmap. |
| Inputs | Pasted text + URLs in v1; images (vision) → roadmap. |
| Interaction | Two-stage: **pick-a-direction → concrete edit queue + comments**, feedback at both stages. |
| Brain storage | Separate persistent **live brain**; seeds stay **frozen** as the `Hexpert` baseline; per-session snapshots for rollback. |
| Architecture | Extend `alpha_web` into the cockpit (Approach A): POST endpoints + server-side `MetaAgent` orchestrator. The console is no longer read-only. |
| Red-lines | The 7 immutable doctrine red-lines stay protected even from human teaching (enforced inside `MetaTools.rewrite_doctrine`). |
| HTML extraction | stdlib `urllib` + `html.parser` (zero new deps); paste-the-text is the always-reliable fallback. |
| Nav | `/` = cockpit; Deck → `/deck`; existing batch timeline → `/evolution` relabeled "Autonomous". |
| Live brain everywhere | The whole console reads the live brain (badge: "live · N edits" vs "seed baseline"). |

---

## 2. Scope

**In (v1):**
- Ingest a *lesson source*: pasted text, or a URL fetched + stripped to readable text.
- Two-stage propose loop driven by the refiner LLM (Claude): directions → concrete edit queue.
- Per-edit accept / reject / tweak / comment; comment re-proposes that one row.
- Apply accepted edits through the real meta-tools (same gates as the Refiner), into a persistent
  live brain; snapshot before apply.
- Persist each round as a `Session`; browse history; roll a session back.
- Whole console reflects the live brain, with a seed-vs-live badge.

**Out (v1) → roadmap (§11):**
- Image/chart ingestion (Claude vision).
- The self-learning channel (Refiner reflection surfaced into the same cockpit).
- General domain-agnostic meta-agent core.
- Multi-user / auth / non-localhost serving; branchable named brains.

---

## 3. Concepts & reused machinery

Existing pieces this design reuses verbatim:

- **`HarnessState`** (`alpha/harness/state.py`) — `H = (doctrine, skills, memory)`, with `to_dict`/`from_dict`.
- **9 meta-tools** (`alpha/harness/metatools.py`) — `write_skill`, `patch_skill`, `retire_skill`,
  `revive_skill`, `promote_skill`, `process_memory`, `update_memory`, `demote_memory`,
  `rewrite_doctrine`. Each edits `H` in place and appends one `EditRecord`. `rewrite_doctrine` already
  refuses immutable entries.
- **`EditLog` / `EditRecord`** (`alpha/harness/edit_log.py`) — append-only audit;
  `EditRecord{seq, tool, target_kind, target_id, op, summary, payload, rationale}`.
- **`RefineOp` + `parse_ops`** (`alpha/refine/ops.py`) — the LLM op schema + tolerant parser.
- **Refiner dispatch + gates** (`alpha/refine/refiner.py` `_dispatch` / `_apply_op`) — to be extracted
  into a shared `try_apply_op` (§6).
- **`HarnessManager` + `SnapshotStore`** (`alpha/harness/manager.py`, `snapshot.py`) — checkpoint /
  rollback, with the cached-reference rebind hazard already handled.
- **`make_client(role)`** (`alpha/llm/config.py`) — `refiner` → Claude; `mock` for offline.
- **Brain-injection rendering** (`alpha/agent/prompt.py`) — compact doctrine/skills/memory summary.
- **Store pattern** — `DecisionStore` / `VerdictStore` (atomic JSON-by-key) as the template for the
  new stores.

---

## 4. Data models (`alpha/meta/models.py`, pydantic)

```
LessonSource
  kind: "text" | "url"
  url: str | None
  title: str
  text: str                     # the readable content the LLM sees
  fetched_at: str               # ISO timestamp (stamped by app code)

ProposedDirection
  direction_id: str
  title: str
  summary: str
  rationale: str
  target_kinds: list[str]       # subset of {doctrine, skills, memory}
  families: list[str]           # runner/swing/event/meme (optional hints)
  phases: list[str]             # phase keys (optional hints)
  est_edits: int

ProposedEdit                    # a DRY-RUN candidate; mirrors EditRecord + UI state
  edit_id: str
  tool: str                     # one of the 9 meta-tools
  target_kind: str              # skill | memory | doctrine
  target_id: str | None
  op: str                       # create | update | retire | revive | promote | demote | rewrite
  summary: str
  payload: dict | None          # before/after preview computed from the live brain (not committed)
  rationale: str
  args: dict                    # the RefineOp args used to apply
  status: "proposed" | "accepted" | "rejected" | "applied" | "failed"
  user_comment: str = ""
  apply_reason: str = ""        # reject/failure reason after apply attempt
  applied_seq: int | None       # EditRecord.seq once applied

Session
  session_id: str               # timestamp-based slug
  created_at: str
  channel: "teach"
  status: "drafting" | "directions" | "editing" | "applied" | "discarded"
  sources: list[LessonSource]
  directions: list[ProposedDirection]
  chosen_direction_id: str | None
  direction_comment: str = ""
  edits: list[ProposedEdit]
  applied_seqs: list[int]
  snapshot_before: int | None   # SnapshotStore version
  snapshot_after: int | None
  notes: list[str]              # e.g. "rolled back to snapshot 4"
```

---

## 5. The `MetaAgent` orchestrator (`alpha/meta/agent.py`)

Holds the live `HarnessState`, its `MetaTools`, and an injected refiner `LLMClient`. Three methods,
two of which call the LLM:

1. `propose_directions(source, *, comment=None) -> list[ProposedDirection]` — one LLM call. System
   prompt injects a compact summary of the *current* brain (reusing `agent/prompt.py` rendering) + the
   source text (+ optional comment for regeneration); asks for 2–4 distinct directions as strict JSON.
2. `expand_to_edits(source, direction, *, comment=None) -> list[ProposedEdit]` — one LLM call. Reuses
   the Refiner op schema; the LLM emits ops in the 9-tool vocabulary; `parse_ops` parses them. Each op
   becomes a dry-run `ProposedEdit` with a `payload` before/after preview computed from the live brain
   **without committing** (current field value vs proposed arg for patches; `None`→value for creates).
3. `apply(accepted: list[ProposedEdit]) -> (applied: list[EditRecord], results: list[ProposedEdit])` —
   snapshots the brain first, runs each accepted op through the shared `try_apply_op` (allowed = all 9
   tools), updates each `ProposedEdit.status`/`apply_reason`/`applied_seq`, and returns real
   `EditRecord`s. Persistence back to `LiveBrainStore` is the caller's (route's) responsibility.

**Prompts** (`alpha/meta/prompts.py`): two builders. The edits prompt reuses the same op-vocabulary
the Refiner emits and instructs the model to respect immutable red-lines. Output is strict JSON.

**Determinism / offline:** LLM client injected; temperature from `ALPHA_LLM_TEMPERATURE` (default 0);
tests script JSON via `MockLLMClient`.

---

## 6. Shared apply path (the one existing-code change)

Extract the Refiner's `_dispatch` + `_apply_op` gate logic into a module-level function in a new
`alpha/refine/apply.py`:

```
try_apply_op(meta, harness, op, *, allowed, min_retire_samples, min_promote_samples)
    -> tuple[EditRecord | None, str | None]      # (record, None) applied | (None, reason) rejected
```

Gate order unchanged: whitelist → rationale → empty-patch → retire/promote evidence → dispatch
(dispatch errors → clean reject reason). The Refiner keeps its `AppliedEdit`/`RejectedEdit` wrappers
(with `pass_kind`) and calls this per pass with its per-pass tool set. The `MetaAgent` calls it with
`allowed =` all 9 tools. Behavior must be identical for the Refiner (existing tests stay green).
Immutable-red-line protection lives inside `MetaTools.rewrite_doctrine`, so both callers get it free.

---

## 7. Ingestion (`alpha/meta/ingest.py`)

- `from_text(text, title="") -> LessonSource` — the paste path.
- `fetch_url(url, *, fetcher=None) -> LessonSource` — default fetcher = stdlib `urllib` GET +
  `html.parser`-based text strip (zero new deps, matching the existing urllib-based `AlpacaSource`).
  The fetcher is an injectable seam so tests run fully offline. Fetch failures raise a typed error the
  route turns into "couldn't read that URL — paste the text instead."

---

## 8. Web layer (`alpha_web`)

**Nav reshuffle:** `/` = cockpit; Deck → `/deck`; `/evolution` stays as the **Autonomous** batch
timeline (unchanged content). Nav leads with the cockpit.

**Routes (mutations — the app is no longer read-only):**

| Method/Path | Purpose |
|---|---|
| `GET /` | Cockpit; resumes the latest draft session (refresh-safe). |
| `POST /evolve/ingest` | text/url → create draft `Session` + `LessonSource`; `propose_directions`; return directions partial. |
| `POST /evolve/direction` | `{session_id, direction_id, comment}` → `expand_to_edits`; return edit-queue partial. |
| `POST /evolve/direction/regenerate` | `{session_id, comment}` → re-`propose_directions`. |
| `POST /evolve/edit/{edit_id}` | toggle accept/reject, or comment → re-propose that one row. |
| `POST /evolve/apply` | apply accepted edits; snapshot; finalize session; persist live brain; return result partial. |
| `GET /evolve/sessions[/{id}]` | browse session history. |
| `POST /evolve/rollback/{session_id}` | restore live brain to that session's `snapshot_before`; record a note. |

Each POST returns an HTML partial swapped via HTMX. LLM calls take 10–30 s → htmx-indicator spinners +
disabled buttons (extending the existing `app.js` fade pattern).

**Templates:** `cockpit.html` (home) + partials `directions.html`, `edit_queue.html`, `edit_row.html`,
`apply_result.html`, `session_list.html`. Existing `evolution.html` reused as-is at `/evolution`.

**Live-brain wiring:** `data_access.load_brain()` reads `LiveBrainStore` (falling back to seeds when
empty). Deck/Doctrine/Memory/Skills then show the evolved brain, with a badge "live · N edits" vs
"seed baseline". Decisions/Verdict keep reading their own artifacts.

**Graceful degradation:** ingest/propose need `ANTHROPIC_API_KEY` at serve time; if missing, the
cockpit shows "set your key or use mock mode" instead of erroring. `ALPHA_REFINER_PROVIDER=mock` gives
a fully offline scripted demo.

---

## 9. Persistence & rollback (`alpha/meta/store.py`)

- `LiveBrainStore(root)` — persists `HarnessState.to_dict()` + `EditLog.to_dict()` as JSON
  (`brain.json`). On first load with an empty root, initializes from frozen seeds and saves. The
  cockpit builds a `HarnessManager(harness, SnapshotStore(<root>/snaps), log)` from it; on apply it
  persists back via `LiveBrainStore.save(harness, log)`.
- `SessionStore(root)` — atomic JSON-by-id; `put`, `get`, `list()` (newest first), `latest_draft()`.
  Same atomic-write pattern as `DecisionStore`/`VerdictStore`.
- Roots via env: `ALPHA_LIVE_BRAIN_DIR` (default `./state/brain`), `ALPHA_SESSIONS_DIR`
  (default `./state/sessions`). Both gitignored.
- **Rollback:** each apply takes a pre-snapshot (`snapshot_before`) via the existing `SnapshotStore`;
  `POST /evolve/rollback/{id}` calls `HarnessManager.rollback_to(snapshot_before)`, persists, and
  records a session note. Never silent.

---

## 10. Error handling & testing

**Error handling — never a 500, always recoverable:**
- LLM failure / missing key / timeout → friendly partial, draft preserved, retry button.
- Bad model output → `parse_ops` is tolerant; surface "couldn't use that — regenerate," keep raw for
  debugging.
- Apply is per-edit: gate-blocked or immutable-doctrine edits show their reason inline; partial apply
  is fine and recorded; the pre-snapshot allows wholesale rollback.
- URL fetch failure → paste-the-text fallback.
- Mis-shaped persisted brain/session → same defensive fallback as `_decision_context`/`_verdict_context`.

**Testing (TDD, fully offline via `MockLLMClient` + injected fetcher):**
- Model round-trips (all four models).
- Stores: `LiveBrainStore` init-from-seeds + save/load; `SessionStore` put/get/list/latest_draft;
  atomic writes.
- `try_apply_op` refactor: existing Refiner tests stay green (behavior-identical) + new teaching-path
  (all-tools) + immutable-doctrine rejection.
- `MetaAgent`: scripted JSON → `propose_directions` parses N; `expand_to_edits` → `ProposedEdit`s with
  correct before/after previews; `apply` → `EditRecord`s + snapshot taken; red-line edit rejected with
  reason.
- Ingest: `from_text`; `fetch_url` with a fake fetcher; failure path.
- Web routes: `httpx` TestClient drives ingest→direction→edit→apply→rollback with mock provider;
  asserts partials, that the live brain mutated, and a session persisted; graceful-degradation with no
  key.
- Playwright screenshot of the cockpit + the multi-step HTMX flow (incl. loading state).

**Build order — vertical slices, each shippable + green before the next:**
1. Models + stores (pure data, offline).
2. `try_apply_op` refactor (Refiner regression-green) — de-risks the apply path.
3. `MetaAgent` propose/expand/apply against `MockLLMClient` (offline).
4. Ingest (text + URL seam).
5. Web cockpit: routes + templates + HTMX + nav reshuffle + live-brain wiring of `data_access`.
6. Playwright verify + optional real-key smoke once offline is green.

---

## 11. Roadmap follow-ups (explicitly deferred)

- **Self-learning channel:** surface the Refiner's session-reflection into the same direction→edit
  cockpit, so the agent proposes evolutions from its own task runs, not just from fed content.
- **Image ingestion:** chart/screenshot teaching via Claude vision (extend the LLM client for image
  content blocks; add upload handling).
- **General meta-agent core:** lift the teach + self-learn mechanism off the trading-specific
  `doctrine/skills/memory` onto a domain-agnostic knowledge representation; trading becomes the first
  instance.
- **Branchable named brains** ("aggressive" vs "disciplined"); multi-user / auth / non-localhost.

---

## 12. Naming & file map (new)

```
alpha/meta/
  __init__.py
  models.py        # LessonSource, ProposedDirection, ProposedEdit, Session
  agent.py         # MetaAgent (propose_directions / expand_to_edits / apply)
  prompts.py       # two prompt builders (directions, edits)
  ingest.py        # from_text, fetch_url (injectable fetcher)
  store.py         # LiveBrainStore, SessionStore
alpha/refine/apply.py        # extracted shared try_apply_op (Refiner + MetaAgent)
alpha_web/
  app.py           # + cockpit GET/POST routes, nav reshuffle
  data_access.py   # load_brain() → LiveBrainStore (fallback seeds) + live/seed badge
  templates/cockpit.html + partials/{directions,edit_queue,edit_row,apply_result,session_list}.html
tests/meta/ + tests/web/ (new test modules)
```
