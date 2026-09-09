# Kairos — Product Charter

**Status:** living charter, written 2026-08-30, revised 2026-09-04, §9 added 2026-09-08, §7.1
amended and D11–D13 revised 2026-09-09 (the bots-and-rooms arc) · **Owner:** the operator ·
**Authority:** this charter carries intent and principles; mechanism lives in `DEVELOPMENT.md`
(the as-built front/back-end reference) and in code. On a question of intent, the charter
wins; on a question of mechanism, the code is the fact and the documents follow it. The pointer
is one-way with one honest exception: §4 names gates and surfaces by their current shape so the
write map can be read alone, and those names are re-read against `DEVELOPMENT.md` whenever
either changes. The 2026-09-04 revision exists because they had drifted.

**Scale discipline:** this charter stays readable in one sitting. If a section needs more than a
page, the content belongs in `DEVELOPMENT.md` or the docs, not here.

---

## 1. The product

Kairos is a market–strategy–account research workbench for **one operator, one machine, one
principal agent**. The agent, also called Kairos, runs on DeepSeek Harness (dsh) inside the
operator's chat face and works three layers. The operator may author further agents — bots — as
discussants (§7.1); they are voices on Kairos's substrate, not hands.

- **MARKET** — point-in-time US equities data (Alpaca bars and corporate actions, EDGAR
  filings, two offline PIT beds), guarded against lookahead in code.
- **STRATEGY** — Kairos's arena. A strategy is a directory under `strategies/`, meant to be
  git-versioned: a thesis with falsification terms, an executable screen, backtests, a journal,
  a lifecycle state. In the face, each strategy directory is a **channel**: its conversations,
  its landing page, its roster of helper agents. A channel with bots on its roster is a **room**:
  Kairos dispatches the voices, the operator argues with them, and the conclusion stays Kairos's.
  (As of 2026-09-04 only the template is committed; the three live strategies are untracked, so
  their ledger is not yet written — `DEVELOPMENT.md` §3.4.)
- **ACCOUNT** — an Alpaca paper account, read-only by default. Order capability exists in code
  behind two gates (§4); it has never been armed in the operator's real harness home.

**What a working day looks like.** The operator opens the face at `127.0.0.1:3090`, picks a
channel, and talks to Kairos. Kairos screens, backtests and reads the market through the
`alpaca_kit` tools, then writes thesis, journal and backtest artifacts into the strategy
directory. The operator reads the two read-only instruments (`/market`, `/account`), reads the
git diff, and teaches: trading style lives in an operator-owned skill pack; taste and judgment
arrive through conversation and review, not through machinery. One strategy has already been
carried from idea to a retirement verdict this way (2026-09-02, by its own pre-registered
falsification terms) — in the working tree; its directory has not yet been committed.

**What it is not.** Not an automated trading system, not an autonomy ladder, not a hosted or
multi-user service. Nothing runs unattended.

## 2. Founding principles

**P1 — Wide hands, no self-keys.** Kairos's action space is deliberately large: shell, code,
market tools, the whole strategy arena. Its authority over its own runtime is meant to be zero.
Where this is enforced by placement — the dsh profile patch and the order flag live in the
harness home, outside the agent's workspace, and no file effect or face route can write them —
placement holds. Where placement does not hold, the charter says so instead of pretending: the
credential files the documented run path sources sit at the repo root; the code of the second
order gate is inside the workspace; and the rest of the harness home (the face's own metadata,
the workspace registry) is writable from a shell turn over loopback, which can also register a
local CLI as a live tool (D10). Those are protected by review, tests, logs and the residual
ledger (§5), and they are named there.

**P2 — The operator is the only teacher.** The style pack (`style-kairos`) is operator-owned:
Kairos follows it by default, and when research findings conflict with a style entry, it
reports the conflict — never silently defers to style, never silently overrides it. Mechanics
skills are law, not style: findings never overrule them.

**P3 — Point-in-time honesty is enforced in code, not prose.** Every dated market read through
the two sanctioned channels — `replay_days` for backtests, the MCP tools for interactive queries
— passes a lookahead guard in code; the library seam returns a RAW source by contract, and the
rule that backtests use the replay channel is the first backtest rule (P4). The guard surfaces
are pinned by name in meta-gate tests, so deleting one turns the suite red. A backtest that
cannot be honest must fail loudly rather than succeed approximately.

