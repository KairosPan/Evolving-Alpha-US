# DEVELOPMENT-PLAN.md — Sonia-Kairos-US-Stock

Status: drafted 2026-07-10 (backend-design round); amended 2026-07-12 (growth-doctrine pivot —
P0 program inserted, P1 enriched, P2 retargeted, P5 earnings feed promoted).

Authority: charter (Evolving-Agent-Design-SoniaKairos.md) > Backend-Design.md > DEVELOPMENT-PLAN.md
> code — a downstream doc never leads an upstream one; on conflict, amend upstream first, then sync
down with a dated marker.

Role: **the single forward-looking document** — the ordered build program plus the absorbed backlog.
`ROADMAP.md` was absorbed in full; ROADMAP.md deleted 2026-07-10 in this landing. Its done/✅ items
(arena P-A + live-face wiring + P-B/P-C, episodic read-side flip, polish trio, L3 netting, the
web-console data-wiring arc, cockpit v1–v5 — back-filled into PROJECT_STATE 2026-07-10, before the
deletion — §7 naming closure, the addressed M2 capture-idempotency leftover) live in
`docs/PROJECT_STATE.md`, the append-only what's-built log. The 2026-07-10 recon backlog sweep
(specs + PROJECT_STATE items ROADMAP never listed) is absorbed here too — nothing dropped silently.
One-place discipline: an item lives here or in PROJECT_STATE, never both; when an item ships,
delete it here and record it there.

Two tracks interleave — §1 PRODUCT (the co-pilot trades better) and §2 ARCHITECTURE (the organism
gets safer/more governable). Neither blocks the other. Start order (user-approved): **A1 first**
(shipped 2026-07-11), then **P1+P2**; **amended 2026-07-12 (pivot): P0 precedes P1+P2**;
P0 + P1 + P2 shipped 2026-07-13 → product track resumes at **P3**. Cadence and gates: §5.

## Activation ledger (capability = done only when live)
| Capability | Built | Live in prod | Path to ON |
|---|---|---|---|
| P-B/P-C operational-K coupling | ✓ (882-test arc, dark) | ✗ | `docs/superpowers/runbooks/p-b-p-c-activation.md` (A2 builds the missing steps) |
| Daily production loop | producers only (`save_decisions` / `run_verdict --json` / `save_evolution`) | ✗ | P9 |
| Growth-doctrine H (seeds v2) | ✓ (P0+P2: offline-produce-capable, growth regime read live in drivers) | ✗ | P9 (daily loop); trend_template screen blocked on P5 split cross-check |
| Panic-state L4 veto | ✓ (P1+P2: live on history-threaded decide/verdict paths, both vocabularies) | ✗ (scheduled prod = P9) | P9 |

---

## §1 PRODUCT TRACK — P0..P9
### P0 — Growth-doctrine pivot program
P0 (P0.1–P0.6) SHIPPED 2026-07-12/13 → `docs/PROJECT_STATE.md` (acceptance gate green: growth
DecisionPackages offline; specs `2026-07-12-p01-phase-vocabulary-decision.md` /
`2026-07-12-p03-seeds-v2-design.md` / `2026-07-13-p05-prompt-isomorphism-design.md` /
`2026-07-13-p06-trim-derisk-design.md`). Carry-forwards live in their new homes: trend_template
screen activation blocker (split distortion → P5 corp-action cross-check), trim/exit scoring fence
(pinned at the three entries-sites, implemented by whichever producer first emits them), P2 wires
live market-context history + may narrow the panic veto to the leader list.

### P1 — Adversarial trap-day battery
P1 SHIPPED 2026-07-13 → `docs/PROJECT_STATE.md` (spec `2026-07-13-p1-trap-day-battery-design.md`;
battery + latched panic-state L4 veto, DORMANT — P2 activates by threading real market-context
history into both verdict arms symmetrically; all detector thresholds 待P2校准).

