# Backend-Design — Sonia-Kairos-US-Stock (the live system)

**Status:** drafted 2026-07-10 · standing document (first-class, like the charter).
**Authority:** charter (`Evolving-Agent-Design-SoniaKairos.md`) > `Backend-Design.md` >
`DEVELOPMENT-PLAN.md` > code — a downstream doc never leads an upstream one; on conflict, amend
upstream first, then sync down with a dated marker.
**Role:** the sole design home of the live system's backend AND its three faces.
**Posture:** IN-PLACE EVOLUTION — charter organs land on the existing `alpha/*` packages;
physical splits only where an organ hard-requires one (user decision 2026-07-10). Every gap is
named once (G1–G14, §4) with its closing arc (A1–A12, executed by `DEVELOPMENT-PLAN.md`) or its
deferred home (G13 track-tail note, G14 deferred ledger).

## §1 Process topology

Three uvicorn services, spine-separated — they never import one another; `alpha_web` reaches the
other two over HTTP (`ALPHA_SONIA_URL`, `ALPHA_WORKBENCH_URL`):

| Service | Port | Face |
|---|---|---|
| `python -m alpha_web` | :8100 | read-only "Regime Instrument" console + teach cockpit shell |
| `python -m sonia` | :8810 | **Sonia** the teacher — prose chat → explicit crystallization → gated apply; proposals/conflicts/snapshots adjudication |
| `python -m workbench` | :8820 | **Kairos** the worker — tiered computer-use arena over a project workspace; stage-only edits |

One shared live brain (`./state/brain/brain.json`) mutated by both faces through
`LiveBrainStore`: cross-process `fcntl.flock` with bounded retry that raises on timeout
(`alpha/meta/store.py:69-91`) plus a per-process mutation lock; every landing snapshots the
pre-apply brain into `history/`. After any restore, both faces sweep BOTH derived stores (Sonia
sessions + workbench staged edits) inside the flock — the cross-face reconcile sweep
(`alpha/meta/reconcile.py:14-39`, `sonia/app.py:47-77`, `workbench/app.py:175-205`).

The trading day-cycle is driven by CLI producers, not the services:
`scripts/capture_window.py` (freeze a PIT market window, corp actions included) →
`scripts/save_decisions.py --brain` (screen → regime → agent → guard → sizing → ranked
`DecisionPackage` into `DecisionStore`; the human confirms or ignores — no order path exists) →
`scripts/run_verdict.py --json` (4-arm HCH-vs-Hexpert verdict into `VerdictStore`) → overnight
`scripts/refine_live.py` / `scripts/evolve_from_episodes.py` (default propose-mode: fork →
`EvolutionProposal` → the user adopts or discards in Sonia). The console renders all artifacts
read-only. No scheduler exists; every arrow is a human-invoked script (A1 activation ledger; P9
is the scheduled loop).

## §2 The organ map

Each subsection: **Charter requires** (cited by section name) / **This repo has** (file:line) /
**Gap** (G-number, defined once in §4) / **Landing in place** (the A-arc, on `alpha/*`).

### 2.1 Model

**Charter requires.** *Second Founding Principle*: the Model is one of seven components,
"Swappable; all training decisions are v4-gated". *v4 design: Model Layer*: "collect traces,
build no pipeline". Model-id on traces and swap re-pricing come from *Harness = Kernel + Body*
fixed point 1 and *Resources as Security* ("the attribution tuple already carries model-id, so a
model swap re-prices correctly"), not the v4 section.

**This repo has.** One seam: `make_client(role)` at `alpha/llm/config.py:21-42` — roles
`agent|refiner|sonia|converse`, per-role env `ALPHA_<ROLE>_{PROVIDER,MODEL}`, temperature
default 0, providers `mock|anthropic|openai_compat`; `MockLLMClient` keeps the 969-test suite
offline. Per-client transient retry with backoff (`alpha/llm/openai_compat.py:8-12`);
enforced-JSON completes for crystallization. Known landmine: all four role defaults name
`deepseek-v4-pro`, not a valid live API id — every live run overrides per role.

**Gap.** G14 — no failover chain, no caching, no usage capture (`resp.usage` discarded); the
clients' docstrings say model/temperature are public "for the (future) cache key" —
designed-for, not built.

**Landing in place.** Deferred ledger (§4). When it lands, it lands behind `make_client` — the
data layer's `make_source()` registry (`alpha/data/registry.py:29-41`) is the built twin
showing the shape. Usage capture is pulled forward by A6 at this same seam.

### 2.2 Kernel

**Charter requires.** *Harness = Kernel + Body*: the kernel = loop + context-assembly
machinery, watchdog/kill-switch, Applier, vault proxy, trace logger, quotas, static gates,
kernel prompt stub — "kernel ≡ the operator-release-only stratum". *Immutable Kernel*: enforced
structurally, binding on both principals; governed data rows change only through designated
gates.

**This repo has.** A conventional kernel: all committed Python is the operator-release stratum —
the agent has no tool that edits repo code; the modification ladder is locked at data rungs
R1/R2 (`docs/superpowers/specs/2026-06-27-modification-ladder-and-body-axis-design.md`).
Enforcement: `ActivityPolicy.dispatch` is a single fail-closed choke point
(`alpha/arena/policy.py:18-26`); `write_mode="apply"` raises (`alpha/converse/agent.py:24-27`);
red-line doctrine has kernel-grade immutability — `ImmutableDoctrineError` on
`__setattr__`/rewrite/remove (`alpha/harness/doctrine.py:32-37,70-81`) plus adopt-time byte-equality
of the immutable core (`alpha/meta/evolution.py:72-76`). The locked carve-out: the
maximally-reshapeable agent = the Body MINUS its own gate/firewall/audit/lint.

**Gap.** G6 — the kernel is tests + code discipline, not physical: `brain.json` is an ordinary
writable file, `try_apply_op` is an importable function any in-process code can bypass;
`SandboxedEnv` is named and deferred (`alpha/arena/environment.py:4`). G10 — no context
management for long Sonia/workbench sessions (context assembly is a charter kernel duty; today
long sessions just grow).

**Landing in place.** G6 → A10: kernel `SandboxedEnv` + body-axis R3+ STAYS deferred behind the
commercial gate — immutable-TCB byte-hash pin (`tcb.lock`; defining the manifest is that spec's
one NOW deliverable, still unbuilt — manifest definition pulled forward into A1, decided
2026-07-10, backend-design round) + outer verifier + mandatory human approval; never on
`LocalEnv`. G10 → A3's precondition trio: provenance-preserving pruning (lose bytes, not
handles), content-addressed offload + a T0 recall tool, compaction with protected bookends —
all on the existing `alpha/converse` loop.

