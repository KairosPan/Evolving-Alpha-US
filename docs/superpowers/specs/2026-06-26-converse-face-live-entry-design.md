# Conversational Face — Live Entry Point (Workbench) Design

> Status: **APPROVED** (brainstormed 2026-06-26). Next: writing-plans.
> Scope: v1 of giving the B-WIDE conversational face (`alpha/converse/`) a live, usable entry point.

## Goal

Today evolving-alpha's conversational face (`alpha/converse/{converse, converse_project, build_converse_registry}`) exists only as library code reachable from tests. **Give it a live entry point** so the user can actually converse with evolving-alpha — have it answer in its own voice, run a real point-in-time `decide` for a date, produce artifacts into a git-backed project workspace, and **propose changes to its own brain that the user previews and approves** before they touch the live H.

This is the payoff of the Phase-1A (converse package) → 1B (decide-for-date) → §4 (project workspace) arc.

## Confirmed decisions (from brainstorming)

1. **Write semantics = preview & approve.** A conversational brain edit is *staged* as a pending proposal (dry-run validated, never applied during the turn); it touches the live brain only when the user approves — mirroring the Sonia teaching cockpit's edit→apply flow.
2. **Placement = an independent third service** (`workbench`, :8820), NOT folded into Sonia and NOT run inside `alpha_web`. The conversational face is evolving-alpha's *own* face; Sonia is the *teacher* face; they stay separate processes.
3. **Cross-process brain writes = self-held `LiveBrainStore` + a file lock.** The workbench service owns its own `LiveBrainStore` on the shared `ALPHA_LIVE_BRAIN_DIR` (no HTTP coupling to Sonia). A cross-process file lock (`fcntl`, zero new deps) guards the load→mutate→save / snapshot / restore critical sections so the two services never clobber each other.
4. **v1 scope = a single default project.** One ongoing conversation + its git workspace; multi-project create/list/switch UI is deferred to v2.

## Architecture

Three processes share **one brain** (`ALPHA_LIVE_BRAIN_DIR`):

- **Sonia** (`:8810`, existing) — the teaching face; owns its own `LiveBrainStore`.
- **`workbench`** (`:8820`, NEW) — the conversational face; owns its own `LiveBrainStore` + a `ProjectStore` + a `Workspace` + a data `source` + the `converse`/`agent` LLM clients.
- **`alpha_web`** (`:8100`, existing) — the read-only console; gains a **Workbench** page that is a thin HTTP client over `workbench` (exactly as the existing cockpit is a thin client over Sonia).

```
 alpha_web (:8100)  ──HTTP──►  workbench (:8820) ──┐
   /workbench page              converse loop      │  fcntl file lock
   WorkbenchClient              ProjectStore        ├─►  ALPHA_LIVE_BRAIN_DIR  ◄── Sonia (:8810)
                                Workspace (git)     │     (LiveBrainStore)
                                LiveBrainStore  ────┘
```

### New service `workbench/` (mirrors `sonia/`)

- `workbench/app.py` — `create_app() -> FastAPI`, env-wired stores (same idiom as `sonia/app.py::_brain_store/_session_store`):
  - `_brain_store()` → `LiveBrainStore(ALPHA_LIVE_BRAIN_DIR)` (now file-locked; shared with Sonia)
  - `_project_store()` → `ProjectStore(ALPHA_PROJECTS_DIR)` (§4)
  - `_workspace(pid)` → `Workspace(ALPHA_WORKSPACE_DIR/<pid>)` (§4), `.init()` on first use
  - `_source()` → `make_source()` (the data layer; for `decide`-for-date)
  - LLMs via `make_client("converse")` (chat) and `make_client("agent")` (decide)
  - a module-level `_MUTATION_LOCK = threading.Lock()` for in-process serialization (same as Sonia), layered over the cross-process file lock
- `workbench/__main__.py` — `uvicorn.run("workbench.app:app", host=ALPHA_WORKBENCH_HOST or 127.0.0.1, port=ALPHA_WORKBENCH_PORT or 8820)` (copy `sonia/__main__.py`).
- The single default project uses a fixed id `DEFAULT_PROJECT_ID = "default"`, auto-created on first `/converse`.

