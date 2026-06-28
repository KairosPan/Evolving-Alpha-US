> **Status:** DRAFT — pending user review (2026-06-27). Companion to `2026-06-27-activity-space-arena-design.md` (the inner-loop activity space) and `2026-06-25-evolving-alpha-hermes-rebase-architecture-design.md` (the parent). This spec answers: **given the two evolution loops, how is the sandbox positioned, and how far can the receiving agent be reshaped without breaking the one-write-waist moat?** Grounded in a 10-agent adversarial design panel (4 candidate "maximal-modifiability" architectures, all verdicted *broken* at the same seam; the recommendation below is the synthesis of what survived).
>
> **Confirmed decisions (2026-06-27, via brainstorming + adversarial panel):**
> - **Fork 1 — scope (USER-CONFIRMED):** build **NOW = Local phase, data rungs R1/R2 only**; the code-level rungs (R3+) are **designed-for but DEFERRED** behind the commercial kernel-sandbox + immutable-TCB + outer-verifier + human-approval pipeline. This is a conscious, *gated* lift of parent §1.2 ("evolution is file/prompt/config-level only"), not drift.
> - **Fork 2 — how authored code reaches `H`:** hybrid — convention now (data-only, no agent-authored code runs in-process), **isolated writer-sidecar required before ANY R3+**.
> - **Fork 3 — image↔`H` coupling:** orthogonal axes, joined into an atomic `(H-version, body-digest)` change-set **only for rollback**.
> - **Fork 4 — operational second fitness:** human/verifier as judge (default), optional task-episode sample floor; LLM-judge rejected. Operational autonomy is explicitly **semi-autonomous** (human-confirm).
> - **Fork 5 — trading-vs-operational classification:** per-element `domain` tag (target); **interim hard rule:** until it is pinned in code, no task-evidenced op may touch ANY gated surface.

# Modification Ladder & the Body Axis (Design)

## 1. Goal, and where the sandbox sits

The system has **two evolution loops** around the receiving agent (the Hermes-runtime B-WIDE face):
- **Loop ① — self-modification.** The agent's brain `H=(p,G,K,M)` is edited (taught by the user + Sonia, or proposed by self-study). Governed by the **gate** (`try_apply_op`) and an **immutable TCB**, *not* by the sandbox.
- **Loop ② — activity space.** The agent acts in a general computer-use world. Governed by the **sandbox** (`ToolEnvironment` + the membrane), per the activity-space spec.

**The sandbox belongs to Loop ②.** Its job in two-loop terms is to be the **membrane** that guarantees Loop ② can reach Loop ① (the brain) **only through the gate** — never by a direct file write. A common mistake to avoid: "put the agent in a sandbox so the teacher can modify it safely." Modification safety is the **gate's** job; the sandbox secures **action**. Different loops, different mechanisms.

```
  Loop ① self-modification  (the GATE guards this, not the sandbox)
  ┌─────────────────── TCB (OUTSIDE the sandbox · immutable · dev/git-only) ───────┐
 user +│  gate try_apply_op → MetaTools → SnapshotStore → EditLog                   │
 Sonia │  + breaker + red-lines + firewall(AsOfGuard) + recall PIT-mask + choke pt  │
   │   └──────▲──────────────────────────────────────────────┬──────────────────────┘
   │ RefineOp │ (Loop②'s ONLY channel to mutate H = emit a RefineOp through this gate)│ read-only H
   ▼ (gated)  │                                                                       ▼
  ┌───────────┴──────────────────────────────────────────────────────────────────────┐
  │  SANDBOX = Loop ② activity space (the receiving agent / Hermes runtime runs here)  │
  │   shell · code · files(workspace) · net(allowlist) · trading tools / MCP            │
  │   H volume: READ-ONLY mount   ·   outward: membrane B (allowlist + human-confirm)   │
  │   live orders: NO capability                                                         │
  └────────────────────────────────────────────────────────────────────────────────────┘
```

**The cross-phase invariant:** *Loop ② → Loop ① only through the gate; the gate / TCB are never inside the sandbox's writable or reshapeable surface.*

**The load-bearing truth about "maximal reshapeability."** The adversarial panel proved that every naive "let the agent reshape its own code/runtime/image" architecture collapses the moat at the same seam: the instant the *gate / firewall / audit / red-line* code becomes reshapeable, one promotion can author a permissive successor (a self-amending gate; trusting-trust). Therefore the maximum safely-reshapeable surface is **the whole body MINUS its own gate/firewall/audit/lint**. That immutable carve-out — the TCB (§3) — *is* the moat. You can reshape everything except the cage that makes reshaping safe, forever.