### 2.3 Body

**Charter requires.** *Second Founding Principle* + *Body Persistence & Versioning*: the Body
lives in "the **Body Store**, one git repository per Kairos instance"; apply = commit carrying
the deliberation-ID/user-edit-ref; revert = checkout + reconcile; fork = branch; body-version ≡
the commit hash; boot reconciles to tip or the session is "flagged/quarantined, not run as a
chimera"; safe mode after N dead sessions; a six-component evolvable surface.

**This repo has.** The Body = `HarnessState` H=(p doctrine, K skills, M memory) serialized as
gitignored `state/brain/brain.json` via `LiveBrainStore` (atomic tmp+rename, pre-apply
`history/` copies, flock; `alpha/meta/store.py:32-91`); `SnapshotStore` versioned snaps
(`alpha/harness/snapshot.py:11-63`, used by the in-run breaker); `EditLog` append-only,
seq-numbered, provenance-stamped (`alpha/harness/edit_log.py:39-91`); committed `seeds/` as the
frozen initial H. Of the charter's six components, three are evolvable today (doctrine≈prompt
segment, skills, memory); `PASS_TOOLS["G"]` is a reserved empty pass;
workflows/connectors/subagents are read-only console stubs.

**Gap.** G2 — nothing about the live Body is git-versioned: `history/` is a flat pile of full
copies with no ancestry, no stable body-version identifier (log length is the ordinal in use);
three divergent persistence mechanisms (history copies, SnapshotStore, proposal packets); the
`EditLog` journal lives INSIDE the artifact it journals, so restore rolls the journal back too.

**Landing in place.** A5 — Body-Store-as-git: `git init` the brain dir and commit at the ONE
existing save waist (`LiveBrainStore`), message carrying the edit seq / proposal id / user-edit
ref; audit = the commit trail; body-version ≡ commit hash falls out for free as the attribution
stamp A4 consumes. No gate changes; the three mechanisms unify onto the commit DAG
incrementally, not in one cut.

### 2.4 Memory Stores

**Charter requires.** *Memory Design → Decision for SoniaKairos*: "The store of record is
**Mem0** (decided 2026-07-09)", written `infer=False` verbatim, Kairos holding a
"retrieval-only Mem0 client with no write path"; every write is also an immutable row in the
git-committed journal ("reconcile-authoritative"); rollback = "checkout + journal-replay"; the
ungated hot-path write-waist is retired; content typed facts vs Sonia-authored procedures; the
*Convergence Principle*: "never destructively modified by an automatic process".

**This repo has.** Two memories (name collision documented in CLAUDE.md): (a) H's lessons M —
`Lesson` with phase/family tags, double-decay `Importance`, `learned_asof` PIT key, mutated only
via gated MetaTools (`alpha/harness/memory.py`, `metatools.py:76-103`); (b) `EpisodeStore` —
PIT episodic SQLite `brain.db`, frozen `Episode` rows `kind∈{trade,task}`, `for_asof` PIT-masked
recall, `INSERT OR IGNORE`, superseded-flag instead of deletion (`alpha/memory/store.py`).
Writes to (b) are DELIBERATELY ungated: `apply_credit` mutates `SkillStats` in place and writes
episodes at the credit seam (`alpha/refine/credit.py:81-114`) — CLAUDE.md pins this as the
observation channel, "do not route them through the gate".