**P4 — Honest evaluation.** The five backtest rules (`docs/backtest-rules.md`) bind every
experiment: PIT channel only; a delisting during a hold is a terminal loss, never dropped;
returns are gross unless the strategy adds a cost model and declares it in its thesis; no
same-day round trip; missing data is discarded and counted, never fabricated. Evidence fidelity extends beyond backtests: every cited number states what
was actually measured, and vendor claims motivate but never carry load.

**P5 — The human is the steady state.** There is no autonomy ladder and no graduation
criteria. Operator attention is the scarcest resource in the system and its binding rate limit;
the design economizes it but never designs it away.

## 3. Architecture in one page

```
┌──────────────────────────────────────────────────────────────────┐
│ OPERATOR   teaches via skills · reviews via git · reads the two  │  outside the
│            instruments · owns ~/.dsh (profile patch, gate flag,  │  agent's reach
│            LLM key); broker keys sit at the repo root (D8)       │  (except the keys)
├──────────────────────────────────────────────────────────────────┤
│ FACE       kairos-face, one Node process at 127.0.0.1:3090:      │  the operator's
│            hosts dsh in-process · chat per channel · /market ·   │  surface; also
│            /account · the per-order approval card (Gate 2)       │  where Gate 2 lives
├──────────────────────────────────────────────────────────────────┤
│ KAIROS     dsh runtime · skills (mechanics + style) ·            │  the agent
│            works strategies/ · queries via MCP tools ·           │
│            may call rostered local CLIs as tools                 │
├──────────────────────────────────────────────────────────────────┤
│ alpaca_kit one Python package, two faces: importable lib         │  the workbench
│            (backtests) + MCP server (interactive queries) ·      │  (this repo)
│            shared PIT guards · Gate 1 (registration)             │
├────────────────────────────────┬─────────────────────────────────┤
│ MARKET                         │ ACCOUNT                         │
│ Alpaca REST · EDGAR ·          │ Alpaca paper: account /         │
│ offline PIT beds               │ positions / orders queries      │
│                                │ (order tools double-gated)      │
└────────────────────────────────┴─────────────────────────────────┘
```

Everything below the operator row is mechanism and lives in `DEVELOPMENT.md` and the code
alongside this file. This charter does not restate tool tables, route tables, or bed windows.

## 4. The write map

Who may change what. This table is the charter's core; everything else supports it.

| Surface | Writer | Audit / gate |
|---|---|---|
| `strategies/` | **Kairos, freely** | git history is the ledger; the operator reviews diffs |
| `alpaca_kit/`, `face/`, `scripts/`, tests | normal engineering (operator and coding agents, reviewed) | offline suites, meta-gates, and the drills — this tier includes the code of both order gates |
| `dsh/skills/mechanics/` | operator only | law, not style: backtest rules and tool mechanics; Kairos treats them as binding |
| `dsh/skills/style-kairos/` | operator only | Kairos proposes changes in its journal or in conversation; it never edits the pack |
| `$DSH_HOME`: the profile patch, the order flag, keys, sessions | operator (the patch file); the face rewrites `cordis.yml` and its own metadata files | outside the workspace: no file effect can reach it; reachable over loopback from a shell turn (D10) |
| a channel's agent roster | operator, through the face | every write appends a dated line to `roster.log`; a menu, not a fence (D9) |
| `data/pit/` beds | nobody — read-only captured artifacts | a `CHECKSUMS` manifest on the 2yr bed (the broad bed predates the manifest and carries none), checked by hand; recapture is the only legitimate write |
| paper orders | nobody today | **Gate 1** (registration; enforced, test-pinned): the order tools exist in a session only when the operator's flag AND broker keys are both present. **Gate 2** (per-order approval; built 2026-09-04, in the face): every call to an order tool stops for a card the operator must answer (under a `never` policy, or with no session to ask in, it is denied outright rather than asked), and a guard admits the call only on a logged one-shot approval for that exact call and tool. Its automated drill passed and is mutation-proven for the refusing half (the card is raised, the read-only listing is not gated, an unapproved order does not dispatch); the admitting half — a real logged grant letting an approved order through the live pipeline — is unit-tested only; its human half — a person reading the card against armed tools in a scratch home — has not been run (D3). It binds only when dsh runs inside the face (D8) |

