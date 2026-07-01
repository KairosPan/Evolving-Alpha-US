# Agent-Modification Drawer (right-side "Agent" cockpit) — Design

**Date:** 2026-06-30
**Status:** Approved (brainstorming), pending implementation plan.

## 0. Goal

Give the Teach page (`/`) a **resizable, collapsible right drawer** — the place
where a teaching conversation visibly *lands as concrete edits to the agent's
brain*. The left column stays the teach chat; the right drawer is the
agent-modification surface, split into two stacked accordion sections:

- **PENDING** (top) — the open session's proposed/accepted edits, moved out of
  the chat bubbles. Per-edit accept/reject, one **Apply accepted (N)** action,
  and **↶ rollback last apply**.
- **CURRENT brain** (bottom) — all six brain components mirrored from the *live*
  brain. Doctrine / Memory / Skills expand to their live items; Workflow /
  Connector / Subagent are read-only stub rows. **Refreshes after every
  apply/rollback** so the operator watches the agent change.

Chat bubbles become prose-only; a turn that proposes edits shows a
**"N proposed changes →"** chip that highlights the drawer.

This round is **UI/surfacing-first**: the teach→edit machinery already exists
and works (propose → accept/reject → apply → rollback via `MetaTools`/`EditLog`).
We are relocating and elevating that landing surface into a dedicated drawer and
adding a live read-only mirror of the brain beside it. No new brain-edit
capability, no new gate, no changes to the write-waist.

## 1. Background (current state)

- The Teach cockpit (`alpha_web/templates/cockpit.html`) is a two-column
  app shell (234px left rail + a center `.thread-wrap` chat). **There is no
  right panel today.** `.cockpit { display:flex; gap:1rem }` in
  `alpha_web/static/cockpit.css`.
- Teaching flow: composer `POST /evolve/message` → `sonia_client.chat()` →
  Sonia `/chat` returns prose + **proposed edits** (`ProposedEdit`, status
  `proposed`). Today those render as **inline edit cards inside the assistant
  bubble** (`partials/edit_card.html`) with accept/reject
  (`POST /evolve/{sid}/edit/{eid}`), then **Apply accepted**
  (`POST /evolve/{sid}/message/{mid}/apply`) and rollback
  (`POST /evolve/rollback/{sid}/{mid}`).
- The write-waist is real and unchanged by this round: apply calls
  `MetaAgent.apply()` → `try_apply_op` → `MetaTools` → one `EditRecord`
  appended to the append-only `EditLog`; a pre-apply snapshot backs rollback.
  Apply and rollback are **per-message** (snapshot keyed `"{sid}-{mid}"`).
- The live brain is owned by the Sonia service and persisted to
  `{ALPHA_LIVE_BRAIN_DIR}/brain.json` (default `./state/brain`). **alpha_web
  reads that same file** via `alpha_web/data_access.py::load_brain()` — it
  prefers the `LiveBrainStore` when `ALPHA_LIVE_BRAIN_DIR` is set and live, else
  frozen seeds. There is **no cache**: every GET reads fresh from disk, so a
  just-applied edit is reflected immediately. The existing `/doctrine`,
  `/memory`, `/skills` pages already render from `load_brain()`.
- Sonia exposes **no** brain-state GET endpoint (only `/healthz`, `/sessions*`,
  `/conflicts`). `sonia_client` has chat/edit/apply/rollback/sessions/conflicts
  only. **The drawer needs no new Sonia endpoint** — CURRENT brain reuses
  `data_access.load_brain()`.
- The console is FastAPI + Jinja2 + **vendored HTMX**, no JS framework. It
  already uses `hx-swap-oob` (the composer's hidden `session_id` is updated
  out-of-band). The left brain drawer's expand/collapse is a tiny vanilla JS
  toggle in `app.js`. This design follows the same house style.

## 2. Scope of change (what moves, what's new)

