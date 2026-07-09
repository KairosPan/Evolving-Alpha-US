# Kairos → Evolving-Alpha-US: transferable-design mining

> **Naming note (2026-07-09):** "Kairos" in this document means the sibling CN legal-agent repo at
> `~/Desktop/self-evolve/kairos` — NOT the Kairos worker entity of Sonia-Kairos-US-Stock (this
> repo, renamed 2026-07-09 from Evolving-Alpha-US). The body below is a frozen record.

**Date:** 2026-07-01 · **Method:** 47-agent workflow — 8 area deep-readers over
`~/Desktop/self-evolve/kairos` → per-pattern mapping against this repo's code + ROADMAP →
adversarial verification of every adopt/adapt candidate → coverage critic + one follow-up round.

**Scale:** 100 patterns mined · **40 already-have** (alpha has an equivalent) · 24 adopt/adapt
candidates adversarially verified (**8 confirmed, 16 weakened-with-correction, 0 refuted**) ·
21 unverified extras from the critic round · 17 not-applicable (multi-tenant/legal/web-product).

---

## 0. Meta-finding: convergent evolution validates both architectures

40 of 100 kairos patterns already exist in alpha under different names — independently converged:
kairos `RunExecutor.execute` single seam ≈ alpha's `try_apply_op` write-waist + decorator stack;
kairos D12 audit-before-state-change promotion gate ≈ `try_apply_op` floors + append-only EditLog;
kairos L1–L6 optimizer ladder ≈ alpha R1–R6 modification ladder; kairos candidacy-vs-authorization
split ≈ `StagedEdit.valid` vs `status=='approved'`; kairos MatterScopedSession (tenant isolation
compiled into the SDK) ≈ `GuardedSource(AsOfGuard)` (the same move applied to *time*); kairos
dormant-flag shipping ≈ alpha's default-off/byte-identical house style. Treat this as strong
cross-validation of alpha's crown jewels, not as "nothing to learn."

---

## 1. Adopt now — low cost, named-backlog hits

### 1.1 Activation Ledger in ROADMAP.md  *(CONFIRMED, value 5, cost low)*
Kairos `docs/ROADMAP.md` opens with a table — Capability | Built | **Live in prod** | Remaining
activation step — redefining "done" as *flag ON carrying real traffic*, with a WIP rule (don't
start a new track while a finished one sits dark) and ROADMAP as the single status authority.
**Alpha gap (verified, and a real live drift):** ROADMAP.md still says "555 tests / P-A `[ ]`"
while PROJECT_STATE records P-A + live-face + P-B/P-C merged & pushed at 882 tests (@`23e0dbc`);
the P-B/P-C coupling is dormant-by-design and its 4-item activation checklist exists only as one
sentence inside PROJECT_STATE's header paragraph.
**Do:** add the three-column ledger at the top of ROADMAP.md. Clean rows today: **P-B/P-C
operational-K coupling** (built, dark, 4 known activation steps) and the **§6 live daily
production loop** (producers exist, loop not built). *Correction folded in:* GCycle recalibration
is ordinary backlog (not-built tuning), not a ledger row. "Prod" ⇒ "wired into a live driver
(save_decisions / refine_live / workbench) and carrying real runs."

### 1.2 Flag-flip rollout runbooks (`docs/superpowers/runbooks/`)  *(value 5, cost low)*
Kairos gives every dark-shipped capability a dedicated runbook that is the only sanctioned path
to ON: §0 what turning it on does + the named verifying E2E test; §1 the complete flag set as a
Flag | Role | Without-it table with an explicit **"the headline flags are NOT sufficient"**
warning + two-tier kill switch; §2 pre-flip checklist; §3 staged rollout. Fail-closed cost
bounds (over-budget = terminal defer, never silent downgrade).
**Alpha gap:** `docs/superpowers/` has only specs/ + plans/; the episode read-side flip was
coordinated from prose across a plan + PROJECT_STATE; the P-B/P-C flip is strictly harder.
**Do:** create `runbooks/`; first runbook = **P-B/P-C activation** (wire `experience_writer` /
`task_forge` / `confirmed_ids` / pinned-asof + conflict_queue routing; pre-flip checklist
re-asserts verdict read/write symmetry + default-off-when-dark; kill switch = un-wire
`experience_writer` / the `for_asof(kind=)` fence; verifying test = the verdict-neutrality
regression). *Correction:* the runbook is the **ops companion** to an implementation plan (alpha
activations are code-wiring, per the episode-readside precedent), not a replacement.

