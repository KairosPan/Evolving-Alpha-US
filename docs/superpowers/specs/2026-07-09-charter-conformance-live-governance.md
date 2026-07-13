# Charter conformance — live-governance convergence

**Date:** 2026-07-09 · **Status:** BUILT (as amended by §5 — read §5 with every section below)
**Mandate:** user: "按照设计稿的指引，修正 evolving-alpha-us" — converge this repo's LIVE
governance seams to the `../Sonia-Kairos/` charter, per the violations verified in
`docs/findings/2026-07-09-two-way-alignment-sonia-kairos.md`.

## 0. The charter rules being conformed to

1. **Two hands, one Applier** (First Founding Principle + 2026-07-08 amendment): every change to
   the live Body lands through the Applier via exactly two triggers — an agent proposal that
   passes **user approval**, or the **User's direct edit** (stamped, audited, no deliberation).
2. **The worker never self-lands** ("Kairos acts, Sonia evolves"): no code path may let a
   conversational agent's own edit reach the live brain without a human step.
3. **Machine detects, user reverts** (machine authority boundary): no machine-initiated revert of
   the live Body. Inside a disposable trial fork, machine autonomy (incl. rollback) is the
   charter's *trial semantics* — allowed.
4. **Revert reconciles derived state** (rev-09): a rollback must clear every derived record that
   asserts a reverted edit exists (`applied_seqs`, staged-edit terminal states).
5. **Provenance names the true principals**: proposer vocabulary gains `kairos` + `user`
   (keep `hermes` for stored-brain read-compat); `human_approver` is populated wherever a human
   actually approved.

## 1. Scope boundary (what is deliberately NOT touched)

- **The offline eval/verdict harness is byte-identical**: `InnerLoop`, `compare_harnesses`,
  `walk_forward`, `Refiner`, `LoopConfig` are unchanged. Autonomous refinement + breaker
  rollback inside an eval run ARE the trial fork the charter permits. Zero eval-test diffs.
- No kernel/Body physical split, no sandbox egress work, no Mem0 — those belong to the design
  repo's SP1–SP5 new build, not this donor.
- `LocalEnv` operator-trust posture unchanged (already user-accepted, documented).

## 2. Design

### D1 — Worker face: stage-only (kills anti-donor rev-04)
- `make_gated_write_tool` (the live-landing tool) is **deleted**. `build_converse_registry`
  accepts `write_mode ∈ {"stage","none"}`; `"apply"` raises `ValueError` (fail-closed, not a
  silent downgrade). Defaults flip `"apply"→"stage"` in `build_converse_registry`,
  `converse_project`, `build_arena`. Live workbench already passes `"stage"` — unchanged.
- `make_propose_edit_tool`'s dry-run provenance proposer `"hermes"→"kairos"`.

### D2 — Approve-time provenance (workbench)
`approve_edit` stamps `EditProvenance(path="teaching", proposer="kairos",
human_approver="user")`. (Conflict-queue threading at approve time is a no-op — teaching-path
ops never trip `is_conflict` — so it is not added.)

### D3 — Provenance vocabulary (`alpha/harness/edit_log.py`)
`path`: + `"user_direct"`. `proposer`: + `"kairos"`, `"user"` (keep `"hermes"`: persisted brains
carry it; additive Literal change validates old records).

### D4 — Sonia apply records the human
`MetaAgent.apply(accepted, *, human_approver=None)`; the sonia `/apply` route passes
`human_approver="user"` (the user accepted the edit cards). `preview_op` unchanged.

### D5 — User direct edit (the second hand)
New sonia endpoint `POST /edit {tool, args, rationale}` → under the brain lock: snapshot →
`try_apply_op(allowed=ALL_TOOLS, provenance=EditProvenance(path="user_direct", proposer="user",
human_approver="user"))` → save. No LLM, no deliberation; still through the gate (red-lines and
floors bind the user's hand too — the Applier validates mechanically, matching the charter's
"stamped and audited" landing).

### D6 — Live self-study becomes fork + proposal packet (kills anti-donors: live self-edit, live
machine-revert, long-held brain lock)
- New `alpha/meta/evolution.py` + `ProposalQueue` (in `alpha/meta/proposal_store.py`, the
  ConflictQueue file pattern: flat by-id JSON, atomic writes):
  - `run_forked_evolution(bstore, runner) -> EvolutionProposal | None`: under the lock, load the
    live brain and record `base_len = len(log)`; **deepcopy → fork**; release the lock; run
    `runner(fork_h, fork_log)` (the existing InnerLoop / forge machinery, unchanged — full
    autonomy inside the fork); package the **surviving** delta `fork_log.records()[base_len:]`
    (breaker rollbacks inside the fork already truncated the log) + the serialized fork brain
    into an `EvolutionProposal{proposal_id, created_at, kind: "refine"|"forge", base_len,
    window, records, harness_dict, log_dict, summary}`. Empty delta → no proposal (stated, not
    silent: the script prints the reason).
  - `adopt_proposal(bstore, proposal) -> (ok, reason)`: under the lock: **staleness check by
    content hash** — the packet stores `base_hash = sha256(canonical_json(harness_dict,
    log_dict))` captured at fork time; at adopt, recompute over the live brain and reject on
    mismatch (`"stale: live brain differs from the packet's base; re-run"`). Length-only checks
    are NOT sufficient (a land+rollback sequence reproduces the same length with different
    content); the hash pins the packet to its exact base body-version. Then: snapshot;
    re-stamp the delta records' provenance with `human_approver="user"`;
    save the fork brain+log as the live brain. Soundness: every delta edit passed the full gate
    against a base identical to the current live brain, so landing the fork ≡ landing the
    gate-approved results.