| Element | Change |
|---|---|
| Assistant chat bubble | **Remove** inline `edit_card` controls; **add** a "N proposed changes →" chip when the message has edits. Prose still markdown-rendered. |
| Right drawer | **New.** `<aside class="agent-drawer">` beside `.thread-wrap`. |
| PENDING section | **New** home for the edit cards + accept/reject + Apply/rollback (same underlying endpoints). |
| CURRENT brain section | **New** live read-only mirror of the six components. |
| Apply / rollback semantics | **Unchanged** (per-message snapshot; write-waist untouched). |
| Sonia service | **Unchanged** (no new endpoint). |
| Nav | **Unchanged** (no new nav item; drawer lives on `/`). |

## 3. Approach (chosen: server-rendered partials + HTMX OOB)

**A. Server-rendered partials + HTMX out-of-band swaps (CHOSEN).** The existing
mutation endpoints additionally return `hx-swap-oob` fragments that update the
PENDING section, the CURRENT-brain section, and the chip. Fits the house style
exactly (already OOB-swaps `session_id`; vendored htmx; no framework). Only new
JS is vanilla drag-resize + collapse (mirrors the brain-accordion toggle).
Snappy, idiomatic, testable via rendered HTML. Cost: OOB threaded through four
endpoints carefully.

Rejected alternatives (recorded for the plan):

- **B. One `/evolve/drawer` endpoint reloaded via `hx-get`.** Single render path
  but an extra round-trip per action and a full re-render each time (loses
  expand/scroll state). Simpler to test, less snappy.
- **C. Client-side JS store off Sonia's JSON.** Introduces a client state layer
  the repo deliberately avoids; diverges from HTMX-first house style.

We take **A**, borrowing one idea from **B**: a single `_drawer.html` template
(with `_pending.html` + `_brain_panel.html` sub-partials) that the mutation
endpoints re-emit as OOB fragments. One template, OOB updates.

## 4. Components

### 4.1 View-model — `alpha_web/drawer.py` (new, thin, unit-testable)

Pure functions, no I/O beyond being handed the inputs; keeps `app.py` handlers
thin and gives a tested seam:

- `pending_view(session) -> PendingView` — flatten the session's messages into
  actionable edits grouped by status. Fields (illustrative — finalized in the
  plan): the ordered edit rows (each carrying `session_id`, `message_id`,
  `edit_id`, `tool`, `target`, `summary`, `status`, `apply_reason`), the count
  of `accepted` edits (for the "Apply accepted (N)" footer), and the most-recent
  applied `message_id` (for "rollback last apply"). Edits with terminal status
  `applied` collapse to a thin "applied ✓ · rollback" line rather than a full
  card.
- `brain_view(harness) -> BrainView` — build the six-component summary from a
  `HarnessState`: for the three live kinds (doctrine/memory/skills) a count plus
  the live item rows (reusing the existing compact fields the brain pages
  already surface); for the three stub kinds a fixed `{title, blurb}` (reuse the
  left-drawer stub copy) marked read-only. Never raises on an empty/partial
  brain.

`BrainView` reads from `data_access.load_brain()` in the route, not inside the
view-model, so the pure function stays trivially testable with a constructed
`HarnessState`.

### 4.2 Templates (`alpha_web/templates/`)

- `cockpit.html` — add `<aside class="agent-drawer" id="agent-drawer">` beside
  `.thread-wrap`; wrap both in the resizable 2-col grid; include `_drawer.html`.
- `partials/_drawer.html` — drawer shell: the resize handle, the collapse
  toggle button (`aria-expanded`), and the two accordion sections. Includes:
  - `partials/_pending.html` — renders `PendingView`: the edit rows (reusing
    `edit_card.html` markup for a row), the footer **Apply accepted (N)**
    (`hx-post` to the per-message apply; disabled when N=0 or Sonia down) and
    **↶ rollback last apply** (disabled when nothing applied). Wrapped in
    `id="pending"` so it is OOB-swappable.
  - `partials/_brain_panel.html` — renders `BrainView`: six component accordions;
    the three live ones expand to item rows with a "→ open full page" link to
    the existing `/doctrine|/memory|/skills`; the three stubs are
    non-expandable read-only rows. Wrapped in `id="brain-panel"`.
