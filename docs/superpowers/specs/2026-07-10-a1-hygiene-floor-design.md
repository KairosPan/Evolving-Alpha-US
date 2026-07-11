# A1 — Hygiene + observability floor

**Date:** 2026-07-10 · **Status:** APPROVED (user, 2026-07-10; two user rulings: TCB +2 additions; ledger at DEVELOPMENT-PLAN top)
**Mandate:** DEVELOPMENT-PLAN §2 A1 (*START HERE*; closes G12 + the redact leg of G3). Sources:
kairos-mining §1.1/§1.2/§1.5/§1.6/§2.1/§2.6/§2.7/§4.1/§4.3; modification-ladder spec §3+§8.5.
**Branch:** `feat/a1-hygiene-floor`; ff-merge to local `main` at the end; push only on explicit "push".

Seven deliverables, D1–D7. Global constraints: offline defaults byte-identical (the untouched
suite is the proof); everything stdlib-or-existing-deps (no new dependencies); English; every
deliverable lands TDD with a non-vacuous regression.

## D1 — `redact()` at the persistence waists (the verified leak)

**Leak (verified):** `LocalEnv.run` inherits the parent env, so a T2 shell `env` puts
`DEEPSEEK_API_KEY`/`APCA_*` values verbatim into persisted transcripts. Two channels reach the
converse DB: (a) `ProjectTurn.tool_calls[].result` inside the `turns` JSON blob
(`alpha/converse/session.py:77-82`; shell result dict `{ok, stdout, stderr, exit_code}` from
`alpha/arena/tools.py:52`), and (b) the duplicated `[tool:<name> result]\n…` text appended as a
`ChatMessage` by `run_conversation` (`alpha/converse/loop.py:63`), which lands in both the
`messages` table and the `messages_fts` index. A hook that only scrubs `tool_calls` misses (b).

**Design.** New module **`alpha/redact.py`** (pure stdlib, no intra-repo imports → zero cycle
risk):
- `collect_secrets(env=os.environ) -> dict[str, str]`: values of env vars whose NAME matches
  `KEY|SECRET|TOKEN|PASSWORD` (case-insensitive) and whose value is ≥ 8 chars (guards against
  redacting trivia like `1`); always includes the four known names
  (`DEEPSEEK_API_KEY`, `ANTHROPIC_API_KEY`, `APCA_API_KEY_ID`, `APCA_API_SECRET_KEY`) when set.
- `redact(obj, secrets) -> obj`: recursive over dict/list/str (pydantic-dumped JSON shapes);
  replaces each occurrence of a secret VALUE inside any string with `[REDACTED:<VARNAME>]`.
  Value-based, never pattern-based — precise by construction.

**Hook points (wrapping the waists covers every call site):**
1. `SqliteProjectStore.put` (`alpha/converse/sqlite_store.py:63-79`) — redact the dumped
   `turns` list and the `messages` texts before writing rows + FTS. **Never scrub**
   `staged_edits` (`StagedEdit.op/preview` are rollback-replay payloads — kairos-mining §1.5).
2. `SessionStore.put` (`alpha/meta/store.py:111-114`) — redact `Message.text` and
   `Attachment.text` (user-pasted/relayed secrets); **never scrub** `ProposedEdit` payloads
   (same replay rule). Redact on the dumped dict, then persist; the returned/held model objects
   are not mutated.
