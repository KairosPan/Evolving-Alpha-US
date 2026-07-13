# A8 — Canonical teach surface + deliberation-packet counsel (design)

Status: drafted 2026-07-13. Closes **G8**. Additive, offline byte-identical by default. Authority
chain: charter (*Evolution Deliberation Channel & Preference Charter*; *The External Channel*;
*Memory Design → scope labels from day one*) > Backend-Design.md G8 > DEVELOPMENT-PLAN §2 A8 >
this spec > code.

A8 has three parts, each closing one leg of the G8 gap-ledger row ("Packet counsel absent
(behavior diff, scope-mismatch, dedup, coverage); teaching apply unpinned; two teach-ish surfaces
over one brain"):

- **(a)** one **canonical teach surface** with a single write-scope authority;
- **(b)** the charter's **deliberation-packet counsel** fields on `EvolutionProposal` (behavior
  diff, dedup, evidence coverage, per-refinement cost) — kernel-generated, never proposer-authored
  — **plus the gate-level scope-mismatch refusal**;
- **(c)** a **staleness pin** for teaching `/apply`.

A8 consumes A4's scope labels (part c of A4) and A6's per-refinement cost (deferred to A8 by A6).

---

## (a) Canonical teach surface — one write-scope authority

**The gap.** Two teach-ish surfaces write H through the one gate but each hard-codes its own write
scope at its own call site — and each face has BOTH a preview site and a real-landing site:

- **Sonia teach** — `alpha/meta/agent.py::preview_op` (preview) + `MetaAgent.apply` (real landing) —
  `allowed=ALL_TOOLS`, `EditProvenance(path="teaching", proposer="sonia")`.
- **Workbench worker** — `alpha/converse/tools.py::make_propose_edit_tool` (preview) +
  `workbench/app.py::approve_edit` (**real landing** — saves the approved staged edit to the live
  brain) — `allowed=PASS_TOOLS["M"]` (memory-only), `EditProvenance(path="teaching",
  proposer="kairos", human_approver="user")`.

The scopes legitimately differ (Sonia the teacher may touch all of H; the worker is memory-only by
least-privilege), but the *authority for what a teach edit may do* is scattered across call sites —
"two teach-ish surfaces over one brain" (G8). All FOUR sites (both previews + both real landings)
now route through the authority; the grep-pin test covers all four so a preview can never resolve a
wider scope than its own write site.

**The consolidation.** One new leaf module, `alpha/meta/teach_surface.py`, is the **single source
of truth** for a teach edit's (write scope × provenance stamp). Both faces derive their scope from
it; no call site hard-codes `allowed=` or re-spells the teaching provenance. "Unified write scope"
means **unified authority, one place** — NOT collapsing the two faces to an identical tool set
(widening the worker to `ALL_TOOLS` violates least-privilege and is not byte-identical; narrowing
Sonia to memory-only breaks teach-a-skill). The role-scoping is preserved; its *definition* is
consolidated.

```python
# alpha/meta/teach_surface.py
TEACH_FACES = ("sonia", "kairos")

def teach_scope(face: str) -> frozenset[str]:
    """The tools a teaching edit from `face` may touch — the one authority.
    'sonia' (the teacher) = ALL_TOOLS; 'kairos' (the worker) = PASS_TOOLS['M'] (memory-only)."""

def teach_provenance(face: str, *, human_approver: str | None = None) -> EditProvenance:
    """The canonical teaching stamp: path='teaching', proposer=face, human_approver forwarded."""
```

- `teach_scope("sonia") == ALL_TOOLS` and `teach_scope("kairos") == PASS_TOOLS["M"]` — **byte-for-
  byte the values in force today**, so nothing behaves differently.
- `preview_op` / `MetaAgent.apply` call `teach_scope("sonia")` + `teach_provenance("sonia", ...)`.
- `make_propose_edit_tool` calls `teach_scope("kairos")` + `teach_provenance("kairos")`.
- When A7 retires the worker's propose path, the change is one line here — not a hunt across faces.