### P2 — GCycle US recalibration → growth market clock
P2 SHIPPED 2026-07-13 → `docs/PROJECT_STATE.md` (spec
`docs/superpowers/specs/2026-07-13-p2-growth-market-clock-design.md`; acceptance gate met on the
fixed machine: verdict_pit_broad 90-day replay = 75/10/5 confirmed/pressure/correction, stability
10 state-changes / 3 islands / 2 ABAB — vs the momo read's 35/59-backside thin-by-construction;
reproducible via `python scripts/calibrate_growth_clock.py verdict_pit_broad`). Carry-forwards:
all clock thresholds + the §5 dead-band limit (0.41–0.59 no-op band inflates confirmed) are
待verdict校准 (P6-adjacent); growth skill phase-ordering (`phase_from_read` → retrieval, touches
TCB `retrieval.py`) and the growth console instrument (three-state ring) live in §3 SMALL POOL;
trend_template screen activation still blocked on the P5 split cross-check.

### P3 — Corp-actions tri-state guard-blind fix
P3 SHIPPED 2026-07-13 → `docs/PROJECT_STATE.md` (spec
`docs/superpowers/specs/2026-07-13-p3-corp-actions-tristate-design.md`). Honest scope boundary
recorded there: ssr/halt_then_dump missing-BARS blindness is a separate tape-data seam,
deliberately not covered (revisit with P5 feeds or P9 trust review).