### 1.3 Resolve-once-and-pin SSRF egress guard  *(adopt, value 4, cost low)*
Kairos `ingestion.py::is_safe_public_url` + the A2A egress guard: https-only, no userinfo,
resolve the host **once**, require every resolved IP `is_global` (blocks loopback/private/
link-local/reserved/multicast/CGNAT and metadata `169.254.169.254`), then connect to the
*pinned* IP.
**Alpha gap:** ROADMAP §6 names this verbatim as the **BLOCKING precondition** before any
non-localhost serving; `alpha/meta/ingest.py` has only the scheme allowlist.
**Do:** stdlib-only (`ipaddress` + `socket`) validator in `alpha/meta/` (e.g. `netguard.py`),
called by `fetch_url`, reused later by any arena network tool. *Correction from verify:* to be
DNS-rebinding-safe per the ROADMAP wording, resolve once → validate every returned IP → **connect
by pinned IP** (Host header preserved), and disable/re-validate redirects in `_urllib_fetcher` —
the bare validator alone doesn't close the redirect bypass. Keep kairos's byte cap.

### 1.4 Mandatory negative guards on new trade-proposing skills  *(CONFIRMED, value 3, cost low)*
Kairos `TriggerContract{fire_when, do_not_fire_when}`: a skill declaring a risky class MUST
declare at least one negative guard (model_validator keyed off `model_fields_set` so legacy seeds
don't brick).
**Alpha gap (verified):** `Skill.taboo` defaults empty and nothing enforces it; `GateSpec` is
machine-readable but **unconsumed** (its docstring's `eval/rule_policy` consumer doesn't exist).
**Do:** gate-side check in `try_apply_op`'s `write_skill` branch — a new `type='pattern'`,
`domain='trading'` skill must carry ≥1 taboo entry, rejected with a clean reason (same shape as
the missing-rationale guard). Ship as **step 1 of ROADMAP §6's post-apply red-line lint**. Put it
at the gate (covers refiner/Sonia/converse provenances), not in a pydantic validator.

### 1.5 Redact-before-emit at persistence waists  *(CONFIRMED, value 3, cost low)*
Kairos has one recursive `redact()` (sensitive keys + value patterns → `<REDACTED>`) applied at
every egress, with the ordering invariant *redact before hash*.
**Alpha gap (verified leak vector):** `LocalEnv.run` inherits the parent env; a T2 shell `env`
puts `DEEPSEEK_API_KEY`/APCA keys into tool results persisted **verbatim** into
`ProjectTurn.tool_calls` (converse sqlite store) and SessionStore JSON. *(Task episodes are OK —
`experience.py` persists only a compact summary.)*
**Do:** one dependency-free `redact()` applied in the converse sqlite store and
`meta/store.SessionStore` (experience_writer as a cheap third). Key/credential-scoped only —
never scrub market/PIT data or edit payloads needed for rollback replay.

### 1.6 Assembled-prompt audit record — "drops are recorded, never silent"  *(adopt, value 4, cost low; unverified extra)*
Kairos's prompt assembler takes an optional `collect` callback recording every layer: ref, order,
bytes, `included|dropped` + reason.
**Alpha gap:** `build_system_prompt` silently drops skills failing `depends_on`, lessons under
`MIN_MEMORY_WEIGHT`/budget, episodes beyond budget; nothing persists what a decision's prompt
actually contained.
**Do:** optional collect hook (default None ⇒ byte-identical) in `alpha/agent/prompt.py`,
persisted beside the DecisionPackage by producers. Directly serves diagnosing **ROADMAP §1 GCycle
recalibration** (prove what the suppressed agent was actually shown). Companion cheap win: a
`scripts/render_prompt.py` offline prompt-layout viewer.

---

## 2. Adopt with reshaping — medium cost, backlog-aligned

### 2.1 TCB lockfile — the spec's own NOW deliverable  *(CONFIRMED, value 4)*
Kairos: `scripts/gen_skills_lock.py` + `kairos-skills.lock` pin content hashes of governed
capability dirs; `--check` enumerates typed drift and fails; wired into CI/pre-commit.
**Alpha:** zero hashing anywhere (grep-verified), yet the modification-ladder spec §3 *declares
the TCB manifest a NOW deliverable* (13-row table already enumerated in the spec — extract it,
don't re-derive it; note it deliberately lists floor_breaker/conflict/snapshot rather than
`guard/`).
**Do:** `scripts/gen_tcb_lock.py` + `tcb.lock` over the spec §3 file set + a `--check` pytest.
Optional follow-up: stamp a post-state brain content hash into each EditRecord (additive optional
field, eval never reads it). This is the seed of the deferred R3+ `try_promote_body` byte-hash pin.

### 2.2 Tri-state data availability at the guard seam  *(CONFIRMED, value 4)*
Kairos connector adapters make `exists()` tri-state: found / not-found / **backend-unavailable**
(raises `LookupUnavailable`) so an outage is never mislabeled "verified absent."
**Alpha hole (verified line-by-line):** missing `corp_actions.parquet` → `pit_store` returns
None → empty frame → `has_dilution`/reverse-split flags compute **False** — "no data" is
indistinguishable from "checked, nothing announced"; the dilution veto silently runs blind.
**Do:** a distinguishable unavailable state on the corp-actions path (typed wrapper or
`has_corp_actions()` probe), surfaced by `screen_decision` into `DecisionPackage.key_risks`
("dilution/SSR guard ran blind") — co-pilot-consistent *warn the human*, not a new veto. Ship
default-off, byte-identical when off, threaded **symmetrically** into both verdict arms. *(This
absorbs the separate "per-gate fail posture" candidate: the only genuinely silent seams are the
snapshot-store corp-actions read and `ssr_active`/`halt_then_dump` mapping missing rows → False;
the live Alpaca path already fails loud.)*

### 2.3 Gate-side re-derivation of task evidence — pre-P-C-activation hardening  *(value 4)*
Kairos double-gates promotion: the pure gate hardwires `approved=False` for automated drivers,
and `promote` re-checks floors against **persisted eval records the caller cannot forge**.
**Alpha asymmetry (verified):** trade floors read unforgeable harness-held `sk.stats`
(`_PATCH_FORBIDDEN`), but the P-C task branch trusts **caller-supplied** `task_stats`
(`apply.py:129` "the caller MUST supply precomputed task evidence") — and `confirmed_ids` too.
**Do (before P-C goes live):** thread a **read-only, PIT-pinned** episode-store handle
(`for_asof(asof, kind="task")`, lazy-imported to respect the refine↔memory cycle) into
`try_apply_op`'s task branch and recompute `summarize_task` inside the gate; derive
`confirmed_ids` from durable records (EditLog provenance / persisted verifier verdicts) rather
than producer input. Mirror the verdict's read-only `recall_store` split so the gate can never
become a self-write channel. Add this to the P-B/P-C runbook checklist (§1.2).

### 2.4 Safety-only-tightens partial order at the write-waist  *(value 4, two-step)*
Kairos `safety_only_tightens(baseline, candidate)`: a pure non-LLM gate letting self-evolved
changes move safety posture only monotonically stricter, with safety fields **enumerated from the
pydantic model** so new fields are auto-covered.
**Alpha gap:** only red-line *text* is immutable; nothing stops `patch_skill` shrinking
`Skill.taboo` or retiring a guard-supporting lesson. But alpha has no typed safety surface to
enumerate yet.
**Do:** (1) add a small safety-posture surface (e.g. `safety_critical` tag / designated-field
registry on Skill/Lesson); (2) implement the monotonic check **inside `try_apply_op`**, scoped to
safety-tagged fields only (the Refiner is *supposed* to loosen ordinary trading knowledge —
over-scoping ossifies the harness); route violations to the existing `conflict_queue` → USER
adjudication rather than hard-rejecting. Serves ROADMAP §6 red-line lint.

### 2.5 Adversarial trap-day battery  *(CONFIRMED, value 3)*
Kairos keeps candidate-only adversarial eval rows where the SAFE behavior scores 1.0, held to a
decoupled `ADVERSARIAL_FLOOR=1.0` — one failure blocks regardless of aggregate.
**Alpha:** anti-Goodhart pieces exist (Hmin_chase arm, confirmed-positive, episode-taboo) but no
fixed trap battery survives-recalibration test.
**Do:** a `tests/` battery in the style of the PIT firewall quartet: synthetic FakeSource
blowoff-top/backside days where any new long = fail, run through the full
`SizingPolicy(GuardedPolicy(...))` stack. **This is the guardrail that lets ROADMAP §1's GCycle
threshold loosening proceed safely.** Fail if zero trap days load (no vacuous pass). Keep trap
days OUT of live eval/verdict scoring — regression/promotion preconditions, never training signal.

### 2.6 CHECKSUMS manifest for captured PIT windows  *(value 3)*
Kairos verifies a sha256 manifest of the golden eval corpus **before** reading, fail-closed.
**Alpha:** `snap/` parquet windows — the graded exam — are integrity-unpinned.
**Do:** `capture_window.py` writes a CHECKSUMS manifest; **commit the manifest to git** (parquet
stays gitignored) so tampering requires a reviewable git change; `run_verdict.py` verifies
fail-closed, ad-hoc exploration warns. Drop kairos's K_MAX half (alpha already bounds cost); no
manifest for the growing `brain.db`.

### 2.7 Frozen Settings model at app entry points  *(value 4, from two candidates)*
Kairos policy models: `extra='forbid'`+`frozen`+Field bounds at a validated YAML boundary; flags
resolved **once at boot** into one frozenset threaded to every coupled seam so components can't
disagree mid-run.
**Alpha:** the named config-centralization backlog (~32 inline `ALPHA_*`/`APCA_*` reads;
`./state/brain` duplicated in 4 files; alpha_web reads env per-request inside route handlers).
**Do:** a frozen, bounds-validated Settings object constructed at each app/script entry point
(alpha_web/sonia/workbench/producers) and threaded down as constructor args — kairos's
`from_yaml` posture (coercion ON, unknown-key rejection where applicable), **not** `strict=True`.
Keep it OUT of `alpha/harness` and off the 4 lazy-import cycle edges; offline defaults must stay
byte-identical. Document co-flip couplings (the P-B/P-C flag set) next to each flag. *(An
`ALPHA_*`-prefix audit for typo'd env vars would be new machinery, not a kairos borrow — optional.)*

### 2.8 Purged & embargoed CV — native, kairos for reporting style only  *(value 3)*
The kairos "holdout retest" file is a ~50-line stub (claimed-vs-observed tolerance check); its
marketplace framing is docstring prose. Alpha's promotion evidence is already ground-truth
(oracle-scored realized returns).
**Do:** implement ROADMAP §4 natively in `walk_forward.py` + `compare.py`: embargo the horizon-h
overlap at window edges in `multi_window`; optionally reserve held-out windows never used while
iterating on refiner prompts/config (the real residual Goodhart surface is *human*
meta-iteration). Borrow only kairos's per-metric tolerance-with-reasons reporting shape for
`StatVerdict`. Both arms must see identical holdout windows (verdict symmetry).

### 2.9 Hash-chained EditLog — reduced scope  *(value 2–3, was 4)*
Kairos audit rows carry `prev_chain_hash`/`chain_hash` (sha256 over canonical JSON) + a
`verify_chain()` re-derivation.
**Verify's correction:** without an **external anchor** the chain gives corruption-detection, not
tamper-evidence against the accepted T2-shell operator-trust posture (a shell that can edit
`brain.json` can re-derive the chain). Adopt as: chain + `verify_chain()` finalized at persist
time (after `stamp_last`), legacy snapshots = unchained prefix, **plus** an external chain-head
anchor (append head hash per session to a git-committed file or surface it on `/evolution`).
Groundwork for the deferred BodyLog. Enforce §1.5's redact-before-hash if both land.

---

## 3. Design inputs for planned brainstorm→spec rounds (don't build yet)

| Kairos pattern | Feeds which alpha item | Key detail to keep |
|---|---|---|
| **Content-addressed frozen `WorkflowSpec` + deterministic compile** (CONFIRMED) | the `workflow` brain-component model (ROADMAP §6 brain-drawer) | `spec_hash` over canonical JSON; compile-time cycle rejection (Kahn + lexicographic); edits only via new MetaTools verbs through `try_apply_op`, new `edit_log` target_kind |
| **Governed connector manifest** (side_effect_class / risk_class → central authorize) | the `connector` brain-component model | default to **strictest** class (kairos's own model defaults `pure_read` — copy its frontmatter default instead); manifest-derived tier is **narrowing-only** vs code-assigned tier |
| **Core-skill schema split** (harness roles as shape-discriminated data) | `workflow`/`subagent` models + "Sonia edits the three new components" + "general meta-agent core" | per-role `extra='forbid'` discriminated schemas (a refiner config cannot acquire coordinator powers); `PASS_TOOLS`/gate params stay CODE (TCB); role prompt-body edits are **R5 surfaces** → teaching-path-only + human confirm |
| **Epoch-based fork/rollback sessions** (CONFIRMED) | "Branchable named brains" + "keep-last-K pruning" | fork-at-snapshot-version with `parent_id` lineage; rollback = epoch bump, never delete; **prune only leaf lineages**; edits on any branch still flow through the waist |
| **Sub-run scope narrowing + depth ceiling** | ROADMAP §5 "Master-dispatch G sub-agents" | child tool map ⊆ parent's; per-tool tier may only move **toward stricter oversight** (in alpha, T0→T4 direction — the verify pass fixed the inherited-direction bug); same single ActivityPolicy choke point; record as arena-spec constraint now |
| **Off-hot-path improvement detectors** | ROADMAP §6 "Self-learning channel" (named headline next step) | deterministic forge-style detectors over `kind='task'` episodes (PIT `for_asof` reads) → proposals into the Sonia review queue via `try_apply_op`; human-rejection mining is a separate follow-on consumed as **negative constraints**, never re-surfaced proposals |
| **`harness_digest` decision attribution** | observability polish; later body-axis joint rollback | canonical-JSON sha256 of HarnessState in `snapshot.py` (stdlib, harness stays dependency-free); optional `h_digest` on DecisionPackage/producers; eval never reads it |
| **Teaching funnel state machine** | in-flight teach-crystallize build | validate `ProposedEdit`/session status transitions (table, not free assignment); crystallize's forced `{ops}|{no_edit,reason}` output already fixes kairos's honest-empty concern |
| **Context management trio** (provenance-preserving pruning / content-addressed offload + recall tool / 4-phase compaction with protected bookends) | Sonia/workbench long-session usability; precondition for self-learning channel | prune loses bytes not handles (`[...elided - recall hash=X]`); offload store rooted INSIDE the Workspace, recall tool registered at T0 through the choke point; protect turn-0 task + last-N; FakeSummarizer for the offline suite |
| **Egress posture ladder + sandbox resource manifest** | activity-space spec's open "network allowlist shape" question; R6 kernel sandbox | M1 = monitor-everything (typed `sandbox_egress` audit records at the choke point), M2 = deny-by-default allowlist; resource ceilings declared in the image manifest, policy may only tighten |
| **Operator CLI over agent-written memory** | observability polish | READ-ONLY `scripts/inspect_episodes.py` (or `/episodes` page) over `EpisodeStore.for_asof`, showing the **same** `summarize`/`is_episode_taboo` numbers the veto uses; the write path stays Sonia-only |
| **Dilution lifecycle as typed update events** | ROADMAP §3 EDGAR feed + withdrawal/expiry lifecycle | `updates_since`-shaped checker; keep today's veto-forever as the explicit fail-closed no-connector default; each lifecycle event keyed on its own announce/process date (PIT) |
| **Offered-vs-cited evidence lineage** | self-learning channel + credit precision | persist `Selection` ids + recalled episode ids + asof as an optional DecisionStore sidecar; enables offered-vs-cited attribution |
| **Day-0 launch ledger rows bound to tests** | the P-B/P-C activation checklist | each checklist row → named proving test → blocker type (code / design / human) — merge into the §1.2 runbook rather than a separate artifact |

Downscoped after verification: the **red-line lint** is the only net-new build in the kairos
"protected-modules" pattern (alpha's spec §3 already contains the full TCB table); the lint's
semantic contradiction check needs its own design (kairos's module-reference scan doesn't map).

---

## 4. Bugs / drift found incidentally (verified, independent of any adoption)

1. **ROADMAP.md status drift** — header says 555 tests, §1 still lists P-A unchecked; reality is
   882 tests with P-A/P-B/P-C pushed (@`23e0dbc`). Fix regardless of §1.1.
2. **Corp-actions guard runs blind on missing artifact** — absent `corp_actions.parquet` ⇒ flags
   compute False (§2.2). Real on snapshot-store paths (pre-fix or hand-built captures).
3. **Secret leak into persisted transcripts** — `LocalEnv` inherits parent env; `env` output
   lands verbatim in `ProjectTurn.tool_calls` + SessionStore JSON (§1.5).
4. **`GateSpec` is unconsumed** — its docstring names a consumer (`eval/rule_policy`) that
   doesn't exist. Either wire it or fix the docstring (§1.4 is the natural wiring occasion).
5. **GCycle thresholds unreachable by the Refiner** — `classifier.py` says "the LLM Refiner
   calibrates these thresholds" but they're hardcoded literals no edit path can touch. If the
   Refiner-calibration path (vs a manual US prior) is ever wanted, thresholds must move into a
   declared params object inside H, edited via a new metatool through `try_apply_op` with the
   RISK_OFF veto floor pinned outside the tunable surface.
6. **`session.py` `experience_writer` call is unguarded** — a writer exception kills the live
   turn; one-line try/except-log. Belongs on the P-B/P-C pre-activation checklist.

## 5. Explicitly not applicable (checked, skip)

Ed25519 signed envelopes / Merkle batch roots (single-process trust domain — revisit only at the
deferred body axis), multi-tenant RLS / IDOR / idempotency-key middleware, A2A dual-signed tasks,
SSE fan-out/resume clients, PII-free metric flowback, meet-semilattice policy compile,
perf-budget CI gates at alpha's current scale.

## 6. Suggested order

1. **Docs day (§1.1 + §1.2 + §4.1):** fix ROADMAP drift, add the Activation Ledger, create
   `runbooks/` with the P-B/P-C activation runbook (fold §2.3's gate-side hardening + §4.6 into
   its checklist).
2. **Cheap hardening batch (§1.3–§1.6):** SSRF pin, taboo-required gate check, redact(),
   prompt-audit hook + `render_prompt.py`.
3. **Integrity batch (§2.1 + §2.6, one hashing utility):** `tcb.lock` + PIT-window CHECKSUMS.
4. **Before GCycle recalibration (§2.5):** the trap-day battery, then recalibrate with §1.6's
   audit record as the diagnostic.
5. **Before P-C activation (§2.3):** gate-side task-evidence re-derivation.
6. **When the respective spec rounds open:** feed §3 rows into workflow/connector/subagent
   models, branchable brains, G sub-agents, self-learning channel, context management.