**MOOT sibling — verified, not re-added.** The teach-crystallize v5 deferral listed "`conflict_queue`
threading into the teach path". That is **moot**: `alpha/refine/conflict.py::is_conflict` returns
`False` immediately unless `provenance.path == "self_study"` (charter-conformance D2). A teaching-path
op (`path="teaching"`) can never trip `is_conflict`, so threading a `conflict_queue` into the teach
path is a dead branch. A8 does **not** re-add it. (Confirmed against `conflict.py` at b37655e.)

**Not in this part.** Retiring the worker's proposing path is **A7** (charter: Kairos does not
propose at all). A8 consolidates the *definition*; A7 removes the worker leg. A8 does not change
which faces exist, only where their scope is decided.

---

## (b) Deliberation-packet counsel + the scope-mismatch gate

### The four counsel fields (kernel-generated, never proposer-authored)

`EvolutionProposal` (`alpha/meta/proposal_store.py`, **TCB**) gains four additive fields, all
default-empty so a legacy/pre-A8 packet deserializes and adopts byte-identically:

```python
behavior_diff: list[dict] = Field(default_factory=list)   # structural before/after, per delta record
dedup: list[dict] = Field(default_factory=list)           # similarity vs pending proposals + landed edits
coverage: dict = Field(default_factory=dict)              # evidence coverage of the window
cost: dict | None = None                                  # A6 spend summary (None when unmetered)
```

They are populated by `run_forked_evolution` (`alpha/meta/evolution.py`, **TCB**) — **kernel code**,
computed from the surviving `delta` (plus the live log and the queue for dedup, plus a threaded
`cost=` for A6). Concretely:

- **`_behavior_diff(delta)`** → one row per delta record `{seq, tool, target_kind, target_id, op,
  summary}`. The reviewable *structural* before/after of the change. **Honest limit (stated in
  code):** this is the H-element structural diff, **not** a full session-replay behavior diff — the
  replayed-session fork trial-run infra (charter *Trial-run execution semantics*) is deferred with
  A10. What lands now is the non-forgeable kernel description of *what changed in H*.
- **`_dedup(delta, live_log, pending)`** → for each delta target `(target_kind, target_id)`, the
  landed records in the live log and the pending proposals touching the same target — the charter's
  kernel-generated reuse/dedup listing, never the proposer's self-report.
- **`_coverage(delta, window)`** → `{window, n_delta, has_coverage}`, with `has_coverage=False` when
  the window is empty — the charter's honest "no applicable recorded coverage" value.
- **`cost`** — threaded in from the caller as `run_forked_evolution(..., cost=meter.summary())`;
  `cost=None` (no meter) → byte-identical. Closes A6's carry-forward (per-refinement cost on the
  packet OBJECT).

### The kernel-generated-not-proposer-authored invariant (charter, load-bearing)

The charter: the non-behavior delta / behavior diff / dedup are "generated by kernel code from the
diff itself … never authored by the proposer: a self-reported danger declaration would quietly
invert 'declared, not inferred' into self-report." Two legs prove it:

1. **By construction.** The `Runner` type is `Callable[[HarnessState, EditLog], tuple[HarnessState,
   EditLog]]` — it returns **only** the final handles. There is no field a runner can set that flows
   into a counsel field; `run_forked_evolution` computes every counsel field itself from the delta.
   The proposer has no channel to the counsel.
2. **At adopt.** `adopt_proposal` re-derives `_behavior_diff(proposal.records)` and **refuses** a
   packet whose stored `behavior_diff` disagrees — a hand-forged packet (constructed off the builder,
   dropped into the queue) is caught at the waist, mirroring the existing `records ==
   log_dict[base_len:]` refusal. **Legacy-tolerant:** the check fires only when `behavior_diff` is
   non-empty, so a pre-A8 packet (`behavior_diff=[]`) adopts unchanged. `dedup`/`coverage`/`cost`
   depend on build-time external state (queue, live log, meter) not reproducible at adopt, so they
   are advisory-at-render only; `behavior_diff` — the pure function of the records — is the
   re-derivable, forgery-checked leg.