- Sonia service: `GET /proposals`, `POST /proposals/{pid}/resolve {decision: "adopt"|"discard"}`
  (adopt → `adopt_proposal`; both decisions remove the packet — ConflictQueue-symmetric; a
  discarded fork dies with its session, per charter).
- `scripts/refine_live.py` + `scripts/evolve_from_episodes.py`: default mode = **propose**
  (fork → packet → `$ALPHA_PROPOSALS_DIR`, default `./state/proposals`); `--autonomous` restores
  the pre-pivot in-place behavior (explicit, documented as the escape hatch). The ConflictQueue
  still receives held conflicts from inside the fork run (unchanged behavior).

### D7 — Rollback reconciles derived state (rev-09 / ROADMAP §6 item)
- sonia `rollback_message`: after `restore`, reload the brain, `L = len(log)`; sweep ALL
  sessions: drop `applied_seqs ≥ L`; edits with `applied_seq ≥ L` → `status "applied"→
  "accepted"`, `applied_seq=None`, `apply_reason="rolled back"`. `/propose` 409 dead-end gone.
- workbench `/rollback`: same sweep over `staged_edits`: `applied_seq ≥ L` → `status→"pending"`,
  `applied_seq=None`, `snapshot_before=""`, `reason="rolled back"`.

## 3. Test impact

Updated: `tests/converse/test_registry_provenance.py` (apply-mode wiring → ValueError + stage
default), `tests/converse/test_gated_write_conflict.py` (deleted with its subject; gate-level
conflict coverage lives in tests/refine), `tests/converse/test_tools.py` (2 gated-write tests →
removed; propose-tool coverage exists), `tests/refine/test_proposer_provenance.py` (hermes
expectation → kairos, via the propose/approve path), arena builder default-mode assertions if
any pin `"apply"`. New: literal read-compat (`hermes` record validates), apply→ValueError,
approve provenance kairos+human_approver, sonia human_approver, `/edit` user-direct (+red-line
rejection), rollback reconcile ×2, ProposalQueue round-trip, fork-propose (mock LLM; live brain
byte-unchanged after run), adopt (clean + stale + discard), forge propose mode.

## 4. Acceptance

- Full suite green; zero diffs under `tests/loop/`, `tests/eval/` (eval byte-neutrality).
- No **default** production code path lands an agent-authored edit on the live brain without
  `human_approver` recorded (scoped per §5.3: the env-gated `--autonomous` escape hatch is the
  recorded exception).
- `grep -rn 'proposer="hermes"' alpha/ workbench/ sonia/` → 0 production hits (read-compat only
  in the Literal + tests).

## 5. As-built amendments (2026-07-09, folding the 3-lens adversarial review — all verdicts
"build-with-fixes"; every blocker/major below was verified against code before folding)

1. **D6 runner contract (BLOCKER):** the runner must RETURN the final `(harness, log)` —
   an in-fork breaker rollback rebinds `HarnessManager.harness/.log` to fresh restored objects,
   so packaging from the passed-in handles would ship the discarded timeline. Pinned by
   `tests/meta/test_evolution.py::test_packages_from_returned_handles_not_the_passed_ones`.
2. **D6 fork side-effects (BLOCKER):** propose mode threads `episode_store=None` +
   `recall_store=` (read-only) — a discarded fork writes NO live episodes (pinned by
   `test_propose_mode_writes_no_live_episodes`). Accepted cost: an ADOPTED packet's run doesn't
   retro-write its episodes either; episodic evidence accrues from future live decisions.
   Held ConflictQueue entries DO survive the fork deliberately: they contest LIVE teaching-owned
   elements and are pure adjudication signals (resolution records intent only, never applies).
3. **`--autonomous` (MAJOR):** additionally gated behind `ALPHA_UNSAFE_AUTONOMOUS=1`; named a
   recorded non-conformance (pre-pivot in-place evolution incl. live machine-revert), not
   claimed as conformant. §4's claim is scoped to default paths.
