# A3 — Self-learning channel + context-management trio

> Design date 2026-07-13. Baseline: local main @ 1d2c953, 1740 offline tests, lint 0, tcb-check 0.
> Closes G10 (precondition) + builds the second learning channel (DEVELOPMENT-PLAN §2 A3).
> Additive / default-off / DORMANT: nothing here changes live behaviour until wired, and the
> context-trio path is byte-identical when off.

## Authority & sources

Charter (`Evolving-Agent-Design-SoniaKairos.md`) > Backend-Design > DEVELOPMENT-PLAN > code.
Charter sections this arc implements:
- *Session Is Not the Context Window* — recoverable context storage (the session) is SEPARATED
  from arbitrary context engineering (the loop); the raw record is never lost, the projection into
  the window is the loop's to reshape. Fixed point 5 (*Harness = Kernel + Body*): the context
  window belongs to no stratum — its content comes from Body+Session, its **assembly is kernel
  code** (sorting/filtering/**compaction/offload** enumerated in the *Immutable Kernel* loop row).
- *Dreaming: Letting Agents Improve Between Sessions* — a scheduled consolidation pass over the
  User-curated corpus that produces **deliberation proposals only**, never an ungated write; it
  runs as Sonia's plane. The self-learning channel is the deterministic, LLM-free floor of this.
- *First Founding Principle* (two hands, one waist) + *Refinement Triggers* (self-study
  fork-and-proposes; conflict with teaching/user_direct → HELD for USER adjudication).

Design inputs: kairos-mining §3 — the **context-management trio** row and the **off-hot-path
improvement detectors** row (`docs/findings/2026-07-01-kairos-design-mining.md`).

## The one hard invariant

The proposals produced by this channel go **through the existing gate** (`try_apply_op`, TCB) via
the existing fork wrapper (`run_forked_evolution`, TCB) — **no new write path is added**, and
**no TCB file changes** (verified: the gate already accepts every keyword this channel needs —
`task_stats`, `task_recall`, `asof`, `conflict_queue`, `provenance`). A proposal is an
`EvolutionProposal` in `/proposals`; the human adjudicates in Sonia. Zero live H write.

---

## PART 1 — The context-management trio (the G10 precondition)

Long Sonia/workbench sessions grow `Project.messages` without bound (it is both persisted and
re-fed to the model each turn — session and window are conflated in this repo today). The trio
separates them the charter's way: the **offload store is the recoverable session storage**; the
**compacted message list is the context-engineering projection**. Bytes are never lost — an elided
span is offloaded, addressed by hash, and recoverable through a T0 recall tool.

### Layer placement (the load-bearing constraint)

`alpha/converse` must never import `alpha/arena` (AST-pinned, `tests/arena/test_no_converse_arena_cycle.py`).
The offload store must be **rooted inside the Workspace, under the arena path-guard**. Therefore the
trio machinery lives in **`alpha/arena/context.py`** (new, non-TCB) and is **INJECTED** into
`converse_project` as a `compactor` callable — mirroring the existing `experience_writer` and
`registry_factory` injections. The workbench live-face (which DOES import arena) constructs one
`OffloadStore(workspace.root)`, builds the compactor over it, and registers the recall tool over
the SAME store. `converse` stays arena-free.

### 1a. Content-addressed offload store (`alpha/arena/context.py::OffloadStore`)

- Rooted at `<workspace>/.offload/`. `put(text) -> hash` writes `<root>/<hash>.txt` where
  `hash = sha256_bytes(text.encode())` (`alpha/integrity.py`, stdlib, leaf, no cycle). `get(hash)
  -> str | None` reads it back.
- **Path-guard (no escape).** Both `put` and `get` resolve the blob path and require
  `is_relative_to(root)`, AND `get` additionally validates the hash is 64 lowercase hex chars
  (`^[0-9a-f]{64}$`) before touching the filesystem — the recall tool feeds a MODEL-supplied hash,
  so `get("../../etc/passwd")` / `get("../secrets")` must return `None`, never read outside the
  store. This reuses the arena workspace path-guard discipline (`alpha/arena/tools.py::_within`);
  the offload root lives inside the workspace so an in-workspace shell cannot see outside it either.
- `.offload/` is never git-committed (`Workspace.commit_artifact` only commits explicit paths;
  `artifacts()` = `git ls-files` never lists it) — it is internal recoverable storage, not a
  deliverable.

### 1b. Provenance-preserving pruning marker

When a span is elided, the compacted stream carries a recoverable **handle**, not a silent drop.
Marker format (charter/mining, verbatim en-dash):

```
[...elided – recall hash={hash}]
```

A constant `ELIDED_MARKER = "[...elided – recall hash={hash}]"` and a parser
`elided_hashes(text) -> list[str]` (regex `\[\.\.\.elided – recall hash=([0-9a-f]{64})\]`) let the
recall test extract the hash back out and fetch the original. The marker rides on a **kernel-origin**
message (`origin="kernel"` — context assembly is kernel machinery, charter fixed point 5), so it is
never mistakable for model/tool/user content.

### 1c. 4-phase compaction with protected bookends (`compact_messages`)

```python
def compact_messages(messages, *, summarizer, offload_store,
                     protect_head=1, protect_tail=6, threshold) -> list[ChatMessage]
```

**Entry guard (dormancy):** if `threshold is None` or `len(messages) <= threshold` or there is no
middle to compact (`protect_head + protect_tail >= len(messages)`), **return `messages` unchanged**
(identity — byte-identical when off / under threshold).

Otherwise, the four phases:

1. **Partition** — `head = messages[:protect_head]` (the turn-0 task bookend); `tail =
   messages[-protect_tail:]` (the last-N bookend); `middle = messages[protect_head : len-protect_tail]`.
   The bookends are never touched.
2. **Offload** — serialize `middle` verbatim (role/origin/text per message, canonical) and
   `hash = offload_store.put(serialized)` — lose bytes not handles: the full original span is
   recoverable by hash.
3. **Summarize** — `summary_text = summarizer.summarize(middle)` (FakeSummarizer in the suite →
   deterministic; no LLM ever in tests).
4. **Splice** — reassemble `head + [kernel_note] + tail`, where `kernel_note` is one
   `ChatMessage(role="user", origin="kernel")` whose text is
   `f"[context-compacted] {summary_text}\n{ELIDED_MARKER.format(hash=hash)} — call recall(hash=…) "
   "to retrieve the {n} elided message(s) verbatim."`.

Repeated compaction is safe and recoverable (a prior marker inside a new middle is re-offloaded;
recall chains). `FakeSummarizer` (deterministic extractive: `[summary of N elided messages]` +
truncated role/first-chars digest) keeps the suite offline; `Summarizer` is a Protocol so a live
LLM summarizer is a swap-in at activation (the compaction MECHANISM is what A3 builds).

### 1d. T0 recall tool through the choke point (`make_recall_tool`)

`make_recall_tool(offload_store) -> (schema, fn, CapabilityTier.T0_OBSERVE)`. `fn(hash) ->
{"ok": True, "content": …}` on a valid in-store hash, else `{"ok": False, "error": …}` (guarded by
`OffloadStore.get`). Registered in `build_arena` (new keyword `offload_store=None`; None →
no tool → byte-identical) and dispatched through the single `ActivityPolicy.dispatch` choke point
at T0 (free/autonomous, read-only). The agent recovers any elided span by calling `recall`.

### 1e. Wiring (dormant)

- `converse_project(..., compactor=None)` — new keyword, default None. When present, applied AFTER
  the new user message is appended and BEFORE `run_conversation`, so the just-added turn sits in the
  protected tail: `project.messages = compactor(project.messages)`. Default None → the call is
  never made → **byte-identical** to today (primary DORMANT guarantee).
- `build_arena(..., offload_store=None)` — registers the recall tool when a store is present.
- Workbench live-face (`workbench/app.py`): reads a new dormant setting
  `Settings.context_compact_threshold` (env `ALPHA_CONTEXT_COMPACT_THRESHOLD`, default None). Unset
  → `compactor=None`, `offload_store=None` → fully dark, byte-identical. Set → constructs one
  `OffloadStore(ws.root)`, a `FakeSummarizer`-backed compactor, and passes both (mirrors the
  `_task_capture()` opt-in). A live LLM summarizer is the activation follow-up.

---

## PART 2 — The self-learning channel (the second learning path)

A **reflection→directions** stage on the Refiner's evidence path that reads the agent's OWN task
runs and proposes evolutions into the SAME cockpit — deterministic (LLM-free), read-only over
`kind="task"` episodes, routed through the one gate in a fork, surfaced as an `EvolutionProposal`.

### 2a. Reflection→directions detector (`alpha/refine/reflect.py`)

- `Reflection` (pydantic): `{skill_id, signal ("proven"|"underperforming"), evidence (dict:
  n/confirmed_n/confirmed_success_rate/dominant_failure_kind), rationale (str), op (RefineOp)}` —
  the human-readable "what the agent noticed about its own task runs".
- `reflect_over_tasks(episode_store, harness, *, asof, confirmed_ids=frozenset(), **floors)
  -> list[Reflection]` — deterministic, **read-only**. Reads `episode_store.for_asof(asof,
  kind="task", limit=None)` (PIT-masked; the `kind="task"` fence keeps it off every trade/verdict
  read — verdict symmetry preserved) and reuses `task_forge.propose_task_skill_ops` for the
  gate-enforceable candidate ops (promote/retire of **operational** skills only — NEVER trading),
  wrapping each in a `Reflection` with a `dominant_failure_kind` computed from the episodes'
  `failure_kind` field. No new op class, no new skills authored (avoids the create-and-forget
  funnel); the directions are exactly the confirmed-positive-floor promote/retire the gate already
  vets.
- `direction_signature(op) -> str` = `f"{op.tool}:{_target_id(op.tool, op.args)}"` — the stable
  key for negative-constraint matching (a "direction" = a verb on a target). A record-side twin
  `signature_from_record(record: dict) -> str` = `f"{record['tool']}:{record['target_id']}"` keeps
  proposal→constraint mapping consistent.
- `reflect_task_skills(harness, episode_store, meta, *, asof, confirmed_ids=frozenset(),
  negative_signatures=frozenset(), conflict_queue=None, task_recall=None, **floors)
  -> ReflectReport` — the apply driver (mirrors `forge_task_skills`):
  - for each reflection, if `direction_signature(op) in negative_signatures` → **suppress** (append
    to `report.suppressed`, never sent to the gate — the negative constraint bites here);
  - else route `op` through `try_apply_op(meta, harness, op, allowed=_FORGE_ALLOWED,
    provenance=EditProvenance(path="self_study", proposer="forge", evidence_kind="task",
    evidence_ref={"domain": …}), task_stats=…, conflict_queue=conflict_queue, task_recall=…,
    asof=asof, …)` — identical gate call to `forge_task_skills`, so the confirmed-positive floor,
    the operational-domain gate, and the conflict→held check all apply unchanged;
  - `ReflectReport(applied, held, rejected, suppressed, reflections)`.

### 2b. Negative constraints from human rejection (`alpha/meta/negative_constraint.py`)

- `NegativeConstraint` (pydantic): `{constraint_id, created_at, signature, tool, target_id, reason,
  source_proposal_id}`.
- `NegativeConstraintStore` (flat by-id JSON, ConflictQueue file pattern; root
  `Settings.neg_constraints_dir`, env `ALPHA_NEG_CONSTRAINTS_DIR`, default `./state/neg_constraints`):
  `add(...)`, `all()`, `signatures() -> frozenset[str]`, `resolve(id)`.
- `record_directions_from_proposal(store, proposal, reason="user_discard") -> int` — for each delta
  record, `signature_from_record(record)` → one `NegativeConstraint`. This is the **human-rejection
  mining** step: a rejected direction becomes a constraint, **never re-proposed** (the detector
  reads `signatures()` and suppresses).
- The store is NOT coupled to brain seqs (signatures, not edit positions), so a brain rollback does
  not invalidate it — no cross-face reconcile-sweep coupling needed (unlike the five brain-state
  dirs).

### 2c. Producer (`scripts/reflect_from_tasks.py`)

Mirrors `scripts/evolve_from_episodes.py`. Default mode `"propose"`:
- loads `neg_signatures = NegativeConstraintStore(neg_dir).signatures()`;
- builds a `runner(h, log)` that calls `reflect_task_skills(h, EpisodeStore.open(db),
  MetaTools(h, log), asof=…, confirmed_ids=_derive_confirmed_task_ids(log), negative_signatures=
  neg_signatures, conflict_queue=ConflictQueue(...), task_recall=EpisodeStore.open(db))` on the
  **fork** and returns `(h, log)`;
- `run_forked_evolution(bstore, runner, queue=ProposalQueue(root), kind="reflect",
  window={"asof": …, "reflections": [...]})` → the surviving delta ships as an `EvolutionProposal`
  (`kind="reflect"`). **The live brain is byte-untouched; episodes are only READ.** Held conflicts
  land in the live `ConflictQueue` deliberately (user-adjudication signals), exactly like
  `evolve_from_episodes`.
- `confirmed_ids` is derived from durable human-approved EditRecords via the existing
  `apply._derive_confirmed_task_ids(log)` (read-only, forgery-resistant at the waist, §2.3); the
  gate independently re-derives via `task_recall`+`asof` (defense-in-depth). Empty in the dormant
  default (no confirmations → no promotes → no proposal — correct dark behaviour).
- `mode="autonomous"` escape hatch, gated by `ALPHA_UNSAFE_AUTONOMOUS=1`, mirrors the other two
  self-study scripts (recorded pre-pivot non-conformance).

`kind="reflect"` is safe against the TCB `adopt_proposal`: `EvolutionProposal.kind` is a plain
`str`; adopt's only use of `kind` is the fallback proposer (`"refine"→refiner else forge`), which
never triggers because the delta records already carry explicit `self_study/forge/task` provenance.

### 2d. Cockpit hook — discard mines the direction (`sonia/app.py`, non-TCB, additive)

`POST /proposals/{pid}/resolve` discard branch: when the discarded proposal is `kind=="reflect"`,
call `record_directions_from_proposal(NegativeConstraintStore(...), prop)` before `resolve(pid)`.
Guarded by try/except (a store failure never breaks the discard response) and scoped to
`kind=="reflect"` (discarding a refine/forge packet creates no constraints — those aren't
self-learning directions). Naturally dormant: reflect proposals only exist if the reflect producer
ran.

The two-learning-paths invariant is preserved end to end: self-study **forks-and-proposes** (never
auto-applies); a direction contesting a teaching- or user_direct-owned element is **HELD** at the
gate (`is_conflict`, unchanged); a **user-rejected** direction becomes a negative constraint and is
never re-proposed.

---

## TCB accounting

**Zero TCB files change.** The proposals ride the existing `try_apply_op` / `run_forked_evolution`
/ `adopt_proposal` unchanged. `scripts/gen_tcb_lock.py --check` stays 0; no regen. New non-TCB
files: `alpha/arena/context.py`, `alpha/refine/reflect.py`, `alpha/meta/negative_constraint.py`,
`scripts/reflect_from_tasks.py`. Touched non-TCB files: `alpha/converse/session.py` (+`compactor`
kw), `alpha/arena/builder.py` (+`offload_store` kw), `alpha/settings.py` (+2 dormant fields),
`workbench/app.py` (dormant opt-in), `sonia/app.py` (discard hook). The offload store reuses — never
weakens — the arena/LocalEnv workspace path-guard.

## Dormant / default-off / zero-live-write proofs (the acceptance gate)

1. **Trio byte-identical when off** — `converse_project(compactor=None)` (default) never calls
   compaction; `compact_messages(threshold=None | len<=threshold)` returns its input; `build_arena
   (offload_store=None)` registers no recall tool; workbench with `ALPHA_CONTEXT_COMPACT_THRESHOLD`
   unset passes all-None. Tested at every level.
2. **Pruning loses bytes-not-handles + recall round-trips** — a compacted stream carries the
   `[...elided – recall hash=X]` marker; `recall(hash=X)` (T0, through `ActivityPolicy.dispatch`)
   returns the original span verbatim.
3. **Offload respects the path-guard** — `OffloadStore.get("../../etc/passwd")` / a non-hex hash →
   `None`; the recall tool never reads outside `<workspace>/.offload/`.
4. **4-phase protects the bookends** — turn-0 task (head) and the last-N (tail) are byte-identical
   pre/post compaction; only the middle is replaced by summary+marker.
5. **Detectors → EvolutionProposal, ZERO live write** — `reflect_task_skills` in a fork yields a
   surviving delta packaged as an `EvolutionProposal` in `/proposals`; the live brain hashes
   identically before/after; the human adjudicates.
6. **Rejected direction → negative constraint, not re-proposed** — after
   `record_directions_from_proposal`, a re-run of `reflect_task_skills(negative_signatures=…)`
   suppresses that direction (in `report.suppressed`, absent from the delta).
7. **Conflict → HELD** — a self-study direction contesting a teaching/user_direct-owned skill is
   held at the gate (`held_for_review`), lands in the ConflictQueue, never applies.
8. **Verdict symmetry + PIT masking pinned** — the detector reads only `for_asof(asof,
   kind="task")`; a `kind="trade"` verdict read is unaffected; PIT masking (`learned_asof<=asof`)
   holds. A regression test pins that no trade/verdict read observes task episodes.

## Tests (offline, keyless — FakeSummarizer, MockLLMClient, no new deps)

- `tests/arena/test_context_offload.py` — OffloadStore put/get + path-guard escape (#3) + recall
  tool through the choke point (#2).
- `tests/arena/test_compaction.py` — 4-phase protects bookends (#4), leaves recoverable marker
  (#2), byte-identical under threshold + threshold None (#1), FakeSummarizer deterministic.
- `tests/converse/test_converse_compaction.py` — `converse_project(compactor=None)` byte-identical
  (#1); injected compactor compacts + recall round-trips through the arena dispatch (#2).
- `tests/refine/test_reflect.py` — reads kind="task" only (#8), signature stable, negative filter
  suppresses (#6).
- `tests/refine/test_reflect_propose.py` — fork → EvolutionProposal, zero live write (#5);
  conflict → held (#7).
- `tests/meta/test_negative_constraint.py` — store add/all/signatures + record_from_proposal.
- `tests/scripts/test_reflect_from_tasks.py` — producer: task episodes → proposal in /proposals,
  live brain byte-identical; a stored negative signature suppresses the re-proposal.
- `tests/sonia/test_proposal_negative_constraint.py` — discard of a reflect proposal records the
  negative constraints; discard of a forge/refine proposal records nothing.
- `tests/workbench/test_compaction_dormant.py` — workbench byte-identical when threshold unset.

## Deliberately not done / needs user judgment (report to team lead)

- **Live LLM summarizer** for compaction — A3 ships the MECHANISM + FakeSummarizer; the real
  summarizer is an activation-time swap behind `ALPHA_CONTEXT_COMPACT_THRESHOLD`. Recorded as an
  activation follow-up, not a gap.
- **Richer reflections** (new-skill authorship, patch-from-failure-kind directions) — deliberately
  out of scope: the create-and-forget funnel (charter *Component Lifecycle*, ~95% never succeed)
  makes ungated new-skill authorship risky; A3 keeps directions to the gate-vetted promote/retire
  set. Trigger: task-evidence density high enough to warrant a patch-direction design round.
- **Negative-constraint expiry / review cadence** — constraints accumulate append-only (mirrors
  never-auto-destroy); a keep-last-K / staleness pass is a §3 small-pool follow-up.
- **DEVELOPMENT-PLAN / PROJECT_STATE / Backend-Design sync** — this arc does not edit those; the
  sync rows (delete A3 from the plan, append PROJECT_STATE, close the Backend-Design G10 precondition
  row) are reported to the team lead for the landing commit.