### The gate-level scope-mismatch refusal (charter: "live from day one")

A NEW static-policy refusal in `try_apply_op` (`alpha/refine/apply.py`, **TCB**). Charter (*The
External Channel*): "any edit landing at a scope wider than its cited evidence's scope fails the
static policy gate and bounces to Sonia … never authored by the proposer, vacuous under a single
User, un-retrofittable if skipped, and invisible on a behavior diff." It is a **GATE REFUSAL**
(returns `(None, reason)`), not advisory counsel. Carrying it in A8 rather than day-one is a
**TIMING DEVIATION** from the charter (recorded 2026-07-10, backend-design round; it consumes A4's
scope labels, which landed 2026-07-13).

**Scope ordering** (added to `alpha/trace.py`, next to the `Scope` vocab, non-TCB):
`per-session (0) < per-party (1) < agent-global (2)`; `is_scope_wider(a, b)` iff `rank(a) > rank(b)`.

**The check (byte-identical until scope labels are present):**

```
landed = op.args.get("scope")                 # the scope this edit would land at; None = undeclared
if landed is not None and provenance.path != "user_direct":
    evidence = <narrowest scope in the cited evidence, or "per-session" if unknown>
    if is_scope_wider(landed, evidence):
        return None, "scope-mismatch: landed '<landed>' wider than evidence '<evidence>' (bounces to Sonia)"
```

- **Fires only when the op explicitly declares a landed scope** (`op.args["scope"]`). No existing op
  or test sets it (grep-confirmed at b37655e), so the gate is a no-op on today's corpus →
  **byte-identical**. This is the ADDITIVE/fail-closed shape the arc requires: "an op with no scope
  info / legacy defaults to a safe pass so it's byte-identical until scope labels are present."
- **`user_direct` is exempt** — the user's own hand carries agent-global authority and "forgoes the
  packet's kernel-generated counsel (behavior diff, scope-mismatch, dedup, coverage)" (charter
  *Applier* §, 2026-07-08). A directive *extraction* landing agent-global is `path="teaching"`, not
  `user_direct`, and IS subject (charter *Instruction extraction gate*).
- **The bounce.** Returning `(None, reason)` is the repo's "bounce to Sonia": for a teaching edit
  the reason surfaces on the failed preview card; for a self-study edit it means the edit does not
  survive the fork. No new queue — the refusal reason IS the bounce.

### The evidence-scope-default decision — **FLAGGED FOR USER RATIFICATION**