Three honesty notes the table depends on. First, both order gates hold the MCP tool *surface*,
not the account: the library's order function carries no flag, the broker key file is readable
from the workspace, and a shell turn could import the client directly — the paper-hostname pin
bounds what that can do, and D8 carries the rest. Second, Gate 2 is a gate, not containment: it
stops the model's ordinary tool calls; a wrapper on dsh's execute seam or an unrestricted shell
walks around it, and the same shell can answer its own card over loopback — the respond route
carries no token — leaving a genuine one-shot approval in the log, so the guard proves that a
grant was recorded, not who recorded it (D10; Rule 2 applied honestly). Third, the workspace
boundary protects the runtime,
not the repo: `alpaca_kit`, the face, the mechanics skills and Gate 2's own code are inside the
workspace and are protected by review and tests, not by placement.

## 5. Debts, carried openly

Known gaps, each with why it is acceptable now and when it falls due. Pretending these are
solved would be worse than carrying them.

| # | Debt | Acceptable now because | Due when |
|---|---|---|---|
| D1 | The measured party writes its own measurements: Kairos produces its own `backtests/` and `journal.md` | operator reviews diffs; the rules skill binds method | before any strategy enters paper forward-testing |
| D2 | Agent commits and operator commits are indistinguishable in git | single operator, low volume | cheap fix (distinct commit identity for Kairos) on first confusion |
| D3 | Gate 2's human half is undrilled: no person has yet read the order card against armed tools | orders are unregistered by default; the automated half is drilled | before `ALPACA_KIT_ENABLE_ORDERS` ever flips in the real harness home |
| D4 | Mechanics skills are prose-protected only | single user; every edit reviewed | if skills ever get a second writer, including Kairos |
| D5 | Spend (LLM + data API) is unmetered | costs are small and visible on bills | first surprise bill, or any scheduled autonomous runs |
| D6 | The mechanics red-lines have no drill; no test reads the content of the skill packs | single user; every edit reviewed | carried rule: a new guard ships with its drill in the same change |
| D7 | No instrument for net-negative drift: nothing compares "now" against "never-evolved" | strategies are few; the operator still reads everything | when an independent evaluator exists (see D1) |
| D8 | Both order gates are prose against a shell: they hold the tool surface, the key file sits at the repo root, and Gate 2 exists only inside the face | paper account; hostname pin; the flag has never been armed | real-money intent, or any host other than the face running the profile with the flag set |
| D9 | The channel roster is a menu, not a fence: tool schemas are tree-wide, a session in no channel is never roster-checked, and a shell turn can call a CLI directly | it reduces noise and states intent; writes are logged | if a rostered agent ever gets a capability the operator would not grant every channel |
| D10 | The harness home and the face's own routes are reachable over loopback from inside the workspace — a fence, not authentication — including the approval-answer route, so a shell turn can approve its own order card; and the MCP server, a child of the face process, writes outside the sandbox | one operator, one machine; the writes are small and visible; the paper pin bounds an answered card | a second human, a hosted deployment, real-money intent, or the first unexplained change to `$DSH_HOME/face/*` |
| D11 | *Resolved 2026-09-07.* The model is told it is Kairos: `dsh/profile/persona.md` is the `system-prompt` row's `persona`, set by the face at compose time; a bot's preset shadows it for that bot's sessions | — | — |
| D12 | Bot tool masks are visibility, not authority. dsh scopes and `tools.restrict` are "live visibility composition, not an authority boundary"; a bot with a shell writes whatever its session's sandbox mode allows and reaches whatever the network allows | held by: the `read-only` permission preset logged into every bot room session inside its creation (file effects, subject to an operator-granted escalation card), the `journal/`-scoped `cwd` of every bot home session, Gate 2 tree-wide (the account), and the room transcript naming every dispatch and every member not called. Not held by the mask, and not held for the network | if a bot's composition is ever given the account tools, or a room session is created other than read-only (§8) |
| D13 | Kairos's sessions may have a picked `cwd` at the repository root, which includes `bots/`; "Kairos never edits a bot" is a Rule-7 commitment carried by `AGENTS.md`'s never-edit list and review, not by the sandbox | single operator; every edit reviewed; git is the ledger | the first bot edit that is not the operator's |

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

