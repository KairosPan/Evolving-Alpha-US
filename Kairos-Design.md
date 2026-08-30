# Kairos — Design Charter

**Status:** living charter, 2026-08-30 · **Authority:** this charter carries intent and
principles; mechanisms live in the workbench spec
(`docs/superpowers/specs/2026-08-29-market-strategy-account-skeleton-design.md`)
and in code. On a question of intent, the charter wins; on a question of mechanism, spec and
code win. The pointer is one-way: this document never restates mechanism, so it never needs
syncing when mechanism moves.

**Scale discipline:** this charter stays readable in one sitting. If a section needs more than
a page, the content belongs in the spec or the docs, not here.

---

## 1. What Kairos is

Kairos is a single trading-research agent, run by a single operator, on DeepSeek Harness
(dsh). It works a three-layer workbench:

- **MARKET** — point-in-time US equities data (Alpaca + EDGAR), guarded against lookahead.
- **STRATEGY** — Kairos's arena. A strategy is a git-versioned directory: a thesis with
  falsification conditions, an executable screen, backtests, a journal, a lifecycle state.
  Kairos researches, writes, backtests, and iterates these.
- **ACCOUNT** — an Alpaca paper account, read-only today. Order capability exists in code but
  is double-gated; no order reaches any market through a gate Kairos can open.

The operator teaches directly: trading style lives in an operator-owned skill pack; taste and
judgment arrive through conversation and review, not through machinery. The runtime, the
gates, and the operator's configuration live outside Kairos's reach.

## 2. Founding principles

**P1 — Wide hands, no self-keys.** Kairos's action space is deliberately large: shell, code,
market tools, the whole strategy arena. Its authority over its own runtime is zero. This is
enforced by placement, not by rules: the dsh profile, credentials, and every gate flag live in
the harness home, outside the agent's workspace.

**P2 — The operator is the only teacher.** The style pack (`style-kairos`) is operator-owned:
Kairos follows it by default, and when research findings conflict with a style entry, it
reports the conflict — never silently defers to style, never silently overrides it.

**P3 — Point-in-time honesty is enforced in code, not prose.** Every dated market read passes
a lookahead guard; the guard surfaces are pinned by name in meta-gate tests, so deleting one
turns the suite red. A backtest that cannot be honest must fail loudly rather than succeed
approximately.

**P4 — Honest evaluation.** The five backtest rules (workbench `docs/backtest-rules.md`)
bind every experiment: PIT channel only; a delisting during a hold is a terminal loss, never
dropped; returns are gross and say so; no same-day round trip; missing data is discarded and
counted, never fabricated. Evidence fidelity extends beyond backtests: every cited number
states what was actually measured, and vendor claims motivate but never carry load.

**P5 — The human is the steady state.** There is no autonomy ladder and no graduation
criteria. Operator attention is the scarcest resource in the system and its binding rate
limit; the design economizes it but never designs it away.

## 3. Architecture in one page

```
┌─────────────────────────────────────────────────────────────┐
│ OPERATOR      teaches via skills · reviews via git ·        │  outside the
│               owns ~/.dsh (profile, keys, gate flags)       │  agent's reach
├─────────────────────────────────────────────────────────────┤
│ KAIROS        dsh runtime · skills (mechanics + style) ·    │  the agent
│               works strategies/ · queries via MCP tools     │
├─────────────────────────────────────────────────────────────┤
│ alpaca_kit    one Python package, two faces:                │  the workbench
│               importable lib (backtests) + MCP server        │  (this repo)
│               (interactive queries) · shared PIT guards      │
├──────────────────────────────┬──────────────────────────────┤
│ MARKET                       │ ACCOUNT                      │
│ Alpaca REST · EDGAR ·        │ Alpaca paper: account /      │
│ offline PIT beds             │ positions / orders queries   │
│                              │ (order tools double-gated)   │
└──────────────────────────────┴──────────────────────────────┘
```

Everything below the operator row is mechanism and lives in the spec and the code alongside
this file. This charter does not restate tool tables, gate wiring, or bed windows.

## 4. The write map

Who may change what. This table is the charter's core; everything else supports it.

| Surface | Writer | Audit / gate |
|---|---|---|
| `strategies/` | **Kairos, freely** | git history is the ledger; the operator reviews diffs |
| `dsh/skills/mechanics/` | operator only | law, not style: backtest rules and tool mechanics; Kairos treats them as binding |
| `dsh/skills/style-kairos/` | operator only | Kairos proposes changes in its journal or in conversation; it never edits the pack |
| dsh profile, harness home, `ALPACA_KIT_ENABLE_ORDERS` | operator only | outside the workspace — structurally unreachable, not merely forbidden |
| `alpaca_kit/` + tests | normal engineering (operator and coding agents, reviewed) | offline test suite + meta-gates |
| `data/pit/` beds | nobody — read-only captured artifacts | checksums; recapture is the only legitimate write |
| paper orders | nobody today | **Gate 1** (enforced, test-pinned): order tools register only when the operator's flag AND broker keys are both present. **Gate 2** (intent, not yet validated): per-order human approval in dsh — must be proven live before the flag ever flips |

