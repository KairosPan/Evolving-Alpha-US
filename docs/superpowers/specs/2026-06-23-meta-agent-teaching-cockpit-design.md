# Meta-Agent Teaching Cockpit — Design

**Date:** 2026-06-23
**Status:** Approved (brainstorm) + self-reviewed (adversarial 5-lens, 41 confirmed findings folded). Next: implementation plan.
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
| Brain storage | Separate persistent **live brain**; seeds stay **frozen** as the `Hexpert` baseline; per-apply file copy for rollback. |
| Architecture | Extend `alpha_web` into the cockpit (Approach A): POST endpoints + a stateless, per-request `MetaAgent` orchestrator. The console is no longer read-only. |
| Red-lines | The immutable doctrine red-line *text* stays write-protected even from human teaching (enforced inside `Doctrine.rewrite`, called by `MetaTools.rewrite_doctrine`). See the §1 limitation note. |
| HTML extraction | stdlib `urllib` + `html.parser` (zero new deps); paste-the-text is the always-reliable fallback. |
| Nav | `/` = cockpit; Deck → `/deck`; existing batch timeline → `/evolution` relabeled "Autonomous". |
| Live brain everywhere | The whole console reads the live brain (badge: "live · N edits" vs "seed baseline"). |

**Red-line limitation (explicit, v1):** only the *immutable doctrine entries' text* is write-protected
(`rewrite_doctrine` on an immutable section is rejected; there is no create/patch path that can mint a
new immutable entry). The system does **not** prevent a taught *skill* or *lesson* from contradicting a
red-line in spirit. A post-apply "red-line lint" that flags such contradictions is a roadmap item (§11).

---

## 2. Scope

**In (v1):**
- Ingest a *lesson source*: pasted text, or a URL fetched + stripped to readable text.
- Two-stage propose loop driven by the refiner LLM (Claude): directions → concrete edit queue.
- Per-edit **accept / reject** (pure state), **tweak** (edit the args inline, no LLM), and **comment →
  re-propose that one row** (a scoped single-op LLM call).
- **Regenerate** at direction granularity (whole queue) carrying accumulated comments.
- Each candidate edit previewed as a **dry-run** (apply on a throwaway brain copy); gate failures show
  inline, never apply.
- Apply accepted edits through the real meta-tools (same gates as the Refiner) into a persistent live
  brain; copy the pre-apply brain for rollback.
- Persist each round as a `Session`; browse history; roll a session back.
- Whole console reflects the live brain, with a seed-vs-live badge.

