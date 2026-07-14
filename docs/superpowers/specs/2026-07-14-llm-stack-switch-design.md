# LLM Stack Switch — Claude Fable ↔ DeepSeek per entity (design)

Date: 2026-07-14 · Status: approved by user (brainstorm session) · Builds on the `claude_code`
provider shipped earlier the same day (subscription-quota Fable 5 via `claude -p`).

## Goal

A UI-visible option to switch the LLM between **Claude Fable** and **DeepSeek**, per charter
entity — one switch for **Sonia** (roles `sonia` + `refiner`) and one for **Kairos** (roles
`agent` + `converse`) — taking effect on the **next LLM call** (mid-chat-session included),
applying **globally** (both web faces *and* CLI batch scripts), and **surviving restarts**.

## Decisions (user-confirmed)

| Question | Decision |
|---|---|
| Switch surface | Web UI (the :8100 console), instant effect, no service restart |
| Granularity | Per entity: Sonia (`sonia`,`refiner`) / Kairos (`agent`,`converse`) |
| Scope + persistence | Global (web services + CLI scripts) via a shared state file; survives restart |
| Mid-session switching | Yes — falls out of per-request `make_client` + per-call file read |

## Rejected alternatives

- **Per-service in-memory settings endpoints** — not persistent, CLI scripts unaffected;
  violates the chosen scope.
- **Console rewrites env + restarts services** — requires restart; violates instant effect.

## Architecture

One tiny shared JSON state file is the single source of truth; every process that calls
`make_client` reads it per call. The console writes it. No service imports another (unchanged);
the file is shared on-disk state in `./state`, the same pattern as the shared live brain.

### 1. Named stacks + entity map (`alpha/llm/config.py`)

```python
STACKS = {
    "claude":   ("claude_code",   "claude-fable-5"),   # re-point to claude-opus-4-8 after 2026-07-19
    "deepseek": ("openai_compat", "deepseek-chat"),    # the valid live id, NOT deepseek-v4-pro
}
ROLE_ENTITY = {"sonia": "sonia", "refiner": "sonia", "agent": "kairos", "converse": "kairos"}
```

Both stacks are defined in exactly one place; the post-promo Fable→Opus re-point is a one-line
edit.

### 2. State file + resolution precedence

- Path: `state/llm_stack.json`, overridable via `ALPHA_LLM_STACK_FILE` (tests isolate it through
  `brain_session_isolation`). Shape: `{"sonia": "claude", "kairos": "deepseek"}` — entities may
  be absent (→ fall through).
- Precedence in `make_client(role)`:
  1. explicit `ALPHA_<ROLE>_PROVIDER` / `ALPHA_<ROLE>_MODEL` env (expert escape hatch, highest);
  2. the entity's stack from the state file;
  3. existing `_DEFAULTS`.
  Env and file compose per-field the same way env currently composes with `_DEFAULTS`: provider
  and model each resolve independently through the same 1→2→3 chain.
- Fail-safe reads: file missing / unparseable / unknown stack name → that layer is skipped
  (falls through to `_DEFAULTS`), one warning log line, never an exception. File is read on every
  `make_client` call (it is tiny; no cache invalidation complexity).
- Atomic writes: tmp file + `os.replace` in the same directory.

### 3. Console UI + write endpoint (`alpha_web`)

- New "Models" settings surface (nav entry): two rows — Sonia and Kairos — each a dropdown with
  the current stack selected, showing the resolved provider/model id. When an entity's resolved
  (provider, model) matches no named stack (e.g. env-pinned roles or a mixed override), the row
  shows an "env-pinned (custom)" indicator instead of falsely highlighting a stack; the dropdown
  still works and writes the file, but the env pin will keep winning until removed (the badge
  says so).
- Change → POST `/settings/llm` (form/HTMX, matching existing console patterns) → alpha_web
  writes the state file directly (shared working dir; operational config, not an H mutation —
  the read-only-console posture concerns the brain, which this never touches).
- Warning badge when the selected stack's credential is missing in the *console's* env
  (`DEEPSEEK_API_KEY` for deepseek; `claude` CLI presence for claude) — best-effort hint only,
  since each service resolves its own env; the authoritative failure surface stays the faces'
  existing error boundaries (sonia `/chat` already degrades gracefully).

### 4. Ops prerequisite (the one real gotcha)

For a runtime switch to DeepSeek to work inside a running service, that service's env must
have `DEEPSEEK_API_KEY` **without** the `ALPHA_*` role overrides from `.env.deepseek` (those
sit at precedence 1 and would pin the roles). Therefore:

- Split `.env.deepseek` into the key-only part (`DEEPSEEK_API_KEY`, always safe to source) and
  an optional role-override section moved to `.env.deepseek.roles` (sourced only when explicitly
  pinning roles).
- Service start recipe: source key-only env file(s) (+ `.env.alpaca` for workbench), keep
  `ANTHROPIC_API_KEY` unset (it silently flips the claude stack to metered API billing).

### 5. Error handling

- Unknown stack value POSTed → 422, file unchanged.
- File says `deepseek` but the key is missing in a face's env → that face's existing per-request
  error boundary reports it (sonia: graceful assistant message; workbench: surfaced error);
  console badge forewarns.
- Concurrent writes: single writer (console) + atomic replace; readers only ever see a complete
  old or new file.

### 6. Testing (all offline)

- Resolution precedence unit tests: env > file > defaults; per-field composition; both entities.
- Fail-safe: missing file, corrupt JSON, unknown stack name → defaults, no raise.
- Atomic write round-trip; `ALPHA_LLM_STACK_FILE` honored.
- alpha_web: GET settings page renders current stacks; POST switches + persists; 422 on junk;
  missing-credential badge logic.
- Isolation: `brain_session_isolation` gains the stack-file tmp path so face tests never touch
  the operator's real `./state`.

## Mid-session semantics (explicit)

Both chat faces construct a fresh client per message and both providers are stateless per call
(full history re-sent each turn), so flipping the switch changes the model for the **next
message of an ongoing session**. The switch is global: it affects all sessions of that entity,
not only the one currently open.