- **No privileged second agent.** Teaching, review, and adjudication belong to the operator. One
  hand, many voices: Kairos is the one agent whose composition carries the account tools and the
  write to a strategy directory; the operator may roster other agents on a channel — local CLIs as
  callable tools, operator-authored dsh bots as **discussants** that speak in the room — but a bot
  is a voice, not a reviewer: what it says is evidence the operator and Kairos weigh, never a
  verdict, and the conclusion is written by Kairos. Bots run on Kairos's substrate with their tool
  sets masked by configuration; the mask is a menu (a bot with a shell writes whatever its sandbox
  mode allows — D12), and the fence around the account is Gate 2, tree-wide, the same for every
  agent. Kairos's `dispatch` orders the room but grants nothing, and the operator's `@` bypasses
  it. Bots are authored by the operator, never by Kairos (Rule 7). A voice need not run on this
  machine: an agent reached over A2A is a voice too — untrusted text in the room log, never a hand
  in this tree; the moment anything outside this machine can call *in*, §8's last row applies. A
  reviewer entity with authority would add a plane of machinery to buy safety that already comes
  from P1.
- **No proposal queue.** Change lands by editing; git is the ledger and the rollback. A
  deliberation pipeline is bureaucracy at this scale.
- **No bespoke harness.** dsh owns the runtime — sessions, tools, sandboxing, subagents, and
  the approval channel. The face hosts it in-process and registers the order producer on dsh's
  published `tools/pre-execute` seam; that is configuration in code on a pinned version, not a
  fork, and the two pins make the dependence explicit. We do not fork it or wrap its loop.
- **No hosted face.** Loopback only, one machine, no authentication machinery on the local
  surfaces (see D10 for what that costs).
- **No multi-tenant, cryptographic, or kernel-level machinery.** One operator, one machine.
  The risks are named here in one line each instead of being built against: a hosted or
  multi-user deployment invalidates this charter rather than extending it.
- **No memory substrate beyond what exists.** Git, the strategy directories, and dsh's own
  sessions are the memory. A dedicated store is chosen when content demands one.

## 8. Revisit triggers

Few and concrete. Each names the section it reopens.

| Trigger | Reopens |
|---|---|
| Arming `ALPACA_KIT_ENABLE_ORDERS` in the real harness home | D3 first (run the human half of the order drill in a scratch home) · D8 |
| Real-money intent (any non-paper order path) | §4 both gates · D1 · D3 · D8 · broker-key rotation |
| Running the profile in any host other than the face | D8 (Gate 2 is absent there) |
| Kairos begins authoring reusable skills | Rule 7 → lifecycle machinery · D4 |
| An independent evaluator is introduced | D1 · D7 (the measurement plane) |
| dsh leaves developer preview or ships a breaking change | the two pins · profile and skills format · the drills |
| A bot's composition is given the account tools, a bot room session is created other than read-only, or a bot home session's cwd widens past its `journal/` | §7.1 · D8 · D12 · run the order drill under that bot's preset |
| Starting the interface migration in §9 | §3 (the FACE row) · §7 "No bespoke harness" and "No hosted face" · the two pins · the row inventory of the face's tree against the CLI's (R13 is its first symptom) |
| A second human, or any hosted deployment | this charter is the wrong document; write the next one |

## 9. Forward

Directions the operator has set that are not yet designed. Each is intent only: a spec comes
before any build, and §6 and §7 hold until that spec says otherwise.

- **The face absorbs dsh's operator surface; dsh's own frontends are retired** (set
  2026-09-08). Every interface dsh offers the operator today — the `dsh` command's terminal UI
  and `dsh web` — moves onto the face, and those frontends stop being used for this workbench.
  dsh stays the runtime, hosted in-process, exactly as §7 "No bespoke harness" says; what
  changes is that the face becomes the only client of dsh's gateway the operator ever opens.
  Recorded so the spec starts from the tree, not from the idea: the face's composition must
  carry every row the operator today gets from the CLI's tree (R13, the missing projection
  cache, is the first symptom of a row the CLI has and the face lacks); every gateway RPC the
  retired frontends used needs a home in the face's client or a recorded reason it has none;
  the two-pin upgrade path stays; D10 and the roster-as-menu residuals are unchanged by the
  move. Open for the spec: whether the face keeps sharing `$DSH_HOME` with the dsh the operator
  runs in other projects, or gets a home of its own. Not designed; no spec; nothing built.