**Out (v1) → roadmap (§11):**
- Image/chart ingestion (Claude vision).
- The self-learning channel (a reflection→directions stage on the Refiner's evidence path).
- Auto-resume of an in-flight draft on `GET /` (drafts are persisted and browsable, but `GET /` starts
  a fresh cockpit).
- Post-apply red-line lint for skills/lessons.
- General domain-agnostic meta-agent core; branchable named brains; multi-user / auth / non-localhost.

---

## 3. Concepts & reused machinery

Existing pieces this design reuses (verified against the code in self-review):

- **`HarnessState`** (`alpha/harness/state.py`) — `H = (doctrine, skills, memory)`, with `to_dict`/`from_dict`.
  Note: `HarnessState` does **not** carry an `EditLog`; the log is a separate object persisted alongside it.
- **9 meta-tools** (`alpha/harness/metatools.py`) — `write_skill`, `patch_skill`, `retire_skill`,
  `revive_skill`, `promote_skill`, `process_memory`, `update_memory`, `demote_memory`,
  `rewrite_doctrine`. Each edits `H` in place and appends one `EditRecord`. `rewrite_doctrine` delegates
  to `Doctrine.rewrite`, which refuses immutable entries.
- **`EditLog` / `EditRecord`** (`alpha/harness/edit_log.py`) — append-only audit;
  `EditRecord{seq, tool, target_kind, target_id (required str), op, summary, payload, rationale}`. `seq`
  continues from `len(log)`, so a reloaded log keeps numbering correctly. `EditRecord.payload` already
  holds the before/after snapshot the meta-tool computed (we reuse this for previews).
- **`RefineOp` + `parse_ops`** (`alpha/refine/ops.py`) — the LLM op schema (`tool`, `args`, `rationale`;
  **no `op` field** — `op` is derived from the resulting `EditRecord`) + a tolerant parser.
- **Refiner dispatch + gates** (`alpha/refine/refiner.py` `_dispatch` / `_apply_op` / `_target_id`) — to
  be extracted into a shared `try_apply_op` (§6).
- **`make_client(role)`** (`alpha/llm/config.py`) — `refiner` → Claude; `mock` for offline.
- **Brain rendering** (`alpha/agent/prompt.py` `build_system_prompt`) — renders doctrine/skills/memory,
  but only as part of a full trading-decision prompt with an output contract. There is **no** standalone
  "compact summary" helper today; §5 adds a new `render_brain_summary(h)` (it does not reuse
  `build_system_prompt` verbatim).
- **Store pattern** — `DecisionStore` (atomic JSON keyed by `date`, `<YYYY-MM-DD>.json`) and
  `VerdictStore` (atomic JSON keyed by run-name) are the template for `SessionStore` (atomic JSON keyed
  by `session_id`).

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
  target_kinds: list[str]       # advisory: subset of {doctrine, skills, memory}; injected as a HINT
                                # into the edits prompt, not a hard constraint

ProposedEdit                    # a DRY-RUN candidate; fields below are derived from a real EditRecord
  edit_id: str                  # stable row id (uuid-like; app-generated)
  tool: str                     # one of the 9 meta-tools
  target_kind: str              # skill | memory | doctrine
  target_id: str | None         # from the dry-run EditRecord; None only if the dry-run failed pre-assignment
  op: str                       # derived from the dry-run EditRecord.op (create/update/retire/...)
  summary: str
  payload: dict | None          # the dry-run EditRecord.payload (before/after); None if dry-run failed
  rationale: str
  args: dict                    # the RefineOp args used (so apply/tweak/re-propose can re-run it)
  status: "proposed" | "accepted" | "rejected" | "applied" | "failed"
  user_comment: str = ""        # free text; on a comment the row is re-proposed (§5.4)
  apply_reason: str = ""        # dry-run or apply rejection/failure reason (shown inline)
  applied_seq: int | None       # real EditRecord.seq once applied for real

Session
  session_id: str               # sortable slug: "YYYYMMDDTHHMMSSffffff-<4hex>" (timestamp + random suffix)
  created_at: str
  channel: "teach"
  status: "open" | "applied" | "discarded"   # open covers ingest→directions→editing
  sources: list[LessonSource]
  directions: list[ProposedDirection]
  chosen_direction_id: str | None
  direction_comment: str = ""
  edits: list[ProposedEdit]
  applied_seqs: list[int]
  snapshot_before: str | None   # path to the pre-apply brain copy (state/brain/history/<session_id>.json)
  notes: list[str]              # e.g. "rolled back to pre-apply snapshot"
```

`target_id` is `str | None` (not a strict mirror of `EditRecord`, which is always `str`) because a
preview can fail before an id is assigned — consistent with the Refiner's `RejectedEdit.target_id`
being nullable.

---

## 5. The `MetaAgent` orchestrator (`alpha/meta/agent.py`)

**Lifecycle (load-bearing): the `MetaAgent` is stateless and per-request.** It caches no long-lived
brain. Each request rebuilds it from `LiveBrainStore` — matching the existing `load_brain()`-per-route
pattern (`alpha_web/app.py`). Construction takes a freshly loaded `(HarnessState, EditLog)`, builds a
`MetaTools(harness, log)`, and an injected refiner `LLMClient`. There is no `HarnessManager` and no
`SnapshotStore` in this path (see §9 for why rollback is a file restore instead).

Four methods; three call the LLM:

1. `propose_directions(source, *, comment=None) -> list[ProposedDirection]` — one LLM call. System
   prompt = `render_brain_summary(harness)` + the source text (+ optional comment for regeneration);
   asks for 2–4 distinct directions as strict JSON.
2. `expand_to_edits(source, direction, *, comment=None) -> list[ProposedEdit]` — one LLM call. The LLM
   emits ops in the 9-tool vocabulary; `parse_ops` parses them. **Preview by dry-run:** for each op,
   deep-copy the `HarnessState`, bind a throwaway `MetaTools` over a fresh `EditLog`, and run the op via
   the shared `try_apply_op` (§6, `allowed = all 9 tools`). On success the resulting `EditRecord` gives
   `op`, `target_id`, and `payload` (before/after) directly — no bespoke diff logic; on a gate/validation
   failure the `ProposedEdit` is `status='failed'` with `apply_reason` set (rendered "couldn't build this
   edit — regenerate"), never raising. The live brain is untouched.
3. `apply(accepted: list[ProposedEdit]) -> (applied: list[EditRecord], results: list[ProposedEdit])` —
   runs each accepted op (its stored `args` + `rationale`) through `try_apply_op` against the **real**
   `MetaTools`/brain, updating each row's `status`/`apply_reason`/`applied_seq`. Returns the real
   `EditRecord`s. Snapshotting and persistence are the **route's** responsibility (§8/§9), not the
   MetaAgent's.
4. `repropose_edit(source, direction, prior_edit, comment) -> ProposedEdit` — one LLM call. Re-proposes
   a single row. Injects `render_brain_summary(harness)` + the source + the chosen direction + the prior
   edit's `tool`/`target`/`args` + the user comment; instructs the model to emit **exactly one** op,
   preferably for the same `target_kind`/`tool` (else a clean `status='failed'`). Preview via the same
   dry-run path. The returned `ProposedEdit` keeps the same `edit_id` so the route replaces the row
   in place.

**Prompts** (`alpha/meta/prompts.py`): `render_brain_summary(h)` (a new compact renderer — red-line
doctrine + active skill/lesson lines, no output contract), plus three builders: directions, edits,
single-edit re-propose. The edits prompt reuses the Refiner's op vocabulary and instructs the model to
respect immutable red-lines; `target_kinds` from the chosen direction is injected as an advisory hint.

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

It returns a **bare** `(record, reason)`. The Refiner keeps `_target_id` and re-wraps the result into
its own `AppliedEdit`/`RejectedEdit` (carrying `pass_kind` + normalized `target_id`) at the call site;
the `MetaAgent` builds `ProposedEdit` fields from the `EditRecord`. The full gate order is preserved and
must be enumerated in the extraction: whitelist → rationale present → empty-patch (`patch_skill`/
`update_memory`) → retire evidence (`n ≥ min_retire_samples`) → promote evidence
(`n ≥ min_promote_samples` **and** `expectancy > 0`) → dispatch (dispatch errors → clean reject reason).
The Refiner calls it per pass with its per-pass tool set; the `MetaAgent` calls it with `allowed =` all 9
tools. Immutable-red-line protection lives inside `Doctrine.rewrite` (reached via dispatch), so both
callers get it free.

**Hard acceptance gate:** the existing `tests/refine/test_refiner_*.py` suite must pass unchanged after
the extraction — behavior identity for the Refiner is non-negotiable, and is verified before any new
code builds on `try_apply_op` (build order step 2).

---

## 7. Ingestion (`alpha/meta/ingest.py`)

- `from_text(text, title="") -> LessonSource` — the paste path.
- `fetch_url(url, *, fetcher=None) -> LessonSource` — default fetcher = stdlib `urllib` GET +
  `html.parser`-based text strip (zero new deps, matching the existing urllib-based `AlpacaSource`).
  The fetcher is an injectable seam so tests run fully offline. Fetch failures raise a typed error the
  route turns into "couldn't read that URL — paste the text instead."

---

## 8. Web layer (`alpha_web`)

**Nav reshuffle (a breaking change to a tested public route — surfaced explicitly):** `/` = cockpit;
Deck → `/deck`; `/evolution` stays as the **Autonomous** batch timeline (unchanged content). `NAV` is
rewritten; the existing dashboard test moves from `/` to `/deck`, and `test_pages_render` (or equivalent
parametrized route test) is updated so `/` asserts cockpit content. This migration is an explicit
sub-task of the cockpit slice (§10).

**Brain access is stateless and split read/write:**
- `data_access.load_brain()` is **extended** (signature unchanged, still returns `HarnessState`) to
  prefer `LiveBrainStore` and fall back to seeds when the store is empty/uninitialized. It is
  **side-effect-free on read** — a `GET` never writes; initialize-from-seeds-on-disk happens only in the
  cockpit's apply/init path. A mis-shaped on-disk brain falls back to seeds with a banner (same
  defensive pattern as `_decision_context`/`_verdict_context`), never a 500.
- A new `brain_badge() -> {is_live: bool, edit_count: int}` reads the `LiveBrainStore` `EditLog` length +
  live/seed status and is injected as a template global for the "live · N edits" / "seed baseline" badge.
  This keeps `load_brain()`'s return type unchanged so existing callers/tests stay green.

**Routes (mutations — the app is no longer read-only):**

| Method/Path | Purpose |
|---|---|
| `GET /` | Cockpit — always a fresh draft (no auto-resume in v1). |
| `GET /deck` | The former dashboard. |
| `POST /evolve/ingest` | text/url → create+persist an `open` `Session` + `LessonSource`; `propose_directions`; return directions partial. |
| `POST /evolve/{session_id}/direction` | `{direction_id, comment}` → `expand_to_edits`; persist; return edit-queue partial. |
| `POST /evolve/{session_id}/direction/regenerate` | `{comment}` → re-`propose_directions`. |
| `POST /evolve/{session_id}/edit/{edit_id}` | `accept`/`reject` (pure state) **or** `tweak` (mutate `args`, no LLM) **or** `comment` → `repropose_edit` (scoped 1-op LLM). Return the row partial. |
| `POST /evolve/{session_id}/apply` | under a mutation lock: copy current brain → `snapshot_before`; `apply` accepted edits; persist live brain atomically; set `status='applied'`; return result partial. |
| `GET /evolve/sessions[/{session_id}]` | browse session history. |
| `POST /evolve/rollback/{session_id}` | under the lock: restore `snapshot_before` into `LiveBrainStore`; append a note. |

**Concurrency & state-machine guards (single-process localhost v1):** all mutating routes (`apply`,
`rollback`) acquire a process-level `threading.Lock` so two requests can't interleave a load→mutate→save
and lose updates. `apply` is guarded by the session state machine — only an `open` session whose edits
include accepted rows may apply (server-side, not just disabled buttons) — preventing double-submit.

Each POST returns an HTML partial swapped via HTMX. LLM calls take 10–30 s → an htmx-indicator spinner +
disable-on-inflight handler. **Note:** the current `app.js` only has `htmx:beforeRequest`/`afterSwap`
fade hooks; the spinner/disable affordance is a *new* item to build (not a free extension), and the
Playwright loading-state test depends on it.

**Templates:** `cockpit.html` (home) + partials `directions.html`, `edit_queue.html`, `edit_row.html`,
`apply_result.html`, `session_list.html`. Existing `evolution.html` reused as-is at `/evolution`.

**Graceful degradation:** ingest/propose need `ANTHROPIC_API_KEY` at serve time; if missing the cockpit
shows "set your key or use mock mode" instead of erroring or attempting a propose.
`ALPHA_REFINER_PROVIDER=mock` gives a fully offline scripted demo.

---

## 9. Persistence & rollback (`alpha/meta/store.py`)

No `SnapshotStore`/`HarnessManager` in the cockpit path — for an interactive single-brain flow they add
a per-request rebind hazard and a double-write without buying version-tree navigation we don't need.

- `LiveBrainStore(root)` — persists `HarnessState.to_dict()` + `EditLog.to_dict()` as one JSON
  (`brain.json`). `load() -> (HarnessState, EditLog)`; with an empty/missing root it returns seeds
  in-memory (and does **not** write — writing happens only via `save()` on the apply/init path).
  `save(harness, log)` writes atomically (temp + `os.replace`). `edit_count()`/`is_live()` back the badge.
- **Rollback by file copy:** `POST /evolve/{id}/apply` first copies the current `brain.json` to
  `state/brain/history/<session_id>.json` and records that path as `Session.snapshot_before`. Apply then
  mutates the in-memory `(harness, log)` and `save()`s atomically; **on a save failure the in-memory
  state is discarded** (next request reloads from the unchanged file), so on-disk and in-memory can never
  diverge. `POST /evolve/rollback/{id}` copies `snapshot_before` back over `brain.json` and appends a
  session note. Simple, no rebind hazard, point-in-time semantics (restores the pre-apply brain; later
  applies after it are not individually undoable — stated in the session-list UI).
- `SessionStore(root)` — atomic JSON keyed by `session_id`; `put`, `get`, `list()` (newest first by
  `session_id`). Same atomic-write pattern as `DecisionStore`/`VerdictStore` (which key by date / run-name
  respectively).
- Roots via env: `ALPHA_LIVE_BRAIN_DIR` (default `./state/brain`), `ALPHA_SESSIONS_DIR`
  (default `./state/sessions`). **Build step:** append `/state/` to `.gitignore` (it is not currently
  ignored). A web-test `conftest` fixture pins both env vars to `tmp_path` so the suite never reads or
  writes a developer's real `./state/`.

---

## 10. Error handling & testing

**Error handling — never a 500, always recoverable:**
- LLM failure / missing key / timeout → friendly partial, draft preserved, retry button.
- Bad model output → `parse_ops` is tolerant; surface "couldn't use that — regenerate," keep raw for
  debugging.
- Preview/apply is per-edit: a gate-blocked or immutable-doctrine op becomes a `failed` row with its
  reason inline; partial apply is fine and recorded; `snapshot_before` allows wholesale rollback.
- URL fetch failure → paste-the-text fallback.
- Mis-shaped persisted brain/session → seed/empty fallback with banner, same as the decision/verdict
  pages.

**Testing (TDD, fully offline via `MockLLMClient` + injected fetcher):**
- Model round-trips (all four models).
- Stores: `LiveBrainStore` seed-fallback-on-empty + `save()`/`load()` + no-write-on-read; atomic writes;
  rollback file copy; `SessionStore` put/get/list.
- `try_apply_op` refactor: existing `tests/refine/test_refiner_*.py` stay green (behavior-identical) +
  new teaching-path (all-tools) + immutable-doctrine rejection + promote-expectancy gate.
- `MetaAgent` (mock JSON): `propose_directions` parses N; `expand_to_edits` dry-run produces correct
  before/after payloads from the throwaway copy and leaves the live brain untouched; a bad-field op →
  `failed` row (no raise); `apply` mutates for real + returns `EditRecord`s; `repropose_edit` replaces one
  row by `edit_id`; red-line edit rejected with reason.
- Ingest: `from_text`; `fetch_url` with a fake fetcher; failure path.
- Web routes (`httpx` TestClient, mock provider, tmp `ALPHA_LIVE_BRAIN_DIR`): drives
  ingest→direction→edit(accept/tweak/comment)→apply→rollback; asserts partials, that the live brain
  mutated and a session persisted, and that rollback restores; graceful-degradation with no key; the
  mutation lock / state-machine guard rejects an out-of-state apply.
- **Live-brain read-wiring regression:** the deck-count and other seed-count assertions are re-pointed at
  a fixed seed fixture (or a tmp `LiveBrainStore` seeded into `tmp_path`) and the deck-count test moves to
  `/deck`; `brain_badge()` reads correctly for empty (seed) vs populated (live) stores.
- Playwright screenshot of the cockpit + the multi-step HTMX flow incl. the new loading state.

**Build order — vertical slices, each shippable + green before the next:**
1. **Models + `LiveBrainStore`/`SessionStore`** (pure data, offline; incl. rollback file copy).
2. **`try_apply_op` refactor** — Refiner regression-green is the gate.
3. **`MetaAgent`** propose/expand(dry-run)/apply/repropose against `MockLLMClient` (offline).
4. **Ingest** (text + URL seam).
5. **Live-brain read-wiring** — `load_brain()` prefer-store-with-seed-fallback + `brain_badge()` + the
   web `conftest` tmp fixture + re-pointed seed-count tests. Its own slice with a full regression pass
   over the existing web suite, **before** the cockpit routes.
6. **Cockpit routes + templates + HTMX + nav reshuffle** (incl. the `/` → `/deck` test migration and the
   loading-state affordance).
7. **Playwright verify** + optional real-key smoke once offline is green.

---

## 11. Roadmap follow-ups (explicitly deferred)

- **Self-learning channel:** add a reflection→directions stage on top of the Refiner's evidence path (the
  Refiner currently emits ops directly; a direction-proposal stage does not yet exist), surfaced into the
  same cockpit so the agent proposes evolutions from its own task runs.
- **Image ingestion:** chart/screenshot teaching via Claude vision (extend the LLM client for image
  content blocks; add upload handling).
- **Auto-resume** an in-flight draft on `GET /` (render partials matching `Session.status`; re-validate
  dangling `target_id`s against the current brain).
- **Post-apply red-line lint:** flag a taught skill/lesson whose `taboo`/`entry` contradicts an immutable
  doctrine section.
- **General meta-agent core:** lift teach + self-learn off the trading-specific `doctrine/skills/memory`
  onto a domain-agnostic representation; trading becomes the first instance.
- **Branchable named brains**; snapshot retention/pruning if a version tree is reintroduced; multi-user /
  auth / non-localhost.

---

## 12. Naming & file map (new)

```
alpha/meta/
  __init__.py
  models.py        # LessonSource, ProposedDirection, ProposedEdit, Session
  agent.py         # MetaAgent (propose_directions / expand_to_edits / apply / repropose_edit)
  prompts.py       # render_brain_summary + 3 builders (directions, edits, single-edit re-propose)
  ingest.py        # from_text, fetch_url (injectable fetcher)
  store.py         # LiveBrainStore, SessionStore
alpha/refine/apply.py        # extracted shared try_apply_op (Refiner + MetaAgent)
alpha_web/
  app.py           # + cockpit GET/POST routes, /deck, nav reshuffle, mutation lock
  data_access.py   # load_brain() prefer-LiveBrainStore (seed fallback, no write-on-read) + brain_badge()
  templates/cockpit.html + partials/{directions,edit_queue,edit_row,apply_result,session_list}.html
  static/app.js    # + htmx loading-state (spinner/disable-on-inflight)
  conftest or tests/web/conftest.py   # pins ALPHA_LIVE_BRAIN_DIR/ALPHA_SESSIONS_DIR to tmp_path
tests/meta/ + tests/web/ (new test modules)
.gitignore         # + /state/
```
```
