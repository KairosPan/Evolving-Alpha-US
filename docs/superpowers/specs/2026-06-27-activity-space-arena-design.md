> **Status:** DRAFT — pending user review (2026-06-27). Designs the **inner-loop activity space** (the "arena") for the receiving agent (the Hermes-runtime B-WIDE face). This is the concrete realization of the parent Hermes-rebase spec's §7 (sandbox & safety) "Open" items, scoped up from "which tool tiers" to the full perception→action→feedback arena. Companion to `2026-06-25-evolving-alpha-hermes-rebase-architecture-design.md`.
>
> **Confirmed decisions (2026-06-27, via brainstorming):**
> - **Receiving agent** = the Hermes-replaced agent runtime (`alpha/converse/`, the B-WIDE conversational face). **Two evolution loops:** the **outer** loop (self-modification of `H`, taught by user + Sonia) is **already built**; this design builds the **inner** loop (the activity space where the agent acts and generates experience). Maps onto the project's root `H=(p,G,K,M)` two-loop Continual Harness.
> - **External world scope = general computer-use** (sandboxed shell / code / files / network + trading tools/MCP + the human + market data). The broadest option.
> - **Experience coupling = broad** (trading outcomes **+** general task/tool/skill experience).
> - **Sandbox mechanism = `LocalEnv` first** (host subprocess, no kernel isolation) behind a `ToolEnvironment` seam; the heavier kernel sandbox (Codex-style two-axis) is **deferred to the commercial route**.
> - **Structure strength = lightweight `ActivitySpace` contract** (not a gym-style `Arena` object).
> - **Package = new `alpha/arena/`**; **`Episode` gains `kind ∈ {trade, task}`** (extend, not a new type); **membrane as drawn** (§4).

# Receiving Agent — Activity Space / Inner-Loop Arena (Design)

## 1. Context & goal

### 1.1 The two loops

The system is a two-loop Continual Harness `H=(p,G,K,M)`. We name the loops:

- **Outer loop — self-modification (BUILT).** The agent's brain `H` is edited along the two learning paths (self-study Refiner + teaching Sonia), through the one gated write-waist (`alpha/refine/apply.py::try_apply_op`), with provenance, conflict→user adjudication, and the capability-floor breaker. The user and the teacher agent (Sonia) supervise this loop. This is done.
- **Inner loop — the activity space (THIS DESIGN).** The agent *acts in a world*: it perceives, calls tools, does work, and gets feedback. This is where the experience the outer loop learns from is **produced**. Today this loop is thin: the conversational runtime exposes exactly two tools (`decide`, `propose_memory_edit`), a bounded loop (`max_iters=8`), a git workspace that only stores decision artifacts, and **no capability tiers, no sandbox, no conflict-hold wired, no breaker on the live path, and no defined feedback/experience return.**

In short: *how to learn* exists; *the place to do things and generate learnable experience* does not. This design builds that place.

### 1.2 What the activity space is

The receiving agent acts in a **general computer-use world**: a sandboxed computer (shell, code execution, files, network) plus the trading-domain toolset/MCP, the human, and the (PIT-guarded) market data sources. It acts **safely and autonomously** — autonomous and free *inside* a disposable sandbox, controlled only when it *crosses a membrane* (edits the brain, touches the outside world, or would place an order).

### 1.3 Broad experience, one hard separation

The inner loop feeds the outer loop **two kinds** of signal:
1. **Trading quality** — the existing walk-forward excess advantage (gross). Governs *decision* quality.
2. **General operating capability** — did the task complete, was a tool/skill useful, did the human approve, what new skills were written. Governs *how well the agent does things*.

**Load-bearing separation invariant (the moat protection):** the general-operating signal governs **only** operational/tooling `H` — `K` (skills/tools), `G` (sub-agents), and operational doctrine. **Trading-relevant `H` (trading doctrine, the keep/retire of trading skills) is judged *only* by the walk-forward fitness, forever.** The two signals feed different parts of `H` and never cross. This extends the existing "eval is verdict-neutral to sizing" invariant: eval is also verdict-neutral to the general-operating signal.

### 1.4 Explicitly out of scope (now)

