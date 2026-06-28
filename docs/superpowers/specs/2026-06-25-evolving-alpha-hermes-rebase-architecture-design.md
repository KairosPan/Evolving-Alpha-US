> **Status:** APPROVED (2026-06-26) — all open decisions (§5.7 / §6.10 / §7 / §8) confirmed by the user; entering implementation planning, **Phase 0 vendor-feasibility spike first**. Re-base of evolving-alpha onto the NousResearch/hermes-agent harness (Strategy C, narrow-waist vendor).
>
> **Confirmed decisions (2026-06-26):**
> - **§5.7** — Hermes fast self-study sub-tier **deferred**; provenance = `{path, proposer, evidence_ref={kind,id}, parent_checkpoint_version, reflection_lm_id(+seed), resolution?}`; conflict flood-control **conservative** (any self-study touch of a teaching-owned H element escalates) + digest UI.
> - **§6.10** — **SQLite split** (semantic Lessons in JSON snapshot, episodes+FTS in `brain.db`); `learned_asof = max(exit_date of summarized episodes)` + a PIT-leak regression test; auto-promote/demote on credit **ON** (sample-floor + gated `demote_memory`/`update_memory`, episode writes ungated, and any auto-adjust of a *teaching-owned* Lesson escalates per §5.4); graph = **recall+episodes first, `links` second**; **add a per-backtest-day recall latency benchmark gate**.
> - **§7** — Hermes sandbox provisional; tiers = read/compute→none, workspace-write→git-workspace-scoped, shell/exec→Hermes isolated env, network→allowlist; **live-order tools NOT exposed to the B-WIDE face** (human-confirm + revisit if ever added).
> - **§8 — RESOLVED (2026-06-27): hard-pin `5add283e`, do not track upstream** (the Phase-0 spike measured coupling — the whole monolith is reachable; reference-vendor the registry leaf, reimplement the rest).

# evolving-alpha — Hermes Re-Base Architecture (Design)

## 1. Context & goal

### 1.1 What evolving-alpha is becoming

evolving-alpha today is a **deterministic, self-evolving trading harness**: a day-agent that emits one strictly-typed `DecisionPackage` per call, wrapped in an offline walk-forward loop that scores decisions at `t+horizon`, assigns credit, and lets an autonomous 4-pass Refiner edit a structured brain `H=(p,G,K,M)` through a single gated write path. Sonia (a separate FastAPI service) is the human-facing teacher; she proposes edits through the *same* gate.

This re-architecture re-bases that system onto the **hermes-agent harness** (NousResearch, MIT) using a **Strategy-C "narrow-waist vendor"** boundary. The end state is a single agent that is simultaneously:

- **Teachable** — Sonia continues to teach via gated, previewed edits.
- **Self-evolving** — two learning paths share one gated brain: a **self-study path** (the Refiner; a deeper GEPA-style search is its deferred future) and a **teaching path** (Sonia). Every write funnels through one gate; path conflicts escalate to the user (§5.4).
- **Conversational** — a new general (B-WIDE) tool-calling face built on Hermes's `conversation_loop`, sharing the *same* brain `H` as the deterministic decider.
- **Trading-capable** — the entire 555-test trading system becomes **one domain toolset / MCP**; the deterministic `decide` becomes **a registry tool returning a typed `DecisionPackage`**.

The organizing principle is unchanged: **one brain `H`, one write-waist (`try_apply_op`), many proposers.** Hermes supplies the conversational loop, the tool registry, SQLite/FTS5 session persistence, and the SOUL/SKILL/memory file model. evolving-alpha keeps its moat: the unified gate, red-lines, the capability-floor breaker, offline InnerLoop scoring, and the deterministic decider.

### 1.2 Explicitly out of scope (now)

- **Model / weight-level evolution.** All evolution is **file/prompt/config-level only**. The separate `hermes-agent-self-evolution` (DSPy+GEPA weight RL) repo is *not* adopted.
  - **Scope-lift gate (added 2026-06-27).** *Code-level* self/teacher-modification of the agent (skill-code, tool-code, runtime, container image) is now **designed-for but gated**, not flatly out of scope: it is permitted **only** behind a kernel sandbox + an immutable TCB carve-out + an outer verifier + mandatory human approval, **never autonomously**, and **never** on the no-kernel `LocalEnv`. See `2026-06-27-modification-ladder-and-body-axis-design.md` (the modification ladder R1–R6; NOW ships data rungs R1/R2 only). Weight-level evolution stays fully out of scope.
- **Codex-grade sandbox.** We adopt Hermes's existing execution sandbox (docker/ssh/modal tool environments) as a **provisional** safety story and revisit a stronger sandbox later (§7).
- **Per-project forked brains.** There is **ONE shared evolving brain**, not a fork per project (§4).
- **Offline self-study search (GEPA-style Forge).** Deferred (§5.6); it is a future *deepening of the self-study path*, not a new organ. The gate / fitness / provenance substrate is kept ready for it, but it is not built now.
- **Whole-H global coherence checking** is deferred (§10).

---

## 2. Architecture overview

### 2.1 Layers