## The preview/approve write flow (the crux)

The converse registry's write tool changes from **apply-direct** to **stage-a-proposal**:

- **`alpha/converse/tools.py::make_propose_edit_tool(harness)`** (NEW) — a registry tool that, instead of calling `try_apply_op` on the live harness, **dry-run validates** the op on a `deepcopy` scratch harness through `try_apply_op` (exactly how `alpha/meta/agent.py::preview_op` validates against a scratch copy) and returns a JSON-safe staged record:
  `{"staged": true, "edit_id": <id>, "tool": ..., "op": <RefineOp dump>, "summary": ..., "valid": <bool>, "reason": <str|None>, "preview": {...before/after...}}`. It never mutates the live brain.
- **`alpha/converse/agent.py::build_converse_registry(..., write_mode: str = "apply")`** (additive param) — `write_mode ∈ {"apply","stage","none"}`. `"apply"` keeps today's `make_gated_write_tool` (back-compat default; existing callers + tests unchanged). `"stage"` registers `make_propose_edit_tool`. `"none"` registers neither (read-only). The workbench service uses `"stage"`.
- **`alpha/converse/session.py::converse_project`** — gains an additive `write_mode: str = "apply"` param threaded into `build_converse_registry`; when a turn's `tool_calls` include `{"staged": true, ...}` results, it materializes them into a new `Project.staged_edits` list (status `"pending"`). (converse_project already owns Project mutation + JSON-safe tool_calls; this is the one addition. Default `"apply"` keeps the §4 tests unchanged.)
- **`alpha/converse/project.py`** gains `StagedEdit` (`edit_id, op: dict, summary, valid, reason, preview: dict, status: Literal["pending","approved","rejected"], snapshot_before: str = "", applied_seq: int | None = None`) and `Project.staged_edits: list[StagedEdit] = []`.

Approval is a workbench endpoint, applied through the **same gate** under the **same lock** as any live mutation.

## Endpoints (`workbench/app.py`)