Two honesty notes the table depends on. First, Gate 2 is written down as intent because dsh
is in developer preview and the approval mechanism gets pinned at install; until an order call
demonstrably prompts a human, Gate 1 is the only enforced layer. Second, the workspace
boundary protects the runtime, not the repo: mechanics skills and `alpaca_kit` are inside the
workspace and are protected by review and tests, not by placement.

## 5. Debts, carried openly

Known gaps, each with why it is acceptable now and when it falls due. Pretending these are
solved would be worse than carrying them.

| # | Debt | Acceptable now because | Due when |
|---|---|---|---|
| D1 | The measured party writes its own measurements: Kairos produces its own `backtests/` and `journal.md` | operator reviews diffs; the rules skill binds method | before any strategy enters paper forward-testing |
| D2 | Agent commits and operator commits are indistinguishable in git | single operator, low volume | cheap fix (distinct commit identity for Kairos) on first confusion |
| D3 | Gate 2 unvalidated (see §4) | orders are unregistered by default | before `ALPACA_KIT_ENABLE_ORDERS` ever flips |
| D4 | Mechanics skills are prose-protected only | single user; every edit reviewed | if skills ever get a second writer, including Kairos |
| D5 | Spend (LLM + data API) is unmetered | costs are small and visible on bills | first surprise bill, or any scheduled autonomous runs |
| D6 | The untested guards have no drills (Gate 2, mechanics red-lines) | carried rule: a new guard ships with its drill in the same change | as guards land |
| D7 | No instrument for net-negative drift: nothing compares "now" against "never-evolved" | strategies are few; the operator still reads everything | when an independent evaluator exists (see D1) |

## 6. Rules carried forward

Standalone rules this design treats as settled. They are stated without their histories; each
was expensive.

1. **Recording is not governing.** A reported number governs nothing until something
   thresholds it. A measurement plane the measured code can write is not a measurement plane.
2. **Enforce below the layer that runs arbitrary code** — or admit the gate is prose. A
   tool-wrapper guard that a shell command can walk around is documentation, not enforcement.
3. **Containment beats claimed secrecy.** State what actually holds and record the residuals;
   never ship a guarantee that fails at code level.
4. **A guard that has never been drilled is presumed broken.**
5. **What is never surfaced is never governed.** Anything filtered away silently — dropped
   candidates, discarded days, skipped checks — gets counted and shown.
6. **Codification always reads as an efficiency win** and hides what it removes. Prefer prose
   and conversation until code has earned its place with evidence.
7. **A self-extending library without lifecycle machinery is noise.** If Kairos ever authors
   reusable skills, lifecycle states and retirement come first, not later.
8. **Substrate decisions taken before there is content are taken blind.** Choose stores and
   schemas when real data demands them, never in anticipation.

## 7. What this design deliberately does not build

- **No second agent.** Teaching, review, and adjudication belong to the operator. A reviewer
  entity would add a plane of machinery to buy safety that already comes from P1.
- **No proposal queue.** Change lands by editing; git is the ledger and the rollback. A
  deliberation pipeline is bureaucracy at this scale.
- **No bespoke harness.** dsh owns the runtime — sessions, tools, approvals, sandboxing,
  subagents. We configure it; we do not fork it or wrap it.
- **No multi-tenant, cryptographic, or kernel-level machinery.** One operator, one machine.
  The risks are named here in one line each instead of being built against: a hosted or
  multi-user deployment invalidates this charter rather than extending it.
- **No memory substrate beyond what exists.** Git, the strategy directories, and dsh's own
  sessions are the memory. A dedicated store is chosen when content demands one.

## 8. Revisit triggers

Few and concrete. Each names the section it reopens.

| Trigger | Reopens |
|---|---|
| Real-money intent (any non-paper order path) | §4 Gate 2 validation · D1 · D3 · broker-key rotation |
| Kairos begins authoring reusable skills | Rule 7 → lifecycle machinery · D4 |
| An independent evaluator is introduced | D1 · D7 (the measurement plane) |
| dsh leaves developer preview or ships a breaking change | profile + skills format re-pin |
| A second human, or any hosted deployment | this charter is the wrong document; write the next one |