## 2. Two axes, one gate each

- **Brain axis (BUILT, unchanged).** `try_apply_op → MetaTools → SnapshotStore checkpoint → one EditRecord on the append-only EditLog` is the **sole** writer of `H`. Not touched by this design.
- **Body axis (DEFERRED — commercial).** A single writer `try_promote_body` whose only verb is *"rebuild the live image from a human-approved, declared diff and atomically repoint."* It physically cannot touch `h.skills/h.memory/h.doctrine` (§5).
- **Between them: the immutable TCB (§3).**

The two axes are **orthogonal** (Fork 3): a fast cheap brain edit (the Refiner runs daily) must not force a slow image rebuild. They are joined into one atomic change-set **only for rollback** (§7).

## 3. The immutable TCB manifest (the load-bearing addition)

The TCB is the set of files that **enforce an invariant**. It is **dev/git-only, permanently excluded from the reshapeable set at every tier**, and (in the body phase) **byte-hash-pinned** — `try_promote_body` refuses to promote any image whose TCB bytes diverge from the dev/git baseline.

Initial manifest (any file enforcing an invariant MUST be listed; the list is itself a red-line, and additions are highest-approval, human-only):

| File | Enforces |
|---|---|
| `alpha/refine/apply.py` | the gate (`try_apply_op`) — one-write-waist |
| `alpha/refine/ops.py` | `PASS_TOOLS` whitelist / `RefineOp` vocabulary |
| `alpha/refine/conflict.py` | two-loop conflict → `held_for_review` |
| `alpha/harness/metatools.py` | the only edit facade; rationale floor |
| `alpha/harness/edit_log.py` | append-only audit + provenance stamping |
| `alpha/harness/snapshot.py` | atomic checkpoint (the version authority) |
| `alpha/harness/manager.py` | rollback + handle rebinding |
| `alpha/harness/doctrine.py` | red-line immutability (`__setattr__`) |
| `alpha/loop/floor_breaker.py` | capability-floor breaker (rollback-then-FREEZE) |
| `alpha/data/firewall.py` | PIT firewall (`AsOfGuard`/`GuardedSource`) |
| recall PIT-mask (`alpha/memory/recall.py` / `agent/retrieval.py` causal mask) | no future leakage in recall |
| `alpha/arena/policy.py` | the single dispatch choke point + tier enforcement |
| red-line lint · `try_promote_body` · the verifier harness (NEW, body phase) | the body-axis gate + its checks |

**Defining the manifest is a NOW deliverable** (cheap, clarifies what is off-limits) even though byte-hash-pin *enforcement* only runs at body promotion (deferred).

## 4. The modification ladder R1–R6

| Rung | What | Gated path | Rollback | Scope |
|---|---|---|---|---|
| **R1** brain-knowledge (p non-red-line doctrine + M Lessons) | the knowledge the agent reasons from | `RefineOp(rewrite_doctrine / *_memory) → try_apply_op` → one EditRecord, provenance at the gate | Lessons inside `harness.to_dict()`; atomic SnapshotStore checkpoint; breaker rollback-then-FREEZE (autonomous) | **NOW** |
| **R2** skill-config (K value objects, NO code) | author/revise/retire/promote skills as config | `RefineOp(*_skill) → try_apply_op` with evidence floors; optional in-process walk-forward fork *precondition* (no Docker, no new write path) | as R1 | **NOW** |
| **R3** skill-code (Python implementing a skill) | proposed implementation code as a declared git patch | propose → kernel-isolated fork from live image → apply declared patch only → fitness via TCB-pinned firewall (network-denied) + offline suite + red-line lint + no-bypass test → **human approval** → `try_promote_body` rebuilds from declared diff → BodyRecord. Code runs in sandbox with **no H handle**; reaches `H` only via RefineOp over IPC | joint `(H-version, body-digest)` change-set | deferred |
| **R4** tool-code (non-TCB tool impls) | reshape registered-tool implementations (TCB tools permanently excluded) | as R3; the no-bypass test runs against the rebuilt manifest | joint change-set | deferred |
| **R5** runtime (prompt templates, loop/agent/session glue; **TCB excluded**) | reshape non-TCB runtime code | as R3 + template-anchor lint (doctrine slot, PIT-asof binding, human-confirm banner) + TCB byte-hash pin; code edits have no `(kind,id)` → **all self-study runtime edits `held_for_review` unconditionally** | joint change-set | deferred |
| **R6** image/OS/packages/env (the "body" as a versioned unit) | base OS, pip/apt lockfile, MCP servers, network allowlist | propose env-delta (Dockerfile + pinned lockfile) → reproducible build (identical digest, else store full bytes) → suite + red-line lint + **every new data ingress proven `GuardedSource(AsOfGuard)`-wrapped** → human approval → `try_promote_body` repoints; running container = read-only rootfs, no self-commit, no pip-install | `BodyManager.rollback_to(digest)` paired with H via change-set | deferred |