```
┌──────────────────────────────────────────────────────────────────────┐
│  PROJECT / WORKSPACE LAYER                                             │
│  project = { resumable Hermes session  +  git-backed workspace        │
│              +  H-version provenance refs }   (§4)                     │
├──────────────────────────────────────────────────────────────────────┤
│  HERMES NARROW-WAIST CORE  (Strategy C, §8 — registry reference-       │
│   vendored; loop + session reimplemented — see §8)                    │
│   • tool-calling conversation loop (reimpl: alpha/converse/loop.py)   │
│   • tools/registry.py (reference-vendor; active: converse/registry.py)│
│   • SQLite state.db + FTS5 (CJK trigram) sessions (reimpl schema)     │
│   • SOUL.md / SKILL.md / MemoryProvider file & hook model             │
├──────────────────────────────────────────────────────────────────────┤
│  PRESERVED EVOLVING-ALPHA MOAT  (kept yours, unchanged at call sites)  │
│   • unified gate  try_apply_op  ← the ONLY mutator of H               │
│   • red-lines (immutable doctrine), evidence floors                   │
│   • 4-pass Refiner  (live online curator)                            │
│   • capability-floor breaker (rollback-then-FREEZE)                  │
│   • offline InnerLoop / walk-forward scoring  = the sole fitness     │
│   • deterministic decide → typed DecisionPackage                     │
│   • HarnessManager + SnapshotStore (version authority) + EditLog     │
├──────────────────────────────────────────────────────────────────────┤
│  BRAIN   H = (p doctrine, G sub-agents, K skills, M memory)           │
└──────────────────────────────────────────────────────────────────────┘
```

One new organ is added on this base: a **trading-oriented PIT-safe memory system** (`alpha/memory/`, §6), constrained to write *only* through `try_apply_op`. (A deeper self-study search — a GEPA-style Forge — is designed-for but deferred, §5.6.)

### 2.2 How a turn flows (prose diagram)

**Conversational (B-WIDE) turn.** A user message lands in the project's resumable Hermes session (SQLite row). The vendored `conversation_loop` builds context from SOUL + recalled memory + available tools, calls the provider, and dispatches tool calls. One registered tool is **`decide`** — invoking it runs `build_state → LLMAgentPolicy.decide (temp=0) → typed DecisionPackage`, returned as a recognized artifact (§4). Other tools cover the trading domain (capture window, run verdict, save decisions) and general work. Memory recall on this path is **PIT-gated** (§6): every recall masks `WHERE learned_asof <= :asof`. Turn output, tool results, and a **provenance ref into the current `H`-version** are persisted to the session and (for file artifacts) committed to the git workspace.

**Deterministic decide.** Independently of any chat, the offline `InnerLoop`/walk-forward driver steps per day: `build_state` under an `AsOfGuard` data cursor → `decide(temp=0)` → score at `t+horizon` → `apply_credit`. This path **never uses tools or chat**; it is the reproducible substrate on which fitness is measured. The same `decide` is also exposed as the registry tool above — one implementation, two callers.

### 2.3 How an edit flows

Every actor — the Refiner (self-study), Sonia (teaching), the Hermes curator — is a **candidate generator** whose only output is `list[RefineOp]`. The flow is identical regardless of proposer (a self-study op that contests teaching-owned `H` is held for user review, §5.4):

```
proposer → list[RefineOp] (+ provenance) → try_apply_op(gate):
     whitelist (per-pass PASS_TOOLS) → non-empty rationale → non-empty patch
     → retire/promote EVIDENCE FLOORS → RED-LINE immutability check → dispatch
   → MetaTools mutate H → SnapshotStore checkpoint → EditRecord(+provenance) → EditLog
```

Rejected ops are dropped exactly as in the live path. The breaker watches the per-day advantage series and can `rollback-then-FREEZE`. There is **no second write path** anywhere in the system — this is the invariant the whole re-base protects.

---

## 3. One H, two faces (decision a)

### 3.1 Shared H ↔ Hermes file model

`H=(p,G,K,M)` is the single source of truth. Hermes's file/hook model is mapped onto it rather than replacing it:

| evolving-alpha `H` component | Hermes analog | Authority |
|---|---|---|
| **p** doctrine (incl. immutable `[RED-LINE]`) | SOUL.md (identity) | `H` is authoritative; SOUL.md is rendered *from* p |
| **G** sub-agents | (sub-agent spawning) | `H`; note `PASS_TOOLS['G']` is empty today (§10) |
| **K** skills (`SkillRegistry`) | SKILL.md (agentskills.io) | `H`; SKILL.md files rendered from / synced to K |
| **M** memory (`MemoryStore` + episodes) | MemoryProvider hooks + FTS5 | semantic `Lesson` stays in `H`'s JSON snapshot; episodes in `brain.db` (§6) |

The mapping direction matters: **`H` (and `SnapshotStore`) remain authoritative.** Hermes's native file writes (SKILL.md edits, memory-tool writes) are **intercepted and re-expressed as `RefineOp`s** routed through `try_apply_op` — Hermes never writes `H` directly. SOUL/SKILL files are a *projection* of `H` for the conversational loop to read.

### 3.2 The deterministic face

`decide` is exposed as a **registry tool** with a typed return contract:

- Input: a build-state spec (date / universe / as-of).
- Behavior: `LLMAgentPolicy.decide` → exactly one `llm.complete` at **temp=0**, strict-typed parse.
- Output: a `DecisionPackage` recognized as a **typed artifact** (§4), not free text.

This face is the **self-evolution scoring substrate**: it is reproducible (temp=0), tool-free, and PIT-safe, so it can be replayed identically across forks during search.

### 3.3 The conversational face

The B-WIDE face is Hermes's `conversation_loop`: free multi-turn, tool-calling, MCP-aware. It can *call* `decide` as one tool among many, read memory via the PIT-gated recall path, and walk the derived memory graph (§6.7) to answer "why did we do X" / "when did this theme last run."

### 3.4 How both share one H

