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
| P-B/P-C operational-K coupling | ✓ (A2: opt-in, forgery-resistant gate) | ✗ | ALPHA_EPISODES_DB Stage-2 shadow; Stage-3 = approve-path evidence stamp + task_forge wiring |
| Daily production loop | ✓ (P9: stage-then-finalize, loud) | ✗ | the cron/systemd scheduler (needs-the-machine) |
| Growth-doctrine H (seeds v2) | ✓ (P0+P2: offline-produce-capable, growth regime read live in drivers) | ✗ | P9 daily loop scheduled; trend_template screen blocked on P5 split cross-check |
| Panic-state L4 veto | ✓ (P1+P2: live on history-threaded decide/verdict paths) | ✗ (scheduled prod) | P9 scheduler |
| Self-learning + context trio (A3) | ✓ (dormant mechanism) | ✗ | A2 activation evidence + a live LLM summarizer |
| Git Body audit / spend meter / SSRF guard (A5/A6/A9) | ✓ (opt-in / default-off) | ✗ | operator opt-in (ALPHA_BODY_GIT / a Budget / non-localhost serving after A10) |

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

### P4 — Data-source layer (CompositeSource)
P4 SHIPPED 2026-07-13 → `docs/PROJECT_STATE.md` (spec
`docs/superpowers/specs/2026-07-13-p4-composite-source-design.md`; CompositeSource per-capability
composition — P5's substrate; second vendor + fallback decorator in the §4 deferred ledger by user
decision). Carry-forward: conditional `DataConfig` object only if per-source ctor params proliferate
(reconcile with A1's frozen Settings first) — deferred until that pressure appears.

### P5 — Real feeds (consume-paths wired; ingestion missing)
**Goal.** Flip the offline placeholders live, each as a CompositeSource backend (P4):
- **Earnings calendar + actual/estimate EPS & revenue** — **P5a INGESTION SHIPPED 2026-07-13**
  (spec `docs/superpowers/specs/2026-07-13-p5a-earnings-feed-design.md`; PROJECT_STATE): EarningsFact
  (filing_date PIT key) + EarningsCalendarEntry (known_asof), Protocol `earnings` capability,
  EdgarSource (data.sec.gov XBRL, mockable seam) + offline PITStore backend, feature helpers
  (days_to_earnings / has_upcoming_earnings(T-3)). Capture persistence SHIPPED (P5-consume,
  878dee1). **CONSUME-PATH T-3 GATE STILL PENDING**: wire `earnings_gap_discipline.rule` (§4.5 T-3
  gate) + the 扛 hold-through-earnings veto into the guard/doctrine decide path — BLOCKED on a
  holdings producer (the hold branch needs a position book); the vendor consensus/estimate backend
  (EDGAR has no consensus → estimate legs are None) also remains.
- **FINRA short interest** — INGESTION SHIPPED 2026-07-13 + **CONSUME-PATH SHIPPED 2026-07-13**
  (P5-consume, 878dee1; spec `2026-07-13-p5-consume-path-activations-design.md`): `short_squeeze`
  now populates (short_interest %-of-float, days_to_cover) on both builders via
  `alpha/features/short_squeeze.py`; feeds ONLY the agent skill menu (`depends_on`), never the L4
  veto or scorer; days_to_cover rides short-interest alone, %-of-float needs the float feed too
  (else the skill stays dormant). Feed absent → byte-identical.
- **EDGAR/SEC offerings** — INGESTION + LIFECYCLE SHIPPED + **VETO SWAP SHIPPED 2026-07-13**
  (P5-consume, 878dee1): `screen_decision` uses `is_dilution_overhang(offering_events_known)` when
  `offerings_available()`, else `has_dilution_filing` (veto-forever fail-closed, unchanged);
  a withdrawn/expired shelf lifts the veto as of its own process_date and no earlier; same guarded
  source both verdict arms → symmetric + PIT. safety-only-tightens. (The present-but-empty-feed
  corp-veto-lift case is architecturally excluded — no production corp backend emits dilution kinds;
  reviewed 0 confirmed, refuted on three grounds; recorded in the P5-consume spec.)
- **THEME/SECTOR BREADTH** — **SHIPPED 2026-07-13** (`sector_map` + `theme_breadth`; the growth
  §1.2 theme-clock's data prerequisite). The theme-CLOCK CONSUMER also SHIPPED (`GrowthThemeClock`,
  f60f5a3). Narrative clustering (dynamic per-narrative-line theme discovery from the agent's
  `narrative` key) remains — see §1.5 THREE-CLOCK ACTIVATION below (small-N breadth caveat).
- **Float feed → float-based L3 sizing** — **SHIPPED 2026-07-13** (spec
  `2026-07-13-p5b-float-feed-design.md`): FloatFact keyed on knowable_date (period-only records
  DROPPED — no lookahead-safe key), float-capped tier + float-participation share-count, additive/
  default-off, verdict-neutral. `short_squeeze` %-of-float denominator now consumed (P5-consume,
  878dee1); the SEPARATE float→StockSnapshot.free_float state channel + float-aware sizing wiring
  (float-feed spec §7) remains.
- **Options-flow + social-sentiment** (`gamma_squeeze`/`social_euphoria_top` consume paths wired) —
  remaining.
- **capture_window persistence + CHECKSUMS** — **SHIPPED 2026-07-13** (P5-consume, 878dee1):
  `_capture_feeds` persists earnings/short-interest/offerings/float knowable-by-window-end, scoped
  to captured symbols; `write_checksums` auto-covers the new parquets. Theme-breadth is N/A (derived
  at state-build from the captured snapshot + static sector_map — a replayed window reconstructs it).
  Default source (Alpaca) → all absent → byte-identical capture.
**Acceptance gate.** Per feed: PIT-guard tests (announce-date keying), offline suite stays keyless,
`depends_on` skills activate only when the feed is present.
**Sources.** ROADMAP §3 (absorbed); PROJECT_STATE US-3c/d/f; kairos-mining §3; the 2026-07-13 P5
feed specs.

### PX — Three-clock activation (clock_cadence orchestration) — THE next coherent product arc
The doctrine (§1) fractals the sentiment cycle into THREE scale-typed clocks. **All three LEAVES are
now built as pure `s_t`-side READS (never written into H), each with state-machine hysteresis:**
- **market** (§1.1) — `GrowthMarketClock` (P2, `market:confirmed_uptrend`/`under_pressure`/`correction`).
- **theme** (§1.2) — `GrowthThemeClock` (theme-clock consumer, f60f5a3; over `sector_map` groups).
- **stock** (§1.3) — `StockStageClock` (31d6a4e; `stock:base`/`advance`/`top`/`decline` + `climax_run`
  reduce-flag) + `detect_stock_reread_events` (§1.4 triggers, detector only).

**NONE is live-wired yet** — deliberately DORMANT (like P2's own dormant→live sequence). Remaining =
one coherent activation arc, NOT piecemeal per-clock consume (wiring stock stage into state alone would
not compose with the deferred market+theme activation). Scope:
1. **§1.4 clock_cadence authority** — high-scale VETOES low-scale (market vetoes theme vetoes stock),
   low-scale does NOT score high-scale; phases modulate appetite/guard/sizing (the way P2 maps market
   state → `frontside`/`risk_gate`). The composition RULE is user-specified in manuscript §1.4 (not an
   invention). `event_reread` (§1.4) is the intra-cadence override forcing high-scale re-read.
2. Thread each clock's read into `MarketState`/the decide path on its cadence (market daily / theme
   weekly / stock weekly), computed from the tape cross-section + `sector_map`.
3. **Narrative clustering** (theme's dynamic half): cluster candidates by the agent's `narrative` key,
   run the theme phase logic per-cluster. CAVEAT: small-N breadth — a narrative line is 3-5 names
   (§2.5 theme_portfolio), so per-cluster `pct_above_200dma` is statistically thin; may need a
   min-cluster-size floor or a design pass before it's meaningful.
**Posture / sequencing decision (HELD FOR USER).** The three clock LEAVES were safe to build dormant
because they are pure READS (stable, zero decide-path integration). This arc is the INTEGRATION — how
the three reads compose authority (market vetoes theme vetoes stock) and how each phase maps to
`frontside`/`risk_gate`/appetite/guard/sizing. That integration SHAPE is exactly what P6's calibration
(stratified verdicts over captured PIT windows — the tool exists, the constants stay 待verdict校准)
should inform. **Engineering recommendation: CALIBRATE FIRST, then build the integration** — building
the authority composition ahead of the calibration that should shape it is building ahead of
validation. (The alternative — build it DORMANT/default-off now, flip on after calibration — matches
the P2/theme/stock dormant pattern but risks reworking the integration once calibration lands.) Either
way touches guard/sizing/state (+ likely TCB veto/retrieval) and wants its own
brainstorm→spec→plan→build→review round. **User picks the sequencing.**

### P6 — Eval methodology
P6 SHIPPED 2026-07-13 → `docs/PROJECT_STATE.md` (spec
`docs/superpowers/specs/2026-07-13-p6-eval-methodology-design.md`): purged/embargoed CV
(`embargo_trajectory` shared by walk_forward + compare; reporting-layer fence, no live-decision
change), regime-stratified eval (`stratified_verdicts` — THE tool that calibrates the growth-clock
thresholds + §5 dead-band per market state, resolving the P2 carry-forward), Hcredit ablation arm.
Carry-forwards (deliberately-not-done): pooled cross-window significance test; auto-selecting
embargo from measured return autocorrelation; running the stratified readings into new growth-clock
constants (a calibration RUN over captured PIT windows — the tool exists, the constants stay
待verdict校准).

### P7 — Episodic refinements
P7 SHIPPED 2026-07-13 → `docs/PROJECT_STATE.md` (spec
`docs/superpowers/specs/2026-07-13-p7-episodic-refinements-design.md`): recall soft-blend
(recall_score.py leaf, calibratable weights), phase-scoped + recency-windowed taboo, forge
patch-on-promote + per-phase/narrative aggregation (retire stays GLOBAL). Additive/default-off,
review 0 findings, no TCB touched. Carry-forwards: consumer wiring for the recall blend (into TCB
retrieval.py) + taboo-scoping (into guard/screen.py) ship as follow-ups; narrative-scoped recall
inert (blocked on pre-decision narrative signals); **Retire-on-task** still deferred (confirmed-
failure floor symmetric to P-C; no design; queue after A2 activation evidence); the §4 offline
recall-weight tuner is the calibrator for the hand-set weights.

### P8 — Intraday path
**Goal.** Real LULD halts / halt-count (tick feed), **MWCB / `Breaker` portfolio wiring** (P&L state
machine + index-crash monitor — `Breaker.set_mwcb` has zero production callers), and **intraday
fill-feasibility** (size-at-offer; the `eval/fill` module + soft per-candidate `taboo_check`
annotation — today the guard DROPS vetoed candidates rather than annotating).
**Why this order.** Blocked on an intraday tick feed → sequenced after P4/P5.
Sources: ROADMAP §5 (absorbed); PROJECT_STATE US-3e + L3-sizing deferrals.

### P9 — Live daily production loop
P9 SHIPPED 2026-07-13 → `docs/PROJECT_STATE.md` (spec
`docs/superpowers/specs/2026-07-13-p9-daily-loop-design.md`; `scripts/daily_loop.py`:
stage-then-finalize all-or-nothing, decision published last, precondition gate [non-empty window +
same-filesystem destinations] + finalize-plan-before-execute [review-hardened], corp-blind note into
the manifest, loud non-zero-exit failure). Carry-forward: the scheduler (cron/systemd) is the
needs-the-machine runbook step; the loop is invocable + idempotent. A browsable evolution history
(vs the single overwritten file) is a small Settings + alpha_web follow-up.

---

## §2 ARCHITECTURE TRACK — A1..A12
Every arc cites the Backend-Design.md §4 gap-ledger row(s) it closes (G1..G14).

### A1 — Hygiene + observability floor
A1 SHIPPED 2026-07-11 → `docs/PROJECT_STATE.md` (spec
`docs/superpowers/specs/2026-07-10-a1-hygiene-floor-design.md`).

### A2 — P-B/P-C live activation
A2 SHIPPED 2026-07-13 (closes G11) → `docs/PROJECT_STATE.md`. Opt-in/default-off (ALPHA_EPISODES_DB
shadow switch); 4+2 checklist wired; gate-side re-derivation forgery-resistant + waist-enforced
human_approver; verdict-neutral bit-identical; kill switch. Stage-3 (approve-path evidence stamp +
task_forge live-wiring) remains a user-gated step.
### A3 — Self-learning channel (the headline next step)
A3 SHIPPED 2026-07-13 (closes G10 precondition) → `docs/PROJECT_STATE.md` (spec
`2026-07-13-a3-self-learning-design.md`). Context-management trio (provenance-preserving pruning +
content-addressed workspace-path-guarded offload + T0 recall + 4-phase compaction) + the
reflection→directions self-learning channel (kind=task detectors → EvolutionProposal, zero live
write, conflict→held, negative-constraint mining). Dormant/default-off. Deferred: live LLM
summarizer; new-skill authorship; negative-constraint expiry.
### A4 — Session organ, phase 1
A4 SHIPPED 2026-07-13 (closes G1 first slice) → `docs/PROJECT_STATE.md` (spec
`2026-07-13-a4-session-organ-design.md`). Origin-stamp class (forge-resistant), hash-chained EditLog
+ external anchor (corruption-detection-only honest limit), scope labels on learned-context writes
(resolves the 2026-07-10 unlabeled-learning timing deviation), attribution tuple. NEEDS A8-era call:
scope defaults agent-global (A8 derives narrowest for its gate). verify_chain live wake()/load
wiring is A5/A10.
### A5 — Body-Store-as-git
A5 SHIPPED 2026-07-13 (closes G2) → `docs/PROJECT_STATE.md` (spec
`2026-07-13-a5-body-store-git-design.md`). Commit-per-apply audit via GitBodyStore (opt-in
ALPHA_BODY_GIT, default-off byte-identical; git leg audit-mirror-only, never aborts a landed op;
Applier-alone; forward-revert rollback). NEEDS USER JUDGMENT: whether GitBodyStore joins tcb.lock
(TCB additions are human-only; precedent excludes LiveBrainStore). True git-checkout rollback
deferred to A10.
### A6 — Spend metering
A6 SHIPPED 2026-07-13 (closes G5) → `docs/PROJECT_STATE.md` (spec
`docs/superpowers/specs/2026-07-13-a6-spend-metering-design.md`): MeteredClient at the make_client
seam (real usage side-channel + estimate fallback + fail-toward-metering on unknown models),
Budget (positive ceiling, soft warn / HARD breach → BudgetExceeded → non-zero exit — governed not
reported, adversarially confirmed un-swallowed), threaded into refine_live/run_verdict/save_decisions
(shared meter across verdict arms = symmetric). Additive/default-off. Carry-forward: the
per-refinement cost on the EvolutionProposal OBJECT needs a TCB edit → folded into **A8** (packet
counsel); daily_loop metering is a small additive thread; the richer charter ladder (foreground
pause-and-prompt, cross-session accumulator, egress meter, per-party rate limiting) is queued.

### A7 — Sonia-side proposer over worker traces
A7 SHIPPED 2026-07-13 (closes G7) → `docs/PROJECT_STATE.md` (spec
`2026-07-13-a7-sonia-proposer-design.md`). The worker's propose path is RETIRED (channel removed +
teach_surface kairos leg dropped + waist refuses proposer kairos/hermes); two hands only — a Sonia
proposal (A3 reflect channel) or the user's direct edit. Worker compute-use retained. Inert
staged-edit UI plumbing left for a future repurpose to review Sonia proposals.
### A8 — Canonical teach surface + deliberation-packet counsel
A8 SHIPPED 2026-07-13 (closes G8) → `docs/PROJECT_STATE.md` (spec
`2026-07-13-a8-teach-counsel-design.md`). One teach write-scope authority (all four sites);
kernel-generated counsel (behavior_diff forge-resistant) + A6 cost on the packet; the gate-level
scope-mismatch refusal; teaching /apply staleness pin. NEEDS USER RATIFICATION: the scope-mismatch
gate derives the effective evidence scope as NARROWEST (dormant today; load-bearing in the
multi-party future) — a governance-behavior choice.
### A9 — Egress ladder + two-class credential split
A9 SHIPPED 2026-07-13 (closes G4 + G3 long-term) → `docs/PROJECT_STATE.md` (spec
`2026-07-13-a9-egress-creds-ssrf-design.md`). SSRF guard netguard.py (resolve-once/all-IPs-is_global/
pin-IP/redirect-revalidate/metadata-block — bypass-swept), egress deny-by-default allowlist (M1/M2,
the activity-space §10 answer), two-class credential ALLOWLIST split. NEEDS USER JUDGMENT: netguard.py
should join tcb.lock (human-only). REMAINING before non-localhost serving: kernel netns egress
(A10), content DLP, CSRF/Origin loopback check, data-source-fetcher adoption.
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
  ordering (`phase_from_read` → retrieval; touches TCB `alpha/agent/retrieval.py`). Until then
  growth skills order by phase_prior only (P2 carry-forward). **NOT a "minimal seam" (investigated
  2026-07-13):** the momo regime helpers (`CANONICAL_PHASES` = the 6 momo tokens) don't recognize
  the growth clock's `market:x` scale-typed tokens, and growth skill seeds don't carry `market:x`
  phases — so threading the growth read needs the Option-B vocab bridge, not a one-liner. **FOLDED
  into the three-clock activation arc (§1 PX)** — it's the market-clock's skill-selection consume leg.
- ~~**Growth console instrument**~~ SHIPPED 2026-07-13 (three-state market-clock dial + panic badge,
  momo ring byte-identical; spec `2026-07-13-growth-console-instrument-design.md`) → PROJECT_STATE.
- ~~**Sonia small fixes**~~ ALL 4 SHIPPED 2026-07-13: `/chat` brain-load inside the error boundary;
  `edit_action` under `_MUTATION_LOCK`; the file-count/aggregate-size cap in `ingest_attachments`
  (`_MAX_FILES=20` / `_MAX_TOTAL_BYTES=20MB`, fail-open with a summarizing note, 13 tests in
  `tests/meta/test_ingest_attachments.py`; the network/SSRF leg is A9's netguard); and the console
  banner split "Sonia 404" (`HTTPStatusError` → "service is up but the request failed") vs "Sonia
  unavailable" (`ConnectError` → "start it") — `app.py::_sonia_banner`, wired at all 3 call sites,
  3 tests in `tests/web/test_cockpit.py`.
- **Cockpit direct-edit UI for the user-direct hand** — form → `POST /edit`, an honest-limits line
  (a direct edit forgoes packet counsel), revert lever `POST /snapshots/{name}/restore` beside it.
  Own brainstorm→spec→plan round; deferred 2026-07-10 by user (landing-doc spec D6).
- **`tweak` action** — manual inline arg-editing of a proposed edit (no LLM; cockpit spec §8 route
  table) — merged with teach-crystallize §10's "re-preview when `ProposedEdit.args` is edited
  between propose and apply"; they ship together.
- **Post-apply red-line lint + mandatory-taboo gate step** — step 1: gate-side check in
  `try_apply_op`'s `write_skill` branch that a new `type='pattern', domain='trading'` skill carries
  ≥1 taboo entry, + wire-or-fix the unconsumed `GateSpec` (confirmed 2026-07-13: `.gate` has ZERO
  production consumers — the docstring's `eval/rule_policy` consumer does not exist); step 2:
  safety-only-tightens monotonic check (needs a typed safety surface); the semantic contradiction
  check needs its own design. (kairos-mining §1.4/§2.4/§4.4.)
  > **HELD FOR USER (investigated 2026-07-13, NOT a "cheap" step):** (1) it encodes a DOCTRINE POLICY —
  > "every trading pattern skill MUST carry a red-line taboo" is the user's 魂骨宪法 to ratify (the 6
  > seed pattern/trading skills all carry one = convention; enforcing it AT THE WAIST is a new rejection
  > path). (2) It breaks ~6 existing tests that create taboo-less pattern skills for UNRELATED reasons
  > (`tests/refine/test_apply_growth_vocab.py::_write_skill_op` tests phase-vocab, no taboo). RECOMMEND
  > enforcing (matches doctrine + seeds; cost = add a taboo to those ~6 test ops) — but it changes
  > write-waist gate semantics, so it wants a user OK before shipping.
- **Delete-× while Sonia is DOWN** swaps the unavailable banner into the `<li>` — cosmetic.
- **Agent-modification drawer polish** — post-apply diff overlay, cross-session PENDING
  aggregation, drawer on other pages, optional Playwright resize test (drawer spec §7).
- ~~**`docs/blueprint.md` demotion**~~ SHIPPED 2026-07-13 (14ac8ba) — formal-demotion banner: both
  doctrinally superseded (growth pivot) + structurally pre-build-out; points to the growth doctrine
  draft + CLAUDE.md + PROJECT_STATE + DEVELOPMENT-PLAN as authoritative; CLAUDE.md pointer synced.
- ~~**EpisodeStore WAL / busy-timeout**~~ SHIPPED 2026-07-13 (7be0431): `journal_mode=WAL` +
  `busy_timeout=5000` in `EpisodeStore.__init__` (WAL a no-op on `:memory:` → in-memory path
  byte-identical; +2 tests; store.py is TCB → tcb.lock regen'd). Closes charter-conformance §5.12.
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
  pairs with branchable brains (§2 tail). **DEFER confirmed 2026-07-13:** SnapshotStore is LINEAR
  today (snap_NNNN, version=latest+1) — there is no branch/lineage tree, so "prune only leaf
  lineages" has no structure to key off; a naive linear keep-last-K would silently DELETE rollback
  targets (`POST /snapshots/{name}/restore`), a destructive behaviour change. Correctly coupled to
  branchable brains (§2 tail, deferred); do NOT build a naive pruner that loses restore history.
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