- **Kernel-level sandbox** (Seatbelt/bwrap/Docker/microVM). Deferred behind the `ToolEnvironment` seam to the commercial route (§3, §8 P-D).
- **LLM-judge / self-reflection fitness** for general tasks. Deferred like the GEPA Forge (§5).
- **Live order placement.** Never exposed at any phase (hard wall, §4).
- **Model/weight-level evolution.** Out of scope for the whole project.

---

## 2. Architecture — the `ActivitySpace` contract

Structure strength is deliberately light: **not** a gym-style `Arena` object that rewrites the loop, but an explicit **contract** that names the four faces of the activity space. The offline walk-forward world and the live conversational world are two implementations of the *same* contract.

```
┌──────────────────────────── external world ─────────────────────────────┐
│  ┌─────────────────────────────────────────────────────────────────────┐ │
│  │  sandbox interior  (free · autonomous · disposable)                  │ │
│  │   files · shell · code-exec · compute · PIT-guarded market reads      │ │
│  │   + trading tools (decide / capture / verdict / save) + MCP           │ │
│  │   ← the receiving agent (Hermes runtime) works here; mistakes thrown  │ │
│  └─────────────────────────────────────────────────────────────────────┘ │
│   ▲ membrane A — edit brain H → ONLY as a proposer via try_apply_op(gate)  │
│   ▲ membrane B — outside effects (net write/send/external) → allowlist +   │
│   │              human-confirm; market reads still bound by PIT firewall   │
│   ⛔ hard wall — live orders: NEVER registered                              │
└───────────────────────────────────────────────────────────────────────────┘
                 │ experience (what was done + outcome)
                 ▼   … fed to the OUTER loop to evolve H (K/G only; §5)
```

The four faces (`O`/`A`/`E`/`F`):

| Face | Definition | Today | This design |
|---|---|---|---|
| **O — observation** | conversation history + SOUL/SKILL (projection of `H`) + **PIT-gated recall** + workspace state + tool results | recall lives only *inside* `decide`; the conversational prompt itself sees only identity + tool names + a doctrine one-liner | thread PIT-gated `recall(asof=)` into the conversational prompt itself |
| **A — action** | a tiered tool catalog (§4) | 2 tools, no tiers | expand the catalog + tag each tool with a `CapabilityTier`; dispatch enforces per-tier policy |
| **E — environment** | `ToolEnvironment` seam + project git workspace + per-conversation budget + PIT firewall | direct in-process; only `max_iters`; workspace stores only decisions | §3 |
| **F — feedback** | tool result / gate verdict (applied·rejected·**held**) / human confirm·deny / verifier pass·fail | none on the live path | dispatch layer returns these to the agent each turn |

---

## 3. The `ToolEnvironment` seam (sandbox mechanism)

Computer-use execution goes through one seam so the isolation backend is swappable:

```
ToolEnvironment (Protocol):  run(cmd|code, *, cwd, timeout, net) -> ExecResult
  ├─ InProcessEnv   # offline tests: no external process, deterministic
  ├─ LocalEnv       # [BUILD NOW] host subprocess; workspace-scoped (path guard) +
  │                 #   Hermes-style hardline command blocklist + network deny-by-default
  │                 #   (an allowlist permits autonomous reads; everything else denied)
  └─ SandboxedEnv   # [DEFERRED · commercial] Seatbelt(mac)/bwrap(linux)/Docker/microVM
                    #   + kernel-enforced network allowlist
```

**Policy model (copied from Codex's two axes):** `sandbox_mode × approval_policy`. In the Local phase the *sandbox axis* is fixed to "host", so safety rests on the *approval axis* + tool-level policy (§4) — an honest **provisional, operator-trust posture** (≈ Hermes `Local` + Codex's logical policy *without* the kernel enforcement). The seam exists precisely so flipping on `SandboxedEnv` later is additive, not a rewrite.

**Borrowings:** the interface shape (pluggable backend) is from Hermes's `BaseEnvironment`; the principled two-axis policy and "network off by default / approve on boundary-cross" defaults are from Codex; the **hardline command blocklist** (`rm -rf /`, `mkfs`, fork-bomb, reboot, raw block-device writes) is ported from Hermes `tools/approval.py` as defense-in-depth for the `LocalEnv` shell tool.

**Offline-test guarantee (repo hard constraint):** the 704-test suite is fully offline (no network, no assumed Docker). `InProcessEnv` is the test/default backend; `LocalEnv` in tests runs only harmless commands in a temp workspace with network forced off. No test may require a real sandbox.