- `partials/message_assistant.html` — **remove** the inline edit-card loop; when
  the message has edits, render the `.change-chip` ("N proposed changes →",
  links/scrolls to `#agent-drawer` and flashes it). Prose unchanged.
- `partials/_two_turns.html` — after the two turns, also emit OOB fragments:
  `<div id="pending" hx-swap-oob="true">…</div>` and the brain panel, so a teach
  turn updates the drawer in the same response.

### 4.3 Routes (`alpha_web/app.py`) — extend, don't add

No new nav route. Each handler additionally renders the drawer partials as OOB
(the view-models make this a couple of lines each):

- `GET /` (`home`) — pass the drawer context: `pending_view(session)` +
  `brain_view(load_brain())`. Renders the full page including the drawer.
- `POST /evolve/message` — return `_two_turns.html` (prose + chip) **plus** OOB
  `#pending` (new edits appended) and OOB `#brain-panel` (unchanged this turn,
  cheap to re-render).
- `POST /evolve/{sid}/edit/{eid}` — return the updated edit row **plus** OOB
  `#pending` footer count ("Apply accepted (N)").
- `POST /evolve/{sid}/message/{mid}/apply` — return the apply result **plus** OOB
  `#pending` (applied edits collapse to the applied line) and OOB `#brain-panel`
  (now re-read from `load_brain()`, reflecting the mutation — the visible
  landing).
- `POST /evolve/rollback/{sid}/{mid}` — return the rollback result **plus** OOB
  `#pending` and OOB `#brain-panel` (reverted).

### 4.4 CSS / JS

- `alpha_web/static/cockpit.css` — turn `.cockpit` into a grid
  `grid-template-columns: 1fr var(--drawer-w, 22rem)` (chat | drawer) with the
  `.drawer-resizer` handle between; `.agent-drawer` styling; the collapsed state
  (`.agent-drawer.is-collapsed` → thin edge / `--drawer-w` clamped); the chat
  `.change-chip`; the two sections reusing the `.nav-group`/`.is-open` accordion
  pattern already in `app.css`.
- `alpha_web/static/app.js` (or a small `cockpit.js`) — vanilla:
  drag-to-resize (pointer events update `--drawer-w`, persisted to
  `localStorage`), collapse toggle (persisted), and the two section accordions.
  Mirrors the existing brain-drawer toggle handler. Consistent with the repo's
  untested-`app.js` posture (see §6).

## 5. Data flow & error handling

- **Teach turn** → `/evolve/message` → Sonia `/chat` → prose + chip; OOB append
  new edits to `#pending`.
- **Accept/reject** → `.../edit/{eid}` → Sonia updates status → OOB-update that
  edit row + the "Apply accepted (N)" count.
- **Apply** → `.../message/{mid}/apply` → Sonia mutates + persists the live brain
  → OOB `#pending` (applied edits → applied line) + OOB `#brain-panel`
  (`load_brain()` now reflects the change, e.g. a promoted skill flips to
  *active*). This is the visible landing.
- **Rollback** → `/evolve/rollback/...` → Sonia restores the snapshot → OOB
  `#pending` + `#brain-panel` revert.

Apply/rollback stay **per-message** under the hood (matching the existing
snapshot-per-message model). The PENDING footer's "Apply accepted" applies the
accepted edits of the message(s) that have them; because snapshots are
per-message, when the session has accepted edits across multiple messages the
handler applies them message-by-message (each with its own snapshot), and
"rollback last apply" targets the most recent applied message. (Common case:
one message with pending edits — a single apply. The plan will confirm the
multi-message case renders honestly, e.g. one applied line per message.)

Error handling (never-500 posture preserved):

- **Sonia unavailable** — `/` already renders the existing banner; the drawer
  still renders: PENDING shows an empty state, CURRENT brain still renders from
  disk (`load_brain()` is independent of Sonia). Apply/reject/rollback buttons
  are disabled while the banner is shown.
