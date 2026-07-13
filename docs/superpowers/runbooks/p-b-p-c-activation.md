# Runbook: P-B/P-C (operational-K experience/fitness coupling) activation

Structure per `docs/findings/2026-07-01-kairos-design-mining.md` §1.2. This runbook is the **ops
companion** to `DEVELOPMENT-PLAN.md` §2 A2 — A2 is the arc that BUILDS the missing wires; this
document is how a human decides when and how to flip them, not a replacement for A2's plan.

Sources: `docs/PROJECT_STATE.md` P-B/P-C entry (2026-06-28 paragraph, "Pre-live-activation
checklist"); `docs/superpowers/specs/2026-06-28-pb-pc-experience-fitness-design.md`;
`docs/findings/2026-07-01-kairos-design-mining.md` §1.2, §2.3, §4.6.

---

## §0 What flipping ON does

P-B/P-C shipped 2026-06-28 (882-test arc, merged + pushed @ `23e0dbc`) **additive and
default-off**. **A2 (2026-07-13) built the missing activation wires** (conflict routing,
operational-M reject, gate-side confirmed-evidence re-derivation, pinned asof, guarded writer) +
the opt-in workbench flip — all still default-off. See **§4** for the concrete flip and kill
switch. `task_forge` remains unwired into a live driver (Stage 3).
Flipping it ON means: the live conversational face (`converse_project`) starts writing
`kind="task"` episodes at every turn boundary (P-B), and a second fitness channel starts
promoting/retiring **operational** K-skills from that evidence (P-C) — entirely separate from the
trading K-skills the LLM agent reads at decision time.

**Named verifying tests** (the verdict-neutrality regression — the trade path must stay
bit-identical before, during, and after the flip):

- `tests/loop/test_verdict_neutrality_task.py::test_verdict_neutral_to_task_episodes_single_window`
- `tests/loop/test_verdict_neutrality_task.py::test_verdict_neutral_to_task_episodes_multi_window`
- `tests/refine/test_separation_integration.py::test_verdict_neutral_with_operational_skill_and_task_episodes`

Run before and after every stage in §3:

```bash
python -m pytest -q \
  tests/loop/test_verdict_neutrality_task.py \
  tests/refine/test_separation_integration.py::test_verdict_neutral_with_operational_skill_and_task_episodes
```

---

## §1 The wires

Warning (verbatim, kairos-mining §1.2): **the headline wires are NOT sufficient** — each row below
is necessary; none is a complete activation on its own, and the four A2-owned rows of §2 do not
exist yet.

| Wire | Role | Without it |
|---|---|---|
| `experience_writer` injection (`converse_project(..., experience_writer=None)`, `alpha/converse/session.py`) | Injects `alpha/arena/experience.py::record_task_episode` at the turn boundary so `kind="task"` episodes get written — observation-only, never gated, never touches `SkillStats` | No task episodes are ever captured; P-C's evidence pool stays permanently empty (the safe, current, dark state). The call site was unguarded pre-A2 — **A2 wrapped it in try/except-log (2026-07-13)** so a writer exception is logged, never propagated past the persisted turn (kairos-mining §4.6) |
| `task_forge` producer (`alpha/refine/task_forge.py::propose_task_skill_ops`, built, unwired into any live driver) | Deterministic proposer — promotes/retires `domain="operational"` K-skills only, from confirmed task evidence, routed through `try_apply_op` stamped `EditProvenance(evidence_kind="task")` | No operational-K proposals are ever generated even once episodes accrue; the evidence sits inert |
| `confirmed_ids` resolution (currently caller-supplied — `apply.py:129` comment: "the caller MUST supply precomputed task evidence") | Must be derived from durable records (EditLog provenance / persisted verifier verdicts), not trusted from producer input | The gate's confirmed-positive floor (`task_stats.confirmed_n`) is forgeable by whatever caller passes `confirmed_ids` — this is the same gap as kairos-mining §2.3's gate-side re-derivation: thread a read-only, PIT-pinned `episode_store.for_asof(asof, kind="task")` handle into `try_apply_op`'s task branch and recompute `summarize_task` inside the gate, mirroring the verdict's read-only `recall_store` split so the gate can never become a self-write channel |
| Pinned logical-date asof | `record_task_episode`'s `asof` must be the SAME pinned logical date threaded into PIT-gated recall (`select_for_prompt(..., asof=...)`), not two independent wall-clock reads | Today `session.py` computes `_asof` from `turn.created_at` (falling back to `date.today()`) for the writer, while `build_system_prompt` is called with no `asof` at all (defaults `None` → its own wall-clock read internally). These can drift on turn replay or a midnight-spanning turn; task and trade episodes must share one PIT-masked read (`learned_asof <= asof`) |
| `conflict_queue` routing for operational task ops | `try_apply_op`'s domain-aware branch (PC-5, `apply.py` lines ~128-150) currently **short-circuits and returns before reaching the `conflict_queue` check** (line 166) — a task-evidenced op that is ALSO a self-study-contests-teaching conflict is rejected on domain grounds, never held for review | An operational op that collides with a teaching- or user-owned element is silently rejected instead of surfaced to Sonia's conflict queue for adjudication — the same held-for-review discipline the trade path already gets |
| Gate-side re-derivation of task evidence | See the `confirmed_ids` row — this is the same mechanism, named separately in kairos-mining §2.3 and A2's goal text because it is the one BEFORE-P-C-activation hardening item, not a checklist step in its own right | Trade floors read unforgeable harness-held `sk.stats`; the task branch trusting caller-supplied `task_stats`/`confirmed_ids` is the one asymmetry between the two fitness channels |

**Two-tier kill switch:**

1. **Soft** — un-wire `experience_writer` (pass `None`, the default, back into `converse_project`).
   Stops new task episodes from being written; existing rows in `brain.db` remain (harmless —
   observation-only, never read by the trade path).
2. **Hard floor** — the `for_asof(kind=)` fence in `alpha/memory/store.py` (`kind="trade"` is the
   default on every verdict-path and recall-path call). Even if every wire above is live and
   misbehaving, this fence is what actually keeps `kind="task"` rows out of every trading
   decision, recall, taboo, and verdict computation. It requires no runtime toggle — it is the
   floor every live caller already relies on (`for_asof(kind=None)` at any live call site would be
   the loosening to catch and revert, never to introduce). This is the one guarantee the three
   named tests in §0 pin.

---

## §2 Pre-flip checklist

| # | Step | Named proving test | Blocker type | Status |
|---|---|---|---|---|
| 1 | Route operational task ops through `conflict_queue` (close the PC-5 short-circuit in `apply.py`) | `tests/refine/test_apply_task_activation.py::test_operational_task_op_contesting_teaching_is_held_not_applied` (+ `..._without_conflict_applies`) | code (A2) | ✅ landed 2026-07-13 |
| 2 | Reject-or-amend operational-M scope — DECISION: **reject** (arena-spec §5 scopes the task signal to K + operational-doctrine only, never M/Lessons; closes the create-path gap where `process_memory(domain="operational")` slipped through) | `tests/refine/test_apply_task_activation.py::test_task_evidenced_operational_memory_create_rejected` (+ `..._plain_memory_op_rejected`) | design+code (A2) | ✅ landed 2026-07-13 |
| 3 | Wire `confirmed_ids` resolution from durable records (EditLog `human_approver` stamps) — the gate-side re-derivation in §1 | `tests/refine/test_apply_task_activation.py::test_forged_task_stats_cannot_promote_when_recall_threaded` (+ `..._gate_derives_confirmed_from_human_approver_records_and_promotes`, `..._recall_threaded_without_asof_fails_closed`) | code (A2) | ✅ landed 2026-07-13 |
| 4 | Pin the task-episode asof to the logical date shared with PIT-gated recall | `tests/converse/test_session_activation.py::test_pinned_asof_reaches_both_prompt_and_writer` | code (A2) | ✅ landed 2026-07-13 |
| 4b | Guard the `experience_writer` call (a writer exception must not kill the live turn — kairos-mining §4.6) | `tests/converse/test_session_activation.py::test_writer_exception_does_not_kill_turn` (+ `..._is_logged`) | code (A2) | ✅ landed 2026-07-13 |
| 5 | Verdict read/write symmetry re-assert — HCH still gets `recall_store=` (read-only), never `episode_store=`, on every verdict-path caller; no new caller of `InnerLoop` was added that violates this | the three §0 tests, rerun green | human (sign-off before flip) | standing |
| 6 | Default-off-when-dark re-assert — confirm `experience_writer` defaults `None` and no live driver (`save_decisions`, `refine_live`, `workbench`) passes a non-`None` value except the one flip being staged | the three §0 tests, rerun green + `grep -rn "experience_writer=" alpha/ scripts/ workbench/` shows only the default and the intended flip site | human (sign-off before flip) | standing |

Rows 1-4b are A2's four logged activation steps + the two before-live items; **A2 built them
(2026-07-13) — see §4 for the concrete flip.** Rows 5-6 stay the human sign-off a flipper runs
through each time. A2 did NOT flip live behaviour on by default — the flip is opt-in (§4).

---

## §3 Staged rollout

**Stage 1 — dark (today).** `experience_writer=None` everywhere; `task_forge` unwired; `brain.db`
accrues zero `kind="task"` rows. Watch: nothing live to watch; the three §0 tests stay green in
CI as the standing regression.

**Stage 2 — shadow (writer on, forge off).** Wire `experience_writer` into one live driver (the
workbench conversational face is the natural first target) with A2's four steps + the two
re-asserts in §2 all closed. `task_forge` stays unwired — no promote/retire proposals yet, task
episodes only accumulate as evidence.
Watch signals: `kind="task"` episode volume/rate via `scripts/inspect_episodes.py` (or `/episodes`
once built); zero unhandled writer exceptions in the live logs (confirms the try/except-log from
§1's `experience_writer` row landed); the three §0 tests still green on every run, not just at
flip time; `brain.db` storage growth stays bounded.

**Stage 3 — full (forge on).** Wire `task_forge` into a live driver (Sonia's review queue, per the
governance charter — self-study forks-and-proposes, never lands in place). `confirmed_ids`
resolution is live (gate-side re-derivation closed).
Watch signals: `task_forge` proposal rate and quality reviewed manually in the Sonia queue before
any adoption; `conflict_queue` holds for operational ops reviewed individually (should be rare —
review every one, don't let a backlog accrue silently); promote/retire decisions on operational
skills spot-checked against the confirmed-positive floor (kairos-mining anti-Goodhart: an
agent-authored default-pass must never promote); the three §0 tests green on every CI run,
permanently — this is the one invariant that must never regress, staged rollout or not.

---

## §4 Activation performed (A2, 2026-07-13) — the concrete flip

A2 built the four checklist wires + the two before-live items **additive and opt-in** — merging A2
flipped nothing. Files touched: `alpha/refine/apply.py` (TCB — the gate; `tcb.lock` regenerated),
`alpha/converse/session.py`, `alpha/arena/experience.py`, `workbench/app.py`. The whole feature
stays dark until an operator sets one env var. The gate reads `TaskStats` (not `sk.stats`) — the
arena-spec §5 SkillStats-accrual intent for task-used K-skills was **deferred** by pb-pc spec §1.3
and remains so; A2 invented no parallel `ToolStats` (none needed).

### What each item wired

- **Item 1 (conflict routing).** The task branch now runs the same `conflict_queue` check the trade
  path always had — an operational task op contesting a teaching-/user_direct-owned element is
  **held_for_review**, not silently applied. (A TRADING target still rejects on domain first, so the
  queue is only reachable for operational targets that clear the domain wall.)
- **Item 2 (operational-M scope).** Decision: **reject.** `try_apply_op` rejects every
  task-evidenced memory op (`_target_kind == "memory"`), closing the create-path gap where a
  task-evidenced `process_memory(domain="operational")` could mint an operational Lesson. The task
  signal targets K + operational-doctrine only (arena-spec §5).
- **Item 3 + before-live (a) (gate-side re-derivation).** `try_apply_op` gained two keyword-only
  params — `task_recall` (a read-only PIT-pinned `EpisodeStore`) and `asof`. When both are threaded
  in on a task op, the gate recomputes `TaskStats` itself from `task_recall.for_asof(asof,
  kind="task")` and derives `confirmed_ids` from **durable** records only
  (`_derive_confirmed_task_ids`: EditLog records stamped with `human_approver` whose `evidence_ref`
  lists `confirmed_episode_ids`). A caller-supplied `task_stats` is then **ignored** — mirroring the
  verdict's read-only `recall_store` split so the gate can never become a self-write channel.
  `task_recall=None` (the default) → byte-identical: the gate trusts the caller's `task_stats`
  exactly as the dormant P-C build did. **`human_approver` is waist-enforced** (review-fix, two
  legs so the confirmation source can't be forged): (leg 1) `try_apply_op` refuses any op that
  self-stamps `human_approver` on a path other than `user_direct`/`teaching` — a self-study
  proposer cannot self-approve; (leg 2) `_derive_confirmed_task_ids` harvests
  `confirmed_episode_ids` ONLY from `teaching`/`user_direct` records, fencing out a `self_study`
  record that carries `human_approver` via `adopt_proposal`'s post-gate direct save (which bypasses
  the waist). Together: the confirmed-positive count derives only from a genuine human-approval act.
  **Note for Stage 3:** to make the positive path fire live,
  the approve path must stamp `evidence_ref={"confirmed_episode_ids": [...]}` onto the
  `human_approver` EditRecord — that stamping is the one remaining live-wire (the gate mechanism +
  its forgery-resistance are built and pinned now).
- **Item 4 (pinned asof).** `converse_project` gained an `asof` param threaded into BOTH
  `build_system_prompt` (→ `select_for_prompt` recall) AND the writer, so task and trade episodes
  share one PIT-masked read. Unpinned (`asof=None`) → the writer falls back to the turn's own
  logical date (dormant default).
- **Before-live (b) (guarded writer).** The `experience_writer(...)` call is wrapped in
  try/except-log; a writer exception is logged (`alpha.converse.experience`) and the turn still
  persists.

### The opt-in flip (Stage 2 — shadow)

```bash
# Off (default): unset → fully dark, byte-identical to pre-A2.
# On: point the workbench conversational face at a task-episode brain.db.
export ALPHA_EPISODES_DB=./state/brain.db      # workbench/_task_capture() reads Settings.episodes_db
python -m workbench                             # :8820 — now writes kind="task" episodes per turn
```

`workbench/app.py::_task_capture()` returns `(None, None)` when `ALPHA_EPISODES_DB` is unset (dark),
else `(make_experience_writer(EpisodeStore.open(db)), date.today())` — the writer + the live turn's
pinned logical date, both handed to `converse_project`. `task_forge` stays unwired (Stage 3), so
this is shadow-mode: task episodes accrue as evidence, no promote/retire proposals yet.

### Kill switch (proven — `test_kill_switch_off_is_byte_identical`)

1. **Soft (env).** `unset ALPHA_EPISODES_DB` → `_task_capture()` returns `(None, None)` →
   `converse_project` gets no writer → **zero** new task episodes; the persisted project is identical
   (modulo the intrinsic wall-clock/uuid fields) to a run where capture never existed — the writer is
   pure observation. Existing `kind="task"` rows in `brain.db` stay harmless.
2. **Hard floor (code, no toggle).** `for_asof(kind="trade")` — the default on every verdict- and
   recall-path call — keeps `kind="task"` rows out of every trade decision, recall, taboo, and
   verdict number regardless of the wires. Pinned by the three §0 tests; **never loosen it.**

### Acceptance evidence (A2)

- Verdict-neutrality: the three §0 tests green — the trade path (HCH-vs-Hexpert numbers) is
  bit-identical. `task_recall=None`/`experience_writer=None`/`asof=None` defaults make every gate,
  session, and workbench change byte-identical when off.
- Full offline suite green (1595 passed), `python scripts/gen_tcb_lock.py --check` = 0, no new lint.
- New regressions: `tests/refine/test_apply_task_activation.py` (items 1-3),
  `tests/converse/test_session_activation.py` (item 4, guard, factory, kill switch).