### P4 — Data-source layer (mechanism shipped 2026-06-22; narrowed 2026-07-13)
**Goal (narrowed — user decision 2026-07-13: no second vendor for now; (a)+(c) moved to the §4
deferred ledger).** (b) **`CompositeSource`** — per-capability composition, the natural home for
P5's enrichment feeds (own spec) — this is now P4's whole substance, ordered as P5's prerequisite.
(d) Conditional: a validated **`DataConfig`** object, only if per-source constructor params
proliferate (overlaps A1's frozen Settings — reconcile there first).
**Acceptance gate.** Pure-swap contract holds (full Protocol or NotImplementedError); `make_source`
still returns RAW; PIT firewall tests untouched.
**Sources.** `docs/superpowers/specs/2026-06-22-multi-source-switching-design.md` (Future work).
**Consequence accepted with the deferral:** eval windows stay bounded at ~2021+ (Alpaca free IEX);
P6's appetite for longer history rides the §4 revisit trigger.

### P5 — Real feeds (consume-paths wired; ingestion missing)
**Goal.** Flip the offline placeholders live, each as a CompositeSource backend (P4):
- **Earnings calendar + actual/estimate EPS & revenue** (promoted to FIRST feed by the 2026-07-12
  pivot — the growth doctrine's only hard data gap: `earnings_gap_discipline.rule` and thesis-card
  verification nodes are manual until it lands; candidates: EDGAR company facts (free, filing-date
  PIT key), vendor calendars).
- **FINRA short interest** (`short_interest`/`days_to_cover`; activates `short_squeeze` via `depends_on`).
- **EDGAR/SEC offerings** for dilution + the **withdrawal/expiry lifecycle** — today any announced
  ATM/shelf/offering vetoes forever. Design input (kairos-mining §3): `updates_since`-shaped typed
  events, each keyed on its own announce/process date (PIT); veto-forever stays the explicit
  fail-closed no-connector default.
- **Options-flow + social-sentiment** (`gamma_squeeze`/`social_euphoria_top` consume paths wired).
- **Float feed → float-based L3 sizing** (`size_tier` is wired; share-count sizing needs real float).
- **Per-narrative-line regime read** (per-line `GCycle` vs today's global one) — blocked on a
  theme/sector breadth feed landing here; narrative clustering is the other half.
**Acceptance gate.** Per feed: PIT-guard tests (announce-date keying), offline suite stays keyless,
`depends_on` skills activate only when the feed is present.
**Sources.** ROADMAP §3 (absorbed); PROJECT_STATE US-3c/d/f; kairos-mining §3.

### P6 — Eval methodology (gate-non-blocking, spec §10)
**Goal.** (a) **Purged & embargoed cross-validation** — native in `walk_forward.py` + `compare.py`:
embargo the horizon-h overlap at window edges in `multi_window`; optionally reserve held-out windows
never used while iterating on refiner prompts/config (the real residual Goodhart surface is human
meta-iteration). (b) **Regime-stratified eval.** (c) **Hcredit (C4) ablation arm.**
**Acceptance gate.** Both arms see identical holdout windows (verdict symmetry preserved); borrow
only the per-metric tolerance-with-reasons reporting shape for `StatVerdict`.
**Sources.** ROADMAP §4 (absorbed); kairos-mining §2.8.

### P7 — Episodic refinements (each its own small spec)
**Goal.** Deepen the shipped v1 memory capabilities: **recall** — soft blended score;
narrative-scoped recall (blocked on pre-decision narrative/theme signals). **Taboo** — phase-scoped
(veto only if the name nukes in the current regime) + recency-windowed variants. **Forge** —
patch-on-promote, per-narrative/phase-scoped aggregation (lesson demote stays the Refiner's job).
**Retire-on-task** — a confirmed-failure floor symmetric to P-C's confirmed-positive counting
(deferred out of P-C; no design yet — queue after A2 activation evidence accrues).
**Acceptance gate.** Each refinement additive/default-off; verdict symmetry and PIT masking pinned.
**Sources.** recall/taboo/forge specs 2026-06-26/27 (Out-of-scope sections); pb-pc spec.

### P8 — Intraday path
**Goal.** Real LULD halts / halt-count (tick feed), **MWCB / `Breaker` portfolio wiring** (P&L state
machine + index-crash monitor — `Breaker.set_mwcb` has zero production callers), and **intraday
fill-feasibility** (size-at-offer; the `eval/fill` module + soft per-candidate `taboo_check`
annotation — today the guard DROPS vetoed candidates rather than annotating).
**Why this order.** Blocked on an intraday tick feed → sequenced after P4/P5.
Sources: ROADMAP §5 (absorbed); PROJECT_STATE US-3e + L3-sizing deferrals.

### P9 — Live daily production loop
**Goal.** A scheduled loop that writes `DecisionStore`/`VerdictStore`/evolution artifacts
automatically, replacing the three on-demand producers (`save_decisions` / `run_verdict --json` /
`save_evolution`); the console then reads a living record.
**Why this order.** Last: wants P3 (no silent guard-blind days unattended) and A1's runbooks +
activation-ledger discipline.
**Acceptance gate.** One scheduled run produces all three artifacts end-to-end; failure is loud (no
partial-write silent days). Sources: ROADMAP §6 optional-polish prose; kairos-mining §1.1 ledger row.

---

## §2 ARCHITECTURE TRACK — A1..A12
Every arc cites the Backend-Design.md §4 gap-ledger row(s) it closes (G1..G14).

### A1 — Hygiene + observability floor
A1 SHIPPED 2026-07-11 → `docs/PROJECT_STATE.md` (spec
`docs/superpowers/specs/2026-07-10-a1-hygiene-floor-design.md`).

### A2 — P-B/P-C live activation
**Closes G11.**
**Goal.** The built-but-DORMANT experience/fitness coupling goes live via its logged 4-step
checklist: (1) route operational task ops through `conflict_queue`; (2) reject-or-amend
operational-M scope; (3) wire `confirmed_ids` resolution; (4) pin the task-episode asof to the
logical date. Plus two before-live items from kairos-mining: gate-side re-derivation of task
evidence (thread a read-only PIT-pinned episode-store handle into `try_apply_op`'s task branch;
derive `confirmed_ids` from durable records, not producer input — §2.3) and guard the unguarded
`experience_writer` call in `session.py` (a writer exception kills the live turn — §4.6). Ship the
flip as a **runbook** with kill switch (A1's runbooks/). Verify against code whether the arena-spec
§5 SkillStats-accrual intent for K-skills used/written in task episodes shipped (the gate floor
reads `TaskStats`, not `sk.stats`) before planning any extension; avoid inventing a parallel
ToolStats absent real need.
**Acceptance gate.** Verdict-neutrality regression stays bit-identical; kill switch proven.
**Sources.** PROJECT_STATE P-B/P-C entry; pb-pc spec; kairos-mining §1.2/§2.3/§4.6.

### A3 — Self-learning channel (the headline next step)
**Closes G10 (precondition), builds the second learning channel.**
**Goal.** Precondition first — the **context-management trio** for long Sonia/workbench sessions:
provenance-preserving pruning (lose bytes not handles: `[...elided – recall hash=X]`),
content-addressed offload (store rooted INSIDE the Workspace, under the arena path-guard) + a T0
recall tool through the choke point, 4-phase compaction with
protected bookends (turn-0 task + last-N); `FakeSummarizer` keeps the suite offline. Then the
channel: a reflection→directions stage on the Refiner's evidence path, surfaced into the SAME
cockpit, so the agent proposes evolutions from its own task runs. Design inputs: deterministic
forge-style detectors over `kind="task"` episodes (PIT `for_asof` reads) → proposals into the Sonia
review queue via `try_apply_op`; human-rejection mining as negative constraints only.
Charter: *Session Is Not the Context Window* — recoverable context storage (session) separated from
arbitrary context engineering (loop); *Dreaming: Letting Agents Improve Between Sessions*.
**Acceptance gate.** A task-run trace yields an `EvolutionProposal` in `/proposals` with zero live
H writes; trio changes are byte-identical when off.
**Sources.** ROADMAP §6 self-learning (absorbed); kairos-mining §3 (context row, detectors row).

### A4 — Session organ, phase 1
**Closes G1 (first slice).**
**Goal.** (a) **Origin-stamp vocabulary + emit seam** at the converse/sonia persistence boundaries —
today tool results are re-injected as `role="user"` messages with a `"[tool:{name} result]"` string
prefix, i.e. tool-result origin is a text convention the model itself could forge; no
kernel/system origin class exists. `EditProvenance` already stamps H mutations; extend the idea to
message capture. (b) **Hash-chained EditLog with external anchor** — `prev_chain_hash`/`chain_hash`
+ `verify_chain()` finalized at persist time, legacy snapshots = unchained prefix, PLUS an external
chain-head anchor (git-committed head hash or surfaced on `/evolution`). Honest limit, one home,
here: **without the anchor this is corruption-detection only** under the accepted T2-shell
operator-trust posture (value downgraded 4→2-3, kairos-mining §2.9); groundwork for A10's deferred
`BodyLog`. Ordering invariant: A1's redact runs before hashing. (c) **Scope label on every
learned-context write** — the charter's scope field {agent-global / per-party / per-session} rides
every lesson/skill/episode write (*The External Channel*; *Memory Design → scope labels from day
one*). This is a TIMING DEVIATION from the charter's day-one rule (recorded 2026-07-10,
backend-design round): until A4 lands, today's learning accumulates unlabeled — exactly the
un-retrofittable risk the charter names.
Charter: *Trust Roots & Principal Authentication* + *Session Is Not the Context Window → Traces* —
four trace pieces are carved out **non-deferred**: the attribution-tuple stamp (body-version ×
model-id × kernel-version), the kernel counter-event schema, the principal-origin stamp, and the
append-time integrity chain. The attribution tuple lands here in A4, alongside the stamp work
(A1's `h_digest` covers the body-version leg).
**Acceptance gate.** Forged-origin regression (a model-authored "[tool:…]" string ≠ a stamped tool
result); `verify_chain()` green across a rollback; new lessons/skills/episodes carry a scope label.

### A5 — Body-Store-as-git
**Closes G2.**
**Goal.** The Body today is `brain.json` + SnapshotStore — no commit-per-apply audit. Move to one
git repository per instance: every `try_apply_op` landing = one commit; audit = the commit trail;
rollback reconciled with SnapshotStore/epoch semantics. Charter (*Second Founding Principle*): "the
**Body Store**, one git repository per Kairos instance"; write access is the Applier's alone.
**Acceptance gate.** One landed op ↔ one commit carrying provenance; revert lever still reconciles
derived state across both faces.

### A6 — Spend metering
**Closes G5.**
**Goal.** Zero metering exists anywhere. Meter at the `make_client` seam → per-run budgets
(refine_live, verdict, dreaming/replay batches) → a watchdog ladder that treats spend as an
enforced signal beside failure. Charter: *Resources as Security: Cost Is Also the Adversary's
Weapon* — "a *reported* scalar is not a *governed* one"; both §4.3 adversaries (injected session,
looping Body) are live today on the single-user machine.
**Acceptance gate.** Every LLM call carries a cost record; a budget breach halts the run loudly;
per-refinement cost appears on proposal packets (feeds A8).

### A7 — Sonia-side proposer over worker traces
**Closes G7 (the named deviation).**
**Goal.** The 2026-07-09 arc killed worker self-LANDING only; the worker still proposes staged
edits. Charter (*First Founding Principle*): "only two hands may send it there" — a Sonia proposal
or the User's direct edit; Kairos does not propose at all. Build the Sonia-side proposer that reads
worker traces (A3's detectors are natural input) and does the proposing; retire or gate off the
worker's staged-edit proposing path.
**Acceptance gate.** Deviations-ledger row (charter-conformance spec §5.4) closed; no
worker-originated `StagedEdit` reaches the gate.

### A8 — Canonical teach surface + deliberation-packet counsel
**Closes G8.**
**Goal.** (a) Consolidate the two teach-ish surfaces over one brain (Sonia + workbench) into a
canonical surface with a unified write scope (deliberately deferred out of teach-crystallize v5).
Note: the old "thread conflict_queue into the teach path" sibling item is likely MOOT —
charter-conformance D2 established teaching-path ops never trip `is_conflict`. (b) Add the
charter's packet counsel fields to `EvolutionProposal`: before/after **behavior diff** from fork
trial runs, dedup against pending/landed edits, and evidence coverage —
charter: *Evolution Deliberation Channel & Preference Charter* ("standard contents"; the
non-behavior delta is generated by kernel code from the diff, never authored by the proposer).
Plus the **gate-level scope-mismatch check** — an edit landing at a scope wider than its cited
evidence's scope FAILS the static policy gate and bounces to Sonia; a GATE refusal, not advisory
counsel (charter: *The External Channel* — "live from day one"). Carrying it here, not day-one, is
a TIMING DEVIATION from the charter (recorded 2026-07-10, backend-design round; consumes A4's
scope labels). (c) **Staleness pin for teaching `/apply`** — pin the previewed brain hash at
accept; `/apply` refuses (re-preview) on mismatch (Backend-Design G8: "teaching apply unpinned").
**Acceptance gate.** One canonical teach surface; every packet renders the counsel fields; a
wider-than-evidence scope bounces at the gate; what was previewed is what lands (staleness pin);
direct-edit hand still bypasses counsel with its honest-limits line (see §3 cockpit item).
**Sources.** teach-crystallize spec §10 + §2; charter sections above.

### A9 — Egress ladder + two-class credential split
**Closes G4, and G3 long-term (the vault split; A1 took the redact leg).**
**Goal.** **M1 monitor-everything** — typed `sandbox_egress` audit records at the choke point
(`LocalEnv` `net` is a documented no-op today) → **M2 deny-by-default allowlist**; resource
ceilings declared in the image manifest, policy may only tighten. Two-class credential split per
the charter (*Security Boundary: Two-Class Credentials — the Work Token Is Contained; Everything
Else Never Enters*; *Sandbox egress: default-deny + destination allowlist*): the work token is
repo-scoped and physically incapable of reaching the Body remote; everything else never enters the
sandbox — replaces today's env-var custody where the arena shell can read every key. Sub-item:
**SSRF IP-range hardening** (BLOCKING precondition before any non-localhost / multi-user serving):
reject private/loopback/link-local ranges + `169.254.169.254`, DNS-rebinding-safe — resolve once,
require every resolved IP `is_global`, connect by pinned IP with Host preserved, re-validate
redirects in `_urllib_fetcher`, keep the byte cap (stdlib-only `alpha/meta/netguard.py`, verified
not built). The `ingest_attachments` cap (§3) and the no-Origin/CSRF loopback-approval accepted
risk ride this same precondition.
**Acceptance gate.** M1: every arena net touch produces an audit record. M2/vault: a stolen work
token has one useful destination; keys absent from the sandbox env.
**Answers** the activity-space spec §10 open question on the LocalEnv allowlist shape.

### A10 — Kernel SandboxedEnv + body axis R3+ *(ordered here; STAYS DEFERRED — commercial)*
**Closes G6 when built.**
The whole deferred program: kernel `SandboxedEnv` (Seatbelt/bwrap/Docker/microVM) behind the
existing `ToolEnvironment` seam + kernel-enforced network allowlist + H volume read-only + writer
sidecar (brain writes only via `try_apply_op` IPC) + outer supervisor `BodyManager` +
`try_promote_body`/`BodyLog` + propose→fork-verify→rebuild-from-declared-diff + joint
`(H-version, body-digest)` change-set rollback — unlocking the modification ladder **R3 skill-code
→ R4 tool-code → R5 runtime → R6 image/OS** strictly in order.
**Gate/trigger.** Commercial phase. Hard preconditions: immutable-TCB byte-hash pin (A1's
`tcb.lock` is the seed) + outer verifier + mandatory human approval; never autonomous, never on
`LocalEnv` (a code rung on the TOCTOU-bypassable LocalEnv "must be refused" — modification-ladder
spec §11.2). Also the compensating fix for the USER-ACCEPTED operator-trust posture (live shell can
reach the brain around the gate; today's control is the workbench boot assert only) and the
precondition for any multi-user/untrusted arena use. Charter: *Immutable Kernel: The Trust Base of
Evolution*. Sources: modification-ladder spec §5–§9; activity-space spec §3/§8 P-D.

### A11 — Mem0 decision point
**Closes G9 (either way).**
The charter decided memory's **store of record is Mem0 OSS** (2026-07-09, user-ratified — *Memory
Design → Decision for SoniaKairos*: Applier writes `add(infer=False)` verbatim, Kairos reads
retrieval-only, git journal reconcile-authoritative). This repo's substrate is H-lessons +
`EpisodeStore` (SQLite). Decide explicitly: **adopt** (Mem0 + journal-replay reconcile pattern,
mapped onto the existing gate/waist), or **amend the charter** to record permanent divergence —
code never wins silently; per the authority chain, amend upstream first, then sync down dated.
**Acceptance gate.** A decision memo referencing the charter section, before any code.

### A12 — GEPA population search *(ordered here; STAYS DEFERRED)*
Substance + triggers held in the §4 ledger row; kept in the track so the ordering intent (after
A3/A6, atop whole-H coherence) stays visible.

**Track tail — future arcs, not yet numbered:**
- **Master-dispatch `G` sub-agents** (`PASS_TOOLS["G"]` stays a reserved no-op; "evolve K/G" is
  really evolve-K until this lands). Arena-spec constraints to record: child tool map ⊆ parent's,
  per-tool tier moves only toward stricter oversight, same single `ActivityPolicy` choke point,
  + a sub-run depth ceiling.
- **Real models/stores/seeds for the three stub brain components** (workflow · connector ·
  subagent; one brainstorm→spec→plan round each — content-addressed frozen `WorkflowSpec`,
  governed connector manifest, per-role `extra='forbid'` subagent schemas with role prompt-bodies
  as R5 surfaces), then **Sonia EDITS them** (extend H + meta-tools + gated apply + `target_kind`).
- **Branchable named brains** ("aggressive" vs "disciplined") — fork-at-snapshot-version with
  `parent_id` lineage; rollback = epoch bump, never delete; prune only leaf lineages (pairs with
  the keep-last-K item in §3); edits on any branch still flow through the waist.
- **General meta-agent core** — lift teach + self-learn off trading-specific H. The in-repo
  2026-07-06 design is SUPERSEDED (its §3 extraction-boundary analysis stays valid input); any
  restart reconciles with the amended charter and its named deferrals first.
- **Scheduled live drills** (G13) — drills are CI-tests only today; the drill runner is queued
  behind A1's runbooks; the restore/rollback drill subset additionally wants A4/A5 landed
  (mirrors Backend-Design §4 G13).
- **Governance-pins existence meta-gate** (queued 2026-07-10, backend-design round; named in
  Backend-Design §6) — a us0-style meta-test asserting the governance-pin test FUNCTIONS still
  exist (arena no-order, stage-only, stamp coherence, red-line set), so deleting a governance
  drill fails the suite the way deleting a firewall guard does.

---

## §3 SMALL POOL (unordered; polish and one-liners)
- **Growth skill phase-ordering** — thread the growth market-clock read into skill selection
  ordering (`phase_from_read` → retrieval; touches TCB `alpha/agent/retrieval.py` — minimal seam
  + regen ritual). Until then growth skills order by phase_prior only (P2 carry-forward).
- **Growth console instrument** — a three-state market-clock ring/legend for growth packages
  (today: graceful degradation to raw tokens, no 500s; P2 carry-forward, own design round).
- **Sonia small fixes ×4** (ROADMAP §6 absorbed): widen `/chat`'s `try` to include the brain load
  (`sonia/app.py:144`); `edit_action` under `_MUTATION_LOCK`; file-count/aggregate-size cap in
  `ingest_attachments` (rides A9's non-localhost precondition); split "Sonia 404" from "Sonia
  unavailable" in the console banner (`ConnectError` vs `HTTPStatusError`).
- **Cockpit direct-edit UI for the user-direct hand** — form → `POST /edit`, an honest-limits line
  (a direct edit forgoes packet counsel), revert lever `POST /snapshots/{name}/restore` beside it.
  Own brainstorm→spec→plan round; deferred 2026-07-10 by user (landing-doc spec D6).
- **`tweak` action** — manual inline arg-editing of a proposed edit (no LLM; cockpit spec §8 route
  table) — merged with teach-crystallize §10's "re-preview when `ProposedEdit.args` is edited
  between propose and apply"; they ship together.
- **Post-apply red-line lint + mandatory-taboo gate step** — step 1 (cheap): gate-side check in
  `try_apply_op`'s `write_skill` branch that a new `type='pattern', domain='trading'` skill carries
  ≥1 taboo entry, + wire-or-fix the unconsumed `GateSpec` (its docstring names a nonexistent
  consumer); step 2: safety-only-tightens monotonic check (needs a typed safety surface);
  the semantic contradiction check itself needs its own design. (kairos-mining §1.4/§2.4/§4.4.)
- **Delete-× while Sonia is DOWN** swaps the unavailable banner into the `<li>` — cosmetic.
- **Agent-modification drawer polish** — post-apply diff overlay, cross-session PENDING
  aggregation, drawer on other pages, optional Playwright resize test (drawer spec §7).
- **`docs/blueprint.md` demotion** — stale on structure; refresh or formally demote to
  perception/eval reference pointing at CLAUDE.md + PROJECT_STATE (docs-day leftover).
- **EpisodeStore WAL / busy-timeout** — concurrent-writer exposure on `brain.db`; small SQLite
  pragma change (charter-conformance §5.12 "noted, not done").
- **Console/UI trigger for forge + refine_live** — both self-study producers are operator scripts;
  post-charter the trigger drives the fork+packet propose flow (shared deferred item, two specs).
- **Conflict re-surface dedup** — repeated refine-live runs re-surface the same held conflict until
  adjudicated (refine-live-conflict-feed spec).
- **Offered-vs-cited evidence lineage sidecar** — persist Selection ids + recalled episode ids +
  asof beside the DecisionStore record; feeds A3 and credit precision (kairos-mining §3).
- **Teach-crystallize small deferrals** — apply atomicity (brain/session transaction, all-or-nothing
  multi-edit batch, auto-rollback on partial failure) and per-direction crystallize button
  (spec §10); the teaching-funnel state machine (validate status transitions as a table) as
  design input (kairos-mining §3).
- **Converse face v2** — multi-project create/list/switch UI + per-project H-version pinning
  surface, streaming, multi-user concurrency
  beyond the file-lock floor (the spec's "apply-directly write mode" deferral is DEAD — superseded:
  `write_mode="apply"` raises).
- **Sonia cockpit token streaming (SSE) + voice input** — the Sonia-face siblings of the converse
  streaming item above (one home each): SSE + async streaming `chat()` + incremental console
  render, and voice input (sonia-standalone spec §13; multimodal-cockpit spec §11).
- **Keep-last-K snapshot pruning** — SnapshotStore grows unboundedly; prune only leaf lineages;
  pairs with branchable brains (§2 tail).
- **Web-console residue** — HTMX-swap the date/run pickers; auth + non-localhost serving if it ever
  leaves the desk (trips A9's SSRF blocking precondition).

---

## §4 DEFERRED-BY-DECISION LEDGER
Consciously not queued; each row carries its recorded revisit trigger.

| Item | Decision / trigger |
|---|---|
| **M3 delist tradeoff** | A `worthless_removal` with `process_date == entry_day` is skipped by `ReturnOracle._delisted_between`'s strict `ex_date > entry_day`. Accepted (bar-disappearance is the primary signal); listed so it isn't silently rediscovered. Trigger: any rework of delisting handling. |
| **`--autonomous` escape hatch** | Pre-pivot in-place evolution (incl. live machine-revert) survives behind `--autonomous` + `ALPHA_UNSAFE_AUTONOMOUS=1`; recorded non-conformance (charter-conformance §5.3), conformance claim scoped to default paths. Trigger: a future remove-or-keep decision point. |
| **Adopted forks don't retro-write episodes** | Propose mode threads `episode_store=None`; an ADOPTED packet's run writes no episodes either — evidence accrues only from future live decisions (§5.2 accepted cost). Trigger: evidence starvation becomes real. |
| **GEPA + preventive adoption gate (A12)** | Population/Pareto self-study search, designed-for, substrate kept ready (hermes-rebase spec §5.6/§5.5). Recorded open questions: instance unit (regime-bucket over single-day given MDE ~0.26 @ ~30 days); a cost-budget probe before building the pool (wants A6); merge coherence (wants whole-H coherence below). The preventive adoption gate (refuse to ship a degrading offline champion) is deferred with it. |
| **Hermes fast self-study sub-tier** | Vendored curator/background_review restricted to `PASS_TOOLS["M"] ∪ {patch_skill}`, behind a flag; named the riskiest seam, ordered LAST. Trigger: the B-WIDE face emits frequent turns. |
| **Whole-H global coherence check** | No mechanism checks doctrine/skills/memory stay mutually consistent after many edits (hermes-rebase spec §10). Trigger: observed many-edit drift, or A12 revisit (it is GEPA's stated prerequisite). |
| **Offline recall-weight tuning** | Tuner for `w_rel/w_rec/w_imp/w_reg/w_narr` + regime-distance penalty over captured PIT windows, winners pinned to an H-version. Hand-set weights adjusted via self-study/teaching for now. Trigger: hand-set weights shown inadequate. |
| **`reference/cn/` deletion** | Contractually temporary (PROJECT_STATE locked decision). Trigger: rebuild judged complete AND the knowledge survives in English docs first. |
| **`third_party/hermes` bump gate** | Hard-pinned `5add283e`, do-not-track-upstream. Trigger: any deliberate bump → re-run the Phase-0 spike's `coupling.py` as the gate first (Phase-1 spec D3). |
| **Conflicts: accept records intent only** | Auto-applying a held self-study op on "accept" was deliberately rejected; held entries survive forks as pure adjudication signals. Recorded so a future plan doesn't "complete" adjudication by making accept apply. Any change = a charter-level machine-authority decision. |
| **Session-local self-adaptation** | Charter deferral (*First Founding Principle*): Kairos editing its own prompt/skills/tools mid-session is shelved; accepted cost — Kairos cannot self-unblock and fails into Sonia's offline refinement. Trigger (charter-recorded): offline-only refinement shown too slow on Kairos's own real workload traces. |
| **Model failover/caching (G14)** | Charter *v4 design: Model Layer*. No failover/caching policy in `make_client`; per-role env override is the whole story today. Trigger: live multi-provider operation or first provider outage that costs a run. |
| **Second data vendor + fallback decorator (ex-P4 a/c)** | User decision 2026-07-13: no second vendor for now (Polygon/Tiingo 2016+ history + primary/backup auto-failover both deferred; `make_source` registry seam stays ready — one line to register when wanted). Accepted cost: eval windows bounded at ~2021+ (Alpaca free IEX). Trigger: P6 needs pre-2021 windows for statistical power, an Alpaca coverage/quality blocker, or a data outage that costs a run. |
| **`refine_live` production-seam pin** | Library seam is test-pinned (`test_packages_from_returned_handles_not_the_passed_ones`); forcing an in-fork breaker trip at script level judged disproportionate (§5.17). Companion recorded limit: reconcile sweep's length-only check on abandoned-branch restores. Trigger: any refactor of the runner wiring. |
| **Vision / image teach ingestion** | `deepseek-v4-pro` has no vision via the API (verified); Sonia rejects images with a friendly note. Trigger: a vision-capable model adopted for the Sonia role (+ image content blocks + composer upload re-enable). |

---

## §5 CADENCE & GATES
- **Interleave.** The two tracks run interleaved; neither blocks the other. Start order
  (user-approved): **A1 first** (small, urgent — the verified secret leak; shipped 2026-07-11),
  then **P1+P2**; amended 2026-07-12: **P0 (pivot program) precedes P1+P2**; P0+P1+P2 shipped 2026-07-13 — next **P3** (or A-track interleave).
- **Discipline.** Every arc runs the repo's established loop: brainstorm/spec → plan →
  subagent-driven build → adversarial multi-lens review, offline tests throughout.
- **Sync rule.** An arc is not done until all three are updated: Backend-Design.md (its gap-ledger
  row), this plan (item deleted or moved), and `docs/PROJECT_STATE.md` (entry appended). Downstream
  never leads upstream; charter conflicts get amended upstream first with a dated marker.
- **Pushes** to `origin/main` only on explicit user "push".
