> **Status:** APPROVED (2026-06-28) — design blessed by the user after a 11-agent design+adversarial-verification workflow (all 5 invariants at_risk-but-fixed; the 3 substantive fixes — SkillStats deferred to P-C, read-side domain filter, confirmed-positive floor — folded in). Implements P-B (experience capture) then P-C (fitness coupling + the trading-vs-operational classification) of the activity space. Follows `2026-06-27-activity-space-arena-design.md` §5 (this spec AMENDS §5's "K-skills accrue SkillStats in P-B" → deferred to P-C behind the domain tag) + `2026-06-27-modification-ladder-and-body-axis-design.md` (Fork 5 classification).

# Activity-Space P-B + P-C — Experience Capture & Fitness Coupling (Design)

## Activity-Space Experience Capture & Coupling — Design Spec (P-B then P-C)

Grounded in live code: `alpha/memory/episodes.py`, `store.py`, `aggregate.py`, `refine/credit.py`, `refine/apply.py`, `refine/forge.py`, `harness/skill.py`, `harness/doctrine.py`, `harness/memory.py`, `harness/edit_log.py`, `agent/prompt.py`, `agent/retrieval.py`, `converse/session.py`, `converse/loop.py`, `arena/experience.py` (empty), `arena/contract.py`. The trade half (`apply_credit` + `episodes_from_step`) is the template; the task half mirrors it with one structural difference — **no `t+horizon`**, so a task episode matures synchronously at the turn boundary.

This spec folds in all five adversarial verdicts. Three of them turn "recommended forks" into **binding requirements**; two add **new required mechanisms** (read-side domain filter; gate-side task floor with confirmed-positive counting) and **move the gate insertion point**.

---

### Part 1 — P-B: experience capture (observation only)

#### 1.1 `Episode.kind`
Add to the frozen `Episode` (`alpha/memory/episodes.py`):
```python
kind: Literal["trade", "task"] = "trade"
```
Default `"trade"` keeps every existing call site (incl. `episodes_from_step`) byte-identical at the model level. For a **task** episode the trade-semantic fields degrade cleanly:
- `entry_date == exit_date == learned_asof == turn_date` (the single synchronous date; `_default_learned_asof` sets `learned_asof = exit_date` for free).
- `advantage = 0.0`, `score = 0.0` — **never** populated for tasks (they are the trade-fitness numerics the gate floor / Welford read).
- `symbol = ""`, `family = None`.
- `skill_id` = resolved K-skill used/written, else sentinel `"__task__"` (mirrors `"__unattributed__"`).
- `narrative` = task-type tag; `phase` = conversational regime read if any.
- `outcome` ∈ task vocabulary `{"succeeded","failed","incomplete"}` (NOT the trade labels).
- `reflection_text` = compact JSON trajectory summary (tools used, gate verdicts, `hit_max_iters`); FTS-indexed.
- `episode_id = f"{turn_date.isoformat()}:{project_id}:{turn_seq}"` (deterministic ⇒ `INSERT OR IGNORE` idempotent).

#### 1.2 Persistence + the verdict-neutrality fence (`alpha/memory/store.py`)
1. Add `"kind"` to `_COLS`.
2. Add `kind TEXT NOT NULL DEFAULT 'trade'` to the `CREATE TABLE` in `_SCHEMA`.
3. **Guarded migration**: `CREATE TABLE IF NOT EXISTS` is a no-op on an existing `brain.db`. In `__init__`, after `executescript`, `PRAGMA table_info(episodes)`; if `kind` absent, `ALTER TABLE episodes ADD COLUMN kind TEXT NOT NULL DEFAULT 'trade'`. `_row_to_episode` reads `r["kind"]` (default-tolerant).
4. **`for_asof` gains a `kind` filter, default `"trade"` (BINDING — Fork A=trade):**
```python
def for_asof(self, asof, *, phase=None, narrative=None, kind="trade", limit=50):
    ...
    if kind is not None:
        clauses.append("kind = ?"); params.append(kind)
```
All three trade-recall consumers — `agent/retrieval.py::select_episodes_for_prompt`, `guard/screen.py` taboo (`summarize`), `refine/forge.py::propose_skill_ops` — currently call `for_asof(asof, limit=None)` with no kind filter. Defaulting `kind="trade"` silently scopes every existing caller to trade with no edit, so a forgotten call site cannot leak task rows. This is the load-bearing neutrality mechanism: with it, every HCH-vs-Hexpert number is provably unchanged whether or not task rows share `brain.db`. `aggregate.summarize`/`is_episode_taboo` hardcode the trade labels and `mean_advantage`; with the `kind="trade"` default they never see task rows.

> Note (folded from verdict 4): `mark_superseded` and any future FTS recall path lack a kind filter. Neither is on the verdict path today, but any future verdict-path consumer of either MUST replicate `kind="trade"` scoping.

#### 1.3 The activity-credit seam (`alpha/arena/experience.py`)
New function, twin of `apply_credit`:
```python
def record_task_episode(
    res: ConversationResult, h: HarnessState, *, asof: Date,
    project_id: str, turn_seq: int, episode_store=None,
) -> Episode | None:
```
**Where it fires.** From `converse_project` (`alpha/converse/session.py`), after step 6b (staged-edit materialization), gated behind a new injected param `episode_store=None` (default `None` ⇒ byte-identical when off). converse is **below** arena on the spine, so the writer is **injected, never imported** — same pattern as `registry_factory`/`dispatch`. The arena/workbench app layer that already builds the registry constructs the `EpisodeStore` and passes it down. P-B writes task episodes from the **live converse path only** (Fork L=live-only), keeping verdict-neutrality structural — the verdict never invokes `converse_project`, and `InnerLoop` writes episodes only via `apply_credit` (trade-only).

**What it captures** (all in hand at the turn boundary from `ConversationResult`): `res.tool_calls` (`[{tool,args,result}]`), per brain-edit gate verdict `result["status"] ∈ {applied,held,rejected}`, shell `ExecResult{ok,exit_code}`, `res.final_text`, `res.hit_max_iters`.

**BINDING — observation-channel (verdict 1):** `record_task_episode` writes **solely** via `episode_store.add(ep)`. It is **forbidden from importing or mutating any `Skill`/`SkillStats`**. This makes the membrane structural: no `try_apply_op`, not in `harness.to_dict()`, no H-rollback, and zero contamination of the trade gate floor. Spec §5 ("K-skills the agent uses/writes accrue the existing `SkillStats`") is **explicitly DEFERRED to P-C behind the domain tag** — in P-B, skill/tool usage is recorded **only inside the `kind="task"` episode** (`skill_id` + a tools/skills-used list in `reflection_text`).

#### 1.4 Synchronous outcome (no `t+horizon`, no LLM-judge)
The recorded `outcome` is a deterministic precedence over `res` (invariant #6, temp=0-safe):
1. `res.hit_max_iters` → `"incomplete"`.
2. any `shell` `ExecResult.ok is False` (non-zero exit code) → `"failed"`.
3. any tool `result` carrying `{"error": ...}` → `"failed"`.
4. else → `"succeeded"`.

This is the **endogenous, synchronous** half of the second fitness. The **exogenous** half (human/teacher approval) is **async**: it arrives in a later turn when `workbench/app.py POST /edits/{eid}/approve|reject` flips `StagedEdit.status` and stamps `EditProvenance.human_approver`. EpisodeStore.add is `INSERT OR IGNORE`, append-only, frozen — no in-place update.

**BINDING — temporal split (Fork B=a):** write the task episode at the turn with synchronous signals only; leave the human verdict where it already lives (`StagedEdit.status`/`StagedEdit.applied_seq` on the persisted `Project`, `EditProvenance.human_approver` on the gated `EditRecord`). P-C joins it at fitness time via the `applied_seq`/`edit_id` key. Episodes stay immutable + PIT-clean.

> **Anti-Goodhart caveat carried into P-C (verdict 5):** the synchronous `outcome="succeeded"` is **agent-authored and default-pass** (a no-op or `echo ok` scores "succeeded"). It is recorded in P-B but is **NOT a promote-eligible win**. P-C counts a task "success" toward a promote floor ONLY when an **external** signal confirms it (see §3.4).

#### 1.5 `asof` source (Fork D)
`record_task_episode`'s `asof` is the turn's **pinned logical date** (the same date threaded into PIT-gated recall), not wall-clock `today`, since task and trade episodes share one PIT-masked store read `learned_asof <= asof`.

#### 1.6 P-B done-when
- Task episodes persist and are recallable via `for_asof(kind="task")`.
- Full suite byte-identical with `episode_store=None`.
- **Additionally (verdict 1):** `harness.to_dict()` byte-identical AND every `Skill.stats` unchanged after `record_task_episode` runs on a turn that used/wrote a skill — even with `episode_store` ON.
- **Additionally (verdict 4):** `compare_harnesses`/`multi_window` produce bit-identical numbers when the shared recall `brain.db` contains `kind="task"` rows vs not.

---

### Part 2 — P-C prerequisite: the trading-vs-operational classification (Fork 5)

This is the gate-prerequisite. The **interim hard rule ships with P-B**; the domain tag and the domain-aware gate ship at the head of P-C.

#### 2.1 Evidence-kind carrier + interim hard rule (ships with P-B)
Add one field to `EditProvenance` (`alpha/harness/edit_log.py`, TCB):
```python
evidence_kind: Literal["trade", "task"] | None = None
```
Default `None` = legacy/trade-equivalent ⇒ byte-identical back-compat. A task-evidenced op == `provenance is not None and provenance.evidence_kind == "task"`.

**Interim blanket reject in `try_apply_op` (`alpha/refine/apply.py`, TCB).** Folding verdict 5's insertion-point fix: insert the task branch **immediately after the empty-patch check (after line 83), BEFORE the retire/promote trade floors (lines 84-94)** — not between 94 and 95. Reason: an operational skill being promoted on task evidence has `sk.stats.n == 0`/`expectancy is None`, so the trade floor at 88-94 would reject first with the wrong reason and (in P-C) block every legitimate operational promote. Placing the task branch first lets it fully own task ops and short-circuit the trade floors.
```python
# after line 83 (empty-patch), before the retire/promote trade floors:
if provenance is not None and provenance.evidence_kind == "task":
    return None, "separation: task-evidenced op may not touch a gated surface (domain tag not pinned)"
```
Correct because every tool reaching `try_apply_op` is by definition touching a gated surface. Byte-identical when off (P-B emits no task-evidenced ops). Placement before `conflict_queue` is deliberate: a domain reject beats a conflict hold (confirmed: a task op that is also a self-study-contests-teaching conflict is REJECTED on domain grounds, not held).

#### 2.2 Per-element domain tag (ships at head of P-C)
A new per-element field — **not** a map, **not** inferred:
```python
domain: Literal["trading", "operational"] = "trading"
```
added to `Skill` (`harness/skill.py`, not TCB), `DoctrineEntry` (`harness/doctrine.py`, TCB), `Lesson` (`harness/memory.py`, not TCB).
- **Field over map/inference**: all three have `from_seed` passing `rest` through (seedable for free), travels through `to_dict()`/snapshot/rollback, queryable at the gate as `harness.skills.get(tid).domain`.
- **Default `"trading"` is fail-closed**: untagged/legacy elements are protected from the task signal.
- **Inference rejected**: `family` (`None` spans cross-cutting trading doctrine and future operational) is ambiguous; proposer/path is wrong — domain is a property of the *target*.
- **Orthogonal to `immutable`**: `immutable` = red-line write-protection; `domain` = which-fitness-may-edit. An operational doctrine entry is `domain="operational", immutable=False`.

#### 2.3 Set-once relabel guard + create-path guard (ships with the tag, verdict 2 + Fork H)
`metatools.patch_skill`/`update_memory` accept arbitrary `**fields`. The tag must be **set-once** for ALL provenances:
```python
if op.tool in ("patch_skill","update_memory") and "domain" in op.args:
    return None, "domain is set-once; cannot be relabeled"
```
**Create-path guard (verdict 2 secondary crack):** `write_skill`/`process_memory` route `domain` through `from_seed`'s `rest`, so a CREATE could mint a trading-relevant element labeled `domain="operational"` to escape the wall. A task-evidenced create that declares `domain="operational"` is the only legitimate operational create; a **trade-evidenced** create that declares `domain="operational"` must be rejected (`"create may not mint operational under trade evidence"`).

---

### Part 3 — P-C: fitness coupling (deferred behind Fork 5)

The trading path stays byte-identical: a trading-evidenced op (no task provenance) skips every new branch and hits the unchanged `sk.stats.n`/`expectancy` floor.

#### 3.1 Domain-aware gate branch (replaces §2.1 blanket reject)
Same insertion point (after empty-patch, before trade floors):
```python
def _element_domain(h, tool, tid, args):
    if tool in ("write_skill", "process_memory"):
        return args.get("domain", "trading")          # create: declared in args
    if tid is None:
        return None
    kind = _target_kind(tool)
    el = (h.skills.get(tid) if kind == "skill"
          else h.memory.get(tid) if kind == "memory"
          else h.doctrine.get(tid) if kind == "doctrine" else None)
    return getattr(el, "domain", None) if el is not None else None

if provenance is not None and provenance.evidence_kind == "task":
    domain = _element_domain(harness, op.tool, tid, op.args)
    if domain != "operational":
        return None, f"separation: task-evidence may only target operational H (target domain={domain})"
    # then the gate-side task floor (§3.4) — BEFORE _dispatch; then dispatch and RETURN
    #   (short-circuits the trade floors at 84-94 entirely)
```
Fail-closed: `None` (missing/legacy/unknown), `"trading"`, or any mixed value all reject. M `Lesson`s default `"trading"`, so task-evidenced M ops always reject — consistent with arena §5 (K/G/operational-doctrine only). No third enum value is needed; mixed elements auto-protect.

#### 3.2 Read-side domain filter (NEW — verdict 2, the symmetric counterpart)
Separation is currently enforced only on the WRITE side, but the trading act path READS H with **no domain filter** (`agent/prompt.py::build_system_prompt` lines 87-90, 106-109; `agent/retrieval.py::select_for_prompt`). A P-C operational promote/rewrite would then be rendered into the trading agent's prompt and steer the `DecisionPackage` — defeating invariant #2 and breaching verdict-neutrality in P-C. **Required fix:** add a fail-closed read-side filter, shipped with the domain tag:
- `build_system_prompt` (both `injection="full"` and `injection="retrieval"` branches): `skills/trials` keep only `getattr(s, "domain", "trading") == "trading"`; `lessons` keep only `getattr(l, "domain", "trading") == "trading"`; doctrine loops render only `getattr(e, "domain", "trading") == "trading"`.
- `select_for_prompt` applies the same predicate so operational elements can never enter the trading prompt by either path.

Default `"trading"` keeps it fail-closed and byte-identical when no operational element exists. This makes separation symmetric: operational H is write-editable by task fitness AND unreadable by the trading agent.

#### 3.3 Task aggregator (NEW — verdict 3)
`aggregate.summarize`/`EpisodeStats` count only the trade vocabulary (`continued/faded/nuked`) and average `advantage`; over `kind="task"` rows they return `win_rate=0`/`mean_advantage=0` — a degenerate dead feature. Add a kind-aware task aggregator (`TaskStats` or a `kind`-parameterized `summarize`) over `for_asof(asof, kind="task", limit=None)` keyed by `skill_id`, counting `succeeded/failed/incomplete` and a **confirmed** task-success rate (§3.4). The gate floor reads THIS, never `sk.stats` (operational skills have `stats.n == 0`).

#### 3.4 Gate-side task floor with confirmed-positive counting (verdicts 3 + 5)
The trade floor is load-bearing because it is re-checked **inside** the waist; a task floor enforced only in the proposer would leave the LLM Refiner K-pass and Sonia (which run no proposer-side sample gate) able to over-promote. **Required:** extend `try_apply_op` to accept the precomputed task aggregate and floor knobs:
```python
try_apply_op(..., task_stats: TaskStats | None = None,
             min_task_samples: int = ..., min_task_success_rate: float = ...,
             min_task_confirmed_samples: int = ...)
```
In the task branch, before `_dispatch`: reject unless `task_stats is not None` AND `task_stats.confirmed_n >= min_task_confirmed_samples` AND `task_stats.confirmed_success_rate >= min_task_success_rate`. **A `None` aggregate fails closed.** Every producer (forge-twin, Refiner K-pass, Sonia) must pass `task_stats`.

**Confirmed-positive (anti-Goodhart, verdict 5):** the shell verifier signal is agent-authored and "succeeded" is the default, so a task contributes a **success** toward the floor ONLY when an **external** signal confirms it — either `EditProvenance.human_approver` is set (the StagedEdit was actually approved via workbench) OR a designated **independent** verifier (not agent-chosen) returned exit 0. A synchronous default-pass episode with no external confirmation counts as **neutral** (raises observed-n, never confirmed-success). This restores exogenous-arbiter symmetry with the trade path.

#### 3.5 The task-signal proposer → K-pass / Sonia
A new deterministic proposer modeled on `forge.propose_skill_ops`, reading `for_asof(asof, kind="task", limit=None)`, emitting `promote_skill`/`retire_skill` ops **only for operational K** (and later operational doctrine via the p-pass; **not G** — Fork K), each stamped:
```python
EditProvenance(path="self_study", proposer="forge"|"refiner",
               evidence_kind="task",
               evidence_ref={"domain":"operational","applied_seq":...})
```
All route through the **same** `try_apply_op` (one-write-waist, invariant #3). The LLM Refiner K-pass (`refiner.py`) and Sonia (`meta/`) feed the same gate with the same provenance shape. New `RefinerConfig` fields with off-keeping defaults: `min_task_samples`, `min_task_success_rate`, `min_task_confirmed_samples`. Existing `min_promote_samples=3`/`min_retire_samples=5` untouched.

#### 3.6 Don't over-promise G (Fork K)
`PASS_TOOLS['G'] = frozenset()` is a no-op today. P-C realistically evolves **K** (+ operational doctrine via the p-pass) only, until sub-agent meta-tools exist. The gate already routes a future G tool to the same wall; the design does not claim G evolution.

#### 3.7 TCB-file churn (red-line review)
P-C/Fork-5 touches four TCB-manifest files: `apply.py` (task gate branch + relabel/create guards + task floor), `ops.py` (verify whitelist unchanged), `edit_log.py` (`evidence_kind`), `doctrine.py` (`DoctrineEntry.domain`). `skill.py`/`memory.py`/`prompt.py`/`retrieval.py`/`forge.py` are not TCB. All additive, frozen-safe.

#### 3.8 Snapshot byte-identicality (Fork E, verdicts 1 & 4)
`Episode.kind` (model_dump) and `domain` on Skill/Lesson/DoctrineEntry change serialized snapshot bytes (add keys), breaking pinned fixtures (`tests/harness/test_state.py`, `test_edit_log.py`, `test_edit_provenance.py`, `tests/memory/test_episode_model.py`). The verdict **number** is unchanged (prompt renders explicit fields; the number reads `c.advantage` only). Decide per Fork E: adopt `model_serializer(exclude_defaults=True)` to keep bytes identical, vs schedule a one-time reviewed fixture regen. Either way, confirm none of those fixtures gate a verdict assertion.