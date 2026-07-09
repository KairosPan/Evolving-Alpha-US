# Two-way alignment: Sonia-Kairos design charter ↔ this codebase

**Date:** 2026-07-09 · **Method:** 31-agent workflow — 5 exhaustive readers (charter, backend
design, design ledger, code naming audit, code architecture-reality audit) → forward/reverse
synthesis → adversarial verification of every load-bearing claim (24 verified: **21 CONFIRMED,
3 CORRECTED, 0 REFUTED**). Sources pinned: design repo `../Sonia-Kairos/` as of 2026-07-09;
this repo at `main` @ `a1a8acd` (919 tests).

> **Naming note:** as of 2026-07-09 this repo is **Sonia-Kairos-US-Stock** (formerly
> Evolving-Alpha-US). **Sonia** = teacher (`alpha/meta/` + `sonia/`); **Kairos** = worker
> (`converse/` + `arena/` + `workbench/`). Lowercase `kairos` below = the sibling CN legal-agent
> donor repo. The design charter's "harness" = Kernel ∪ Body; this repo's (and the paper's)
> "harness" = the evolvable playbook `H` = the charter's **Body**.

---

## Part A — Forward: what changed in this repo (landed 2026-07-09)

All landed this session; recorded here for the log, details live in the diffs:

1. **Rebrand** to Sonia-Kairos-US-Stock across CLAUDE.md §1 (with an honest divergence note vs
   the charter's 2026-07-06 pivot), README, pyproject description, doc headers
   (blueprint/PROJECT_STATE/ROADMAP), web console title + brand mark, workbench title, the live
   Kairos system prompt (`converse/agent.py`), verdict-run banner, ingest User-Agent.
   Kairos naming **option (A)** chosen: the worker face carries the name AS-IS; its divergences
   (T3 `propose_memory_edit`; `write_mode="apply"` lands its own edit through the gate) are
   documented, not hidden.
2. **CLAUDE.md drift fixes:** freshness `dce2a0a`/704 → `a1a8acd`/919 + owner/review date; the
   entire `alpha/arena/` package added to spine/map (it was absent!); 6 newer modules mapped
   (`extractor.py`, `approve.py`, `task_forge.py`, `refiner_prompt.py`, `baselines.py`,
   `errors.py`); terminology bridge added (harness trap, Sonia/Kairos roles, lowercase kairos);
   blueprint "Authoritative" claim scoped to perception/eval v1.0.
3. **README truth repair:** US-1/US-2/US-3 were still marked "Planned" — all are built; stale
   `docs/ROADMAP.md` links repointed at the root backlog; `docs/ROADMAP.md` stubbed to a pointer;
   Kairos workbench section added; License line made honest.
4. **Packaging:** `workbench*` added to `pyproject` `packages.find` (a wheel build silently
   dropped the service).
5. **Deferred, recorded in `ROADMAP.md` §7 Naming:** GitHub repo rename + design-repo pointer
   sync; EditProvenance migration (`'hermes'`→`'kairos'`, add `'user'`, populate
   `human_approver`); subdirectory CLAUDE.md files + committed settings deny-list. The import
   package stays `alpha`, env prefix stays `ALPHA_*` (~1,340 import lines / ~296 files;
   rename cost ≫ value).

Full suite green after the rebrand (919 tests, exit 0).

---

## Part B — Reverse: what this codebase suggests to the design repo

**Landing discipline (respect it):** architectural/governance items = proposed **charter
amendments** (dated markers, then sync down); precision/presentation items = **backend sync
corrections** landing directly in `Backend-Design-SoniaKairos.md`; process items = **ROADMAP
appends**. Never edit the frozen `docs/research/` records. This file is itself a frozen record —
each item below is a suggestion for the design repo's own process, not an edit made there.

Verification status: rev-01…rev-12 adversarially verified this session (11 CONFIRMED,
rev-08 CORRECTED-and-strengthened); rev-13…rev-19 evidence-cited but not independently
re-verified.

### B1. Factual corrections — the design doc is wrong today

- **rev-01 (critical) · Charter internal contradiction: memory failure semantics.**
  Charter line 33 (Memory Stores bullet, 2026-07-07 sentence) still says an unreconcilable store
  *quarantines the session*, while line 383 (revised with Mem0, 2026-07-09) declares memory *the
  deliberate exception* that self-heals by journal rebuild. The founding enumeration states the
  opposite of the mechanism section it points to. Amend line 33 to state the memory exception
  (new dated marker alongside the old). *(CONFIRMED)*

- **rev-02 (critical) · Anti-donor pointer is unresolvable.** Backend §4 (lines 368/379) names
  "α `floor_breaker.py` … its auto-`rollback_to` is deleted" — but `floor_breaker.py` is pure
  detection math with zero `rollback_to` hits; the machine-revert actually lives in
  `loop/inner_loop.py` (trip → `self._mgr.rollback_to(target)`) + `harness/manager.py::rollback_to`.
  Correct the citation so the demolition map greps true. *(CONFIRMED)*

- **rev-16 (medium) · Sonia "zero egress" vs her own vendor LLM calls.** `sonia/propose` and
  dreaming are LLM-driven; a vendor-hosted model call IS an outward socket (this repo's Sonia
  calls DeepSeek directly — `sonia/app.py:92,133`). State where model-inference egress physically
  exits (kernel-mediated dispatch) and carve it out of the SP2 zero-egress socket test, or the
  test as written fails any vendor-model Sonia.

### B2. Donor-map refresh — backend §5 vs `main` @ `a1a8acd`

- **rev-03 (high) · Five new organs are unmapped** (the map's alpha snapshot post-dates P-A but
  predates teach-crystallize v5): (1) `meta/extractor.py::extract_ops` +
  `refine/ops.py::parse_extraction` → `sonia/propose` prior art; (2) `converse/approve.py`
  (`StagedEdit`/`assert_approvable`) → `kernel/approvals` prior art (currently cites κ only);
  (3) `meta/conflict_store.py::ConflictQueue` + `refine/conflict.py::is_conflict` → `sonia/triage`
  prior art; (4) `arena/experience.py` + the `experience_writer` seam + `Episode.kind∈{trade,task}`
  → the "episodes are appended session events" row's located implementation; (5) P-C's
  domain-tagged operational-K gate machinery → scope-labeled Body content prior art. *(CONFIRMED)*

- **rev-04 (high) · Missing anti-donor: the worker-face brain-edit channel.**
  `arena/builder.py` registers `propose_memory_edit` at T3 whenever `write_mode∈{apply,stage}`,
  and `converse/tools.py::make_gated_write_tool` in `apply` mode lands the worker's own edit live
  via `try_apply_op` with no human step — the most direct violation of "Kairos does not propose
  and does not self-edit", yet the does-not-survive list omits it. Add it. *(CONFIRMED)*

- **rev-14 (medium) · Faces have no home in the §3 layout tree**, though the doc has owned the
  faces since the 2026-07-09 frontend-design teardown and SP4 builds three of them. Add a
  `faces/` (or `apps/`) entry citing this repo's proven three-apps-over-HTTP pattern
  (:8100/:8810/:8820, HTTP not imports, offline-testable with a mock model) — and encode the
  battle-found packaging trap: pin the packaging manifest to the face roster (workbench was
  silently dropped from wheels here until 2026-07-09).

### B3. Proposed charter amendments — battle-tested lessons the charter lacks

- **rev-05 (high) · Never-silent proposal crystallization.** Prose→proposal transduction must be
  an explicit schema-enforced act returning ops **or** `{no_edit, reason}` — silent empty
  extraction is a contract violation surfaced to the user. This is teach-crystallize v5's core
  lesson: the gated write path was never the gap; teaching evaporated *upstream* of the gate when
  volunteered ops parsed to `[]` silently. Donor: `extract_ops`/`parse_extraction`. *(CONFIRMED)*

- **rev-06 (high) · Trial arm-symmetry: read/write-handle split.** When an evolving arm runs
  against a frozen arm, the evolving arm is denied the WRITE handle on shared learned state for
  the comparison's duration; all arms read the same fixed pool. Today this exists only as a
  backend donor-cell remark — an evaluation-fairness rule that per the repo's own discipline
  belongs in the charter. Also annotate the deferred counterfactual-blind-comparison decision
  with "donor located: `loop/compare.py::compare_harnesses`". *(CONFIRMED)*

- **rev-07 (high) · PIT / knowable-as-of discipline.** The charter has **zero** PIT/lookahead
  concept, yet the backend already load-bears on `learned_asof` (§5, Fitness Protocol, SP3/SP5,
  §8 invariants) — a downstream doc leading the charter. Concretely: charter line 430's trial
  fork reads *current-tip* memory read-only, so a replay of last month can consult facts learned
  last week — dishonest evidence. Amend: learned artifacts carry a knowable-as-of key; every
  replay/trial/counterfactual masks retrieval to it. *(CONFIRMED — and the only "point-in-time"
  string in the charter is the unrelated audit-recovery sense at line 244.)*

- **rev-08 (high) · Ratify episodes-as-session-events + define saturation metrics.**
  (a) Kernel-observed per-decision outcome facts are kernel-written session events, NOT
  memory-content proposals — they never transit the approval queue; only interpretations do
  (backend §5 already asserts this; its own §10 risk row flags the charter never spelled it out).
  (b) Replace qualitative queue-saturation/starvation revisit triggers with measurable ones.
  *(CORRECTED, strengthened: this repo writes one PIT-keyed episode per scored **pick** — several
  per decision-day, not one — so routing facts through the approval queue saturates it even
  faster than first claimed.)*

- **rev-09 (high) · Revert must reconcile ALL derived state.** The reconcile set includes every
  derived record asserting a landed edit exists (session-side applied-flags, queue/terminal
  states, UI dispositions), not just the declared stores. Live specimen: this repo's `/rollback`
  restores the brain but leaves `applied_seqs` on the session → `/propose` 409s and the
  teaching turn is permanently dead (tracked in our ROADMAP). *(CONFIRMED)*

- **rev-10 (high) · Contest/hold when a Sonia proposal targets a user-landed edit.** The
  2026-07-08 second trigger created two writer provenances; nothing says what happens when
  Sonia's "correction" contests the user's landed edit. Donor solved this seam:
  ownership-by-latest-provenance (kernel-computed, never proposer-asserted), contested packet
  held for explicit user adjudication, create-verbs never contest
  (`refine/conflict.py::is_conflict` + `ConflictQueue` + `apply.py` held-for-review). *(CONFIRMED)*

- **rev-11 (high) · Post-rollback evidence quarantine.** After a revert triggered by bad
  outcomes, the evidence window produced UNDER the reverted Body version is excluded/flagged for
  the next proposal pass — else the same edit re-lands from the same degraded evidence. Donor:
  `inner_loop.py:215-229` advances `last_refined_idx` past the discarded window for exactly this
  stated reason. Landing-authority-independent. *(CONFIRMED)*

- **rev-12 (high) · Confirmed-positive anti-Goodhart norm.** Only externally-confirmed positives
  count toward promotion-grade claims in a packet; agent self-reported success is advisory at
  best. Donor: `TaskStats` confirmed-only counting + the fail-toward-strict task floor ("a
  'succeeded' episode NOT in confirmed_ids is neutral"). The charter has adjacent concepts but
  no such norm inside proposal evidence — the exact channel by which Goodharting re-enters via
  Sonia's packets. *(CONFIRMED)*

- **rev-17 (medium) · Advice-integrity residual for co-pilot verticals.** "A session's blast
  radius dies with the session" is blind to harm via acted-upon recommendations: one injected
  session biasing one day's ranked picks "dies with the session" while its financial harm does
  not. Name the residual; note domain output-side mitigations (deterministic veto/guard + sizing
  wrappers as pinned mechanism plugins, policy content in Body) as the vertical's responsibility
  — this repo's `SizingPolicy(GuardedPolicy(·))` + human-confirmation doctrine is the worked
  shape.

### B4. Process / roadmap items

- **rev-13 (high) · Rename-referencing plan** (execute when the GitHub rename lands): update the
  two NON-frozen pointers (Backend line 5 donor path; design CLAUDE.md's "`../evolving-alpha-us/`
  literally implements a Sonia" line) with an "(ex evolving-alpha-us)" gloss; record the old→new
  mapping in a ROADMAP append instead of touching frozen research; add a §4 donor-legend
  disambiguation "κ/kairos = the CN legal-agent donor repo, NOT Kairos the worker"; decide
  consciously between the design's "finance vertical" phrasing and this repo's "US-stock".

- **rev-15 (medium) · Enforcement-class labeling.** Standing §8 rule: every guard declares its
  class (kernel boundary / access control / advisory / convention), and advisory guards must
  name, in code, the structural invariant that actually holds the line (with a boot assert where
  possible). Donor: arena `LocalEnv`'s "NOT a security boundary … TOCTOU-bypassable" honesty +
  workbench's fail-fast brain-outside-workspace assert.

- **rev-18 (low) · SP2 decomposition discipline.** SP2 bundles seven new kernel packages + two
  sonia packages; comparable scope here only ever shipped as 7–20 reviewed TDD subagent tasks
  per arc. Sub-stage it or record the intended decomposition.

- **rev-19 (low) · Composition order pinned in one factory.** Wrapper stacking order is
  semantics (`SizingPolicy(GuardedPolicy(·))` — guard inner, sizing outer), and the assembly must
  live in ONE factory that live path and every trial arm call — else the trial measures a
  differently-wired agent. Donor: `compare_harnesses` chaining all arms through one shared
  closure.

---

## Meta-observation

The 2026-07-01 mining found 40/100 kairos patterns already present here by convergent evolution.
This pass found the same in the other direction: the design repo has already absorbed this
repo's governance organs (write-waist → Applier, verdict harness → kernel/trial, arena → sandbox)
— what it has NOT yet absorbed is concentrated in two classes: **time-discipline** (PIT,
evidence quarantine, arm symmetry — rev-06/07/11) and **failure-honesty at seams** (never-silent
extraction, revert-reconciles-derived-state, contest-hold, confirmed-positive — rev-05/09/10/12).
Both classes were bought with real bugs here; they are the cheapest lessons the design can
import before SP1 code exists.