Both faces read the **same in-memory `HarnessState`** loaded from the **same `SnapshotStore` version**. The deterministic face renders prompts from p/K/M directly; the conversational face reads SOUL/SKILL projections of the same p/K and the same memory tables. Neither face mutates `H` except by emitting `RefineOp`s through the gate. A single `H`-version pin (§4) therefore pins *both* faces identically — there is exactly one brain, viewed two ways.

---

## 4. Artifacts & project workspace (decisions b, c)

### 4.1 Project = three things bound together

```
project := { one resumable Hermes conversation (SQLite session)
             one git-backed workspace (files / artifacts)
             H-version provenance (refs into SnapshotStore) }
```

- **Conversation / messages → SQLite** (`state.db` + FTS5), vendored from Hermes. Resumable.
- **Artifacts / files → git workspace** (additive). Isolation between projects is achieved by **separate git workspaces**, *not* by forking the brain.
- **Brain → ONE shared evolving `H`.** Not forked per project. The version authority stays **yours** (`SnapshotStore` / `EditLog`).

### 4.2 DecisionPackage as a recognized typed artifact

`DecisionPackage` is a first-class, schema-validated artifact. When produced (via the `decide` tool or the `save_decisions` producer), it is written into the git workspace as a typed file and indexed by date, exactly as the existing `DecisionStore` already does. The web console's `/decisions` view consumes it unchanged.

### 4.3 Per-turn provenance & optional pin

Every turn stamps a **provenance ref** = the `SnapshotStore` `H`-version that was live when the turn ran. This lets any artifact, decision, or chat answer be traced to the exact brain that produced it. A project **may optionally pin to a specific `H`-version** (e.g. to reproduce a past run against a frozen brain); absent a pin, projects float on the latest live `H`. Because the brain is shared, pinning affects only how that project *reads* `H`, never a private copy.

---

## 5. Self-evolution (REDESIGNED — two learning paths, GEPA deferred)

> **Design name: "Two Learning Paths, One Gated Brain."** evolving-alpha learns along two distinct pathways that share one brain `H`, one write-waist (`try_apply_op`), and one provenance trail: a **self-study path** (endogenous — learns from its own data) and a **teaching path** (exogenous — a human teaches it via Sonia). When the two paths contend over the same brain, the conflict is **escalated to the user (human) for adjudication** — never silently auto-resolved. An offline population search (GEPA-style) is a *future deepening of the self-study path*, **deferred** for now (§5.6).

### 5.1 The invariant (non-negotiable)

The **only** function that mutates `H=(p,G,K,M)` is `alpha/refine/apply.py::try_apply_op(...)` via the `MetaTools` facade. Every actor on either path is a **candidate generator** emitting `list[RefineOp]`. This generalizes a proven pattern: the Refiner and Sonia (`preview_op`) already do exactly this — Sonia even dry-runs on a scratch harness. Any future proposer (incl. a later self-study Forge, §5.6) plugs into the same waist.

**Immutable-TCB carve-out (added 2026-06-27, non-negotiable).** This invariant only holds while the *code that enforces it* is itself unmodifiable by the agent. Therefore the gate + its guards — `apply.py`, `metatools.py`, `ops.py`, `edit_log.py`, `snapshot.py`, `manager.py`, `conflict.py`, `doctrine.py` (immutability), `floor_breaker.py`, `firewall.py`/recall PIT-mask, `arena/policy.py`, and (in the body phase) the red-line lint + `try_promote_body` + the verifier — form an **immutable Trusted Computing Base**: dev/git-only, permanently excluded from the reshapeable set at every modification tier, and byte-hash-pinned on any body promotion. The maximally-reshapeable agent is *the body minus its own gate/firewall/audit/lint*. See the modification-ladder companion spec §3.

### 5.2 The two paths

**SELF-STUDY (endogenous, autonomous).** The agent improves itself by reflecting on its own measured experience — `Trajectory` + `CreditReport` + `FailureSignature` from the walk-forward loop. Its driver is the InnerLoop fitness (walk-forward excess advantage). Today this path IS the **Refiner**: 4 ordered passes p→G→K→M, gated by `refine_every`/`evidence_min`, owning the structural edits (`promote_skill`/`retire_skill` behind the evidence floors `min_promote_samples`, `expectancy>0`, `min_retire_samples`, enforced in `try_apply_op`). A deeper, search-based version (GEPA-style population/Pareto) is the **future** of this path (§5.6). A FAST online janitorial sub-tier — the vendored Hermes `curator`/`background_review` restricted to `PASS_TOOLS["M"] | {patch_skill}` — also belongs here, but is deferred until the B-WIDE face emits frequent turns (§5.7).

**TEACHING (exogenous, human-in-the-loop).** A human teaches the agent things it cannot derive from its own data — regime intuition, "this setup is a trap right now," qualitative risk discipline. This path IS **Sonia**: free multi-turn chat → dry-run `preview_op` → human accept → gated apply → rollback. Unchanged from today. Teaching is the *designed corrective* for self-study's metric-gaming (Goodhart): self-study exploits the measurable fitness, teaching guards the fitness's blind spots.

The two paths are **complementary, not redundant** — different epistemic sources (own data vs human judgment) — and they **feed each other**: self-study *proposes* candidate findings the teacher can confirm/correct; teaching *injects priors/constraints* that shape the self-study search space.

### 5.3 Provenance (the path tag — genuinely missing today)