4. **§0 rule 2 honest scope (MAJOR) — G7. CLOSED by A7 (2026-07-13).** the charter's actual rule is
   stronger — *Kairos does not propose at all*. This 2026-07-09 arc killed self-LANDING only; the
   worker still proposed staged edits. **A7 closed the gap** (spec
   `2026-07-13-a7-sonia-proposer-design.md`): the worker's propose ORIGINATION is retired (no
   `propose_memory_edit` tool; `teach_surface` kairos leg removed) and the two-hands invariant is
   enforced at the gate — `try_apply_op` refuses `proposer∈{kairos,hermes}`, so no worker-originated
   edit reaches the waist. The Sonia-side proposer over worker traces is A3's reflect channel
   (`alpha/refine/reflect.py` → `scripts/reflect_from_tasks.py` → `/proposals`). Only two hands now
   land: a Sonia proposal (sonia / self-study forge|refiner via /proposals+adopt) or the User's
   direct edit (user_direct).
5. **Unauthenticated loopback approvals (MAJOR, accepted risk):** `human_approver="user"` is
   minted from bare localhost POSTs (no Origin/CSRF checks). Accepted for the single-operator
   localhost posture; the ROADMAP SSRF/non-localhost item remains the BLOCKING precondition
   before any multi-user serving, and this is part of it.
6. **Serialization (MAJOR):** `HarnessState.to_dict`/`EditLog.to_dict` switched to
   `model_dump(mode="json")` — a gate-landable `learned_asof` date crashed every json.dumps
   consumer (pre-existing latent bug, regression-pinned). `canonical_json`/`brain_hash` defined
   ONCE in `alpha/meta/proposal_store.py`, imported by both packager and adopter.
7. **D7 cross-face sweep (MAJOR):** both faces share one brain, so BOTH apps sweep BOTH derived
   stores (sonia sessions + workbench staged edits) after any restore; `SessionStore.list()`
   hardened to skip unparsable files (sweep must complete; retry-idempotent). Workbench
   `/rollback` now targets the HIGHEST `applied_seq` (the true last apply), not list position.
8. **Adopt mechanics (minors):** materialize-before-snapshot for seeds-only stores; delta
   re-stamp is a dict-level transform (frozen models; provenance=None minted from packet kind);
   `adopt_proposal` owns the brain lock (callers must not wrap it — flock self-nesting 500s).
9. **New user levers:** `sonia GET /snapshots` + `POST /snapshots/{name}/restore` (traversal-
   guarded, full reconcile sweep) — the revert lever for `user_direct` edits, which have no
   session message to roll back through.
10. **D5 posture (as built):** sample floors LIFTED for the user's hand (`min_*=0`); structural
    checks (whitelist, rationale, red-line immutability, set-once domain, positive-expectancy
    promote) bind everyone including the user.
11. **Bare `converse()`** → `write_mode="none"` (no staging persistence/approval surface exists
    there; a stage tool would silently drop stagings — decide-only is the honest surface).
12. Noted, not done: `EpisodeStore` WAL/busy-timeout (propose mode no longer writes episodes;
    concurrent-writer exposure unchanged from before this arc).

**Second fold (final whole-branch review, 3 lenses, all "fix-then-merge" — folded 2026-07-09):**

13. **Test isolation (BLOCKER):** the cross-face sweeps made each face open the OTHER face's
    store — tests isolating only their own face's dirs would read/write the operator's REAL
    `./state`. `brain_session_isolation` now sets all five vars (brain/sessions/projects/
    conflicts/proposals); `tests/workbench/conftest.py` added (autouse).
14. **adopt validates the RESULT, not just the base (MAJOR):** base_len == live log length;
    fork log must extend the live log (prefix equality); reviewed `records` == landing delta;
    red-line `immutable_core` byte-equality vs the live brain; snapshot name sanitized
    (packet-supplied id fed a guard-less `snapshot()`). Each attack pinned by a test.
15. **`/proposals/{pid}/resolve` validates `decision` (MAJOR):** anything other than
    adopt/discard → 422, packet kept — discard is destructive (a packet is a full,
    non-reproducible evolution run) and used to swallow typos as discards.
16. **Sweep concurrency + visibility (minors):** the reconcile sweep now runs INSIDE the brain
    flock in all three revert paths; apply paths persist derived records inside the flock;
    `_reconcile_all` catches only `FileNotFoundError` as the no-DB no-op and SURFACES other
    failures in the response (`workbench_sweep` field); workbench `/rollback` sweeps ALL
    projects. Cross-face heal pinned in BOTH directions; route-level `human_approver` pin added
    for sonia `/apply`; env-gate refusal pinned for `evolve_from_episodes`; torn-session-file
    listing pinned; the URL-encoded traversal test was vacuous (Starlette decodes before
    routing) — replaced by store-level guard unit tests + an honest routed-404 pin.
17. Noted, not done: a production-seam pin for refine_live's runner returning `mgr` handles
    (the library seam is pinned; forcing an in-fork breaker trip at script level is
    disproportionate — revisit if the runner wiring is ever refactored). The reconcile sweep's
    length-only limitation on abandoned-branch restores is recorded in `alpha/meta/reconcile.py`.