- **No live brain yet** (`ALPHA_LIVE_BRAIN_DIR` unset or not materialized) —
  `load_brain()` falls back to frozen seeds (existing behavior); counts still
  render. No write occurs on GET.
- **No edits in the session** — PENDING empty state; no chip in the bubble.
- **Gate-failed edit** — the row shows status `failed` + `apply_reason` (reuse
  existing `edit_card` handling).
- **Stub components** — non-expandable, explicitly labeled read-only.

## 6. Testing (offline, mirrors `tests/web`)

New `tests/web/test_drawer.py`, using the FastAPI `TestClient` pattern and the
shared `brain_session_isolation` fixture; Sonia mocked with the existing doubles.

- **View-model units** (`drawer.py`): `pending_view` flattens edits by status
  and computes the accepted-count and last-applied message; `brain_view`
  produces all six components from a constructed `HarnessState` (three live with
  item rows, three stubs), and does not raise on an empty brain.
- **`GET /`** renders the drawer: an `#agent-drawer` with `#pending` and
  `#brain-panel`, the brain panel containing all six component labels.
- **`POST /evolve/message`** returns the two-turns fragment with the
  `.change-chip` and OOB `#pending`/`#brain-panel`; the assistant bubble does
  **not** contain inline edit-card accept/reject controls (regression against
  the old layout).
- **Accept** (`.../edit/{eid}`) OOB-updates the "Apply accepted (N)" count.
- **Apply** (`.../message/{mid}/apply`) OOB-swaps `#brain-panel` reflecting a
  real mutation — e.g. seed a brain where applying the accepted edit promotes a
  skill, assert the panel now shows that skill *active*; and `#pending` shows the
  applied line.
- **Rollback** reverts both `#pending` and `#brain-panel`.
- **Sonia-down** path renders the drawer with empty PENDING + a brain panel from
  disk, buttons disabled, no 500.
- JS drag/collapse behavior itself is not unit-tested (consistent with the
  codebase's treatment of `app.js`); the server-rendered partials carry the
  tested state. An optional Playwright screenshot of resize/collapse may be
  added later but is not required for the core.

## 7. Out of scope (deferred)

- Any **new** brain-edit capability. This round only relocates/surfaces the
  existing propose→apply→rollback flow. Brain edits still originate exclusively
  from the Teach chat with Sonia via the unchanged write-waist.
- Editing the three stub components (workflow/connector/subagent) — read-only,
  as in the left brain drawer.
- A post-apply **preview/diff** overlay in CURRENT brain: PENDING *is* the diff;
  CURRENT shows the live committed brain, refreshed on apply. (Could be a later
  enhancement.)
- Cross-session aggregation: PENDING scopes to the open session.
- Putting the drawer on pages other than `/` (PENDING is teach-session-specific).
- A Sonia brain-state endpoint (not needed; `load_brain()` reads the same file).

## 8. Files touched (anticipated)

- `alpha_web/drawer.py` — **new** view-model (`pending_view`, `brain_view`).
- `alpha_web/app.py` — extend the five handlers to render + OOB the drawer
  partials; pass drawer context on `GET /`.
- `alpha_web/templates/cockpit.html` — add the right `<aside>` + resizable grid;
  include `_drawer.html`.
- `alpha_web/templates/partials/_drawer.html` — **new** shell.
- `alpha_web/templates/partials/_pending.html` — **new** PENDING section.
- `alpha_web/templates/partials/_brain_panel.html` — **new** CURRENT brain.
- `alpha_web/templates/partials/message_assistant.html` — drop inline cards; add
  the change chip.
- `alpha_web/templates/partials/_two_turns.html` — emit OOB drawer fragments.
- `alpha_web/static/cockpit.css` — grid, drawer, resizer, collapsed state, chip,
  accordions.
- `alpha_web/static/app.js` (or new `cockpit.js`) — drag-resize + collapse +
  section accordions.
- `tests/web/test_drawer.py` — **new** (view-model + route + OOB + apply-reflects
  + Sonia-down).