3. `record_task_episode` (`alpha/arena/experience.py:93-94`) — redact the verbatim
   `result["error"]` strings copied into `reflection_text` (the compact payload's one residual).

**Rules carried from mining §1.5:** key/credential-scoped ONLY — never scrub market/PIT data or
rollback-replay payloads. Ordering invariant recorded for A4: **redact before hash** (the future
chain hashes redacted bytes).

**Tests:** end-to-end regression — a fake T2 shell result carrying a planted secret value runs
through `converse_project` → `SqliteProjectStore.put`; assert the secret appears NOWHERE in the
DB file (raw sqlite dump grep), while the `[REDACTED:…]` marker does (non-vacuous). Same for a
sonia session with a pasted secret. StagedEdit/ProposedEdit payload with a secret stays verbatim
(the never-scrub pin). Unit tests for `collect_secrets` (pattern, length floor) and `redact`
(nesting, non-str passthrough).

## D2 — Frozen `Settings` (application-layer collection round)

New **`alpha/settings.py`**: a frozen pydantic model (`frozen=True, extra="forbid"`) that is THE
single definition of env names + defaults. **Two consumption tiers** (refined 2026-07-10 after
seam recon — the test-isolation contract turns out to be load-bearing: the autouse
`brain_session_isolation` fixture and tests/web's module-scoped `TestClient` set env AFTER app
creation, across 106 `monkeypatch.setenv` sites; production's lazy per-call reads are what makes
that work):
- **Scripts (freeze-once):** the six producer mains (`save_decisions`, `run_verdict`,
  `capture_window`, `refine_live`, `evolve_from_episodes`, `save_evolution`) construct
  `Settings.from_env()` once in `main()` and thread values down as args —
  `refine_live`/`evolve_from_episodes` already have exactly this shape.
- **Services (single definition, per-call resolution):** the sonia/workbench/alpha_web store- and
  client-helpers construct `Settings.from_env()` per call, replacing their scattered
  `os.environ.get(...)` literals — the 6 duplicated `./state/brain` defaults (and the
  `sessions/projects/conflicts/workspaces/brain.db/iex` duplicates) collapse into one definition
  while the per-call timing the tests depend on is preserved verbatim. A boot-time freeze is
  DEFERRED until the web/sonia fixture strategy is reworked (recorded here, not silently).
- **Asymmetric defaults are encoded, not papered over:** alpha_web's brain dir has NO default
  (unset → frozen seeds) — a distinct `web_live_brain_dir: str | None` field;
  `episodes_db: str | None = None` matches `save_decisions` (no-default), with the evolution
  scripts' `./state/brain.db` default a named constant in the same module.
- **Exemptions, documented in the module docstring:** secrets stay OUT (APCA/DEEPSEEK/ANTHROPIC
  keys keep their lazy RuntimeError-at-construction behavior — the offline suite needs no keys);
  `alpha/llm/config.py`'s per-role reads stay put (already a centralization point);
  `ALPHA_UNSAFE_AUTONOMOUS` is deliberately NOT centralized (the duplicated friction is the
  point, charter governance); `__main__` host/port uvicorn args stay inline.
- Constraints: stays OUT of `alpha/harness`; imports nothing from `alpha/refine.{apply,credit,
  conflict}` or `alpha/memory.episodes` (the four lazy-import cycle edges).
- Acceptance: full suite green with zero test edits (byte-identical offline behavior); the
  duplicated default literals appear exactly once (in `alpha/settings.py`).
- Co-flip couplings documented at the field (the brain-state quintet the cross-face reconcile
  couples; `workspace_dir`×`live_brain_dir` feeding the workbench boot assert).

## D3 — Assembled-prompt audit record + `scripts/render_prompt.py`

`build_system_prompt` (`alpha/agent/prompt.py:69-75`) gains **`collect=None`** — an optional
callback/collector receiving one record per candidate element: `{kind: skill|lesson|episode,
id, offered|dropped, reason}` (reasons: `depends_on-unmet`, `budget-cut`, `weight-cut`,
`taboo`, …) plus the final assembled text. Default `None` = byte-identical behavior (pinned by a
test asserting identical output with and without a collector).
- `scripts/save_decisions.py` threads a collector and persists a sidecar
  **`<date>.prompt.json`** next to the DecisionPackage in the DecisionStore dir. Eval/verdict
  never read it (they already don't; the sidecar is a new file they never open).
- **`scripts/render_prompt.py`**: given a decisions dir + date, prints the assembled prompt and
  the offered/dropped table — the P2 diagnosis tool.

## D4 — Episode inspector + `harness_digest`

- **`scripts/inspect_episodes.py`**: read-only CLI over `EpisodeStore.for_asof` printing, per
  symbol/asof, the SAME numbers the veto path computes — `summarize()` and `is_episode_taboo()`
  outputs (imported from their production homes, never re-derived) plus recent episode rows.
  Write path stays gated; this is a window, not a hand.
- **`h_digest`**: `sha256(canonical_json(HarnessState.to_dict()))` helper in
  `alpha/harness/snapshot.py` (via D5's `alpha/integrity.py`); `DecisionPackage` gains an
  optional `h_digest: str | None = None` field, populated by `save_decisions`. Eval never reads
  it (regression: verdict numbers bit-identical with/without). Feeds A10's joint rollback later.

## D5 — One hashing utility: `alpha/integrity.py`

Mining §6 order-3 couples §2.1+§2.6 into one hashing utility. New low-level, stdlib-only
**`alpha/integrity.py`**: `sha256_file(path)`, `sha256_bytes(b)`, `canonical_json(obj)`,
`sha256_canonical_json(obj)`. `alpha/meta/proposal_store.py`'s `canonical_json`/`brain_hash`
delegate to it (public names re-exported unchanged — existing imports and tests untouched).
D4/D6/D7 all consume this module. No cycle risk: `alpha/integrity` imports nothing from alpha.

## D6 — CHECKSUMS manifest for captured PIT windows

- **Write:** `alpha/data/capture.py::capture_window` finishes by writing **`CHECKSUMS`**
  (sha256sum text format: `<hash>  <relpath>` per line, sorted) into the pit root — both capture
  scripts inherit it automatically. The capture CLI prints the commit ritual:
  `git add -f <root>/CHECKSUMS` (snap dirs are whole-directory gitignored and negation patterns
  don't pierce ignored parents — `-f` is the mechanism; the manifest is the only tracked file).
- **Verify:** `alpha/data/integrity_check.py::verify_checksums(root, *, fail_closed: bool)`
  (thin wrapper over `alpha/integrity`): missing/extra/mismatched files are typed in the error;
  a MISSING manifest is a warning in both postures (migration story for pre-existing windows).
  Wired into script mains only (constructor-enforced checks would break the offline suite's
  manifest-less tmp stores):
  - **fail-closed:** `run_verdict` (mining letter), `save_decisions` (persisted decisions),
    `refine_live` (self-study evidence feeding EvolutionProposals);
  - **warn:** `save_evolution` (display artifact), `scan_tradeable` (explicitly ad-hoc).
  - **Not wired (recorded limit):** the registry path `make_source("snapshot")` reachable by the
    live faces — a live-face concern outside A1; recorded as an honest limit in Backend-Design
    §2.12's landing note when this arc closes G12.
- Explicit mining exclusions carried: no K_MAX half; no manifest for the growing `brain.db`.

## D7 — `tcb.lock` + `runbooks/` + activation ledger

**`tcb.lock`** (repo root) + **`scripts/gen_tcb_lock.py`** over the modification-ladder §3 file
set, corrected and extended (user ruling 2026-07-10):
- Rows 1–10, 12 as listed (apply.py, ops.py, conflict.py, metatools.py, edit_log.py,
  snapshot.py, manager.py, doctrine.py, floor_breaker.py, firewall.py, arena/policy.py).
- Row 11 fixed at extraction: the recall PIT-mask actually lives in `alpha/memory/store.py`
  (`for_asof`) + `alpha/agent/retrieval.py` — the named `alpha/memory/recall.py` never existed.
- Row 13 (red-line lint · try_promote_body · verifier harness): declared-but-absent — listed as
  a comment in the manifest, hashed as nothing.
- **Additions (human-approved 2026-07-10, dated marker in the manifest):**
  `alpha/meta/evolution.py` (adopt-time red-line/prefix validation) and
  `alpha/meta/proposal_store.py` (brain_hash staleness pin).
- **Deliberate exclusions stay excluded:** `alpha/guard/` (spec's own choice),
  `alpha/refine/credit.py` + `alpha/arena/experience.py` (the observation channel is a
  deliberate bypass, not an invariant enforcer), `alpha/meta/store.py` (locks are ops).
- **`tests/test_tcb_lock.py`** (`--check` as pytest): manifest exists, is non-empty, every listed
  file exists, every hash matches. Docstring documents the **regen ritual**: any legitimate TCB
  edit re-runs `gen_tcb_lock.py` and commits `tcb.lock` in the same change — the red suite is
  the reminder. (These new checks become rows in the future governance-pins meta-gate — that arc,
  not this one.)

**`docs/superpowers/runbooks/`** + first runbook **`p-b-p-c-activation.md`** (mining §1.2
structure): §0 what flipping on does + the named verifying tests
(`tests/loop/test_verdict_neutrality_task.py::test_verdict_neutral_to_task_episodes_single_window`
+ `_multi_window`, `tests/refine/test_separation_integration.py::test_verdict_neutral_with_operational_skill_and_task_episodes`);
§1 the complete flag/wiring set as a Wire | Role | Without-it table with the "headline flags are
NOT sufficient" warning + two-tier kill switch (un-wire `experience_writer` / the
`for_asof(kind=)` fence); §2 pre-flip checklist (A2's 4 steps + gate-side re-derivation +
guard-the-unguarded-`experience_writer` — steps A2 will BUILD; the runbook is the ops companion
to A2's plan, not a replacement); §3 staged rollout. Day-0 row detail (checklist step → proving
test → blocker type) lives HERE, per mining §3's merge rule.

**Activation ledger** (user ruling: DEVELOPMENT-PLAN top): a compact three-column table
(Capability | Built | Live-in-prod) right under the plan's header — day-0 rows: P-B/P-C
operational-K coupling (built ✓ / dark / runbook link) and the daily production loop (producers
only / not built / P9). The A1 bullet in DEVELOPMENT-PLAN §2 is updated at landing (one-place
discipline). `tcb.lock`/CHECKSUMS get no rows (born live, never dark).

**Housekeeping in the same arc:** delete the stale 5-line `docs/ROADMAP.md` tombstone (points at
the deleted root file).

## Acceptance (arc gate)

1. T2-shell `env` regression: no key material in any persisted transcript; markers present.
2. Full suite green; zero eval/verdict diffs; collect-hook + Settings rounds byte-identical.
3. `render_prompt` reproduces a decision's prompt from the sidecar.
4. `tests/test_tcb_lock.py` green against the committed `tcb.lock`.
5. A captured tmp window verifies clean; a tampered parquet fails run_verdict fail-closed;
   a manifest-less window warns.
6. DEVELOPMENT-PLAN ledger + A1 bullet updated; runbook exists; `docs/ROADMAP.md` gone.