> **This is a governance-behavior choice the user must ratify.** A4 shipped the *stored* scope label
> defaulting to `agent-global` (the widest) and explicitly deferred to A8 "whether the evidence leg
> should default narrowest (per-session)". **The scope-mismatch gate has teeth ONLY if the EVIDENCE
> scope defaults NARROW.** If the gate read evidence as `agent-global` (widest), then "landed wider
> than evidence" is never true — nothing is wider than agent-global — and the gate is **VACUOUS**
> (the charter's "vacuous under a single User", made permanent).
>
> **A8's decision (recommended, charter-aligned, conservative):** the **effective evidence scope the
> GATE uses** is the **narrowest scope actually observed in the cited evidence**, or **`per-session`
> (narrowest) when unknown**. The **stored default label stays `agent-global`** (A4, for backward-
> compat and because today's corpus is Kairos's agent-global craft). The gate *derives* the evidence
> scope conservatively; it does not read the stored label. So an edit that *declares* it lands wide
> off narrow/unknown evidence bounces, which is exactly the discipline the charter wants the moment
> per-party/per-session learning appears.

**Honest vacuity note (stated in code + here).** Because the gate fires only on an op that
*explicitly declares* `op.args["scope"]`, and no producer stamps a landed scope yet, the gate is
**dormant in practice today** — byte-identical, and "vacuous under a single User" exactly as the
charter says. It becomes load-bearing the moment a producer stamps a landed scope on an op (the
multi-party / per-session-learning future). A8 builds and tests the *mechanism* and fixes the
*conservative default* that gives it teeth; it does not (and cannot, honestly) make single-user
agent-global-by-default writes bounce, because those declare no landed scope. This mirrors A4's
posture: the labels ride; the gate that consumes them activates when the labels are declared on ops.

**Where the evidence scope is read.** From `provenance.evidence_ref`: a list `evidence_scopes`
(narrowest taken) or a single `evidence_scope`; absent → `per-session`. This keeps the charter's
"evidence scope is computed from the cited events, not the proposer's word" — the cited-evidence
scopes ride in the provenance the kernel stamped, and the *default when absent* is the conservative
narrowest.

---

## (c) Staleness pin for teaching `/apply`

**The gap (Backend-Design G8, §5).** Sonia `/apply` re-runs accepted ops against the **current**
brain, loaded fresh at apply time. If the brain moved between preview and apply (another teach
landed, a rollback, a fork adopt), what lands can differ from what the preview showed. No pin.

**The pin.** `Message.previewed_hash: str = ""` (`alpha/meta/models.py`, non-TCB, additive):

- At `/propose`, when ops produce cards, capture `previewed_hash = brain_content_hash(h, log)` —
  the content hash of the brain the preview was dry-run against (`brain_hash` over
  `h.to_dict()` + a chain-agnostic `log.to_dict()`, matching the evolution staleness pin so a
  persist-time chain finalize can't spuriously invalidate it).
- At `/apply`, recompute the current brain's content hash under the lock; if
  `msg.previewed_hash` is set and differs, **refuse with 409** ("stale: brain changed since preview;
  re-preview") and do **not** apply. Byte-identical when `previewed_hash == ""` (legacy messages, or
  cards built outside `/propose`) → the check is skipped.

The first-ever apply (seeds not yet materialized) is safe: both propose and apply hash the same seed
content (materialize saves identical content; the hash is chain-agnostic), so the pin matches.

---

## TCB accounting

Three TCB files touched, all minimal-additive, `tcb.lock` regenerated
(`python scripts/gen_tcb_lock.py`); zero change to existing enforcement/immutability. The TCB
**file set is unchanged** (no additions — additions are human-only); only three existing members'
content hashes move.

- **`alpha/refine/apply.py`** — the scope-mismatch static gate: two module-level helpers
  (`_landed_scope`, `_evidence_scope`) + a ~4-line check block inside `try_apply_op`, guarded by
  "landed scope declared AND not user_direct". Byte-identical when no op declares `scope`. Imports
  `is_scope_wider` from the non-TCB `alpha/trace.py`. No existing gate/branch is reordered or
  weakened.
- **`alpha/meta/proposal_store.py`** — four additive fields on `EvolutionProposal`, all
  default-empty. No behavior change; `brain_hash` untouched.
- **`alpha/meta/evolution.py`** — `run_forked_evolution` computes the four counsel fields
  (`_behavior_diff`/`_dedup`/`_coverage` helpers + a `cost=` kwarg) and passes them to `queue.new`;
  `adopt_proposal` gains the legacy-tolerant behavior-diff re-derivation refusal. The existing
  staleness/prefix/red-line checks are untouched.

Non-TCB touched: `alpha/trace.py` (scope ordering helpers, next to `Scope`), `alpha/meta/agent.py`
+ `alpha/converse/tools.py` + `workbench/app.py::approve_edit` (all route through `teach_surface` —
both faces' previews AND both real-landing sites), `alpha/meta/models.py` (`Message.previewed_hash`),
`sonia/app.py` (capture + check the pin), `alpha/meta/teach_surface.py` (NEW leaf).

---

## Test plan (TDD)

- `tests/meta/test_teach_surface.py` — one write-scope authority: `teach_scope("sonia") ==
  ALL_TOOLS`, `teach_scope("kairos") == PASS_TOOLS["M"]`; both faces route through it (grep-pin that
  `agent.py`/`converse/tools.py` no longer hard-code `allowed=ALL_TOOLS`/`PASS_TOOLS["M"]` at the
  teach sites); `teach_provenance` stamps `path="teaching"`, `proposer=face`. Regression: teaching a
  skill through Sonia still lands (ALL_TOOLS preserved); the worker still stages memory-only.
- `tests/meta/test_packet_counsel.py` — every packet from `run_forked_evolution` renders the four
  counsel fields; `behavior_diff` has one row per delta record derived from the records; `dedup`
  lists a landed/pending collision; `coverage.has_coverage` is False on an empty window; `cost`
  rides when a summary is threaded and is `None` otherwise. **Forgery:** a packet whose stored
  `behavior_diff` is hand-forged (≠ its records) is refused by `adopt_proposal`; an honestly-built
  packet (or a legacy `behavior_diff=[]` packet) adopts. **Byte-identity:** a packet built with no
  cost/counsel kwargs deserializes and adopts exactly as pre-A8.
- `tests/refine/test_scope_gate.py` — a wider-than-evidence edit BOUNCES (declares
  `scope="agent-global"` off `evidence_scopes=["per-session"]` → refused); a within-scope edit
  PASSES (`scope="per-session"` off per-session evidence); **unknown evidence defaults narrow**
  (declares agent-global, no evidence_ref → bounces, proving the ratified default); `user_direct` is
  exempt (declares agent-global, lands); **byte-identical** when the op declares no scope (a
  create/patch with no `scope` arg lands exactly as today).
- `tests/sonia/test_apply_staleness.py` — `/propose` sets `previewed_hash`; `/apply` with an
  unchanged brain applies (hash matches); `/apply` after the brain moved between preview and apply
  returns 409 and does not mutate; a message with `previewed_hash==""` applies (legacy, byte-
  identical).

All offline, keyless (`MockLLMClient`/`FakeSource`), no new deps. `tests/sonia` autouses
`brain_session_isolation`. Full suite + `ruff`/lint + `python scripts/gen_tcb_lock.py --check` stay
green.

## Deliberately not done / needs user judgment

- **The evidence-scope-default is flagged for user ratification** (above) — it is a governance-
  behavior choice; A8 implements the recommended conservative default and documents the honest
  vacuity note.
- **Full session-replay behavior diff** — deferred with the trial-run replay infra (A10). A8's
  `behavior_diff` is the structural H-element diff.
- **Retiring the worker's proposing path** — A7 (charter: Kairos does not propose). A8 consolidates
  the scope authority; A7 removes the worker leg.
- **Re-deriving dedup/coverage/cost at adopt** — not done (they depend on non-reproducible build-time
  state); only `behavior_diff` is forgery-checked at adopt.
- **Deriving evidence scope from the cited durable evidence's OWN scope labels** (fully non-proposer-
  authored) — the gate reads `provenance.evidence_ref['evidence_scopes']`, a kernel-stamped
  convention; a proposer that *claims* wide evidence could bypass. The conservative default
  (`per-session` when the scopes are absent) makes *omission* fail-closed today, and the gate is
  vacuous under a single User (charter). Deriving the scope from the cited episodes' A4 scope labels
  (the way A2 re-derives `confirmed_ids` from durable records rather than the proposer's word) is the
  multi-party hardening, deferred with the tenant machinery (charter *The External Channel* deferral).
- **Sonia-side render of the counsel fields on `/proposals`** — the console surfacing is a thin
  alpha_web follow-up (§3 small pool); A8 lands the packet fields the console will read.