**NOW = R1/R2 only.** R3+ requires the kernel sandbox + TCB + outer verifier — none built today — so they are designed-for and deferred. The pressure to enable a code rung on the (TOCTOU-bypassable) LocalEnv before the kernel sandbox exists **must be refused** (§11).

## 5. Body-axis machinery (DEFERRED — commercial)

- **`try_promote_body`** — the single body writer; verb = rebuild-from-declared-diff + atomic repoint. Never repoint to the fork's built digest (closes undeclared-drift).
- **BodyLog** — append-only, keyed by image digest; cross-linked read-only to the EditLog by `body_image_digest` for `/evolution` lineage. Lives on storage unwritable from inside the sandbox.
- **BodyManager** — the trusted **outer supervisor**, running OUTSIDE the candidate container, owning verification + rollback (so a broken promoted image can still be reverted; defeats trusting-trust).
- **Writer sidecar (Fork 2)** — the `H` volume is **read-only** to the general runtime and read-write **only** to an isolated process exposing nothing but the `try_apply_op` IPC surface. "No second write path" is enforced by **process isolation**, not by an (undecidable) AST scan.

## 6. Fork-verify rules (DEFERRED)

Every code/runtime/image proposal: **propose → kernel-isolated fork from the live image → apply the DECLARED diff only → verify → human-approve → rebuild-from-declared-diff → BodyRecord.** Non-negotiable verify rules and why:
- **TCB-pinned firewall, network-denied fork.** The fork's trading fitness must run through a firewall the candidate *cannot modify*, with egress denied — otherwise a PIT-weakening change is judged by the weakened firewall and scored as *alpha* (the panel's sharpest finding: fitness rewards leakage).
- **Rebuild from the declared diff**, never promote the fork's built image (closes undeclared shell drift).
- **Outer verifier** (BodyManager), never the candidate verifying itself (trusting-trust).
- Fitness only proves *machine-checkable* regressions; a subtly worse prompt/strategy can pass — the body-breaker is the only backstop and it is slow + Goodhart-exposed. The gate proves who/what, not soundness.

## 7. Joint change-set rollback + breaker across axes (DEFERRED)

- Brain rollback unchanged (atomic SnapshotStore; Lessons inside `to_dict()`; autonomous capability-floor breaker).
- Body rollback = content-addressed digest repoint.
- A degradation trip rolls back the **joint `(H-version, body-digest)` change-set** to a co-verified pair (or FREEZEs) — never leaving a never-co-verified brain-on-new-body hybrid.
- A **generation counter fail-closes** any stale cached `MetaTools`/`harness`/`log` handle after rollback (closes the `manager.py` cached-handle hazard in a long-lived containerized runtime).
- Cross-axis commit must be genuinely atomic (a journal / two-phase commit across SnapshotStore + BodyLog) with explicit roll-forward/back to a consistent pair (§11).

## 8. The NOW phase (what actually gets built now)

This is the activity-space spec's **P-A** plus the modification-ladder framing:
1. `alpha/arena/` per the activity-space spec: `ToolEnvironment` seam + `InProcessEnv`/`LocalEnv`; the single dispatch **choke point** (`policy.py`, in the TCB); capability tiers.
2. **Data rungs only (R1/R2).** The tool catalog exposes **no "execute arbitrary code holding an `H` handle"** capability — the agent emits RefineOps and runs workspace-scoped shell, nothing that can `import` the harness.
3. **Brain files (`SnapshotStore` root + `brain.db`) live OUTSIDE the LocalEnv workspace cwd and are path-guarded out**, so even a T2 shell cannot `open(snap.json,'w')`. This is the NOW-phase stand-in for the writer sidecar — *weaker* (path-guard is TOCTOU-bypassable, Snyk) and only valid under the **single-trusted-operator** posture; documented as provisional, not a kernel boundary.
4. **Close the two existing build gaps** (both recon- and panel-confirmed, currently making the live-face invariants inert): wire `conflict_queue` + real provenance on the converse brain-edit path; enforce `StagedEdit.status` (T4 human-confirm).
5. **Define the TCB manifest** (§3) as a red-line doc now.

