# SoniaKairos General Core — Design

**Date:** 2026-07-06 · **Status:** approved in brainstorming (all sections user-confirmed)
**Charter:** `~/Desktop/self-evolve/Evolving-Agent-Design-SoniaKairos.md` (the north-star design doc)
**Evidence base:** `docs/findings/2026-07-01-kairos-design-mining.md`,
`docs/findings/2026-07-02-kairos-architecture-comparison.zh.md`,
`docs/findings/2026-07-02-charter-conformance.zh.md` — all claims below about either codebase
were code-verified there.

---

## 1. Goal

Extract a **domain-neutral self-evolving agent core** ("SoniaKairos") from the two existing
codebases — `evolving-alpha-us` (finance) and `kairos` (legal) — so that finance and legal become
**plugins** behind a small domain contract, and the core can later re-enter both industries.

The core = Session + Loop + Sandbox + Harness-Store + evolution (Sonia teaching + self-study
Refiner + Applier) + episodic memory + governance. A domain plugin provides only four things:
**perception, decision schema, fitness/acceptance policy, seed content**.

## 2. Locked decisions (from brainstorming, in order)

| # | Decision | Choice |
|---|---|---|
| D1 | Foundation strategy | **alpha as skeleton, graft kairos strong parts, domains as plugins.** When both repos implement the same concern, alpha's implementation wins by default (it is the literal Sonia+(p,G,K,M) lineage, single-process, offline-testable); kairos supplies the mechanisms alpha lacks. |
| D2 | Charter ambition | **L2: reorganize + build exactly the three merge-forced charter primitives** (Applier w/ deliberation-ID FK, unified event log, candidate→canary→stable). Deliberation-packet UI, preference charter (K4), instruction-extraction gate (K6), telemetry — deferred backlog. |
| D3 | Deployment posture | **Single-user local first, seams reserved.** Files/SQLite persistence, few local processes, no auth. Stores behind Protocols; `scope` field (charter F4) on every learned-context write from day one so multi-user is a backend swap, not a refactor. |
| D4 | Sequencing | **Extract-first (option A):** SP1 extraction (parity gate) → SP2 primitives → SP3 grafts → SP4 faces → SP5 legal vertical. |

## 3. Extraction boundary (alpha's 17 packages, three-way split)