**Gap.** G9 — a SUBSTRATE divergence from the charter's 2026-07-09 decision: no Mem0, no
journal-replay rollback (`brain.db` does not roll back with the brain at all). The observation
channel itself is NOT the retired waist (reframed 2026-07-10, backend-design round): the charter
retired the Kairos-authored memory-CONTENT hot path, and no agent tool writes these rows —
SkillStats map to the charter's enumerated kernel-written observability/ledger-row exception
(≈ per-component telemetry counters), episodes to Session/activity-evidence. Honest residuals:
SkillStats mutate counters in place where the charter's rows are append-only; episodes are
consumed by prompt recall (memory-like consumption); SkillStats carry task-outcome credit where
charter telemetry is execution-level. Conversely this repo's `learned_asof`
PIT discipline is STRONGER than anything in the charter, which has no PIT concept.

**Landing in place → RESOLVED 2026-07-13 (Option B, user-ratified "按你的推荐走"; A11 memo
`docs/superpowers/specs/2026-07-13-a11-mem0-decision-memo.md`).** The decision point was: either adopt
Mem0 + journal, or amend the charter to record permanent divergence — code never wins silently. **The
charter was amended** (its *Memory Design → Decision for SoniaKairos* now carries a dated superseding
note): **Mem0 is NOT adopted**; the store of record is the in-repo SQLite/JSON substrate
(`EpisodeStore` + H-lessons) with the A5 git Body journal + A4 hash-chained `EditLog` as
reconcile/audit authority; a Mem0 *retrieval* adapter behind the existing recall seam stays a future
option. G9 = divergence RECORDED, not a build. The PIT discipline (`learned_asof`) — stronger than
anything in the charter — is now the charter-endorsed substrate. `brain.db` non-rollback (G9 substance)
stays an open follow-up, tracked separately from the store-of-record question. The convergence
principle already holds locally (superseded flags, demote-not-delete, archive semantics — no
auto-destroy anywhere).

### 2.5 Session

**Charter requires.** *Second Founding Principle* + *Session Is Not the Context Window* +
*Trust Roots*: the Session is "an append-only event log that exists outside every other
component", written only through `emitEvent()`, events "principal-origin-stamped and
hash-chained at intake" (five origin values; user-channel split authored/couriered), full
history kept forever, stamps assigned from the physical entry path, "never inferred from
content".

**This repo has.** Four persistence surfaces, none event-sourced: Sonia `SessionStore` (flat
by-id JSON, `alpha/meta/store.py:97-135`), workbench `Project`/`ProjectTurn` +
`SqliteProjectStore` (`alpha/converse/project.py:24-42`), the in-loop transcript, and
`EpisodeStore`. No origin machinery: `ChatMessage` is `role:str` + text; tool results are
re-injected AS `role='user'` messages with a string prefix (`alpha/converse/loop.py:62-63`) —
a text convention the model itself could forge, exactly what origin stamps exist to prevent. No
hash chain anywhere. Partial: `EditProvenance` IS an origin stamp
(`alpha/harness/edit_log.py:8-23`) — but only for H mutations, stamped at the gate, not at
message capture; `brain_hash` pins proposal packets only.

**Gap.** G1 → A4.

