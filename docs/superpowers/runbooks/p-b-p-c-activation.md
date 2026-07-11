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
default-off** — nothing wires `experience_writer` / `task_forge` / `confirmed_ids` live today.
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
| `experience_writer` injection (`converse_project(..., experience_writer=None)`, `alpha/converse/session.py`) | Injects `alpha/arena/experience.py::record_task_episode` at the turn boundary so `kind="task"` episodes get written — observation-only, never gated, never touches `SkillStats` | No task episodes are ever captured; P-C's evidence pool stays permanently empty (the safe, current, dark state). The call site is today **unguarded** (`session.py` line ~96) — a writer exception kills the live turn (kairos-mining §4.6); wire the try/except-log alongside turning it on |
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

| # | Step | Named proving test | Blocker type |
|---|---|---|---|
| 1 | Route operational task ops through `conflict_queue` (close the PC-5 short-circuit in `apply.py`) | none yet — A2 adds a regression asserting a domain-rejected op that is also a self-study/teaching conflict lands in `conflict_queue`, not silently rejected | code (A2) |
| 2 | Reject-or-amend operational-M scope (decide whether operational memory writes get their own scope surface or ride the existing M pass) | none yet — A2's design step decides the scope shape before any test can assert it | design (A2) |
| 3 | Wire `confirmed_ids` resolution from durable records (EditLog provenance / persisted verifier verdicts) — the gate-side re-derivation in §1 | none yet — A2 adds a regression proving a caller-forged `confirmed_ids` cannot promote past the gate once re-derivation lands | code (A2) |
| 4 | Pin the task-episode asof to the logical date shared with PIT-gated recall | none yet — A2 adds a regression proving `record_task_episode`'s asof and `select_for_prompt`'s asof are the same value on one turn | code (A2) |
| 5 | Verdict read/write symmetry re-assert — HCH still gets `recall_store=` (read-only), never `episode_store=`, on every verdict-path caller; no new caller of `InnerLoop` was added that violates this | the three §0 tests, rerun green | human (sign-off before flip) |
| 6 | Default-off-when-dark re-assert — confirm `experience_writer` defaults `None` and no live driver (`save_decisions`, `refine_live`, `workbench`) passes a non-`None` value except the one flip being staged | the three §0 tests, rerun green + `grep -rn "experience_writer=" alpha/ scripts/` shows only the default and the intended flip site | human (sign-off before flip) |

Rows 1-4 are A2's four logged activation steps (`docs/PROJECT_STATE.md` P-B/P-C entry); this
runbook does not build them — it is the gate a human runs through once A2 has.

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