| Class | alpha packages | Destination |
|---|---|---|
| **Generic → core** | `harness/` `refine/` `meta/` `converse/` `arena/` `llm/` `memory/` `loop/` | Move into `soniakairos/` (renames: `refine/`→`evolve/`, `meta/`→`teach/`). Trading-specific *content* (doctrine text, seed skills) moves out into the finance vertical's seeds. |
| **Domain → finance plugin** | `data/` `universe/` `features/` `state/` `regime/` `sizing/` `guard/` | Move into `verticals/finance/`, attached to the core only through the domain contract (§5). |
| **Seam → split in two** | `eval/` (engine: walk_forward/stats/trajectory/*_store = generic; schema: DecisionPackage/Candidate/Portfolio + oracle = finance) · `agent/` (LLM loop = generic; prompt/parse finance schema = domain) | Generic halves → `soniakairos/eval/`, `soniakairos/agent/`; finance halves → `verticals/finance/`. `DecisionPolicy.decide(state, universe)` generalizes to `Policy.decide(Observation) -> Decision`. |

From kairos, nothing is forked wholesale; specific mechanisms are ported in SP2/SP3 (see §6).

## 4. Core repo layout + the three L2 primitives

New sibling repo `~/Desktop/self-evolve/soniakairos`. Tooling: uv + pytest + ruff (kairos's
toolchain hygiene on alpha's code). One installable package `soniakairos` + `verticals/` packages.

```
soniakairos/
  harness/    H=(p,G,K,M) container, doctrine/skill/memory models, manager/snapshot/loader
  evolve/     (was refine/) refiner, forge, credit, signatures, conflict, ops
  teach/      (was meta/) SoniaAgent, MetaAgent, LiveBrainStore, sessions, ingest
  converse/   conversational face        arena/   ActivitySpace, ToolEnvironment, ActivityPolicy
  memory/     EpisodeStore (+ scope)     llm/     clients + make_client(role)
  agent/      generic LLM decide loop    eval/    generic engine half (walk_forward, stats, stores)
  applier/    ① NEW  deterministic apply service (see §5)
  eventlog/   ② NEW  unified append-only event/trace log
  version/    ③ NEW  candidate→canary→stable change-set state machine
  domain/     the four Protocols + Vertical registry (§5)
  app/        single-user local faces: console, teach service, workbench (SP4)
verticals/
  finance/    data/universe/features/state/regime/sizing/guard + DecisionPackage schema
              + gross-return oracle Fitness + algorithmic-floors AcceptancePolicy + seeds/
  legal/      (SP5) citation-verify Fitness + human-approval AcceptancePolicy + seeds/
```

**The three L2 primitives** (each welds shut a divergence found in the conformance analysis):

| Primitive | Divergence it closes | Built from |
|---|---|---|
| ① **Applier + deliberation-ID FK + pluggable acceptance** | alpha's `try_apply_op` vs kairos's `VersionManager` (two write-waists); charter H3's "every persistent mutation carries a deliberation-ID FK"; charter J1/J2 paradigm split (finance auto-accepts, legal human-approves) resolved by making acceptance a strategy | alpha `try_apply_op` + `MetaTools` + `EditLog`, plus an optional `deliberation_id` field on `EditRecord` (frozen-pydantic additive) and the `AcceptancePolicy` seam |
| ② **Unified event log** | kairos's ephemeral in-memory TraceSink (charter C2 violation); neither repo has a true append-only session stream (A1) | New: SQLite append-only table behind a Protocol. Harness-version stamp, cost, deliberation-ID backlinks, correction marks = event metadata. `EditLog`/`DecisionStore`/`EpisodeStore` remain the typed system-of-record projections; the event log is the cross-cutting stream. |
| ③ **candidate→canary→stable** | alpha's "edit→live immediately→breaker reverts after damage" vs kairos's canary tier; gives both verticals one adoption path | kairos's version state machine (statuses + one-stable partial-unique semantics), with canary evaluation supplied by the Vertical (finance: `compare_harnesses` shadow replay — alpha already owns the strongest instrument) |

## 5. Domain contract (the only coupling between core and vertical)

```python
# soniakairos/domain/contract.py

class Observation(Protocol):              # perception input (finance = MarketState+CandidateUniverse)
    asof: datetime                        #   PIT anchor — event log + for_asof recall
    def prompt_block(self) -> str: ...    #   domain context rendered into the user prompt

class Perceiver(Protocol):                # finance = build_universe + build_market_state
    def perceive(self, asof: datetime) -> Observation: ...

class Decision(Protocol):                 # action output (finance = DecisionPackage)
    asof: datetime
    def attributions(self) -> list[str]: ...   # skill/pattern refs → credit assignment
    def dump(self) -> dict: ...                # serialization → event log + decision store

class DecisionCodec(Protocol):            # finance = the finance half of agent/parse.py
    def output_contract(self) -> str: ... # JSON output contract injected into the system prompt
    def parse(self, raw: str, obs: Observation) -> Decision: ...  # hallucination defense: re-anchor to obs

class Fitness(Protocol):                  # finance = gross-return oracle + advantage
    def score(self, decision: Decision, asof: datetime) -> list[Outcome]: ...
    # Outcome{ref, value, learned_asof, kind}; learned_asof is the PIT key feeding
    # credit → SkillStats → Episodes. Value semantics are domain-defined; the core only
    # compares and applies floors.

class AcceptancePolicy(Protocol):         # the Applier's pluggable hinge
    def evaluate(self, op: RefineOp, evidence: Evidence, provenance: EditProvenance) -> Verdict: ...
    # Verdict = accept | reject(reason) | hold  → held items land in ONE pending inbox

class Vertical(BaseModel):                # one industry = one Vertical registration
    name: str                             # "finance" / "legal"
    perceiver: Perceiver
    codec: DecisionCodec
    fitness: Fitness
    acceptance: AcceptancePolicy
    policy_wrappers: list[PolicyWrapper]  # domain decorator stack; finance keeps
                                          #   SizingPolicy(GuardedPolicy(·)) verbatim
    canary_evaluator: CanaryEvaluator | None   # finance = compare_harnesses shadow replay
    seeds_dir: Path                       # initial doctrine/skills/lessons content
```

**Applier pipeline** (splits today's `try_apply_op` into a generic structural gate + pluggable
acceptance):

```
propose(op, provenance)
  ├─ structural gate (generic; today's try_apply_op front half):
  │    tool whitelist · non-empty rationale · domain set-once ·
  │    teaching-vs-self-study conflict detection (conflict → the same pending inbox)
  ├─ AcceptancePolicy.evaluate(op, evidence, provenance)
  │     accept ───────────────┐   ← finance: algorithmic floors (n ≥ min, expectancy > 0), unattended
  │     hold → pending inbox  │   ← legal: always hold; human approval re-enters as accept
  │     reject → recorded     │
  ├─ mint deliberation_id ────┘
  ├─ dispatch → MetaTools → EditRecord(deliberation_id=FK)          ← primitive ①
  ├─ eventlog.append(edit_applied, {deliberation_id, h_version, …}) ← primitive ②
  └─ version/: change-set → candidate → canary (shadow) → stable    ← primitive ③
```

Three commitments baked in:

1. **One pending inbox.** Held edits, teaching-vs-self-study conflicts, and human-approval queues
   converge on a single inbox entity (today alpha has three divergent shapes: transient Refiner
   ops, Sonia session edits, workbench StagedEdits).
2. **Evidence re-derived inside the gate.** The Applier re-derives `Evidence` from Fitness
   outcomes / episodes via a read-only, PIT-pinned store handle — never trusting caller-supplied
   stats (fixes the caller-supplied `task_stats`/`confirmed_ids` asymmetry found in review).
3. **Domain decorator stacks stay out of core.** The core fixes only the shape: wrappers compose
   around the generic agent loop; finance injects `SizingPolicy(GuardedPolicy(·))` unchanged.

## 6. Sub-projects and acceptance gates

| SP | Content | Acceptance gate |
|---|---|---|
| **SP1 Extraction** | New repo; move generic packages (renames per §3); split `eval/`+`agent/` seams; finance becomes the first Vertical; port the test suite | **alpha's ~880 tests green in the new layout** (behavior-parity proof). No new features. |
| **SP2 Primitives** | Build `applier/`, `eventlog/`, `version/`; route finance through the new Applier pipeline; delete the old direct waist | Finance vertical runs end-to-end through Applier; deliberation-ID present on every new EditRecord; canary shadow-run demonstrated on a replay window |
| **SP3 Grafts** | kairos strong parts: env-whitelist for `LocalEnv` + `redact()` at persistence waists (closes the B1 credential leak), SSRF resolve-and-pin, connector manifest model, hash-chained audit projection of the event log | Each graft lands with regression tests; cheap items (env whitelist, redact, SSRF) may ride along in SP1/SP2 where natural |
| **SP4 Faces** | console / teach service / workbench rebuilt on the new core (single-user local; HTTP-not-imports preserved) | Teaching loop + conversational face usable end-to-end against the new core |
| **SP5 Legal vertical** | `verticals/legal/` skeleton: citation-verification Fitness, human-approval AcceptancePolicy, legal seeds; kairos's matter concept simplified as needed | Second Vertical registers and runs; proves the domain contract carries a second industry |

Each SP gets its own implementation plan (`docs/superpowers/plans/`). SP1 is planned first.

## 7. Invariants carried forward (non-negotiable in the new core)

From alpha's CLAUDE.md §5, generalized:

1. **PIT firewall** — generalized to "no future leakage past `asof`": `learned_asof` on all
   learned content; `for_asof` masking; GuardedSource stays finance-side but the discipline
   (as-of guards on Perceiver output) is core doctrine.
2. **One write-waist** — every brain mutation flows through the Applier → MetaTools → EditLog;
   no side channels. (Strengthened by the deliberation-ID FK.)
3. **Immutable doctrine core** — red-line entries reject mutation; the kernel enumeration grows
   toward the charter's Immutable Kernel over time.
4. **Verdict read/write symmetry** — shadow/canary arms get read-only recall handles, never
   write handles.
5. **Decorator order fixed by the Vertical** — core never reorders `policy_wrappers`.
6. **Eval neutrality** — scoring never reads sizing/presentation fields; `deliberation_id` and
   event-log metadata are never read by eval.

Charter mappings added by this design: F4 scope labels (day one), H3 deliberation-ID FK (SP2),
C2 traces-same-store (SP2), J1/J2 resolved as pluggable acceptance (finance auto / legal human).

## 8. Testing strategy

- **SP1 = parity, not novelty.** The ported alpha suite is the acceptance instrument; test moves
  mirror package moves (`tests/<core-pkg>/`, `verticals/finance/tests/`). Fully offline
  (FakeSource/MockLLMClient), temperature=0 determinism preserved.
- **SP2+ = TDD.** Each primitive lands with its own suite; the Applier pipeline gets a
  contract-test battery that any `AcceptancePolicy` implementation must pass (accept/hold/reject
  × conflict × evidence-re-derivation).
- **Domain-contract conformance kit:** a reusable test suite any new Vertical runs against its
  Perceiver/Codec/Fitness/AcceptancePolicy (the mock-domain toy vertical lives here as the
  reference implementation).

## 9. Error handling posture

Carried from both parents: fail-closed at gates (untiered tool → refused; missing evidence →
floors unmet; unknown acceptance verdict → hold), never-500 at faces, loud-fail at data seams
(corrupt store → explicit error, never silent empty). The breaker's autonomous rollback survives
as the finance vertical's posture; core additionally files a "suspect edits + evidence" event
into the pending inbox on every breaker trip (charter J2 grafted onto alpha's mechanism).

## 10. Non-goals (explicitly out of scope for this arc)

- Multi-user / auth / RLS (seams reserved via D3; not built).
- git-per-instance harness store (charter I1): both parents diverge reasonably; snapshot +
  event log + hash-chain audit meet the audit/revert goals. Revisit at body-axis time.
- Full charter v2.5 (deliberation-packet UI, preference charter K4, instruction gate K6,
  per-component telemetry L1) — backlog after SP2 proves the primitives.
- Vault/token-proxy full stack — env-whitelist + redact suffice for single-user operator-trust.
- Kernel sandbox (`SandboxedEnv`) and body-axis R3+ — unchanged from alpha's deferral.
- Migrating kairos's legal product onto the core (SP5 builds a legal *vertical skeleton*, not a
  kairos replacement).

## 11. Risks

| Risk | Mitigation |
|---|---|
| Seam split of `eval/`/`agent/` breaks hidden couplings (4 known lazy-import cycles) | SP1 moves lazy imports verbatim; parity gate catches import-time regressions; cycle edges documented in the new repo's CLAUDE.md |
| Applier refactor of `try_apply_op` changes gate semantics | SP2 keeps the existing gate tests running against the new pipeline before deleting the old waist |
| "Generic" primitives accidentally shaped by finance (only one real vertical until SP5) | Domain-contract conformance kit + mock toy vertical from SP2 onward; legal vertical (SP5) is the real proof |
| Two-repo drift during the arc (alpha keeps evolving) | SP1 snapshots a pinned alpha commit as the extraction base; changes after the pin are cherry-picked deliberately |