## 9. Phased rollout

- **NOW (Local):** §8 — R1/R2 on LocalEnv, choke point, brain-files-outside-workspace, close the 2 build gaps, TCB manifest defined. Fully offline-testable (`pytest -q` never needs Docker).
- **DEFERRED (commercial kernel phase) = activity-space P-D + the body axis:** `SandboxedEnv` (Docker/Seatbelt/bwrap) + writer sidecar + outer supervisor (BodyManager) + `try_promote_body`/BodyLog + fork-verify + joint change-set rollback, then unlock **R3 → R4 → R5 → R6 in order**. TCB byte-hash-pin enforcement turns on here.
- Relationship to the activity-space spec's P-B/P-C (experience capture + general-task fitness): those decide *which* modifications get proposed (and feed K/G); this spec governs *how* any modification is applied safely. The Fork-5 classification (below) gates P-C touching any gated surface.

## 10. Cross-spec updates required (apply on approval)

- **Activity-space spec** (`2026-06-27-activity-space-arena-design.md`): §3 add writer-sidecar / read-only-H-mount / TCB-pinned-firewall to `SandboxedEnv`; §4 fold R1–R6 into the tier table + the "data rungs only in the no-kernel phase" rule + "hold all self-study code edits unconditionally"; §5 pin the trading-vs-operational classification (closes its open Q#4) as the precondition for any task signal touching gated surfaces.
- **Parent hermes-rebase spec** (`2026-06-25-…-design.md`): §1.2 add the **scope-lift gate clause** (code-level evolution permitted ONLY behind kernel-sandbox + TCB + outer-verifier + human-approval, never autonomous); §5.1 add the **immutable-TCB carve-out** as a named non-negotiable.
- `docs/PROJECT_STATE.md`: record the decision. `ROADMAP.md`: add the deferred R3–R6 rungs + the kernel-sandbox milestone.

## 11. Risks

1. **The TCB manifest IS the moat now.** If it omits one enforcement file, a body promotion can weaken an un-pinned guard. Enumerate exhaustively; review as a red-line; TCB additions are highest-approval, human-only.
2. **R3+ is unsafe in the no-kernel phase** and pulls the deferred `SandboxedEnv` onto the critical path. If the kernel sandbox slips, the code rungs cannot ship — and the pressure to enable them anyway on the TOCTOU-bypassable LocalEnv must be refused.
3. **Reproducible Docker builds are hard** (network base layers, mirrors, timestamps, unpinned transitive deps). If rebuild-from-declared-diff does not yield an identical digest, lineage/rollback identity breaks — mitigation (store full image bytes, roll back by digest-pull) costs storage.
4. **Operational autonomy is only semi-autonomous:** code/image promotion needs human approval and the body-breaker rides a weak, non-deterministic, human-rated task-fitness series — a degrading body is not auto-rolled-back the way a degrading brain is. Document loudly.
5. **Cross-axis atomic commit** must be real (journal / two-phase) or a crash mid-commit tears the audit and desyncs the axes.
6. **Fork fitness only proves machine-checkable regressions;** a subtly worse prompt/strategy passes. The gate proves who/what, not soundness.
7. **Two build gaps to close before relying on the live-face invariants** (not inherit): converse passes no `conflict_queue` + hardcodes `provenance(path='teaching', proposer='hermes')` (self-study/teaching conflict detection is inert on the live face); `StagedEdit.status` is defined but never enforced.
8. **Trading-vs-operational classification is undefined in code.** Until pinned (Fork 5 target = per-element `domain` tag), the §1.3/§5 separation invariant is unenforceable and **no task signal may touch any gated surface** — an easy-to-forget interim hard rule.
9. **`docker exec` / interactive shell / `docker commit` on the live container are a standing gate bypass** the moment the runtime is containerized with operator access; forbidding them is runbook+config discipline, not a guarantee. Registry / `:live` retag credentials become a brain-integrity-equivalent secret with no analog in the git-only world.
