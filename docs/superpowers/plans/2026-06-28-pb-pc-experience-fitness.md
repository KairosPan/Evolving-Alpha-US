# Activity-Space P-B + P-C — Experience Capture & Fitness Coupling Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development to implement this plan task-by-task. Each `### Task N:` is one implement->review->fix cycle. The RED/GREEN/REFACTOR bullets are the TDD steps.

**Goal:** Build P-B (live-agent task episodes, observation-only, default-off, verdict-neutral) then P-C (the second-fitness coupling into K + operational doctrine, behind the trading-vs-operational classification), preserving every moat invariant.

**Architecture:** P-B adds `Episode.kind in {trade,task}` + a `record_task_episode` activity-credit seam injected into `converse_project` (default-off; converse never imports arena). P-C adds a per-element `domain` tag, a domain-aware + task-floor gate branch in `try_apply_op`, a read-side domain filter on the trading prompt, a confirmed-positive task aggregator, and a deterministic task proposer — all through the one write-waist.

**Tech Stack:** Python 3.13, pydantic v2 (frozen value objects), SQLite/FTS5, pytest. Fully offline (FakeSource/MockLLMClient, temp=0).

## Global Constraints

- **All English.** Run tests with `python -m pytest tests -q` (NOT `pytest -q .`). Keep the existing 749 tests green.
- **OBSERVATION-CHANNEL (P-B):** task episodes are written ONLY via `episode_store.add`; never through `try_apply_op`, never in `harness.to_dict()`, never in H-rollback. `record_task_episode` must NOT import or mutate any `Skill`/`SkillStats`.
- **VERDICT-NEUTRALITY:** P-B is additive/default-off — byte-identical when `episode_store=None`; `for_asof` defaults `kind="trade"` so no task row reaches the verdict path; a regression test pins bit-identical HCH-vs-Hexpert numbers with/without task rows.
- **SEPARATION (P-C):** the task signal may target ONLY operational K / operational doctrine, enforced at the gate (write side, via `evidence_kind="task"` + the target's `domain`) AND on the read side (operational elements never enter the trading prompt). Trading-relevant H is judged ONLY by walk-forward. Default `domain="trading"` is fail-closed; `domain` is set-once.
- **ONE-WRITE-WAIST:** every H mutation (incl. P-C promotes/retires) flows through `try_apply_op`; the task floor (confirmed-positive task aggregate) is enforced INSIDE the gate, not only in the proposer.
- **NO LLM-JUDGE:** the task outcome is a deterministic precedence; a promote-eligible "success" counts ONLY when externally confirmed (human_approver set, or an independent verifier exit 0). LLM-judge deferred.
- **G stays a no-op** (`PASS_TOOLS['G']=frozenset()`); P-C evolves K + operational doctrine only — do not claim G evolution.
- **TCB files** (`apply.py`, `edit_log.py`, `doctrine.py`, `ops.py`) edits are additive/frozen-safe and flagged for red-line review.

## File Structure
- NEW: `alpha/arena/experience.py` (`record_task_episode`, `_task_outcome`); `alpha/refine/task_forge.py` (or extend `forge.py`); tests under `tests/{memory,arena,converse,loop,refine,agent,harness}/`.
- EDIT: `alpha/memory/episodes.py` (Episode.kind), `store.py` (kind column + migration + `for_asof` kind filter), `aggregate.py` (TaskStats); `alpha/harness/{skill,doctrine,memory,edit_log}.py` (domain / evidence_kind fields); `alpha/refine/apply.py` (gate branches + floors), `refiner.py` (K-pass task evidence); `alpha/agent/{prompt,retrieval}.py` (read-side filter); `alpha/converse/session.py` (inject episode_store); `alpha/meta/agent.py` (Sonia task evidence).

**Spec:** `docs/superpowers/specs/2026-06-28-pb-pc-experience-fitness-design.md`. Execute Tasks 1-9 (P-B) then 10-20 (P-C); do not reorder across the boundary.

---

## Implementation Plan — Activity-Space P-B then P-C (TDD)

Conventions: every step is `RED` (write failing test) → `GREEN` (minimal code) → `REFACTOR`. Tests mirror `alpha/` under `tests/`, run offline via `FakeSource`/`MockLLMClient`, temp=0. Exact paths and signatures cited. Steps are dependency-ordered; do not reorder across the P-B→P-C boundary.

---

### PHASE P-B — experience capture (observation only, default-off)

### Task 1: PB-1 — `Episode.kind` field
- **RED** `tests/memory/test_episode_model.py`: (a) `Episode(...)` built without `kind` has `.kind == "trade"` (back-compat); (b) a task `Episode(kind="task", entry_date=d, exit_date=d, outcome="succeeded", advantage=0.0, score=0.0, symbol="", skill_id="__task__")` validates and `learned_asof == d` (via `_default_learned_asof`).
- **GREEN** `alpha/memory/episodes.py`: add `kind: Literal["trade","task"] = "trade"` to `Episode`.
- **REFACTOR** confirm `episodes_from_step` still constructs trade episodes unchanged.

### Task 2: PB-2 — store column + guarded migration + `kind` read
- **RED** `tests/memory/test_episode_store.py`: (a) add a `kind="task"` episode, reopen store, `_row_to_episode` returns `.kind == "task"`; (b) simulate an OLD db (create the table without `kind`, insert a row), open `EpisodeStore`, assert the row reads back as `kind="trade"` (migration ran).
- **GREEN** `alpha/memory/store.py`: add `"kind"` to `_COLS`; add `kind TEXT NOT NULL DEFAULT 'trade'` to `_SCHEMA`; in `__init__` after `executescript`, `PRAGMA table_info(episodes)` → guarded `ALTER TABLE episodes ADD COLUMN kind TEXT NOT NULL DEFAULT 'trade'`; read `r["kind"]` in `_row_to_episode`.

### Task 3: PB-3 — `for_asof` kind filter (verdict-neutrality fence; BINDING Fork A=trade)
- **RED** `tests/memory/test_episode_store.py`: store with one trade + one task row both `learned_asof <= asof`; (a) `for_asof(asof, limit=None)` returns ONLY the trade row (default `kind="trade"`); (b) `for_asof(asof, kind="task", limit=None)` returns ONLY the task row; (c) `for_asof(asof, kind=None, limit=None)` returns both.
- **GREEN** `alpha/memory/store.py::for_asof`: add `kind: str | None = "trade"` param; when not None append `clauses.append("kind = ?"); params.append(kind)`.
- **REFACTOR** confirm the three production callers (`agent/retrieval.py::select_episodes_for_prompt`, `guard/screen.py`, `refine/forge.py::propose_skill_ops`) need NO edit — they inherit `kind="trade"`.

### Task 4: PB-4 — `record_task_episode` builds a task episode (observation-only)
- **RED** `tests/arena/test_experience.py`: construct a fake `ConversationResult` (`tool_calls=[{"tool":"shell","args":{...},"result":{"ok":True,"exit_code":0}}]`, `final_text="done"`, `hit_max_iters=False`); call `record_task_episode(res, h, asof=d, project_id="p", turn_seq=3, episode_store=store)`; assert one episode written with `kind="task"`, `entry_date==exit_date==learned_asof==d`, `episode_id=="{d}:p:3"`, `advantage==0.0`, `score==0.0`, `outcome=="succeeded"`, `reflection_text` is non-empty JSON listing tools used.
- **GREEN** `alpha/arena/experience.py`:
  ```python
  def record_task_episode(res, h, *, asof, project_id, turn_seq, episode_store=None) -> Episode | None:
  ```
  build the task `Episode`; `if episode_store is not None: episode_store.add(ep)`; return ep (or None when store is None).

### Task 5: PB-5 — outcome precedence rule (deterministic, no LLM-judge)
- **RED** parametrized `tests/arena/test_experience.py`: (a) `hit_max_iters=True` → `"incomplete"`; (b) a `shell` result `{"ok":False,"exit_code":1}` → `"failed"`; (c) any result `{"error":"boom"}` → `"failed"`; (d) otherwise → `"succeeded"`.
- **GREEN** `alpha/arena/experience.py`: implement the precedence in a helper `_task_outcome(res)`.

### Task 6: PB-6 — observation-channel membrane (BINDING — verdict 1)
- **RED** `tests/arena/test_experience.py`: take an `h` whose skills have nonzero `stats`; snapshot `json.dumps(h.to_dict(), sort_keys=True)` and each `skill.stats.model_dump()`; run `record_task_episode` on a turn whose `tool_calls` reference an existing skill_id; assert `h.to_dict()` byte-identical AND every `Skill.stats` unchanged (n/wins/expectancy untouched). Also assert `record_task_episode` never calls `try_apply_op` (no `EditRecord` appended to `h`'s log).
- **GREEN** ensure `record_task_episode` imports/mutates no `Skill`/`SkillStats`; records skill usage only inside the episode (`skill_id` + tools-used list in `reflection_text`). (Spec §5 SkillStats accrual is deferred to P-C — assert by absence here.)

### Task 7: PB-7 — wire into `converse_project` (injected, default-off byte-identical)
- **RED** `tests/converse/test_session_experience.py`: (a) `converse_project(...)` with no `episode_store` arg behaves exactly as today (no episode written; existing session tests unaffected); (b) with `episode_store=store` passed, after a turn exactly one `kind="task"` episode exists keyed `{turn_date}:{project_id}:{turn_seq}`.
- **GREEN** `alpha/converse/session.py::converse_project`: add `episode_store=None` param; after step 6b call `record_task_episode(res, harness, asof=<turn logical date, Fork D>, project_id=project.id, turn_seq=<seq>, episode_store=episode_store)`. NO `import alpha.arena` at module top — accept the writer/store via the param (injected by the arena/workbench app layer that already builds the registry). If injection of the function (not the store) is preferred, accept `experience_writer=None`; pick per Fork.
- **REFACTOR** confirm spine stays one-directional (converse imports nothing from arena).

### Task 8: PB-8 — verdict-neutrality regression (verdict 4)
- **RED** `tests/loop/test_verdict_neutrality_task.py`: run `compare_harnesses` (or `multi_window`) twice over a captured fake window sharing one `recall_store` brain.db — once clean, once after inserting several `kind="task"` rows with `learned_asof <= asof`; assert `hch_minus_hexpert_mean_excess` (and per-window numbers) are bit-identical. This proves the `for_asof(kind="trade")` fence.
- **GREEN** none expected (PB-3 already fences); the test is the guarantee. If it fails, a consumer is calling `for_asof(kind=None)` — fix that call site.

### Task 9: PB-9 — evidence-kind carrier + interim blanket reject (the wall, ships with P-B)
- **RED** `tests/refine/test_apply_separation.py`: (a) existing `EditProvenance(...)` without `evidence_kind` has `.evidence_kind is None` (back-compat); (b) `try_apply_op(..., provenance=EditProvenance(path="self_study", proposer="refiner", evidence_kind="task"))` against ANY skill/lesson/doctrine target returns `(None, "separation: task-evidenced op may not touch a gated surface (domain tag not pinned)")` — including a target that would otherwise pass all trade floors; (c) a normal op with `evidence_kind=None` is byte-identical to today.
- **GREEN** `alpha/harness/edit_log.py` (TCB): add `evidence_kind: Literal["trade","task"] | None = None` to `EditProvenance`. `alpha/refine/apply.py` (TCB): insert the blanket reject **after the empty-patch check (after line 83), before the retire/promote floors (lines 84-94)** and before `conflict_queue`.
- **REFACTOR** run full suite; confirm byte-identical (no caller sets `evidence_kind`).

**P-B done-when:** PB-1..PB-9 green; full suite byte-identical with `episode_store=None`; PB-6 + PB-8 pinned.

---

### PHASE P-C — classification FIRST, then coupling (behind the gate)

### Task 10: PC-1 — `Skill.domain` field
- **RED** `tests/harness/test_skill.py`: (a) `Skill.from_seed({...})` without `domain` → `.domain == "trading"`; (b) `Skill.from_seed({..., "domain":"operational"})` → `.domain == "operational"`; (c) `domain` survives `model_dump()`/round-trip.
- **GREEN** `alpha/harness/skill.py`: add `domain: Literal["trading","operational"] = "trading"` to `Skill`.

### Task 11: PC-2 — `DoctrineEntry.domain` (TCB) + `Lesson.domain`
- **RED** `tests/harness/test_doctrine.py`: operational doctrine entry `domain="operational", immutable=False` round-trips; `domain` orthogonal to `immutable` (an immutable entry can be `domain="trading"`). `tests/harness/test_memory.py`: `Lesson.from_seed` default `domain="trading"`, seedable to operational.
- **GREEN** `alpha/harness/doctrine.py` (TCB): add `domain: Literal["trading","operational"] = "trading"` to `DoctrineEntry`. `alpha/harness/memory.py`: add same to `Lesson`.

### Task 12: PC-3 — snapshot byte handling (Fork E)
- **RED** `tests/harness/test_state.py`: depending on Fork E choice — either (E-exclude) `to_dict()` byte-identical to a pre-change golden when all domains are default (`model_serializer(exclude_defaults=True)`), OR (E-regen) regenerate the four pinned fixtures and assert `domain` round-trips through `to_dict`→`from_dict`.
- **GREEN** implement the chosen Fork E path; if E-regen, update `tests/harness/test_state.py`, `test_edit_log.py`, `test_edit_provenance.py`, `tests/memory/test_episode_model.py` and confirm none gate a verdict assertion.

### Task 13: PC-4 — set-once relabel guard + create-path mislabel guard (verdict 2)
- **RED** `tests/refine/test_apply_separation.py`: (a) any provenance: `patch_skill` with `domain` in args → `(None, "domain is set-once; cannot be relabeled")`; same for `update_memory`; (b) a **trade-evidenced** `write_skill`/`process_memory` declaring `domain="operational"` → reject (`"create may not mint operational under trade evidence"`); (c) a task-evidenced `write_skill(domain="operational")` is allowed past this guard (still subject to the domain branch + task floor below).
- **GREEN** `alpha/refine/apply.py` (TCB): add both guards before `_dispatch`, for ALL provenances.

### Task 14: PC-5 — domain-aware gate branch (replaces PB-9 blanket reject)
- **RED** `tests/refine/test_apply_separation.py`: with the tag pinned — (a) task-evidenced op targeting a `domain="trading"` skill → `(None, "separation: task-evidence may only target operational H (target domain=trading)")`; (b) targeting a non-existent/legacy target → reject (domain `None`, fail-closed); (c) targeting a `domain="operational"` skill PASSES the separation check (then proceeds to the task floor); (d) M Lesson (default trading) task op always rejects; (e) a trade-evidenced op is byte-identical to today (skips the branch). Also: a task op that is ALSO a self-study-vs-teaching conflict is REJECTED on domain grounds, not held.
- **GREEN** `alpha/refine/apply.py` (TCB): add `_element_domain(h, tool, tid, args)` helper; replace the PB-9 blanket reject with the domain-aware branch at the same insertion point (after empty-patch, before trade floors); on operational pass-through fall to the task floor (PC-7); on dispatch, `return` so the trade floors at 84-94 never run for task ops.

### Task 15: PC-6 — read-side domain filter (verdict 2, symmetric counterpart)
- **RED** `tests/agent/test_prompt_domain.py`: build `h` with one `domain="operational"` active skill + one operational lesson + one operational mutable doctrine entry, all otherwise renderable; assert `build_system_prompt(h, injection="full")` renders NONE of them and renders all trading-domain ones; repeat for `injection="retrieval"` (via `select_for_prompt`). Default `"trading"` elements still render (byte-identical when no operational element exists).
- **GREEN** `alpha/agent/prompt.py::build_system_prompt`: filter skills/trials/lessons/doctrine loops by `getattr(x, "domain", "trading") == "trading"` in BOTH branches; `alpha/agent/retrieval.py::select_for_prompt`: apply the same predicate.

### Task 16: PC-7 — task aggregator with confirmed-positive counting (verdicts 3 + 5)
- **RED** `tests/memory/test_task_aggregate.py`: over `kind="task"` episodes keyed by `skill_id` — (a) `succeeded/failed/incomplete` counted into observed-n; (b) a synchronous `outcome="succeeded"` with NO external confirmation contributes to observed-n but NOT to `confirmed_success` (anti-gaming: a no-op/`echo ok` episode is neutral); (c) an episode whose joined `EditProvenance.human_approver` is set OR carries an independent-verifier pass contributes a `confirmed_success`; (d) `confirmed_success_rate = confirmed_success / confirmed_n`.
- **GREEN** add a `TaskStats` (or kind-parameterized `summarize`) in `alpha/memory/aggregate.py` reading `for_asof(asof, kind="task", limit=None)`. The confirmed-signal join key is `applied_seq`/`edit_id` (from `StagedEdit`/`EditProvenance.human_approver`); pass the resolved confirmation set in.

### Task 17: PC-8 — gate-side task floor (verdict 3 — authority lives at the waist)
- **RED** `tests/refine/test_apply_separation.py`: task-evidenced operational promote — (a) `task_stats=None` → reject (fail-closed); (b) `task_stats.confirmed_n < min_task_confirmed_samples` → reject; (c) `confirmed_success_rate < min_task_success_rate` → reject; (d) all floors met → dispatch succeeds AND `sk.stats` is NOT consulted (operational skill has `stats.n==0`/`expectancy is None`).
- **GREEN** `alpha/refine/apply.py` (TCB): extend `try_apply_op` signature with `task_stats: TaskStats | None = None, min_task_samples: int = ..., min_task_success_rate: float = ..., min_task_confirmed_samples: int = ...`; enforce the floor in the task branch BEFORE `_dispatch`; `None` fails closed. `alpha/refine/refiner.py`: add the knobs to `RefinerConfig` with off-keeping defaults; existing `min_promote_samples`/`min_retire_samples` untouched.

### Task 18: PC-9 — deterministic task proposer (forge twin)
- **RED** `tests/refine/test_task_forge.py`: over a store with operational-skill task episodes meeting the floor — (a) proposes `promote_skill` ONLY for `domain="operational"` skills; (b) every emitted op routes through `try_apply_op` stamped `EditProvenance(path="self_study", proposer="forge", evidence_kind="task", evidence_ref={"domain":"operational",...})`; (c) a trade-stamped op produced by this proposer is impossible — pinning test asserts the proposer ALWAYS stamps `evidence_kind="task"` (verdict 5); (d) operational skills below the floor yield no op.
- **GREEN** new `alpha/refine/task_forge.py` (or extend `forge.py`): `propose_task_skill_ops(episode_store, h, *, asof, task_stats, config)` modeled on `propose_skill_ops`, reading `for_asof(asof, kind="task", limit=None)`, feeding the same gate with the task provenance + `task_stats`.

### Task 19: PC-10 — Refiner K-pass + Sonia route task evidence through the same gate
- **RED** `tests/refine/test_refiner_task.py` / `tests/meta/test_agent_task.py`: when the K-pass/Sonia emit a task-evidenced operational promote, it passes `task_stats` to `try_apply_op` and is subject to the gate-side floor (NOT only a proposer-side gate); a task op targeting a trading skill is rejected at the gate regardless of producer.
- **GREEN** `alpha/refine/refiner.py` K-pass and `alpha/meta/agent.py`: thread `evidence_kind="task"` + `task_stats` into their `try_apply_op` calls for task-sourced ops (one-write-waist; no new channel).

### Task 20: PC-11 — separation integration + non-gameable end-to-end
- **RED** `tests/refine/test_separation_integration.py`: (a) full path — a task proposer cannot move ANY `domain="trading"` skill (promote/retire both reject); (b) a task op cannot relabel a trading skill operational via `patch_skill(domain=...)` (PC-4 guard) then promote it; (c) a stream of agent-authored default-pass "succeeded" episodes with no external confirmation never crosses the promote floor (verdict 5 anti-Goodhart); (d) confirm `compare_harnesses` numbers remain bit-identical with operational elements + task episodes present (read-side filter PC-6 + write-side gate hold).
- **GREEN** none expected (PC-4..PC-8 cover it); the test pins the composite invariant.

**P-C done-when:** PC-1..PC-11 green; trade path byte-identical (no task provenance → unchanged trade floor); verdict numbers bit-identical with operational/task data present; all separation-rejection and anti-gaming tests pinned; TCB edits (`apply.py`, `edit_log.py`, `doctrine.py`, `ops.py` verify) flagged for red-line review.