---

## 4. Capability tiers + the safety membrane

Each registered tool carries a `CapabilityTier`; dispatch applies per-tier policy. This *is* the definition of "safe autonomous": free inside, controlled only at membrane crossings.

| Tier | Tools | Enforcement (Local phase) |
|---|---|---|
| **T0 observe** | recall · graph-walk (`why_did_we_X`) · inspect `H` · read workspace · `decide` (analysis only) | free, autonomous |
| **T1 workspace-write** | commit artifacts · `save_decisions` · write workspace files | autonomous + logged; path-scoped to the project git workspace |
| **T2 execute** | shell · code-exec · network reads | via `ToolEnvironment` (`LocalEnv`); hardline blocklist; network reads limited to allowlist |
| **T3 brain-edit** | propose `RefineOp` | **proposer only, via `try_apply_op`**; **wire the currently-absent `conflict_queue` (→ `held_for_review`) + provenance** on the converse path |
| **T4 human-confirm / forbidden** | net write · send · external side-effects = human-confirm; **live orders = never registered** | make the currently-vacuous staged-edit approval *real* (`StagedEdit.status` is defined but never enforced today — recon-confirmed) |

**Single choke-point invariant (the activity-space twin of the one-write-waist).** *Every* tool dispatch — every tier — flows through one enforcement point (`alpha/arena/policy.py`, called from `converse/loop.py`); there is **no second dispatch path** around it. This is non-negotiable: OpenClaw's sandbox was bypassed precisely because one endpoint (`/tools/invoke`) omitted the policy layer, so a single missed call site silently voids the whole membrane. The arena must add no alternate route, and a test asserts every registered tool is only reachable through the policy.

**The three membranes:**
- **Membrane A — brain `H`.** Any self-modification crosses through the existing gate. The new computer-use tools **never** write `H` directly (preserves the "one write-waist" invariant). This membrane is *ours* — neither Codex nor Hermes has a "brain"; the sandbox confines *execution*, the gate confines *the brain*.
- **Membrane B — the outside world.** Network *reads* = allowlist-autonomous; network *writes/sends*/external side-effects = human-confirm. Market-data reads remain bound by the **PIT firewall** (no future leakage), independent of the sandbox.
- **Hard wall — live orders.** Not registered as a tool at any phase. Human-confirm remains mandatory for every `DecisionPackage`.

**Local-phase caveat (must be documented as such):** with no kernel isolation, membranes B and the hard wall rest on tool-level policy (allowlist + human-confirm + not registering dangerous tools + the blocklist), not on the OS. This is the provisional posture; `SandboxedEnv` (P-D) is what makes it kernel-enforced for untrusted/multi-user surfaces.

---

## 5. Experience return + outer-loop coupling

**Capture (observation channel, ungated).** `Episode` gains `kind ∈ {trade, task}` (extend the existing type; reuse `EpisodeStore` + FTS — no second store). A `task` episode records an activity trajectory: tools/skills used, task outcome, human approval, skills written. It is written at a new **activity-credit seam** (analogous to `apply_credit`), strictly observation-channel — it never enters `harness.to_dict()` and never participates in `H`-rollback (same rule episodes already follow). K-skills the agent *uses or writes* accrue the existing **`SkillStats`**; generic built-in tools (shell/file) are recorded in the `task` episode rather than as skills.

**The second fitness (the judge of "good" for general tasks):**
- **Default — human/teacher (exogenous).** The user or Sonia approves/rates task outcomes. Trustworthy, un-gameable, but human-in-loop.
- **Where machine-checkable — objective verifiers (endogenous).** Exit code / tests pass / artifact validates / success-criterion check.
- **Deferred — LLM-judge / self-reflection (`④`).** Powerful but gameable and breaks temp=0 reproducibility; deferred like the GEPA Forge, and when added must be seeded + logged into provenance.

**Coupling to the outer loop.** The outer-loop Refiner **K-pass** (and Sonia) promote/retire skills/tools using (a) `SkillStats` usage + (b) the human/verifier task-success judgment — *the agent evolves its own toolbox by doing*. Every such edit still flows through `try_apply_op` with a sample floor (mirroring `min_promote_samples`), so no noisy window over-promotes before the floor/breaker reacts.