| Method · path | Behavior |
|---|---|
| `GET /healthz` | `{ok, brain_live, edit_count}` (copy Sonia's) |
| `POST /converse` `{text}` | Load the live brain fresh (read context + `decide`), run one `converse_project` turn (registry in `write_mode="stage"`, the default project, the project's `Workspace` for artifacts); persist the turn; return `{project_id, assistant_text, staged_edits:[…pending…], artifacts:[…git ls-files…]}`. Never 500 → on any LLM/source error, return an assistant fallback message and keep the user turn. |
| `GET /project` | The default `Project`: messages, `staged_edits` (pending first), and `artifacts` (the workspace's `git ls-files`). |
| `POST /edits/{edit_id}/approve` | Under `_MUTATION_LOCK` **and** the brain file lock: snapshot the live brain → re-run the op through `try_apply_op` on the **live** harness (provenance `path=teaching, proposer=hermes`) → `save` → mark the `StagedEdit` `approved` + record `applied_seq` + `snapshot_before`. 404 if unknown. |
| `POST /edits/{edit_id}/reject` | Mark the `StagedEdit` `rejected` (no brain touch). 404 if unknown. |
| `POST /rollback` | Restore the most recent `snapshot_before` via `LiveBrainStore.restore` (under the lock); note it on the project. |

### `LiveBrainStore` file lock (`alpha/meta/store.py`)

Add a cross-process lock (stdlib `fcntl.flock` on a `<root>/.brain.lock` file) held around the body of `save`, `snapshot`, and `restore` (and the read in `load` for snapshot consistency). Additive + safe for the existing single-writer Sonia (it just takes an uncontended lock). A blocking acquire with a bounded timeout; on timeout, raise a clear `RuntimeError` (never silently skip the write). This is the ONE change to a shared, brain-owning class — kept minimal and behavior-preserving for existing callers.

## UI — `alpha_web` Workbench page

- **`alpha_web/sonia_client.py`-sibling `alpha_web/workbench_client.py::WorkbenchClient`** — thin httpx wrapper (copy `SoniaClient`): `converse(text)`, `get_project()`, `approve_edit(edit_id)`, `reject_edit(edit_id)`, `rollback()`, `healthz()`. Base URL from `ALPHA_WORKBENCH_URL` (default `http://127.0.0.1:8820`); test-injectable `client=`.
- **`alpha_web/app.py`** — a top-level **Workbench** nav entry + routes: `GET /workbench` (render the project), `POST /workbench/say` (call `converse`, re-render the thread), `POST /workbench/edits/{id}/approve|reject` (HTMX empty-200 row-removal of the proposal, mirroring the conflicts UI), `POST /workbench/rollback`. Workbench-unavailable → a banner, never a 500 (mirror `_sonia()` error handling).
- **`alpha_web/templates/workbench.html`** — `{% extends "base.html" %}`: a chat thread (user/assistant turns), a **decide/artifacts** side panel (the project workspace's committed files), and a **pending proposals** panel (each staged edit: tool + summary + the dry-run preview + **Approve**/**Reject** buttons). All fields via Jinja2 `{{ }}` (autoescape ON); **no raw f-string HTML reflection** (the conflicts-UI XSS lesson). HTMX swap attributes match the existing cockpit style.

## Error handling

- workbench never 500s a conversation: any LLM/source exception in `/converse` → an assistant fallback message, user turn preserved (copy Sonia's `try/except` in `/chat`).
- file lock: bounded blocking acquire; timeout → explicit `RuntimeError`, surfaced as a 503-ish JSON, never a silent no-op.
- alpha_web: `WorkbenchClient` errors caught → "workbench unavailable" banner.
- approve/reject/rollback on unknown ids → 404, never a 500.

## Testing (all offline, deterministic)

- **workbench service** (`tests/workbench/`): `MockLLMClient` (chat + decide) + `FakeSource` + tmp `ALPHA_LIVE_BRAIN_DIR`/`ALPHA_PROJECTS_DIR`/`ALPHA_WORKSPACE_DIR`; Starlette `TestClient(create_app())`. Cover: a converse turn stages a proposal + commits a decide artifact; approve applies through the gate (live brain edit_count rises, snapshot taken); reject leaves the brain unchanged; rollback restores; unknown-id 404s.
- **`make_propose_edit_tool`** (`tests/converse/`): a staged op is dry-run validated on a scratch harness and the **live** harness is unchanged (the proposal does not apply).
- **`LiveBrainStore` lock** (`tests/meta/`): two sequential lock acquisitions on the same dir serialize; a held lock blocks then proceeds (bounded); behavior-preserving for existing single-writer callers.
- **`WorkbenchClient` + Workbench page** (`tests/web/`): inject a workbench `TestClient`; the page renders the thread + pending proposals + artifacts; approve/reject returns empty-200 and removes the proposal; an injected `"><img onerror>` style value is escaped (XSS regression, per the conflicts-UI lesson).

## Out of scope (deferred to v2)

- Multi-project create/list/switch UI + per-project H-version pinning surface (the §4 machinery supports it; v1 uses one default project).
- Apply-directly write mode for the converse face (v1 is preview/approve only).
- Live-order / execution tools exposed to the conversational face (the design doc §7 keeps live-order off the B-WIDE face).
- Wiring a live offline Refiner run to feed the §5 conflict queue (separate follow-up).
- Streaming responses; multi-user concurrency beyond the file-lock safety floor.

## Why this shape

- **Independent service** honors "evolving-alpha's own face ≠ the teacher" cleanly, and keeps `alpha_web` read-only (it only ever renders thin clients).
- **Self-held LiveBrainStore + file lock** gives that independence without HTTP coupling, and is the correct (not just convenient) cross-process write-safety primitive.
- **Preview/approve** keeps the user in control of live brain evolution and reuses the exact discipline (snapshot → gate → save → rollback) the system already trusts.
- **Reusing §4** (`Project`/`ProjectTurn`/`ProjectStore`/`Workspace`) and **§5** (provenance on every gated edit) means the new surface is mostly *wiring already-built, already-reviewed organs* to a live entry — small, low-risk, high-payoff.