**Landing in place.** A4 phase 1 — no big-bang event sourcing: define the origin-stamp
vocabulary (the charter's five values) and an emit seam at the two intake boundaries that exist
(`converse_project` turn capture, sonia message capture), stamping from the physical entry
path, plus the scope label riding every learned-context write — lessons, skills, episodes
(the charter's day-one rule; the recorded timing deviation lives in §2.10); hash-chain the
`EditLog` (`prev_chain_hash` + `verify_chain()`, legacy records an
unchained prefix) with an external chain-head anchor — without the anchor it is
corruption-detection only. Ordering invariant with A1: redact before hash.

### 2.6 Sandbox

**Charter requires.** *Second Founding Principle*: isolated, disposable, called as
`execute(name, input) -> string`; mounts the Body read-only; "outbound network is
**default-deny**, routed through the kernel egress proxy". *Sandbox egress*: enforcement below
the tool layer (any tool-wrapper guard is bypassable by arbitrary code); allowlist derived from
the connector registry.

**This repo has.** `ToolEnvironment` Protocol with `InProcessEnv` (deterministic refusal, the
offline default) and `LocalEnv` (`alpha/arena/environment.py:46-94`): workspace-cwd subprocess
execution, hardline blocklist, path-operand escape refusal, timeout — honestly documented as
"NOT a security boundary" (the path guard is TOCTOU-bypassable and does not parse `-c` strings).
Capability tiers T0–T4, assignments test-pinned (`tests/arena/test_builder.py:12-19`). The
compensating control is the workbench boot assert that the brain lives outside the workspace
(`workbench/app.py:54-61`), re-checked per `/converse` call.

**Gap.** G4 — no egress ladder of any kind: the `net` flag on `ToolEnvironment.run` is a
documented no-op (`environment.py:79-82`); nothing observes, let alone restricts, outbound
network from a T2 shell. (The confinement gap itself is G6/A10; this row is the
observability/policy gap that need not wait for a kernel sandbox.)

**Landing in place.** A9 — the egress ladder: M1 monitor-everything (typed `sandbox_egress`
audit records at the existing `ActivityPolicy` choke point) → M2 deny-by-default allowlist;
policy may only tighten. Kernel-level (netns) enforcement rides A10; until then M1/M2 are
honest about being advisory-plus-audit — a strict improvement over silent.

### 2.7 Vault

**Charter requires.** *Second Founding Principle*: "Secrets never enter the loop or the
sandbox"; vault + token-injection proxy; "fail-closed, no cached or degraded credential path".
*Security Boundary: Two-Class Credentials*: work tokens contained (repo-scoped, physically
unable to reach the Body remote); MCP-class credentials "never touch" literally.

**This repo has.** Pure env-var custody, fail-fast on absence: `APCA_*` at
`alpha/data/alpaca.py:157-160`, `DEEPSEEK_API_KEY` at `alpha/llm/openai_compat.py:16-21`,
`ANTHROPIC_API_KEY` at `alpha/llm/anthropic.py:15-20`; `.env.alpaca` mode 600, gitignored;
paper-trading keys only. Fixed SDK base URLs are a de facto endpoint pin.

**Gap.** G3 — no vault, no proxy, no scoping, no rotation, no redaction, AND a VERIFIED leak
path: `LocalEnv` subprocesses inherit the parent env (`alpha/arena/environment.py:87-88`) and
workspace git splats `**os.environ` (`alpha/converse/workspace.py:65-74`), so a T2 shell `env`
puts the API keys verbatim into a persisted transcript — `ProjectTurn.tool_calls` in the
workbench SQLite store. (Sonia registers no shell tool; `SessionStore` is not a destination of
this leak — it stays in A1's redaction list on its own rationale: user-pasted/relayed secrets
in chat.)

**Landing in place.** Two arcs, split by urgency. A1 (FIRST): one dependency-free recursive
`redact()` at the two persistence waists (converse sqlite store, `alpha/meta/store.SessionStore`),
key/credential-scoped only — never market/PIT data or rollback-replay payloads. A9 (long-term):
two-class credential split — brain/live keys vs workspace-visible work credentials — plus an
env strip-list at the `LocalEnv` spawn boundary (*Work-credential hardening*'s adopted
candidate).

### 2.8 Trust roots & principal origin (cross-cutting)

**Charter requires.** *Trust Roots & Principal Authentication*: Axiom H (the host is the
accepted root), Axiom O (one human, two hats, two distinct channels); a user approval records
deliberation-ID × packet content-hash, verified at landing; "Loopback binding alone is not an
authentication boundary" — Origin AND Host validated on every user-channel surface.

**This repo has.** Exactly the Axiom-O posture: one operator, all services bind 127.0.0.1.
`human_approver="user"` is minted from bare localhost POSTs with no Origin/CSRF checks — a
recorded accepted risk (conformance spec §5.5). Content-hash discipline exists for ONE path
(`adopt_proposal`, see 2.11). Stamp coherence is the FIRST gate check, refused-and-unlogged on
mismatch (`alpha/refine/apply.py:112-115`, drill-pinned).

**Gap.** Substance lives in G1 (no intake stamps outside the gate) and G12 (no audit floor);
the missing teaching-path approval-hash binding is part of G8.

**Landing in place.** A4 brings the stamp vocabulary to the two live intake boundaries.
SSRF/Origin/CSRF hardening of user-channel surfaces stays the BLOCKING precondition before any
non-localhost or multi-user serving (plan A9 sub-item; the charter's admission rule) — not
scheduled, but gating.

### 2.9 Spend & resources (cross-cutting)

**Charter requires.** *Resources as Security*: both cost adversaries are live today; quotas
"gain a **money axis**" — ceilings per session/subtree, per day, per dreaming pass, per replay
batch; the kernel meters every model call itself ("a pure-inference loop with no tool calls is
still metered"); one enforcer (the watchdog); ceiling values are user-direct records.

**This repo has.** Zero metering of money or tokens. What exists under "budget" vocabulary is
different in kind: prompt-slot budgets (`alpha/agent/retrieval.py:11-13`), trading exposure
budget (`alpha/sizing/portfolio.py:21-35`), `max_iters=8` per converse turn with a visible
fallback on exhaustion (`alpha/converse/loop.py:37-38,64-70`), retry amplification capped at 4.
All step/size bounds; none observe cost.

**Gap.** G5 → A6.

**Landing in place.** A6, in order: capture `resp.usage` at the `make_client` seam → per-run
budgets on the bounded units that already exist (a refine pass, a verdict run, a converse turn)
→ the watchdog ladder (unattended breach kills the run; foreground breach surfaces to the
operator). Ceiling values start as A1 `Settings` fields, migrating to user-direct records once
A4's vocabulary exists.

### 2.10 A2A external channel (cross-cutting) — not applicable yet

**Charter requires.** *The External Channel: A2A Counterparties*: an inbound counterparty has
"zero authority — never approves, never proposes, never writes memory"; its events are
"stamped **`a2a-party`** at the protocol intake" — but explicitly "stamped only once the
surface exists (instance-less today)".

**This repo has / why N-A.** No A2A surface is instantiated in this repo's current single-user
phase — the system serves exactly one human as a localhost decision-support co-pilot — so the
charter's instance-less clause applies to the `a2a-party` stamp; the charter's intended outward
A2A shape is deployment intent, not a contingency (reframed there 2026-07-07), and arrives with
a later phase. Two charter rules here are NOT A2A-conditional and hold at full strength: the
scope field {agent-global / per-party / per-session} rides EVERY learned-context write and every
deliberation-landed Body edit, and the kernel's **scope-mismatch check** is a GATE check — an
edit landing at a scope wider than its cited evidence's scope fails the static policy gate and
bounces to Sonia, "live from day one" (*The External Channel*; *Memory Design → scope labels
from day one*). This repo carries them as A4 (scope label on every lesson/skill/episode write)
and A8 (the gate-level mismatch refusal) — a TIMING DEVIATION from the charter's day-one rule
(recorded 2026-07-10, backend-design round): today's learning accumulates unlabeled until A4
lands, which is exactly the un-retrofittable risk the charter names. A4's stamp vocabulary also
reserves the `a2a-party` value. Revisit trigger, per the charter: when Kairos first serves any
counterparty other than the User. No G-number for the A2A surface itself — its absence is
conformance; the scope-label lag is the recorded deviation above.

### 2.11 Evolution layer (cross-cutting) — the strongest conformance area

**Charter requires.** *Evolution Layer: The Applier*: a "deterministic, non-LLM applier
service" as sole writer, "one writer, two triggers" — Sonia proposes → user approves, or the
User's direct edit — landing serially, bouncing stale packets. *Sonia: The Teacher Agent*:
"Sonia is the sole *agent* proposer"; nothing lands without a user act. *Edit Acceptance
Protocol*: "No score, no judge model, no telemetry ever ACCEPTs"; machine authority is "detect
and kill, never revert"; "No probation"; fork trial runs generate packet evidence. *Advanced
Features*: dreaming produces proposals only; Outcomes is "CLOSED (2026-07-07): not built",
"never an acceptance authority". *Component Lifecycle*: "archive, never destroy"; evidence
floors. *Operations*: "a guard without a drill is presumed broken".

**This repo has.** The write-waist: `try_apply_op` (`alpha/refine/apply.py:99-179`) — stamp
coherence first, tool whitelist, rationale required, domain-separation guards, evidence floors
(promote/retire minimums, confirmed-positive anti-Goodhart for task evidence, fail-closed on
missing stats), conflict hold, provenance stamped at the gate never by MetaTools. Every
producer converges on it: Refiner, forge, task_forge, Sonia preview+apply, sonia `POST /edit`,
workbench approve. Two hands live: teaching (`preview_op` dry-run cards → accept → apply with
`human_approver="user"`, `alpha/meta/agent.py:50-68`) and user-direct (`sonia/app.py:223-245` —
floors lifted, structure still binds). Conflicts: only self-study can be held;
teaching/user_direct-owned elements are protected; resolution records intent only, never
auto-applies (`alpha/refine/conflict.py:20-33`). Dreaming: `run_forked_evolution` — full
machine autonomy inside a fork (breaker rollbacks fork-internal; a discarded fork dies with its
session, writes no live episodes), surviving delta shipped as an `EvolutionProposal`;
`adopt_proposal` re-verifies base/prefix/delta/red-lines and re-stamps `human_approver`
(`alpha/meta/evolution.py:29-91`). Acceptance is nowhere keyed to any score — adoption/approval
is the user's act alone, exactly the charter rule. Outcomes: §3. Drills: §6.

**Gap.** G7 — the worker still PROPOSES staged edits (the 2026-07-09 arc killed self-landing
only; the charter's rule is stronger: Kairos does not propose at all) — a named deviation,
conformance spec §5.4. G8 — all four kernel-generated packet counsel fields are absent
(behavior diff + replay fidelity, non-behavior delta + scope-mismatch, reuse/dedup, coverage);
the one honest machine-counsel channel is the gate's own dry-run verdict; teaching `/apply`
re-runs accepted ops against the CURRENT brain with no staleness pin; two teach-ish surfaces
(Sonia + workbench) sit over one brain. G11 — the P-B/P-C experience/fitness coupling (task
episodes → operational-K gate branch) is built, merged, and DORMANT: nothing wires
`experience_writer`/`task_forge`/`confirmed_ids` live. G13 — drills are CI-tests only; nothing
exercises the RUNNING services on a schedule.

**Landing in place.** G7 → A7: a Sonia-side proposer over worker traces/staged intents — the
worker's propose tool then retires the way its apply mode did. G8 → A8: consolidate on the
canonical teach surface and grow packet counsel fields on the existing card/packet shapes
(staleness pin for teaching apply; the gate-level scope-mismatch refusal — fails and bounces,
per the charter's day-one rule, see §2.10's recorded timing deviation; dedup listing over the
skill library; honest "no applicable coverage" value). G11 → A2: the logged 4-step activation
checklist (operational ops through conflict_queue; operational-M scope; confirmed_ids wiring;
pinned logical asof) plus gate-side re-derivation of task evidence, shipped as a runbook with a
kill switch and the verdict-neutrality regression as the proving test. G13 →
architecture-track tail note (not an arc): a scheduled drill runner over the §6 pins, queued
behind A1's runbooks; the restore/rollback drill subset additionally wants A4/A5 landed. A12 — GEPA population search stays deferred with its recorded open
questions (instance unit, cost probe, merge coherence behind whole-H consistency).

### 2.12 Operations (cross-cutting)

**Charter requires.** *Operations: Running a Live System*: backup/restore as a consistent
tuple, restore-tested on a schedule ("an untested backup is a hypothesis"); accepting
storage-loss risk instead must be recorded — the "silent absence of the decision" is not
acceptable; version events for releases/swaps; kernel liveness watched from outside itself.

**This repo has.** Clean process separation and locking discipline (§1); env-overridable
`./state/` layout; test-side ops hygiene (`brain_session_isolation` repoints all five state env
vars, `tests/conftest.py:42-53`); visible degradation in the cross-face sweep
("skipped/failed", never silent-ok). Thin beyond that: `/healthz` returns
`{ok, brain_live, edit_count}` only; no supervision, no metrics/structured logging, no backup
policy beyond the accumulating `history/` files, no runbooks, ~32 scattered `ALPHA_*`/`APCA_*`
env reads with `./state/brain` duplicated in four files.

**Gap.** G12 → A1.

**Landing in place.** A1 (SHIPPED, landed 2026-07-11) — the hygiene + observability floor, all
on existing seams: `redact()` first (landed 2026-07-11; see 2.7); a frozen bounds-validated
`Settings` object built once per entry point and threaded down (landed 2026-07-11; offline
defaults byte-identical; kept out of `alpha/harness`); an assembled-prompt audit record (landed
2026-07-11; optional collect hook in `alpha/agent/prompt.py`, persisted beside the
`DecisionPackage`) + `scripts/render_prompt.py` — `build_system_prompt` today silently drops
skills/lessons/episodes over budget, and nothing can prove what a suppressed agent was shown; a
read-only episode inspector (landed 2026-07-11) showing the SAME numbers the taboo veto uses,
plus a `harness_digest` (landed 2026-07-11; canonical-JSON sha256 of `HarnessState`, optional
`h_digest` on the `DecisionPackage` — eval never reads it; feeds A10's joint rollback); a
`CHECKSUMS` sha256 manifest for captured PIT windows (landed 2026-07-11; verified fail-closed by
`run_verdict`/`save_decisions`/`refine_live`, warn-only by `save_evolution`/`scan_tradeable`) —
**recorded limit (D6):** the registry snapshot path `make_source("snapshot")` reachable by the
live faces is NOT checksum-verified, a live-face concern left outside A1's scope; the `tcb.lock`
content-hash manifest (landed 2026-07-11) over the modification-ladder spec §3 file set (that
spec's one NOW deliverable, unshipped by P-A; seed of A10's byte-hash pin — folded into A1,
decided 2026-07-10, backend-design round);
`docs/superpowers/runbooks/` + a Built/Live activation ledger (landed 2026-07-11; held in the
plan's A1 runbooks deliverable). The backup decision
is surfaced by A1 as an explicit record — accept the risk or schedule the tuple; either way,
recorded.

## §3 The trading vertical as the activity space

The charter is domain-agnostic; this repo instantiates its "activity sessions" as one vertical —
Kairos's task domain is the US-stock decision-support pipeline: `alpha/data` (PIT-guarded
sources; `make_source()` returns RAW by contract, `GuardedSource` + `AsOfGuard` is the caller's
job) → `universe` (daily screen) → `state` (canonical builder, `alpha/state/builder.py`) →
`regime` (`GCycle` six-phase read) → `agent` (LLM policy + PIT episode recall) → `guard` (L4
hard veto incl. episode-taboo; vetoed candidates are DROPPED, never scored) → `sizing` (L3
tiers + same-narrative netting; verdict-neutral) → `eval` (walk-forward, exogenous oracle).

The vertical carries three hard rules of its own — orthogonal to, and compatible with, the
charter (they bind the task domain, not the governance loop):

- **PIT firewall.** Corp actions key on `announce_date` (`:= process_date` for Alpaca — no true
  announce field exists), prices raw/unadjusted, windowed features trailing-only, learned
  artifacts carry `learned_asof` — pinned by name in the meta-gate
  `tests/test_us0_firewall_surfaces.py`.
- **No order tool.** No order-submission path exists anywhere; the arena's no-order rule is
  test-pinned (`tests/arena/test_builder.py:29-33`). The system's output is a ranked
  `DecisionPackage` for explicit human confirmation — the trading twin of the charter's
  "nothing lands without a user act".
- **Honest eval.** Returns gross (stated); a delisting scores −1.0, never dropped; sizing is
  verdict-neutral; decorator order `SizingPolicy(GuardedPolicy(…))` is load-bearing.

The verdict harness is this repo's answer to the charter's *Outcomes* section. The charter
closed Outcomes as not built because its open-ended-preference stance rejects benchmarks; the
trading domain admits what the charter's domain could not — an exogenous, ungameable score
(oracle thresholds "deliberately NOT from H", `alpha/eval/oracle.py:12-16`). So
`compare_harnesses` (`alpha/loop/compare.py:63-139`) is a genuine independent evaluator OF THE
EVOLUTION ITSELF: 4 arms (HCH vs frozen Hexpert vs two floors) on the same window, symmetric
guard+sizing wrap, verdict on the excess delta, paired-day `StatVerdict` CI/p/MDE. Verdict
symmetry is load-bearing: one read-only store is threaded symmetrically into all arms; into
`InnerLoop` it goes as `recall_store=` — never `episode_store=` — so HCH cannot self-write
mid-verdict, while the frozen arms take the same store via their read-only `episode_store=`
recall/taboo parameters (`alpha/loop/compare.py:86-109`). And it obeys the charter's one binding Outcomes rule: no
score ever ACCEPTs an edit; adoption stays the user's act.

The vertical's backlog is the product track (P1–P9, owned by `DEVELOPMENT-PLAN.md`). One
ordering constraint is pinned here: P1 (adversarial trap-day battery) is the guardrail ordered
BEFORE P2 (GCycle US recalibration) may loosen thresholds; P3 closes a verified hole — a
missing corp-actions artifact computes dilution/reverse-split flags as `False`,
indistinguishable from "checked, nothing announced" (fix: a tri-state surfaced into `key_risks`
as "guard ran blind" — warn-the-human, threaded symmetrically into both verdict arms).

## §4 Gap ledger

The contract with `DEVELOPMENT-PLAN.md`. Ids are stable; the plan references them and nothing
renumbers them.

| Id | Organ | Gap | Severity / urgency | Arc |
|---|---|---|---|---|
| G1 | Session | Four persistence surfaces, none event-sourced; no origin stamps, no hash chain | High value, not urgent — forgeable tool-result origin is the sharpest edge | A4 |
| G2 | Body | Body Store is `brain.json`, not a git repo — no commit-per-apply audit, no stable body-version | Medium; cheap to close at one save waist | A5 |
| G3 | Vault | Vault absent; secrets are env vars/`.env.alpaca`; VERIFIED leak: T2 shell env → persisted transcripts — redact leg closed 2026-07-11 (A1); vault/rotation/split remains open (A9) | **Urgent** (verified leak) — redaction first, split later | A1 + A9 |
| G4 | Sandbox | No egress ladder; `LocalEnv` net flag is a documented no-op | Medium; monitor rung is cheap | A9 |
| G5 | Spend | Zero metering anywhere — no tokens, no cost, no ceilings | Medium; both charter cost adversaries are live today | A6 |
| G6 | Kernel | Kernel is conventional (tests + code discipline), not physical; `SandboxedEnv` deferred | Accepted posture; stays behind the commercial gate | A10 |
| G7 | Evolution | Worker still proposes (charter: Kairos does not propose at all) — named deviation, spec §5.4 | Medium; deviation is recorded, not hidden | A7 |
| G8 | Evolution | Packet counsel absent (behavior diff, scope-mismatch, dedup, coverage); teaching apply unpinned; two teach-ish surfaces over one brain | Medium-high; the deliberation channel is the charter's heaviest-loaded component | A8 |
| G9 | Memory | **RESOLVED 2026-07-13 (Option B, user-ratified):** charter AMENDED — Mem0 not adopted; store of record = H-lessons + `EpisodeStore` (SQLite/JSON), A5 git journal + A4 EditLog as reconcile authority; Mem0 retrieval adapter a future option. `brain.db` non-rollback stays a separate open follow-up. | Divergence recorded, not a build | A11 ✅ |
| G10 | Kernel | No context management for long sessions (pruning/offload/compaction) | Precondition of the self-learning channel | A3 |
| G11 | Evolution | P-B/P-C experience/fitness coupling built but DORMANT (4-step activation checklist logged) | High leverage; built code earning nothing | A2 |
| G12 | Operations | Observability floor gaps: no prompt audit record, no episode inspector, no `harness_digest`, no CHECKSUMS, no `tcb.lock`, no runbooks/activation ledger, ~32 scattered env reads — closed 2026-07-11 (A1) | **Urgent-adjacent**; blocks diagnosing P2 | A1 |
| G13 | Evolution | Drills are CI-tests only; no scheduled live drills against running services | Low; drill runner queued behind A1's runbooks; the restore/rollback drill subset additionally wants A4/A5 | architecture-track tail note |
| G14 | Model | No failover/caching policy; usage discarded (charter v4: collect traces; failover/caching are repo-local hardening, uncited in the charter) | Low; seam exists, nothing blocks on it | deferred ledger |

Start order (user-approved): **A1 first** (small, urgent — verified secret leak), then P1+P2;
the architecture and product tracks interleave and neither blocks the other.

## §5 Honest limits & named deviations (consolidated)

Stated plainly; each is a decision or an accepted risk, not an oversight. The deviations ledger
of record is `docs/superpowers/specs/2026-07-09-charter-conformance-live-governance.md` §5 —
cited here, not restated.

- **`LocalEnv` is not a security boundary** (operator-trust posture, user-accepted): a live T2
  shell could reach the brain around the gate; the compensating control is the workbench boot
  assert. Structural fix is A10 and stays gated.
- **Unauthenticated localhost approvals** (spec §5.5): `human_approver="user"` is minted from
  bare loopback POSTs — the charter says loopback is not an authentication boundary. Accepted
  for the single-operator desk; SSRF/Origin hardening blocks any non-localhost serving.
- **Worker still proposes** (G7, spec §5.4): stage-only killed self-landing, not proposing.
  Closed by A7, recorded until then.
- **`--autonomous` escape hatch** (spec §5.3): pre-pivot in-place evolution, including live
  machine-revert by the breaker, survives behind `--autonomous` AND `ALPHA_UNSAFE_AUTONOMOUS=1`.
  A recorded non-conformance with a future decision point: remove, or keep permanently recorded.
- **Mem0 non-conformance** (G9): **RESOLVED 2026-07-13 (Option B, user-ratified) — charter amended,
  Mem0 NOT adopted; the SQLite/JSON substrate IS the store of record** (A5 git journal + A4 EditLog =
  reconcile authority; Mem0 retrieval adapter a future option). The observation channel (`apply_credit`)
  maps to the charter's kernel-written observability/ledger-row exception, NOT the retired
  memory-content waist (reframed 2026-07-10); the honest residuals are in-place counter mutation vs the
  charter's append-only rows, recall-consumption of episodes, and task-outcome credit vs execution-level
  telemetry. A11 was the decision point; it is now decided (`brain.db` non-rollback stays a separate
  open follow-up, below).
- **Adopted forks don't retro-write episodes** (spec §5.2 accepted cost): propose-mode threads
  `episode_store=None`, so an ADOPTED packet's run leaves no episodes either; episodic evidence
  accrues only from future live decisions. Revisit only on real evidence starvation.
- **Teaching apply has no staleness pin** (part of G8): Sonia `/apply` re-runs accepted ops
  against the current brain; what was previewed can land differently than shown.
- **Reconcile sweep is length-only** (`alpha/meta/reconcile.py:7-10`): an abandoned-branch
  restore can keep derived records from the other timeline — display/provenance confusion only;
  brain content is hash-protected at adopt.
- **`brain.db` does not roll back with the brain** (G9 substance): nothing calls
  `mark_superseded` on restore — defensible for an observation channel, unaddressed against the
  charter's journal-replay ideal.
- **M3 delisting tradeoff** (DEVELOPMENT-PLAN §4 deferred ledger, accepted): a same-day
  `worthless_removal` is skipped by
  the strict `ex_date > entry_day` check. Carried so it is never silently rediscovered.

## §6 How conformance stays pinned

Enforcement is tests, never prose (locked doc policy). The governance pins all run offline on
every `python -m pytest -q`:

- **Arena no-order** — `tests/arena/test_builder.py:29-33`: no tool name containing "order" at
  any tier; plus the fail-closed dispatch pin.
- **Stage-only raises** — `tests/converse/test_registry_provenance.py`: `write_mode="apply"` is
  retired and raises (`alpha/converse/agent.py:25-27`).
- **Stamp coherence** — `tests/refine/test_user_direct_stamp.py`: wrong-proposer or missing
  `human_approver` on `user_direct` is refused AND unlogged; first-in-order at the gate.
- **Red-line immutability + unlogged rejection** — `tests/harness/test_doctrine_crud.py`,
  `tests/harness/test_metatools_rejection.py`, `tests/sonia/test_direct_edit.py` (red-lines bind
  the user's hand too), `tests/meta/test_evolution.py` (a tampered fork packet is refused at
  adopt).
- **US-0 firewall meta-gate** — `tests/test_us0_firewall_surfaces.py`: a meta-test asserting the
  four named PIT-guard test FUNCTIONS still exist — deleting a guard is itself a failure.

The us0 meta-gate is the pattern worth generalizing: a **us0-style existence meta-gate over the
governance pins themselves** (arena no-order, stage-only, stamp coherence, red-line set), so
deleting a governance drill fails the suite the way deleting a firewall guard does. Its ancestor
is the charter's standing coupling rule: "a guard without a drill is presumed broken". Queued
(named 2026-07-10, backend-design round; not yet an arc) — the backlog home is
`DEVELOPMENT-PLAN.md` §2 track tail, beside the scheduled-drills note.