`EditRecord` (`alpha/harness/edit_log.py`) is a frozen pydantic model with **no provenance field** (verified). ADD a `provenance` block stamped at gate time:
`{path ∈ self_study|teaching, proposer ∈ refiner|forge|sonia|hermes, evidence_ref (pointer into Trajectory/CreditReport/FailureSignature/session-id), reflection_lm_id, human_approver, parent_checkpoint_version}`.
`ProposedOp` carries it from birth; the gate copies it verbatim into the `EditRecord`. The append-only `EditLog` + `/evolution` console then answer "which path proposed this edit, on what evidence, from which checkpoint" for **every** mutation. **The `path` tag is also the conflict-detection key (§5.4).** This is one extended frozen model + threading it through `try_apply_op`'s record creation.

### 5.4 Conflict → user adjudication (the path interface)

When the two paths contend over the same brain, the system does **not** pick a winner by rule — it **escalates to the human (user)**.

- **Detection (cheap, via provenance).** A **self-study** op is a *conflict* iff it would modify / retire / demote an `H` element whose current authoritative edit has `path = teaching`. (Offline case: a self-study champion op that collides with a teaching edit applied since its proposing fork — §5.6.) Detection reads only the provenance tags + `EditLog`.
- **Asymmetry (important).** **Self-study touching teaching-owned territory → escalate. Teaching touching anything → applies directly** (the human is already in the loop on the teaching path). So self-study stays autonomous on everything it does *not* contest; only contested edits interrupt the human.
- **Gate gains a third outcome.** `try_apply_op` today returns `{applied, rejected}`; add **`held_for_review`** — a detected conflict is neither applied nor dropped; it is enqueued.
- **Adjudication surface.** Held conflicts land in a "conflicts / pending" drawer in the Sonia cockpit. **Sonia frames the conflict (the evidence on each side); the user decides** (accept self-study's revision, keep the teaching, or edit/merge). Sonia is the interface; the user is the final authority.
- **Flood control (the one knob).** "Conflict" is defined narrowly (self-study altering teaching-owned `H` elements) and held conflicts are batchable/digestible; the user may pre-set a default disposition for low-stakes categories. Default for a genuine conflict = human adjudicates.

### 5.5 The capability-floor breaker (unchanged)

The existing breaker stays exactly as-is: it watches the per-day advantage series (`daily_advantage`) and, on a capability-floor trip, **rolls back to the pre-degradation checkpoint then FREEZEs** (`floor_breaker._fallback_trip`/`_shadow_trip`). It is the safety floor for *online* self-study edits. (A "preventive adoption gate" — refusing to ship a degrading *offline* champion before it touches live `H` — is deferred with the offline search, §5.6.)

### 5.6 Deferred: deepening the self-study path (GEPA-style Forge)

**Out of scope now** ("先不要 GEPA"). GEPA is **not a new organ** — it is a *deeper version of the existing self-study path* (population/Pareto reflective search over `H` instead of the Refiner's greedy single step). The architecture is kept **ready** so adding it later is additive, not a rewrite:
- the gate accepts ops from *any* proposer (§5.1);
- `LoopConfig(enable_refine=False)` already exists (verified, `inner_loop.py:42`), so an offline candidate `H` can be scored in isolation by `compare_harnesses` walk-forward fitness — *not* `H`+Refiner;
- provenance (§5.3) already tags the `self_study` path, so Forge edits are attributable and conflict-detectable from day one.

**Re-entry contract (already satisfied by §5.4):** when the offline Forge returns, any champion op that collides with a teaching edit (or an online edit made since its fork) is routed to **user adjudication** via `held_for_review`; non-colliding ops apply through the gate as usual. This pre-empts the offline-concurrency / stale-fork hazard.

When revisited, the remaining design questions are: **instance unit** (regime-bucket recommended over single-day, given MDE ~0.26 @ ~30 days), a **cost budget probe** before building the pool, and **merge coherence** (defer until a whole-`H` consistency check exists). None are built now.

### 5.7 Decisions to confirm

- **Hermes fast self-study sub-tier timing.** The M-only curator only adds value once the B-WIDE conversational face emits frequent turns; in today's one-decide-per-day cadence it collapses into the Refiner's. **Recommendation: defer it; ship the two-path framing + provenance + conflict→user-review against the existing Refiner/Sonia first.**
- **Provenance schema.** Confirm the field set on `EditRecord` (§5.3), especially the `path` and `proposer` enums.
- **Conflict flood control.** Confirm the narrow conflict definition (self-study altering teaching-owned `H` elements) and whether low-stakes categories get a user-preset default disposition.

---

## 6. Memory system (REDESIGNED, trading-oriented)

> **Design name: "Stratum-with-edges"** — a PIT-gated two-tier memory; episodes in SQLite, semantic Lessons staying in the JSON snapshot, all writes through the one gate.

### 6.1 The one real, code-confirmed defect

`alpha/agent/retrieval.py::select_for_prompt` ranks lessons by `h.memory.all()` filtered only on `importance.weight() >= MIN_MEMORY_WEIGHT` (verified). **There is NO temporal gate** — a verdict/backtest at date D can surface a Lesson distilled *after* D. This is the memory-equivalent of look-ahead bias, and it is real. The `:asof` the verdict already uses for the DATA source is reachable at `decide` (`state.as_of` is in hand) but is **NOT** threaded into `build_system_prompt`/`select_for_prompt`/recall. Fixing this is a small, well-defined plumbing change and is the **first deliverable**.

### 6.2 Core decision (resolves the load-bearing risk)

**Do NOT move the semantic layer into a `.db`.** Keep `Lesson`/`MemoryStore` exactly where they are — serialized inside `harness.to_dict()` and atomically checkpoint/rolled-back by `SnapshotStore`. The breaker's rollback-with-`H` invariant stays intact for the self-written rules it actually governs.

Put **ONLY** the high-volume, append-mostly **episodic** layer + FTS indexes in a SQLite file (`brain.db`). Episodes are observation-channel facts (like `SkillStats`), not gated `H` edits, so they do NOT participate in atomic `H`-rollback. On a breaker rollback, episodes written after the checkpoint are marked `superseded` (`WHERE learned_asof > :checkpoint_date` at recall) rather than deleted — recall already filters by date, so stale post-rollback episodes fall outside the as-of window on the re-run.

### 6.3 Components

1. **Semantic layer = unchanged `Lesson` + `MemoryStore` façade.**
   - ADD optional fields to `Lesson` (additive; `from_seed` unchanged for old seeds): `learned_asof: date | None`; `provenance` (source kind ∈ {refiner, sonia, curator}, summarized `episode_ids`, author); `last_accessed: date | None`; `access_count: int = 0` (the last two are observation-channel, bumped on recall, NOT gated).
   - `MemoryStore` keeps its **exact Protocol** (`all/get/by_phase/by_family/by_outcome/add/update/demote`) so MetaTools, the gate, `HarnessState.to_dict/from_dict`, and all existing tests are untouched.

2. **Episodic layer = NEW `alpha/memory/episodes.py` (typed `Episode`) + `alpha/memory/store.py` (`EpisodeStore` over `brain.db`).**
   - One row per scored pick, written at the EXISTING `apply_credit` seam alongside the in-place `SkillStats` update: `(episode_id, symbol, skill_id, family, phase, narrative, entry_date, exit_date, outcome ∈ {continued,faded,nuked}, advantage, score, failure_kind, reflection_text, learned_asof=exit_date)`. `phase` from `step.market`; `narrative` from `Candidate.narrative`; `failure_kind` from `extract_signatures`. All inputs already flow; we persist what is currently discarded.
   - `learned_asof = exit_date` for episodes is CORRECT (the outcome is only known at `t+horizon`) — mirrors the source layer's `announce_date := process_date`.
   - FTS5 virtual table over `(reflection_text, narrative)` + structured columns for WHERE filters.

### 6.4 The `learned_asof` rule for distilled Lessons (subtlest point — explicit + tested)

A Lesson distilled at refine-date R from episodes that matured by D is only KNOWABLE at R. Therefore:
**`lesson.learned_asof = max(exit_date of summarized episodes)`** — NOT the underlying event dates, NOT the refine wall-clock. This is the tightest causally-honest date: the moment the last constituent outcome was realized, the earliest a backtest could legitimately have distilled it. Ship as a single helper with a dedicated PIT-leak regression test (a Lesson distilled from an episode maturing on D is invisible to a recall at D−1).

### 6.5 PIT-safe recall (`alpha/memory/recall.py`)

Replaces the `h.memory.all()` scan inside `select_for_prompt`.
- Signature: `recall(memory_store, episode_store, *, asof, phase, narrative, query_text, budget)`.
- **Plumbing (first deliverable, own test):** thread `decide → build_system_prompt(asof=) → select_for_prompt(asof=) → recall(asof=)`. Confirmed reachable, confirmed not currently wired. This single change closes the leak even before any new scoring lands. **Cover BOTH injection modes** — the `injection='full'` debug path must not still call `h.memory.all()`.
- **Causal mask FIRST:** `WHERE learned_asof <= :asof` on BOTH lessons and episodes.
- **Score** = min-max-normalized `w_rel·relevance + w_rec·recency + w_imp·importance + w_reg·regime_sim + w_narr·narrative_match`, computed as an extension of `Importance.weight()`: `importance=base`; `recency=time_decay` decayed against `last_accessed` (warm-on-retrieval, 0.995/day, with a `touch(asof)` on every recall); `relevance=FTS/BM25 over query_text`; `regime_sim = 1 − thermal-ring distance` (SOFT — adjacent phase downweighted, not excluded); `narrative_match = exact-sympathy boost`. Keep `for_regime(phase)` as the spine. Apply the **History-Rhymes guard**: high text-sim must pair with LOW regime-distance or it is suppressed.
- **Taboo tier hoisted to top, slow/no decay:** any `outcome=principle` or non-empty `failure_signature` row decays slowly; matching rows are returned with a HARD flag in a new `taboos` field on `Selection`, so the existing L4 `GuardedPolicy`/`screen` can hard-veto "do not take this setup in this phase." `Selection` stays frozen + backward-compatible (new optional field).
- Reuse `MIN_MEMORY_WEIGHT=0.15` as render cutoff (recoverable, not deleted).

### 6.6 Credit / attribution auto-adjust (with sample-floor guard)

At `apply_credit`: repeated WINS under a Lesson promote `base`; preceding LOSSES `demote()` it — BUT gate every auto-adjust behind a **sample floor mirroring the gate's `min_promote_samples`**, and route the demote through `try_apply_op`/`demote_memory` so it is LOGGED and rollback-covered (it IS an `H` edit). Episode writes stay ungated observation; **only the Lesson weight change is gated.** This neutralizes the oscillation/feedback risk: no single noisy window can over-promote a Lesson before the breaker or the floor reacts.

### 6.7 Consolidation + the derived graph view

- **Consolidation = the existing Refiner M-pass, episode-grounded + provenance-carrying.** Feed the PIT-safe episode rows for the window into the 4th ordered M-pass; the emitted `process_memory(Lesson)` op carries `provenance = episode_ids` and the computed `learned_asof`. EVERY distillation still flows through `try_apply_op` — the gate IS the curator, which is the memory-poisoning mitigation.
- **Conversational B-WIDE face = a thin derived graph view.** Add a single lightweight `links(src_kind, src_id, edge_type ∈ {distilled_from, sympathy_with, taboo_for}, dst_kind, dst_id)` table, populated as a BY-PRODUCT of the writes above. The deterministic `decide` recall path does **NOT** depend on multi-hop walks — it uses WHERE+FTS+score. The conversational face gets read-only graph-walk tools (`why_did_we_X`, `when_did_this_theme_run`) over the SAME tables. The graph is a read convenience, **not a load-bearing write substrate**.

### 6.8 How the four sources combine (each at its best seam, all through the gate)

- **Continual harness (kept whole):** owns the WRITE side + fitness; `apply_credit` drives episodes + gated auto-adjust; InnerLoop scoring decides whether a distilled Lesson survives; the breaker covers the semantic layer for free (it stays in the JSON snapshot).
- **Hermes (vendored substrate + curator cadence):** SQLite/FTS5 backs `brain.db`; adopt `curator.py`'s decay-tick + stale→archive (NEVER delete) and `background_review` as a post-window distillation TRIGGER — but every op routes through YOUR gate, not Hermes's `write_approval`. (Riskiest seam — roll out LAST.)
- **Sonia (human-gated teacher):** proposes `process_memory`/`update_memory` through the SAME gate; a cockpit Brain "memory" drawer surfaces episodes + provenance + `distilled_from` links so a human sees WHICH episodes back a Lesson before accepting.
- **Offline recall-weight tuning (DEFERRED):** the recall weights (`w_rel/w_rec/w_imp/w_reg/w_narr`, regime-distance penalty, per-tier decay rates) + the distillation prompt are **hand-set now** and adjusted via the self-study / teaching paths. An offline tuner over captured PIT windows (with InnerLoop advantage as fitness — the natural home for a future GEPA-style self-study search, §5.6) is deferred; any winning config would be pinned to an `H`-version in `SnapshotStore`.

### 6.9 Files touched (minimal, additive)

- **NEW:** `alpha/memory/episodes.py` (`Episode`); `alpha/memory/store.py` (`EpisodeStore`: SQLite/FTS5 + `episodes`/`links` + `superseded`); `alpha/memory/recall.py` (`recall(asof,...)` + `touch`).
- **EDIT:** `alpha/agent/retrieval.py` (`select_for_prompt` → `recall`, gains `asof`; `Selection` gains `taboos`); `alpha/agent/prompt.py` + `alpha/agent/agent.py` (thread `state.as_of`); `alpha/refine/credit.py` (also write episodes + gated auto-adjust); `alpha/refine/refiner.py` (M-pass: feed episodes, carry provenance + `learned_asof`); `alpha/harness/memory.py` (`Lesson` gains optional fields).
- **UNCHANGED:** `MemoryStore` Protocol, `try_apply_op`, `SnapshotStore` (semantic layer stays in JSON), all existing tests.

### 6.10 Decisions to confirm

- **SQLite boundary.** Accept SPLITTING the substrate — semantic Lessons in the existing atomic JSON snapshot, ONLY episodes + FTS in a separate `brain.db`? (*Recommended.*) The alternative (everything in SQLite) forces a `.db` to participate in JSON-snapshot atomic rollback.
- **`learned_asof` for distilled Lessons.** Adopt `max(exit_date of summarized episodes)` (recommended), the more conservative refine-date (zero leak risk but starves fresh lessons in-backtest), or a configurable choice?
- **Auto-promote/demote on credit.** ON by default (sample floor + gated/logged demotes, recommended) or OFF until validated offline? It couples memory weight to the same advantage signal the breaker watches.
- **How much graph now.** Minimal `links` table as a derived read-convenience for the conversational face, or defer the conversational graph view entirely until deterministic recall + PIT mask + episodes ship? (*Lean: recall+episodes first, links second.*)
- **Recall latency budget.** Recall stays synchronous on the hottest path (`select_for_prompt` runs every `decide()`, core is non-async). Add a hard per-backtest-day latency budget / benchmark gate to the test suite so a recall regression can't silently slow every walk-forward run?

---

## 7. Sandbox & safety

**Provisional decision: adopt Hermes's execution sandbox as-is for now.** Hermes ships tool **environments** (docker / ssh / modal) that isolate tool execution. We use them for the conversational face's general tool-calling and any code-execution tools, inheriting Hermes's isolation model without building our own.

This is explicitly **provisional**. A Codex-grade sandbox (stronger filesystem/network/syscall confinement, deterministic resource limits) is **revisited later**, not now. The trading domain's hard safety lives elsewhere and is *not* delegated to the sandbox: red-lines (immutable doctrine), evidence floors, the screen/exposure-cap guardrails, the leak firewall, and the capability-floor breaker remain the real safety surface and all route through `try_apply_op`. The sandbox protects *tool execution*; the gate protects *the brain*.

**Open:** which tool classes (file write, shell, network) require which environment tier, and whether any trading tool (e.g. live order placement, if ever added) demands a stricter-than-Hermes confinement before it is exposed to the B-WIDE face.

---

## 8. Narrow-waist vendor boundary

> **Reframed to the Phase-0 spike reality (2026-06-27).** The Phase-0 vendor-feasibility spike (`spikes/2026-06-26-hermes-vendor-feasibility/FINDINGS.md`, NUANCED-GO) disproved the literal "lift these modules" plan: Hermes is a ~2 579-file daily-moving monolith and every target's *total* import footprint is the whole monolith. Only the **eager** footprint is liftable. Strategy C is therefore **"reimplement the thin parts + selective leaf-vendor of the one clean eager leaf."** The first three rows below are updated to that reality; the rest are unchanged.
>
| Concern | Disposition | Notes |
|---|---|---|
| Tool registry (`tools/registry.py`, OpenAI function-calling) + MCP consume/serve | **REFERENCE-VENDOR (pinned `5add283e`)** | clean eager leaf (1 file / 589 LOC, **no `agent/` drag**, per the spike). Committed at `third_party/hermes/` as the audited schema source-of-truth; the *active* code path is the `alpha/converse/registry.py` reimpl (parity-tested against it). Not imported in production. |
| Tool-calling conversation loop (`agent/conversation_loop.py`) | **REIMPLEMENTED (done)** | eager 28 files / drags the whole `agent/` package → the wrong thing to vendor; reimplemented as the thin tool-calling loop `alpha/converse/loop.py` (the B-WIDE face). |
| SQLite `state.db` + FTS5 (CJK trigram) resumable sessions | **REIMPLEMENTED SCHEMA (done)** | `hermes_state.py` is eager 7 files / drags `agent/`; the schema is the stable contract, not the code. Reimplemented as `alpha/converse/sqlite_store.py` (`state.db` + FTS5 trigram, `unicode61` fallback) — NOT a code-level vendor of `hermes_state.py`. Episodic `brain.db` (§6) uses the same SQLite/FTS5 substrate. |
| SOUL.md / SKILL.md / MemoryProvider file & hook model | **VENDOR (as projection)** | rendered *from* `H`; native writes intercepted → `RefineOp`s |
| `curator.py` decay-tick + stale→archive; `background_review` | **VENDOR (re-pointed)** | trigger only; ops routed through YOUR gate, not `write_approval` |
| Sandbox environments (docker/ssh/modal) | **VENDOR (provisional)** | §7 |
| `skills.write_approval` staging | **NOT vendored** | replaced by `try_apply_op` |
| Hermes `/learn` ad-hoc write path | **NOT vendored** | replaced by gated proposers |
| `rl_cli.py` / weight-level evolution | **NOT vendored** | lives in a separate repo; out of scope |
| Unified gate `try_apply_op`, red-lines, evidence floors | **KEEP YOURS** | the moat |
| 4-pass Refiner | **KEEP YOURS** | live online curator |
| Capability-floor breaker | **KEEP YOURS** | unchanged; preventive-adoption extension deferred with the offline Forge (§5.5–§5.6) |
| Offline InnerLoop / walk-forward scoring | **KEEP YOURS** | the sole fitness |
| Deterministic `decide` → `DecisionPackage` | **KEEP YOURS** | exposed as a registry tool |
| `HarnessManager` + `SnapshotStore` + `EditLog` | **KEEP YOURS** | the version authority |
| Offline self-study Forge (`alpha/evolve/`) | **DEFERRED** | designed-for, not built now (§5.6) — a future deepening of the self-study path |
| PIT memory (`alpha/memory/`) | **NEW** | episodes + recall + links |
| Provenance block on `EditRecord` | **NEW** | §5.4 |
| Hermes write-interception adapter | **NEW** | the M-only fast tier |

**Upstream-tracking policy — RESOLVED (2026-06-27): hard-pin SHA `5add283e`; do NOT track upstream.** The Phase-0 spike (§9) measured the coupling: the reachable static footprint is the entire ~2 579-file monolith, and even the little we vendor (only the eager leaf `tools/registry.py`, everything else reimplemented) would force re-running the coupling measurement across every Python file each rebase cycle to confirm the eager surface / schema contract had not shifted — a cost not justified by the benefit. The single stable artifact we depend on is the **tool-calling schema contract** (JSON-serialisable name/schema/fn triples), not the code. Pin the SHA; only bump deliberately when a specific upstream change is needed, and when you do, **re-run the spike's coupling suite (`spikes/2026-06-26-hermes-vendor-feasibility/coupling.py`) as a gating check.** Cross-reference: `third_party/hermes/PROVENANCE.md`.

---

## 9. Phased rollout ("逐个跟进")

### Phase 0 — Vendor-feasibility SPIKE (gating, do first)

**Goal:** prove the narrow waist is real before committing. Extract the minimum — `tools/registry.py`, `hermes_state` (SQLite/FTS5 session), and a minimal conversation loop — and demonstrate a **`decide` tool** and a **`write-file` tool** both routing through `try_apply_op` (or its gated artifact path) **WITHOUT dragging in the whole `agent/` monolith.**
**Done-criteria (success):** a single process registers and calls `decide` (returns a typed `DecisionPackage`) and a gated write tool, with the rest of the Hermes monolith *not* imported; vendored module set + their transitive imports enumerated; coupling depth measured.
**Fallback criteria:** if `registry` / `conversation_loop` cannot be lifted without pulling in the monolith (deep coupling), fall back to (a) a thinner reimplementation of the registry against the Hermes tool *schema* rather than its code, or (b) hard-pinning a fork. Decide the upstream-tracking policy (§8) here.

### Phase 1 — Conversational face (B-WIDE)

**Goal:** the (reimplemented) tool-calling conversation loop runs against the shared `H`, with `decide` + trading tools + PIT-gated recall registered.
**Done:** a multi-turn session can call `decide`, read memory PIT-safely, and **messages persist to SQLite (`state.db`) + FTS5 search**, artifacts to the git workspace; provenance ref stamped per turn. The registry was **reimplemented** (the active `alpha/converse/registry.py`) with the clean eager leaf **reference-pinned** at `third_party/hermes/tools/registry.py` (parity-tested); the SQLite session store was **reimplemented as a schema** (`alpha/converse/sqlite_store.py`), not a code-level vendor of `hermes_state.py` (§8).

### Phase 2 — Project workspace

**Goal:** `project = {resumable session + git workspace + H-version provenance}`; one shared brain, optional H-version pin.
**Done:** two concurrent projects share one `H`, isolate via separate git workspaces, each resumable, each carrying per-turn provenance; `DecisionPackage` recognized as a typed artifact in the workspace.

### Phase 3 — Self-evolution (two paths + provenance + conflict review)

**Goal:** generalize the existing Refiner + Sonia into the clean **two-learning-paths** framework (§5): self-study (Refiner) and teaching (Sonia), one gated brain, full edit **provenance**, and **conflict → user adjudication**. No GEPA.
**Done:** every mutation carries a `{path, proposer, evidence}` provenance block in the `EditLog`; `try_apply_op` has the third `held_for_review` outcome; a self-study op that would alter a teaching-owned `H` element is detected, held, and surfaced for the user to adjudicate in the cockpit; `/evolution` can filter by path/proposer and replay a lineage; existing tests green. (The Hermes fast self-study sub-tier and the offline Forge are deferred — §5.6, §5.7.)

### Phase 4 — Memory system

**Goal:** the "Stratum-with-edges" memory in its recommended rollout order.
**Order (each its own done-criterion):** (1) PIT-mask plumbing + regression test [closes the leak alone]; (2) episodes at `apply_credit`; (3) soft regime/narrative recall score; (4) taboo → L4 veto; (5) gated auto-adjust; (6) M-pass provenance; (7) offline recall-weight tuning (deferred — hand-set for now); (8) Hermes curator adapter LAST (riskiest seam, behind a flag).
**Done per step:** the named deliverable lands with tests; the PIT-leak test (step 1) passes across BOTH injection modes; existing tests stay green throughout.

> Phases 3 and 4 can interleave at the team's discretion (both are additive), but **Phase 0 strictly gates everything**, and within each, the PIT-mask plumbing (4.1) comes first.

---

## 10. Risks & open questions

**Top risks**

1. **`.db`-in-JSON-snapshot tension** — moving memory into a `.db` would break the atomic checkpoint/rollback invariant the breaker depends on. The split (semantic `Lesson` in the JSON snapshot, episodes in SQLite + a `superseded` flag) resolves it **only if** episodes stay strictly observation-channel and never enter `harness.to_dict()`.
2. **Cross-path contention on one shared `H`** — self-study (Refiner) and teaching (Sonia) both edit one brain. The `held_for_review` → user-adjudication policy (§5.4) bounds this: contested edits escalate to the human, non-contested apply autonomously. Residual risk is **review flooding** if "conflict" is defined too broadly — mitigated by the narrow definition + batching (§5.7).
3. **Memory feedback / popularity bias** — promoted Lesson → surfaced more → drives picks → promotes more; warm-on-access has the same shape (frequently-fired lessons starve rare-but-critical ones). The sample floor + gated/logged demotes + slow-decay taboo tier bound but do not eliminate it.
4. **Regime-distance metric is itself a modeling task** — the six-phase thermal ring is *categorical* today, so soft regime-similarity needs a hand-set ring-adjacency distance, hard-capped conservatively.
5. **Proposer nondeterminism** — Sonia (and any future hot-temperature self-study reflector) break temp=0 verdict-reproducibility; acceptable for *proposing*, but must be seeded + logged into Provenance to stay auditable.

**Verified structural limits**

6. **The G pass is a no-op today** (`PASS_TOOLS['G']=frozenset()`, verified) — "four components" is really **p/K/M** until sub-agent meta-tools exist. The design must not over-promise G evolution.
7. **Provenance proves WHO/WHAT, not soundness** — the gate cannot verify a `Trajectory` pointer actually justifies an op, nor that a held conflict was adjudicated *correctly*. It is an audit + routing aid, not a correctness guarantee.
8. **Hermes write-interception may be lossy** — arbitrary umbrella-merge/archive operations may not map onto the fixed `RefineOp` vocabulary, forcing dropped ops or new gate-whitelisted tools. The riskiest part of the Hermes tier and a reason to defer it.
9. **Episode growth** over multi-year walks needs a retention/compaction story (archive-not-delete keeps recoverability but drifts recall latency + db size). Defer compaction, but index `learned_asof` so time-window pruning is cheap.

**Unverified items requiring diligence (flagged, not assumed)**

10. **Vendor coupling depth** — RESOLVED by the Phase-0 spike (2026-06-27): of the three targets, only `tools/registry.py` lifts cleanly (eager = 1 file / 589 LOC, no `agent/` drag); `hermes_state.py` (eager 7 files) and `conversation_loop.py` (eager 28 files) both drag the whole `agent/` package, so they are **reimplemented**, not vendored (§8). The total reachable footprint is the entire ~2 579-file monolith.
11. **Upstream churn** — Hermes commits daily; pin-vs-rebase (§8) is RESOLVED to a **hard pin** (do not track upstream), grounded in (10).
12. **Repo social signals** — claims about Hermes's maturity/adoption are treated as **unverified**; correctness is established by the spike, not external reputation.

**Consolidated "Open" / decisions to confirm:** §5.7 (Hermes fast sub-tier timing, provenance schema, conflict flood-control); §6.10 (SQLite split, `learned_asof` rule, auto-adjust default, graph scope, latency budget); §7 (sandbox tiers, stricter confinement for any live-trading tool). (§8's vendor pin-vs-rebase is **RESOLVED** — hard-pin `5add283e`, do not track upstream, per the Phase-0 spike.) The offline GEPA-style self-study Forge and its remaining questions are deferred (§5.6).
