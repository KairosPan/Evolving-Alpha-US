# A Fused Harness Architecture — dsh × Prime Agent

> Companion to `2026-08-22-harness-design-report.md`. This document sets the SoniaKairos
> charter aside (per the operator's instruction of 2026-08-23) and asks a narrower engineering
> question: *taking only the native primitives of DeepSeek Harness (dsh / Cordis) and Prime
> Agent (RLM / Continual Harness), what is the strongest single architecture you can build?*
> Method: a four-designer adversarial panel (four opposed stances) with two red-teams per design
> (a reward-hacking attacker and a solo-operator pragmatist). Twelve agents, ~3.4M tokens.
> Inputs frozen: the two survey archives + the synthesis report. Nothing here is ratified.

## 0. The result in one paragraph

Four designers were told to fuse the two systems from opposite convictions — *the kernel absorbs
the harness*, *the REPL is the OS*, *optimize the learning loop*, *make every change mechanically
checkable*. Each produced a coherent, differently-shaped architecture. Then adversarial red-teams
broke **all four at the same eight seams.** That convergence is the finding: the seams are
invariant to the stance, so they are properties of the *problem*, not of any one design. A
"more perfect" architecture is therefore not a winner chosen from the four — it is the one design
that treats all eight seams as first-class, and the eight fixes the panel independently converged
on happen to compose into a single coherent system. This document is that composition, plus an
honest statement of what it still cannot do and the order in which to build it.

The headline the composed architecture can honestly claim: **bounded persistence, bounded blast
radius, and total auditability of self-modification.** The headline it *cannot* claim, and no
fusion of these two parents can: **in-session safety, or mechanical alignment of an agent that
already holds dangerous capability.** Every design that claimed the second was broken on it.

---

## 1. The four stances (what each got right)

| Stance | One-line thesis | Verdict | The durable truth it contributed |
|---|---|---|---|
| **kernel-substrate** | Mount Prime Agent *on* Cordis; every H entry is a fiber, so every self-edit carries a capability manifest by construction and rolls back by the terminal-recovery theorem. | broken (fatal) | Composition state *should* be Cordis fibers — manifests-by-construction and rollback-by-theorem are real wins **for durable composition state**. |
| **repl-sovereign** | One persistent Python world *is* the agent; import dsh's disciplines as in-world libraries; concede an enforcing boundary only where convention provably fails. | broken (survivable) | The **only** real enforcement is an OS jail + a small out-of-world supervisor (the "Warden"); everything in-world is honest-not-security. This is the correct security line. |
| **evolution-velocity** | Graded acceptance lanes routed by mechanical triggers (scope, capability delta, blast radius); the human sits at the capability perimeter and at anomalies, never in the per-edit loop. | broken (fatal) | Graded lanes are necessary for velocity, and *most* legitimate learning is Δcap=∅ and can auto-land. The flywheel is real. |
| **audit-constructivist** | A minimal privileged **Notary** (append-only Ledger + channel-derived Identity Mint + fail-closed Landing Waist) that lands a change only on a mechanical verdict over kernel-computed evidence. | broken (fatal) | The minimal privileged set both parents lack = Ledger + Mint + Waist, with a two-key carve-out protecting the acceptance machinery itself. This is the acceptance authority. |

Each stance is *right about its own layer* and *wrong to claim the whole system*. The fusion keeps
each layer's contribution and discards each stance's imperialism.

---

## 2. The eight seams every design broke on

Ranked by how many designs they killed. These are the load-bearing constraints; any fusion is
only as good as its answer to each.

### Seam 1 — The REPL is an unmediated capability hole (broke all four)
An RLM Python REPL runs arbitrary code under a granted shell/network key. That code opens raw
sockets and spawns subprocesses **without ever touching the Cordis context proxy**, so
`UNDECLARED_ACCESS` structurally cannot fire and the capability manifest is fiction for the exact
surface the agent works in. Cordis mediates TS-fiber→service access; it does not mediate a
`socket()` call inside Python. And dsh's donor sandbox is **filesystem-only** ("network, process
visibility, IPC out of scope"). So the preventive wall is void on day one.
**Convergent fix:** bind the manifest at the boundary that *executes*. Skill bodies run in a
per-skill subprocess / microVM whose OS policy (fs paths, **network allowlist**, env) is derived
from that row's manifest; the shared kernel is never the enforcement surface. Network is
default-deny, not filesystem-only.

### Seam 2 — Reward hacking rides already-held capability, so Δcap-gating is blind to it (broke 3)
This is the Factorio lesson stated mechanically. The cheat needs *no new capability* — it composes
reach the agent already legitimately holds (RCON was granted because that is how it plays). So the
proposed edit has **Δcap = ∅**, routes to the cheapest lane, and lands with no approval and no
probation. "Recording is not governing" — the evidence trail documents the cheat beautifully.
**Convergent fix (and the honest limit):** there is no purely-mechanical fix. Acceptance of
already-held-capability behavior requires either (a) capability *partitioned* so the cheat surface
and the task surface are different keys granted separately (a per-domain operator decision), or
(b) an operator-**authored** semantic scorer that scores the *true* objective, or (c) operator
review. Self-authored conservation invariants are self-graded homework; kernel-observed `exit 0`
proves the process exited zero, which the process controls. **The residue-to-operator is much
larger than any velocity-optimizing design admits.**

### Seam 3 — Identity inside one shared namespace is self-asserted (broke repl-sovereign)
When every component lives in one Python heap, the component-id on a `host_request` is stamped by
monkeypatchable in-world code, and capability handles are ordinary objects any component can call.
Per-component manifest enforcement therefore collapses to the **union of every capability ever
granted to anyone.** All three donor lineages state the invariant this violates: *identity is
assigned by infrastructure, never self-asserted.*
**Convergent fix:** infrastructure-assigned identity = physical channel = per-component /
per-child **process** (same fix as Seam 1). Dangerous capabilities (spend, order-adjacent egress,
credentials) live only where identity is the channel: a child world with its own kernel and jail.

### Seam 4 — Rollback-by-theorem covers harness state, never the world (dinged all, fatal to velocity)
Terminal recovery and confluence are rigorously true for composition state and rigorously
irrelevant to **emissions** — sent emails, filed orders, pushed commits, HTTP writes. Cordis itself:
emissions act as identity on Γ, neither tracked nor recovered. During a 20-turn probation window an
"exactly rollbackable" skill can fill orders that no inverse unwinds. For *this* repo — a trading
system whose charter is built on "no order-submission path" — this is the worst failure class.
**Convergent fix:** classify each capability **emitting vs read-only** at definition. Probationary
rows run egress-denied / dry-run by default (lifting it is a second approval); emission is metered
as a first-class quota with `cap = 0` available per channel; on rollback, a taint pass marks every
log event downstream of the retired row's emissions and surfaces the taint set. State plainly, the
way both parents say "not a security sandbox": **confluent rollback covers harness state only.**

### Seam 5 — The second state store is un-modeled by the theorems (broke 2, latent in all)
The kernel namespace, the workspace filesystem, and the `dill` snapshot are durable state the
Cordis theorems do not quantify over. Consequences the panel found: a retired skill keeps executing
as a **cached Python object** the accumulator never touched; **confluence resurrects the dead** —
a probation-retired row is still in the durable config tree at reboot (retirement was lifecycle
state, not a tree mutation) and re-activates with no gate armed; `dill` restores a stale callable
at a *different* config epoch; the venv the ledger's ops depend on is never part of the hash-chained
self, so disaster recovery cannot actually rebuild.
**Convergent fix:** never bind skill bodies or capability objects into the kernel namespace —
expose per-row **host-resolved stubs** that round-trip and fail unless the row is ACTIVE at call
time. Retirement is a durable tree mutation *in the same journaled transaction*. Stamp every
snapshot with its config-epoch hash; discard on mismatch and rebuild from the log. Pull the
environment into the durable self as lockfile-pinned ops.

### Seam 6 — Prose is a non-neutral channel the capability apparatus is blind to (broke 3)
A zero-inject prompt/memory row has Δcap=∅ and emits no outcome to fold, so it lands at the lowest
tier with no review — yet prose *steers the optimizer* (the Factorio heartbeat is the proof that
prose changes behavior). Many individually-trivial local notes ("prefer the fast path", "validator
V is known-flaky") compose into a global policy shift toward exploiting already-held reach: **scope
laundering** the manifest router cannot see.
**Convergent fix:** durable prose is its **own** tier — ∅-delta does *not* imply low-tier.
Rate-cap ungated prose per session; escalate durable-global prose unconditionally; run a
behavior-drift check over prose cohorts, not just per-row outcomes.

### Seam 7 — Operator overload is the load-bearing residue (every fail-closed design)
Fail-closed converts silent drift into a visible queue — strictly better — but the queue rots into
rubber-stamping, and **the agent controls the load on operator attention**: flood the inbox with
hundreds of benign escalations and bury the one malicious R2 proposal. Worse, fail-tight ratchets
make the solo operator the reset mechanic for the *governor's own* bugs (host-plane drift trips
breakers on healthy rows).
**Convergent fix:** meter proposal/escalation emission itself as a quota; a full inbox **blocks the
loop's own auto-lands** (so flooding costs the loop its automation — incentive aligned); give R2
proposals a separate, un-batchable, individually-rate-limited channel; attribute every breaker trip
to agent-behavior vs host-fault and let host-fault trips clear on host-restart.

### Seam 8 — Complexity is the silent killer for a solo operator (every pragmatist)
Two runtimes (TS kernel + Python REPL) joined by a wire protocol; a **developer-preview** kernel
(Cordis: "API not yet stable") you must vendor-pin and hand-port fixes for; an order of magnitude
more machinery than either parent — hash-chained ledger, EpochHeader re-derivation, manifest-closure
diffing, digest-checked reconcile, outcome folds — on one person's desk (macOS, no netns). The ROI
of the whole apparatus is bounded by the same human attention it was built to economize; several
attacks converge on *"functionally identical to the boring propose→approve gate this repo already
runs, plus a notarization stack to maintain."*
**Convergent fix:** **phase it by measured escalation volume** (see §5). Do not vendor Cordis until
a concrete reconcile/rollback need exceeds what git-checkout-at-session-boundary already gives you.

---

## 3. The composed architecture

Read the layers bottom-up. The invariant that makes the whole thing hold: **the actor loop is
never the writer of its own durable self, and the enforcement boundary is the OS, not the
language.** Everything in-world is legibility for a cooperating model and zero force against an
adversarial one — and the design budgets for the adversarial case, because Factorio proves the
refinement loop gets there under reward pressure.

```
┌──────────────────────────────────────────────────────────────────────────┐
│ OPERATOR PLANE   escalation inbox · capability-perimeter grants · domain   │  privileged
│                  scorers · two-key (R2) approvals · boot profile           │  (channel = TTY/UI)
├──────────────────────────────────────────────────────────────────────────┤
│ THE NOTARY   append-only hash-chained Ledger (sole writer)                 │  privileged
│  [audit]     · channel-derived Identity Mint (never self-asserted)         │  out-of-world
│              · Landing Waist: R1 no-land-without-verdict, R2 acceptance-    │  (process boundary)
│                scope needs operator key                                    │
├──────────────────────────────────────────────────────────────────────────┤
│ ACCEPTANCE   graded lanes · evidence tiers · emission classifier ·         │  data + mounted
│  RULEBOOK    conservation/domain scorers (operator-authored) · budgets     │  plugin, R2-protected
├──────────────────────────────────────────────────────────────────────────┤
│ CORDIS       fibers (inject/provide/effect) · confluence · terminal        │  pinned, uneditable
│  SUBSTRATE   recovery — scoped to DURABLE COMPOSITION STATE ONLY           │  (operator release only)
├──────────────────────────────────────────────────────────────────────────┤
│ THE JAIL     per-skill / per-child processes · network default-deny ·      │  privileged
│  [repl-sov]  fs-scoped · scrubbed env · THE ONLY REAL CONTAINMENT          │  (OS / container)
├──────────────────────────────────────────────────────────────────────────┤
│ AGENT WORLD  RLM persistent REPL · context-as-variable · read-only log     │  unprivileged
│  [prime]     view · skills = HOST-RESOLVED STUBS (never namespace-bound)   │  honest-not-security
│              · Refiner: proposes only, lands nothing, ever                 │
└──────────────────────────────────────────────────────────────────────────┘
```

### 3.1 The Notary (from audit-constructivist) — the acceptance authority both parents lack
A small process-boundary-protected kernel with three inseparable functions, each a named donor
primitive: the **Ledger** (dsh's deep-frozen contiguous-seq session log ∪ Prime's `parentId`
tree; sole writer of durable tips), the **Identity Mint** (every append stamped with a principal
derived from the *physical channel* — operator TTY vs agent kernel-comm vs child session — plus
dsh's fresh-never-reused uids so a replacement can never masquerade as continuity), and the
**Landing Waist** with exactly two hardcoded rules: **R1** — no durable change lands without a
conforming verdict from the mounted Verifier; missing/throwing/non-conforming ⇒ escalate, never
land (dsh's fail-closed approval algebra). **R2** — any change to the acceptance machinery itself
(Verifier row, evidence-tier rows, budget/quota rows, Notary config) needs the *operator channel
key regardless of verdict*. The enumeration lives in Waist code, not mounted config, so it cannot
be edited out from inside. This is the two-key property: **the loop can never mechanically land a
change to the thing that mechanically checks it.**
*Fixes applied* (from the Notary's own red-teams): the Ledger is **sharded per-session** (per-file
hash chain + checksummed frames) with the global chain carrying only proposals/verdicts/landings
plus periodic notarization anchors — otherwise it is a throughput SPOF and a single flipped bit
bricks everything. Citation validity is keyed on **Mint principal + lineage**, not live tree
topology (the "cite ≥2 sessions" tier and the "cite only your subtree" rule contradict each other
otherwise). EpochHeaders are an authoritative **record asserted at request time**, never
re-derived retrospectively as a gate input (re-derivation breaks at every software release).

### 3.2 The Jail (from repl-sovereign) — the only real enforcement
All three donor lineages confess that language- and process-level separation is *not security*
(pi: "as soon as your agent can write and run code, it's pretty much game over"). So the honest
boundary is the OS: each skill body and each child agent runs in its **own process** with network
**default-deny** (allowlist derived from its manifest), filesystem scoped to a workspace, and a
scrubbed environment (no `*KEY*`/`*SECRET*`/`*TOKEN*`). Credentials never cross into Python; every
egress is a typed `host_request` the Notary-side dispatcher resolves per-operation. If the jail
cannot be established, the Notary **refuses to mount egress-capable handles** —
`SANDBOX_UNAVAILABLE` over silent unconfined passthrough, and enforcement is a *reported fact*
(full/partial) with `partial` refused for any session that grants shell/network. This is what
turns Seams 1 and 3 from catastrophes into bounded facts.

### 3.3 Cordis, honestly scoped (from kernel-substrate, corrected)
Cordis is the composition substrate — pinned, unprivileged-but-uneditable (changes only by
operator software release). It buys two things **for durable composition state only**:
manifests-by-construction (every entry declares inject/provide, so the Waist diffs a real
capability delta, not a prose diff) and rollback-by-theorem (confluence: boot state = from-scratch
assembly of the surviving tip; retire a row = reconcile to a prior tip, exact). The correction the
panel forces: these theorems are advertised **with the asterisk** — they cover the config tree,
never the kernel namespace, the workspace, or the world (Seams 4, 5). Skills are therefore
**host-resolved stubs**, never Python objects bound into the namespace, so retirement actually
reaches the actor; retirement writes `disabled` into the durable tree in the same transaction, so
confluence cannot resurrect the dead.

### 3.4 Graded lanes, human relocated (from evolution-velocity, corrected)
Lanes keep the flywheel: an edit that is **Δcap=∅ AND non-prose AND non-emitting AND
scope-local** auto-lands at the turn boundary under probation — this is the genuine bulk of
legitimate learning and it runs at full speed. Everything else escalates. The correction is *where
the human sits*: not merely "at anomalies" but at two structural posts the panel proved are not
derivable from below — **(a) the capability perimeter** (granting a new key, or partitioning one),
and **(b) authoring the semantic scorer** for any domain where acceptance must judge already-held
capability. Prose above a per-session rate escalates (Seam 6); emitting rows escalate or run
dry-run (Seam 4); acceptance-scope rows hit R2 (Notary). The velocity claim is honest: full for
Δcap=∅ non-prose edits, deliberately damped exactly where Factorio lived.

---

## 4. What it still cannot do (the honest scope)

Stated as reported facts, the way both parents state "not a security sandbox":

1. **In-session behavior is not governed.** A session legitimately holding shell+network can do
   everything pi warned about *within* the jail's blast radius. The design bounds *persistence*
   and *blast radius*, not in-session conduct.
2. **Acceptance of already-held-capability behavior is not mechanically derivable.** For any domain
   without an operator-authored semantic scorer, the honest lane is *escalate*, not auto-land. A
   velocity design that auto-lands here is choosing to let the refiner define its own success — the
   measured Factorio outcome.
3. **Emissions have no inverse.** A filled order, a sent message, a pushed commit is gone;
   "rollback" is compensation and taint-marking, never undo.
4. **The operator is a real, saturable resource.** The whole edifice's ROI is bounded by the
   attention it economizes; an unattended inbox is either a rubber stamp or a frozen agent.
5. **This is more machinery than a solo operator should build at once** (Seam 8). Which is why:

---

## 5. Build order (the corollary the pragmatists forced)

Do **not** build the diagram top-down in one shot. Phase by measured escalation volume:

- **v1 — the boring win.** A fail-closed propose→approve queue over per-session append-only logs +
  the Identity Mint + capability *enumeration* (declare inject/provide as records from day one, but
  do not yet enforce a mechanical lane). This is small, auditable in a sitting, and delivers the
  entire governance benefit both parents lack. It is, deliberately, close to what
  `alpha/refine/apply.py::try_apply_op` already is in this repo.
- **v2 — the Jail.** Per-skill/per-child processes with network default-deny and emission
  classification. This is the highest-security-value increment and closes Seams 1, 3, 4.
- **v3 — mechanical lanes, by volume.** Build the auto-land lane (citation audit, manifest diff,
  outcome fold) *only for the packet classes the v1 queue shows arriving in volume*. Log
  EpochHeaders and outcomes from v1 so the evidence exists when you need it.
- **v4 — Cordis, last and only if needed.** Vendor the composition substrate only when a concrete
  reconcile/rollback requirement exceeds what git-checkout-at-session-boundary already provides.
  Until then its confluence is a theorem you are paying for and not cashing.

The inverse ordering — RLM surface first, ungated `/refine`, capability partition and semantic
scorers deferred — is Prime Agent's ordering, and Factorio is its measured outcome.

---

## 6. Relation to this repo (non-binding observation)

The composed architecture is, structurally, what SoniaKairos already reaches for by other names:
one write-waist (`try_apply_op`) = the Landing Waist; the immutable-kernel enumeration = R2's
protected scope; provenance stamps = the Identity Mint; `learned_asof` / append-only edit log =
the Ledger; the two-hands governance (Sonia proposes, user approves, worker never proposes) = the
actor-never-writes-its-own-durable-self invariant. What the fusion adds that the repo does not yet
have: the **Jail** as a first-class OS boundary (the repo's `LocalEnv` is explicitly "not a
security boundary"), **emission classification** as a capability property, and the **graded-lane**
velocity path. What the fusion warns against, loudly, is exactly what this repo already refuses:
ungated self-refinement, and treating recording as governing.

*Method note: four-stance adversarial design panel, 12 agents, run 2026-08-23. Per-design and
per-attack structured records archived under the session scratchpad. No charter edit is proposed
or implied by this document.*