**Separation invariant enforcement (§1.3 restated as a rule).** The general-operating signal may only target `K` / `G` / operational doctrine. Trading doctrine and trading-skill keep/retire are reachable **only** by the walk-forward fitness path. The gate is the natural enforcement point: a `task`-evidenced op whose target is a trading-relevant `H` element is rejected (or, like a cross-path conflict, held for the user). This keeps the trading moat un-Goodhart-able by the new signal.

---

## 6. One contract, offline and live

`decide`, the PIT firewall, the build pipeline (`build_universe` + `build_market_state`), and the gate are the *same* implementations on both paths (recon-confirmed). The offline walk-forward `InnerLoop` is the **narrow / deterministic (temp=0)** implementation of the `ActivitySpace` contract — it remains the *sole* trading fitness. The live conversational runtime is the **broad** implementation — general computer-use, human-in-loop. Writing the contract explicitly makes this duality legible and lets a future offline self-study search (GEPA, deferred) reuse the same contract.

---

## 7. Package & files

**Layer placement (CLAUDE.md §2 spine).** New top-level subpackage **`alpha/arena/`** sits *above* `converse`: it depends downward on `converse`, `refine` (the gate), `memory` (episodes), `agent` (`decide`/recall), and `harness`. Nothing in those lower layers may import `arena` — keep the dependency one-directional; do not introduce a new import cycle.

**NEW — `alpha/arena/`:**
- `contract.py` — the `ActivitySpace` contract: `Observation` / `Action` / `Feedback` value objects, the `CapabilityTier` enum, and a `ToolSpec` that pairs a tool with its tier.
- `environment.py` — `ToolEnvironment` Protocol + `InProcessEnv` + `LocalEnv` (workspace path-guard, hardline blocklist, network-off default); `SandboxedEnv` declared but deferred.
- `policy.py` — the membrane dispatch policy: tier → (autonomous | sandboxed | gated | human-confirm), incl. the two-axis `sandbox_mode × approval` model.
- `experience.py` — the activity-credit seam: writes `kind="task"` episodes + bumps `SkillStats` for used/written skills.
- `tools.py` — the new computer-use tools (shell / code / file read+write / network-read), each registered with its tier.

**EDIT (additive, at call sites):**
- `alpha/memory/episodes.py` — `Episode` gains `kind ∈ {trade, task}` (default `trade` for back-compat).
- `alpha/memory/store.py` — persist/query `kind`; existing rows read back as `trade`.
- `alpha/converse/registry.py` — `ToolRegistry` entries carry a `CapabilityTier`.
- `alpha/converse/loop.py` — dispatch through `arena.policy`; return the `Feedback` channel each turn.
- `alpha/converse/tools.py` — wire `conflict_queue` (+ provenance) on the brain-edit tool; route exec/file tools through `ToolEnvironment`.
- `alpha/converse/session.py` — enforce `StagedEdit` approval (T4) before any apply.
- `alpha/converse/agent.py` + `alpha/agent/prompt.py` + `alpha/agent/retrieval.py` — thread PIT-gated `recall(asof=)` into the conversational prompt (with a PIT regression test).
- `alpha/refine/refiner.py` — K-pass may read `task` episodes (subject to the separation invariant); `alpha/refine/credit.py` or the new seam writes the `task` episodes.

**UNCHANGED (reused):** `try_apply_op` (the gate — only newly *wired* from the converse path, not modified in contract), `SnapshotStore`, the walk-forward fitness, the capability-floor breaker, the `MemoryStore` Protocol.

---

## 8. Phased rollout

- **P-A — arena skeleton.** `ActivitySpace` contract + `ToolEnvironment`/`InProcessEnv`/`LocalEnv` + `CapabilityTier` tags + the membrane dispatch policy (**wiring the recon-found gaps: `conflict_queue`, provenance, real T4 approval**) + recall threaded into the conversational prompt. Tools: existing + file read/write (workspace-scoped) + shell/code (`LocalEnv`). Fully offline-testable. *Done when:* a multi-turn session runs tiered tools, a T3 edit is held/applied through the gate with provenance, a T4 action requires confirmation, live orders are absent, and the PIT-recall regression test passes.
- **P-B — experience capture.** `Episode.kind="task"` + `SkillStats` bumps for used/written skills. **Observation only — no fitness coupling yet.** *Done when:* task episodes persist and are recallable, byte-identical behavior with the feature off.
- **P-C — fitness coupling.** General-operating signal → outer-loop `K`/`G` (Refiner K-pass + Sonia), with the separation invariant + sample floor + gate. *Done when:* a useful skill is auto-promoted on `task` evidence through the gate, a `task`-evidenced op targeting trading `H` is rejected/held, and the walk-forward verdict numbers are unchanged.
- **P-D — heavier sandbox (DEFERRED · commercial).** `SandboxedEnv` (Seatbelt/bwrap/Docker/microVM) + kernel-enforced network allowlist + multi-user. (LLM-judge fitness deferred alongside.)

P-A strictly gates the rest; within P-A the recall PIT-mask wiring comes first.

---

## 9. Testing

- `InProcessEnv` is the default test backend; `LocalEnv` tests run harmless commands in a temp workspace with network forced off.
- A new **membrane test suite**: T3 must route through `try_apply_op` (and a conflicting `task`-evidenced trading-`H` op is held/rejected); T4 must require confirmation; live-order tools must not exist; network is dead in tests; market reads still honor the PIT firewall.
- A **no-bypass test** (enforces the single choke-point invariant, §4): enumerate every registered tool and assert each is invocable only through `arena.policy` — there is no second dispatch path that skips tier enforcement.
- Recall-into-prompt gets a dedicated **PIT-leak regression** (a lesson learned on D is invisible to a conversational turn dated D−1), covering both injection modes.
- Existing 704 tests stay green throughout; P-B/P-C are default-off and byte-identical when off.

---

## 10. Risks & open questions

1. **Local phase has no kernel boundary.** Membrane B + hard wall are tool-level only until P-D. Documented as a provisional operator-trust posture (the same posture OpenClaw and Hermes-Local openly adopt — single trusted operator, *not* an adversarial boundary); the seam keeps the upgrade additive. *Do not let any doc imply kernel-grade safety in the Local phase.* **The `LocalEnv` workspace path-guard is NOT a security boundary** — string-path validation is TOCTOU-bypassable (symlink-swap between check and use; Snyk demonstrated exactly this against OpenClaw's `assertSandboxPath`). Treat it as accident-prevention only; `SandboxedEnv` (P-D) must enforce confinement in the kernel/container (fd-based ops or `writable_roots`), never by path strings.
2. **Second-fitness Goodhart.** A general-operating metric is gameable. Mitigated by: human/verifier judge (not an autonomous metric) as default, LLM-judge deferred, the gate + sample floor, and above all the **separation invariant** keeping it away from trading `H`.
3. **Separation enforcement is at the gate.** The gate proves *who/what*, not soundness — it can route a `task`-evidenced op targeting trading `H` to rejection/hold, but cannot verify a human judgment was *correct*. It is a routing/audit aid, not a correctness guarantee.
4. **The trading-vs-operational classification of an `H` element is itself undefined and load-bearing.** The whole separation invariant (§1.3, §5) presumes the gate can tell whether a target `H` element is "trading-relevant" (walk-forward-only) or "operational" (general-signal-allowed). That rule does not exist yet. Candidate mechanisms: a per-element `domain` tag set at creation, classification by component sub-type, or by the proposer/path that authored it. **This must be pinned during P-C planning before the general signal is allowed to touch `H` at all** — until then, P-A/P-B are safe because the general signal writes nothing gated.
5. **`SkillStats` fits K-skills, not generic tools.** Generic built-in tools (shell/file) have no `K` entry; their usefulness lives in the `task` episode, not in `SkillStats`. K/G evolution is therefore driven by K-skill stats + task outcomes, not by built-in-tool counts. (Avoid inventing a parallel `ToolStats` unless P-C shows a real need.)
6. **`G` is a no-op today** (`PASS_TOOLS['G']=frozenset()`). "Evolve K/G" is really *evolve K* until sub-agent meta-tools exist; the design must not over-promise G evolution.
7. **Budget on the hot path.** Adding recall to every conversational turn (and a per-conversation step/token budget beyond `max_iters`) must not regress latency; add a budget knob and keep recall synchronous-but-bounded.

**Open (confirm during planning):** package-internal module boundaries within `alpha/arena/`; exact `network` allowlist shape for `LocalEnv`; whether P-B writes `task` episodes from the live loop only or also from any future offline general-task runs.
