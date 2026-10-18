# Gravit on dsh — the agent redesign

**Status:** design, pending the operator's review of this file (2026-10-15) · **Owner:** the
operator · **Branch:** `feat/agent-redesign`, cut 2026-10-06 from `main @ a6126d1` and
fast-forwarded to `69225d8` · **Provenance:** brainstormed 2026-10-06 and 2026-10-08 (four
layers chosen, four defaults accepted), corrected 2026-10-15 (AGENTS.md stays, the agent is
Gravit, persona and memory wait for the next round, a dsh upgrade guide is owed). The measured
prompt numbers are from the 2026-10-10 trace of the two loops on dsh 0.2.0-rc.2.

**Authority.** The charter (`Kairos-Design.md`, `Gravit-Design.md` after the rename) outranks
this spec on intent; §10 lists the charter sentences this design needs changed, and the
operator approves them by approving this spec. `DEVELOPMENT.md` follows the code; §9 lists the
sections that move. **The rename is a prerequisite, not part of this spec:** the "Agent 名字改为
gravit" arc renames Kairos → Gravit across the tree first (its own spec and branch), and every
identifier below is the post-rename one — `gravit` the preset id, `preset-gravit` the overlay
row, `gravit-face` the binary, `gravit-bot` the bot plugin, `bots/gravit/` the default
composition, `Gravit-Design.md` the charter, `dsh/skills/style-gravit/` the style pack.
Nothing here is implemented until that rename has landed on `main`.

---

## 1. Why

Gravit today is a chat responder. Its mind is spread over four places with no stated
precedence — a 3 KB persona that is half mechanics manual, a 5 KB `AGENTS.md`, a 7.9 KB
`CLAUDE.md` written for coding agents that dsh's instruction loader hands it anyway, and five
skills loaded by name — and the first request of every session carries 4,040 tokens of that
prose plus 32,003 tokens of tool schemas before the operator has said a word. It has no roles:
bots are voices with no hands, and `subagent` is a generic fresh child with Gravit's own persona
and the host's full tool roster. Nothing runs past one turn; a research cycle (idea → thesis and
falsification terms → screen → backtest → journal → verdict) is a dozen operator messages.

The operator wants a product-grade research agent for one operator: one idea in, one batched
question back, then a cycle that runs to its verdict inside the strategy directory with no
further attention, judged afterwards from the journal and the diff. This design lands that on
dsh's own seams — presets, scoped prompt sections, per-role delegation tools, goals — without a
bespoke loop and without touching the host plane.

## 2. The brief — decisions the operator took

| # | Decision | When |
|---|---|---|
| B1 | One operator, one machine; the charter's §1 holds. The one sentence that changes: "nothing runs unattended" becomes "nothing *starts* unattended; a started cycle runs to its verdict inside its strategy directory" | 2026-10-06 |
| B2 | The agent is **Gravit**; the rename lands first (prerequisite, own arc) | 2026-10-15 |
| B3 | One standing Gravit plus a **role library** of prebuilt one-shot subagent presets; bots stay voices | 2026-10-06 |
| B4 | First roles: **screener**, **backtester**, **reviewer**; the journal and the verdict stay Gravit's own | 2026-10-08 (默认) |
| B5 | **`GRAVIT.md`** is the dsh agent-instructions file. `AGENTS.md` stays for coding agents (Claude Code reads it too) and `CLAUDE.md` stays for Claude Code; Gravit reads neither | 2026-10-15 |
| B6 | **Persona content, the style pack (doctrine / signals / lessons), memory and the teaching channel are deferred** to the next design round. This round edits `persona.md` only for the rename and to delete its reference to the `report` tool, which dsh 0.2.0 removed | 2026-10-15 |
| B7 | The cycle: one batched `ask_user_question` up front, then run to the verdict; no further operator gates of Gravit's own; no daily cadence | 2026-10-06 |
| B8 | Caps per cycle: **24 goal rounds, 12 role children**, no wall clock; usage recorded, not capped | 2026-10-08 (默认) |
| B9 | The charter and `DEVELOPMENT.md` are revised in the same change (§10) | 2026-10-08 (默认) |
| B10 | A **dsh upgrade guide** (`docs/dsh-upgrade-guide.md`) is written in this arc, and every dsh seam this design adds is entered in it, so the next dsh upgrade is a checklist rather than a redesign | 2026-10-15 |

**Success, as the operator will recognize it.** (a) In a channel, one message with an idea
produces one `ask_user_question` batch and then `THESIS.md`, `backtests/*.json`, `journal.md`
and `status.yaml` written and a verdict (`validated`, `retired`, or `researching` with a named
blocker) with no further input, within the caps. (b) The first request of a Gravit session
carries `GRAVIT.md` and nothing of `AGENTS.md` or `CLAUDE.md`, and every injected rule has
exactly one home. (c) A role child cannot call what its allow-list does not name — a backtester
cannot reach the account tools, a reviewer cannot write — and bots are unchanged. (d) The
operator can add or edit a role by editing two small files under `roles/` and see it in the
next session.

## 3. Non-goals

- No hosted face, no second human, no multi-tenant anything (charter §7.3 and §8 unchanged).
- No paper trading, no order path, no change to either order gate.
- No daily schedule or unattended *start* of anything; dsh's schedules are session-local and
  the charter's P5 stands.
- No persona rewrite, no memory substrate, no change to the style pack or to how the operator
  teaches (B6). The persona's mechanics paragraphs (rooms, subagents) stay where they are this
  round; §13 records them.
- No change to bots, rooms or `dispatch` beyond the rename. The room findings of the 2026-10-10
  trace (answers reach Gravit unattributed, bots run at effort `high`, bot prompts carry tool
  sections for masked tools) are recorded in §13, not fixed here.
- No cut to Gravit's own tool roster. The 32,003-token schema block is measured and attributed
  (§7) and the lever — a mask in Gravit's own preset — is named for the next round.
- No A2A voices, no `workflow`-scripted cycle (the operator chose roles as tools over a
  committed orchestration script, 2026-10-08), no Ralph loop.

## 4. The mind layer: one file per layer, one seam per file

### 4.1 The stack

| Layer | File (operator-owned unless noted) | dsh seam that injects it | Who reads it | Rule |
|---|---|---|---|---|
| L0 harness identity | dsh's own line | `system-prompt` `includeHarnessIdentity`, order −1000 | every agent | not ours |
| L1 identity | `dsh/profile/persona.md` | `personaPrefix` on the `system-prompt` row (section `deployment:persona-prefix`, order 0), set by `composeFace` — mechanism unchanged | Gravit; a bot's preset shadows it; a role child never sees it (§5.4) | who Gravit is, whom it answers to, what it never does. **Deferred (B6)** except the rename and the dead `report` sentence |
| L2 law | `dsh/skills/mechanics/*/SKILL.md` | the skill catalog + the `skill` tool, on demand | every agent that can call `skill` | binding; findings never overrule; unchanged |
| L3 workspace map | **`GRAVIT.md`** at the repo root, plus any `strategies/<name>/GRAVIT.md`, plus `GRAVIT.local.md` (gitignored) | the `agent-instructions` row: `instructionFileCandidates: ["GRAVIT.md"]`, `localInstructionFileCandidates: ["GRAVIT.local.md"]`, `maxBytes: 65536` restated (a named config replaces the row's whole config) | **every agent in the tree** — Gravit, role children, bots — because the row is host-plane | facts about the tree, never Gravit's identity or behaviour: where things are, the strategy contract, the beds, the never-edit list |
| L4 style | `dsh/skills/style-gravit/*` | the skill catalog, on demand | as L2 | **deferred (B6)**; unchanged this round; the next round moves it to memory |
| L5 role | `roles/<id>/ROLE.md` + `roles/<id>/role.yml` | one `@deepseek-ai/dsh-tool-subagent` row per role in Gravit's preset: `persona` and `toolFilter` applied by the `spawn` backend in the child's creation window | that role's children | one role = one tool; a role narrows, never widens |
| L6 Gravit's contract | `dsh/profile/cycle.md` (the research-cycle contract, new) and the rendered role summaries | scoped prompt sections registered by `face/plugins/gravit.js` from inside Gravit's preset (`gravit:cycle`, `gravit:roles`, `deployment:today`), visible to Gravit's sessions only | Gravit | how Gravit runs a cycle and which roles exist. Lives outside `persona.md` so B6 holds, and outside `GRAVIT.md` so bots and children, who have no goal tools and no roles, never read it |
| L7 task | the conversation; the cycle's goal | `ask_user_question`; `create_goal` / `update_goal` | Gravit | the request |

**Precedence, stated once (in `GRAVIT.md`'s first lines and in the charter):** L1 and L2 bind
everything below them. L3 is fact, not rule — when it disagrees with the tree, the tree is
right and `GRAVIT.md` is wrong. L5 narrows a child's world and can never widen it (the
sandbox, Gate 2 and the host's depth cap bind children exactly as they bind Gravit). L6 tells
Gravit how to work; L7 tells it what to work on; neither can override L1–L2. L4 is the
operator's default, reported against when findings contradict it — unchanged, and its future is
the memory round's.

### 4.2 `GRAVIT.md`

Budget **≤ 4,500 bytes**, English, no `{{` (the loader does not interpolate instruction files,
but the rule costs nothing and spares a future surprise). Sections, in order:

1. **What this is and who reads this file** — three lines: the three layers, and that this file
   is read by every dsh agent in the tree, so it states facts only.
2. **Where things are** — the table rows a working agent needs: `alpaca_kit` (library for
   backtests, MCP tools for interactive reads), `strategies/`, `data/pit/`, `docs/backtest-rules.md`,
   `roles/`, `bots/`.
3. **The PIT rule in one paragraph** — `replay_days` or `GuardedSource` + `AsOfGuard`; a bare
   `make_source()` is RAW; the AKShare tools carry no guard and are never backtest evidence.
4. **The strategy directory contract** — the file set, the lifecycle vocabulary, the three
   `status.yaml` headline keys, the naming rule (one word, no spaces: the `cd` trap, worked
   example kept), "commit your own iterations".
5. **The beds** — the window table copied from `docs/backtest-rules.md`, the two failure modes
   outside a window, the warmup dates. (`alpaca-kit-guide` and `backtest-rules` carry the same
   table; when a bed changes all of them move, as `DEVELOPMENT.md` §3.3 already records.)
6. **Rooms** — three lines: a channel with bots on its roster is a room; the caps per operator
   message; the operator's `@` reaches a voice directly. The dispatch *protocol* (parallel first,
   end the turn, name disagreements) stays in `persona.md` this round (B6).
7. **Never edit** — `data/pit/`, installed profile copies, anything under `bots/` or `roles/`
   (propose in conversation), `docs/research/`.

What leaves the first request with this change: `CLAUDE.md` (7,877 bytes) and the old
`AGENTS.md` (5,148 bytes). What stays out of `GRAVIT.md` on purpose: the cycle contract
(L6), the room protocol and delegation habits (L1, deferred), the style (L4).

### 4.3 `AGENTS.md` and `CLAUDE.md` after this change

`AGENTS.md` is rewritten for its remaining readers, the coding agents (Claude Code, Codex):
about fifteen lines — read `CLAUDE.md` for the map and commands; `GRAVIT.md` is the research
agent's file, edit it as a product file, not a note; `strategies/` is Gravit's arena; never edit
`data/pit/`, `bots/`, `roles/`, `docs/research/` without the operator; keep both suites green.
`CLAUDE.md` changes two rows: the `AGENTS.md` row (no longer "the map written for Kairos … dsh's
loader hands Kairos this file and `CLAUDE.md`") and a new `GRAVIT.md` row, plus the reading-order
line.

### 4.4 The date

The 2026-10-10 trace found no date anywhere in the request. `face/plugins/gravit.js` registers
a context-resolved section `deployment:today` (order 1, directly after the persona) that
renders `Today is <ISO date>, <weekday> (<host time zone>).` at each assembly. A research agent
that reasons about as-of dates and bed windows needs it; it is one line and it is measured.

## 5. The organization: Gravit's preset and the role library

### 5.1 Gravit's preset becomes a composition

Today `bots/gravit/agent.cordis.yml` is `[]` — "the host composition itself, no mask, no
shadowed persona; add nothing here: a row here would reach every session" — and that is exactly
what this design wants. The composition gains rows, and they are **generated** the way every
bot's composition is generated from `SOUL.md` (`face/src/bots.ts` `renderComposition`):

```yaml
# GENERATED by the face (face/src/roles.ts renderGravitComposition) - do not hand-edit.
- id: gravit
  name: ../../face/plugins/gravit.js          # rebased to a file: URL by definitionFor
  config:
    cycle: '<dsh/profile/cycle.md, verbatim>'
    roles:
      - { tool: role_screener,   summary: '<roles/screener/role.yml description>' }
      - { tool: role_backtester, summary: '…' }
      - { tool: role_reviewer,   summary: '…' }
- id: role-screener
  name: '@deepseek-ai/dsh-tool-subagent'
  config:
    provider: spawn
    toolName: role_screener
    backgroundMode: one-shot
    persona: '<roles/screener/ROLE.md, verbatim>'
    toolFilter: <the allow-list from roles/screener/role.yml, in the shape §11 (a) settles>
- id: role-backtester …
- id: role-reviewer …
```

- **Source of truth is `roles/` and `dsh/profile/cycle.md`.** At boot `face/src/roles.ts`
  reads them and renders the rows in memory; `composeFace` hands `definitionFor(botsRoot,
  "gravit")` those rows instead of reading the file. The committed `bots/gravit/agent.cordis.yml`
  is a human-readable mirror written by `face/scripts/render-roles.ts`; a test renders both and
  fails on drift, so the file on disk is never stale and never authoritative.
- **Why the preset and not the host plane:** a preset's rows register into Gravit's scope and
  nothing else's (`dsh-agent-preset-registry`: "plugin registrations inherit the preset scope,
  and the Agent scope's parent link controls visibility"). Bots, which join their own presets,
  never see `role_*`; a role child, which "gets a new flat scope rather than inheriting parent
  registrations", never sees them either. The host roster is untouched, and so are the two
  gates, which are tree-wide.
- **Activation is eager and failure is loud.** The registry mounts a declaration when it is
  declared; `preset-gravit` is the static overlay row that must exist before the first
  `session/create`, so a role row that cannot mount marks the default preset broken and
  `bootFace`'s roster audit (§4.1 step 8 of `DEVELOPMENT.md`) refuses the boot, naming the row.
  The invariant the bots-and-rooms spec called S3 ("Kairos's tools are exactly the host's")
  becomes **"Gravit's tools are the host's plus the role tools, and nothing of Gravit's reaches
  a bot or a child"**; the four tests that pin the empty preset move with it (§9).
- `face/plugins/gravit.js` imports nothing, like `bot.js`, and does three things: validates its
  config (`cycle`, when present, a non-empty string; `roles`, when present, a list of
  `{tool, summary}` with tool names matching `^role_[a-z0-9_]+$` — plan 1 ships the plugin with
  neither key, plan 2 adds `roles`, plan 3 adds `cycle`); registers `deployment:today` (§4.4);
  registers `gravit:cycle` (the contract text) and `gravit:roles` (one line per role:
  `role_<id> — <summary>`), each only when its key is configured, at the first-party tail,
  after the tool sections and before any `personaSuffix` (exact orders chosen in plan 2 from
  `getSectionOrder`). All three sections set `interpolate: false`, so the
  operator's text may contain braces. The role summaries are sections rather than tool
  descriptions because `dsh-tool-subagent` derives every instance's description from the
  provider and exposes no description key — three tools named `role_*` with identical
  descriptions would tell the model nothing.

### 5.2 Roles on disk

```
roles/
  _template/            # the copy source
    ROLE.md             # the child's persona; no "{{" (the system prompt is a strict template)
    role.yml            # name, description (the one-line summary Gravit sees), allow (tool names)
    README.md
  screener/  backtester/  reviewer/
```

- `role.yml`: `name` (display), `description` (≤ 300 characters; it is the model-facing
  summary), `allow` (tool names; `mcp__*__<raw>` expands against every MCP server as in
  `bot.js`), optional `model: <provider>/<model>` (face-only, becomes the row's `agentOptions`;
  unset in v1, every role runs on Gravit's route).
- A role id obeys the bot grammar `[a-z0-9][a-z0-9-]*`; the tool name is `role_` + the id
  with `-` → `_`. `_template` is never rendered.
- **Writer:** the operator, by file edit; Gravit proposes a role in conversation and never
  creates or edits one (the write map gains the row, §10). No face UI for roles in v1 — three
  files, a template and a drift test are the whole authoring surface.

### 5.3 The three roles

| Role | Persona in one line (ROLE.md says it in full) | Allow-list | Returns |
|---|---|---|---|
| `screener` | runs the strategy's screen over the PIT bed for the days asked and returns candidates with the measured fields; reads the market only through the PIT channels; writes nothing but the candidates file; draws no conclusion | `bash`, `read`, `write`, `glob`, `grep`, `skill`, `mcp__*__screen`, `mcp__*__market_snapshot`, `mcp__*__breadth`, `mcp__*__daily_bars`, `mcp__*__calendar`, `mcp__*__corp_actions`, `mcp__*__earnings` | count, the candidates file path, the top names with fields, the days discarded and why |
| `backtester` | loads `backtest-rules` first, runs `backtest.py` (or the variant Gravit names) bounded to the bed window, writes the artifact under `backtests/`, and returns the headline numbers with the five-rule checklist; never edits `THESIS.md` | `bash`, `read`, `write`, `edit`, `glob`, `grep`, `skill`, `mcp__*__daily_bars`, `mcp__*__calendar`, `mcp__*__corp_actions`, `mcp__*__earnings` | artifact path, window actually used, headline numbers, the rule checklist, missing-data counts |
| `reviewer` | read-only: audits `THESIS.md`, the artifacts and `journal.md` against the five rules and the pre-registered falsification terms; reports violations, unmeasured claims and unresolved limits; recommends `validated` / `retired` / `continue` with the reason; edits nothing | `read`, `glob`, `grep`, `skill`, `mcp__*__daily_bars`, `mcp__*__calendar`, `mcp__*__corp_actions`, `mcp__*__market_snapshot` | the verdict recommendation, violations with file and line, limits |

Absent from every role by design: `ask_user_question` (an owned child has no human answerer —
dsh rejects it with `DELEGATED_CALLER` — so a role that needs the operator ends with a blocker
in its report instead), `web_search`, every `subagent*` / `workflow` / `ralph` / goal / todo /
job tool, every `agent_<bin>`, `dispatch`, the account and order tools, the AKShare tools.
Every role's report ends with the same four headings — **status** (`done` / `blocked`),
**what was measured**, **paths**, **limits** — stated in each `ROLE.md`; Gravit treats a report
as a claim to check, not a result to copy (charter D14).

### 5.4 What a role child sees

A `spawn` child starts with an empty conversation in its own session: L0; **its role's persona
in the persona slot — never Gravit's** (§11 (a) settles the mechanism: either the row's
`persona` shadows the global `personaPrefix`, or Gravit's prefix moves into `gravit.js` as a
scoped section and the global stays empty); the `GRAVIT.md` chain (host-plane); the skill
catalog (L2 and L4, loadable); the tool schemas its allow-list admits and nothing else ("the
named tools vanish from the child's prompt AND refuse to execute"); the parent's cwd, provider,
model and effort. It inherits no registration of Gravit's scope, so no `role_*` tool and no
`gravit:*` section; the host's `subagent.maxDepth` of 1 means it cannot delegate at all. Its
writes are fenced by the sandbox to the parent's cwd — in a channel session, `strategies/<name>/`.

### 5.5 Bots and rooms

Unchanged except the rename. A bot's composition still carries `gravit-bot` (today `bot.js`)
with its allow-list, and `DEFAULT_ALLOW` is unchanged: no bot gets a role tool, and §5.1 shows
why none can. Rooms keep `dispatch` and the caps; the persona's room paragraph stays (B6).

## 6. The research cycle

**Where it runs.** In a channel session, cwd `strategies/<name>/`, writes fenced there by the
sandbox; role children inherit the cwd and the fence.

**Step 0 — the ask.** One `ask_user_question` batch and no code before it: the thesis in one
paragraph; the falsification terms as metric + threshold + window; the bed and window, with the
warmup moving the honest start; what the operator wants measured. A brief that already answers
these is the answer and the ask is skipped. (This rule is `AGENTS.md`'s today and moves to
`cycle.md` verbatim.)

**Step 1 — the goal.** Gravit opens one goal (`create_goal`) whose objective is the brief plus
the verdict criteria, with `maxGoalRounds: 24`. The goal is the cycle's durable record: dsh's
round driver re-prompts Gravit at idle until the goal is complete or blocked, each round starts
its own request series (the chat shows the round header), and after a restart the goal stays
disarmed until a human resume (§11 (e) settles how the operator resumes from the face).

**Steps 2–5 — the work, inside rounds.** Write `THESIS.md` and set `status: researching`;
delegate the screen to `role_screener`; delegate each backtest to `role_backtester`; journal
every result as a dated entry with the artifact paths and the numbers as measured; before
concluding, delegate the audit to `role_reviewer` and answer its violations; iterate while the
falsification terms are undecided and the caps have room. Role calls run in the foreground
(`backgroundMode: one-shot`), one at a time by default; the ad-hoc `subagent` and `workflow`
tools stay available for work no role covers.

**Step 6 — the verdict.** `status.yaml` → `validated` or `retired`, each citing the
pre-registered terms it met or failed, or `researching` with the goal **blocked** on a concrete
code (`round-limit`, `child-limit`, `bed-window`, `data-missing`, `needs-operator`) and a
one-line explanation; `one_line`, `next` and `numbers` filled; the journal's last entry is the
verdict with the usage the face reports for the session; the goal completed. The final message
to the operator is the verdict, what to read, and the usage line.

**Gates during the run.** None of Gravit's own after Step 0: asking again is allowed only to
*stop* ("the bed cannot cover the window you asked for"), never to continue. dsh's cards stay:
a write outside the fence escalates, an order tool meets Gate 2 (and is unregistered anyway).

**Caps, and what enforces them.** 24 rounds is enforced by the goal (`round-limit`). 12 role
children per cycle is Gravit's rule, counted in the journal and visible in the face's child
history — **not enforced by dsh**, which has a concurrency cap (`maxActiveSubagents`) but no
per-cycle total outside the workflow engine. Charter Rule 1 applies: a recorded count governs
nothing until something thresholds it. The threshold is deferred to the first overrun, when a
face-side counter on `agent/created` for one session's children is a small change; until then
the journal count is shown, never silent. Usage: per-session, visible in the face and copied into
the verdict entry; no cap (B8), and D5's trigger ("any scheduled autonomous runs") is reworded
to fire on the first cycle whose usage surprises the operator.

## 7. Prompt budget, before and after

Measured 2026-10-10 on the go-live smoke session (heuristic tokens from the projection cache's
`contextBreakdown`; DeepSeek billed 55,635 input tokens for that first request):

| Part | Before | After (estimate; measured in plan 3) |
|---|---|---|
| system (identity, persona, tool sections, `mcp:akshare`) | 1,622 | ≈ 2,200 (+ `deployment:today`, `gravit:cycle` ≤ 1.5 KB, `gravit:roles` ≤ 0.6 KB) |
| messages (prompt, instructions baseline, runtime context, skill catalog) | 4,040 (baseline `AGENTS.md`+`CLAUDE.md` 3,443) | ≈ 1,900 (`GRAVIT.md` ≤ 4.5 KB ≈ 1,200) |
| tools (schemas) | 32,003 | ≈ 32,600 (+3 `role_*`) |

The schema block is the prompt, not the prose. The trace's hypothesis — the 14 AKShare tools,
whose descriptions enumerate every method — is unconfirmed; plan 3 confirms it by dumping
`tools.schemas()` per tool and recording the per-tool token cost in `DEVELOPMENT.md`. The lever
is a mask in `gravit.js` (`tools.restrict`, exactly as `bot.js` does for bots), and it waits for
the next round because which tools Gravit may lose is the operator's decision, taken on numbers.

## 8. Changes by file

| Area | File | Change |
|---|---|---|
| L3 | `GRAVIT.md` (new) | §4.2 |
| L3 | `.gitignore` | `GRAVIT.local.md` |
| L3 | `AGENTS.md`, `CLAUDE.md` | §4.3 |
| L3 seam | `face/src/boot.ts` `composeFace` | after the persona patch, guarded on `rows.has("agent-instructions")`: one id patch restating the row's config whole with the two candidate lists and `maxBytes` |
| L1 | `dsh/profile/persona.md` | rename; delete the sentence that names `report` |
| L6 | `dsh/profile/cycle.md` (new) | the Step 0 rule (moved from `AGENTS.md`), Steps 1–6, the caps, the blocker codes, the four report headings a role returns |
| L6 | `face/plugins/gravit.js` (new) | §5.1: config validation, `deployment:today`, `gravit:cycle`, `gravit:roles`; `tests/gravit-plugin.test.ts` pins the section names and orders against the installed `dsh-system-prompt` the way `bot-plugin.test.ts` pins `PERSONA_PREFIX_SECTION` |
| L5 | `roles/_template/`, `roles/screener/`, `roles/backtester/`, `roles/reviewer/` (new) | §5.2–§5.3 |
| L5 | `face/src/roles.ts` (new) | `readRoles(root)`, `renderGravitComposition(cycle, roles)`, the grammar checks, the `mcp__*__` expansion or its deferral to the row (§11 (a)) |
| L5 | `face/scripts/render-roles.ts` (new); `bots/gravit/agent.cordis.yml`, `bots/gravit/preset.yml` | the mirror and its header; the preset description ("the principal agent: the host composition plus the role library") |
| L5 | `face/src/bot-presets.ts` `definitionFor`; `face/src/overlay.ts` | `definitionFor` accepts pre-rendered rows for the default; the overlay comment and `DEFAULT_PRESET` text |
| L5 | `face/src/bots.ts` | `isDefault` row text; `RESERVED_IDS` unchanged after the rename |
| Tests | `face/tests/overlay.test.ts`, `bot-presets.test.ts`, `boot.test.ts`, `bots-smoke.test.ts` | the default preset is no longer `plugins: []`; the new invariant (§5.1) |
| Tests | `face/tests/roles.test.ts`, `gravit-plugin.test.ts`, `roles-smoke.test.ts`, `instructions-smoke.test.ts` (new) | §9 |
| Tests | `face/tests/room-smoke.test.ts`, `subagents-smoke.test.ts`, `channelName.test.ts` | their `AGENTS.md` fixtures and comments become `GRAVIT.md` |
| Docs | `Gravit-Design.md`, `DEVELOPMENT.md`, `dsh/README.md`, `face/README.md`, `ROADMAP.md`, `docs/dsh-upgrade-guide.md` | §10 and B10 |

Nothing under `alpaca_kit/`, `strategies/_template/`, `bots/<voice>/` or `face/client/` changes.

## 9. Tests, drills, measurement

**Offline (`npm test`, `npm run typecheck`, `python -m pytest`):**
- `roles.test.ts`: `_template` skipped; a role id outside the grammar refused with the path; a
  `ROLE.md` with `{{` refused; the rendered composition equals the committed mirror (drift
  fails); `mcp__*__` entries kept verbatim or expanded per §11 (a).
- `gravit-plugin.test.ts`: config validation; the three section names and their orders; the
  `today` text shape; `interpolate: false` on all three.
- `boot.test.ts`: `composeFace` emits the `agent-instructions` patch with both candidate lists
  and `maxBytes`, and emits nothing when the row is absent from the bundle composition (the
  guard); the default preset row equals the rendered composition.
- `policy.test.ts`: unchanged — the patch is the face's contract, not a policy default, so it
  composes with the overlay and an operator row cannot silently undo it; `PATCH_HEADER` names it.

**Real boots (`FACE_SMOKE=1 npm test`, stub LLM):**
- `instructions-smoke.test.ts`: a tree whose root has `GRAVIT.md`, `AGENTS.md` and `CLAUDE.md`
  with distinct markers: the first request's instructions baseline carries only `GRAVIT.md`'s;
  a channel session also gets `strategies/<name>/GRAVIT.md`; a bot session gets the same chain.
- `roles-smoke.test.ts`: a Gravit session's schemas contain `role_screener`, `role_backtester`,
  `role_reviewer`; a bot session's do not; one `role_reviewer` call under the stub LLM creates a
  child whose schemas contain none of `bash`, `write`, `ask_user_question`, `mcp__*__account`,
  `role_*`, and whose first request carries the role persona and not Gravit's; a role row that
  cannot mount refuses the boot with its id in the diagnostic.

**Live drills (`face/README.md`, scratch home, real keys):**
- The role drill: from the `room-drill` channel, one `role_screener` run on the 2yr bed for one
  day inside the warmup-safe window; the face's child history shows the child, its tool list
  (plugin panel) excludes the account and order tools, and its report carries the four headings.
- The cycle drill: a scratch strategy copied from `_template`, one operator message, one ask
  answered, then the cycle to a verdict within the caps; `status.yaml`, `journal.md`,
  `backtests/` present; the goal complete or blocked with a named code; the session's usage
  copied into the journal. Measured, not asserted: wall time, rounds used, children used, usage.
- The measurement: the first-request numbers of §7 re-read from the projection cache
  (`contextBreakdown`, `tokenUsage`) for a Gravit session and for one role child, before and
  after, recorded in `DEVELOPMENT.md` §4.3 beside the 2026-10-10 figures.

## 10. Charter and `DEVELOPMENT.md` amendments

**`Gravit-Design.md`** (the operator approves these by approving this spec; the exact edits
land in plan 3):
- §1 "What it is not": "Nothing runs unattended" → "Nothing *starts* unattended. A research
  cycle the operator starts runs to its verdict inside its strategy directory without further
  attention; the operator judges it afterwards from the journal and the diff."
- §1 the second paragraph: the roles join bots and temporary subagents as the third kind of
  execution context ("One principal agent does not mean only one execution context").
- §3 the architecture: the KAIROS/GRAVIT row gains "runs research cycles · delegates to the
  role library".
- §4 the write map: a new row — `roles/<id>/` and `dsh/profile/cycle.md`: operator by file
  edit; Gravit proposes, never authors; git and the drift test. The `strategies/` row's writer
  reads "Gravit, including the role children it delegates to under inherited permissions".
- §5 D5: the trigger adds "or the first cycle whose usage surprises the operator"; D14 reads
  "structured room evidence, child-task results **and role reports** have no independent
  verification". A new debt **D16**: the per-cycle child cap is a journal count, not a
  threshold (Rule 1); due at the first overrun.
- §7.2: the role library described in one paragraph as the prebuilt form of the delegated
  task: a role is a persona plus an allow-list the backend enforces, never a bot and never a
  journal.
- §8 revisit triggers: "a role is given a bot's tools, the account tools, or `ask_user_question`"
  reopens §5.3, D12 and the order drill.

**`DEVELOPMENT.md`:** §3.3 becomes "`GRAVIT.md`" (what it carries, that `AGENTS.md` and
`CLAUDE.md` are not in the chain, the local overlay); §3.6 gains the `role_*` rows and the
table's "registered tree-wide" sentence gets its exception; a new §3.8 "The role directory
contract"; §4.3 gains the `agent-instructions` patch and the generated default preset; §4.5 the
mirror file; §7.3–§7.4 the new tests and drills; §9 three residuals (the child cap is a count,
the schema block is unmeasured per tool, the goal resume path); §10 the measured follow-ups.
`dsh/README.md` gains the rows and the `GRAVIT.md` note; `face/README.md` the two drills;
`ROADMAP.md`'s built log the entry. `CLAUDE.md` per §4.3.

## 11. Verifications owed before plan 1 starts (spikes, each an hour at most)

- **(a) `toolFilter` and `persona` on a `dsh-tool-subagent` row over the `spawn` backend.**
  Read `dsh-subagent-in-process-driver` and `dsh-tool-subagent` sources: the `toolFilter`
  shape (allow, deny, or both; exact names or patterns; whether `mcp__*__` must be expanded
  by the face at render time, which then needs re-rendering on `tools/change` as `bot.js`
  does), and whether the row's `persona` registers a scoped `deployment:persona-prefix` that
  shadows the global prefix for the child. If it does not shadow, Gravit's prefix moves into
  `gravit.js` as a scoped section and `composeFace` sets `personaPrefix: ''`; §5.4's rule holds
  either way.
- **(b) a preset-scoped tool row at declaration time.** That `preset-gravit`'s role rows
  activate in the static overlay row (the `spawn` provider is a host row of dsh-base, so it
  exists; the question is ordering under eager activation) and that `bootFace`'s audit sees a
  broken role row.
- **(c) `agent-instructions` at 0.2.0-rc.2** accepts `instructionFileCandidates` and
  `localInstructionFileCandidates` as the README states, and the user-global
  `$DSH_HOME/AGENTS.md` is or is not renamed by the same key (the 2026-10-14 version check
  found 0.2.1-alpha.3 moves that file behind `DSH_AGENTS_HOME`; the guide records both).
- **(d) section orders**: the first-party tail orders `getSectionOrder` allocates, so
  `gravit:cycle` and `gravit:roles` land after the tool sections and before `personaSuffix`.
- **(e) resuming a goal from the face** after a restart: whether the model's own `update_goal`
  counts as the "explicit human-authorized resume" dsh requires, or the face must carry
  `/goal resume` (dsh's `command-goal` row is mounted; the face's client sends no slash
  commands today).
- **(f) a 24-round cycle under compaction**: that `compaction-basic` + the tool-result pruner
  keep the journal and artifact paths in view across rounds (the pruner trims tool results above
  8,192 characters to head 4,096 + tail 1,024 once compaction triggers — role reports stay under
  that by their four-heading shape).

### 11.1 Answers (2026-10-18, from the installed dsh 0.2.0-rc.2 `lib/`)

- **(a)** `toolFilter` is `{ allow?: string[]; deny?: string[] }` of **exact global tool
  names** — no patterns — applied as `childCtx.tools.restrict()` in the child's creation
  window, so an unknown name fails the delegation, not the row mount. Role allow-lists are
  therefore written as exact names (`mcp__alpaca-kit__screen`), the operator's server name
  included; a disconnected server fails every delegation that names its tools, loudly. The row's
  `persona` registers a child-scoped `deployment:persona-prefix` at order 0 that shadows both the
  deployment persona and a preset's — §5.4's rule holds with no change to `composeFace`. The
  spawn backend declares `persona`, `toolFilter`, `agentOptions`, `outputSchema`, `depthLimit`.
  Correction to §5.1 and §5.4: a child **joins Gravit's preset** (`agentPresets.composeFrom`), so
  it sees the preset layer's `role_*` tools and `gravit:*` sections unless the role's allow-list
  omits the tools (it does) and the sections resolve to empty text for delegated children
  (`gravit.js` returns `""` when the assembled agent's session `origin` is `subagent`).
  `dsh-tool-subagent` has no description key; the `gravit:roles` section carries the summaries.
- **(b)** The registry's mount audit rejects failed rows and services leaked into the root
  realm; a `dsh-tool-subagent` row provides no service and passes. A failed row marks the preset
  `broken`, every `session/create` on it fails `agent-preset/invalid`, and `bootFace`'s roster
  audit refuses the boot — the fail-loud contract stands.
- **(c)** `instructionFileCandidates` and `localInstructionFileCandidates` are real keys with the
  defaults the README states (candidates with a path separator are dropped); the user-global file
  is hard-coded `$DSH_HOME/AGENTS.md`; changing the candidates changes the baseline identity, so
  resumed sessions get one replacement baseline.
- **(d)** Orders: `DEPLOYMENT_PERSONA_PREFIX` 0, `PLAN_POLICY` 500, the tool sections 1000–3000
  (`TOOL_SUBAGENT` 2800), `MCP_SERVERS` 3100, `HARNESS_SOURCE` 10000, `WEB_SURFACE` 10100,
  `DEPLOYMENT_PERSONA_SUFFIX` 10200. `Section.text` is `string | (context) => string`;
  `interpolate: false` is honoured. `deployment:today` sits at 1, `gravit:roles` at
  `TOOL_SUBAGENT + 1`, `gravit:cycle` at `DEPLOYMENT_PERSONA_SUFFIX − 50`.
- **(e)** Nothing re-arms a goal after a restart by itself. The model's `update_goal
  {action: "resume"}` is accepted only inside a direct human turn on a root agent, which is
  exactly the operator's next message in the channel; a *paused* goal is the operator's alone
  (`/goal resume`). The tools are `get_goal`, `create_goal(objective, max_goal_rounds)`,
  `update_goal(goal_id, revision, action ∈ edit|pause|resume|complete|blocked, …)`; the blocked
  `code` on the model path is always `model-reported`, so §6's vocabulary (`child-limit`,
  `bed-window`, `data-missing`, `needs-operator`) is the first word of `blocked_reason`;
  `round-limit` is the driver's own code. An automatic round may not block before round 3.
- **(f)** unchanged: the cycle drill measures it.

## 12. Plans, in order

0. **The rename** — the other arc's spec and branch; this branch rebases onto it.
1. **The map and the seam** — `GRAVIT.md`, the `agent-instructions` patch, `AGENTS.md` and
   `CLAUDE.md`, `persona.md`'s two edits, `gravit.js` with `deployment:today` only, the
   instructions smoke, the first measurement. Small, shippable alone, and it alone removes
   10 KB from every first request.
2. **The role library** — `roles/`, `roles.ts`, the generated composition and its mirror,
   `gravit.js`'s role sections, the four moved tests, `roles-smoke`, the role drill.
3. **The cycle** — `cycle.md` and `gravit:cycle`, the cycle drill on a scratch strategy, the
   measurement, the charter and `DEVELOPMENT.md` amendments, the upgrade guide's new seams.

Each plan is one reviewable change on this branch; merging to `main` is the operator's word,
as always. The upgrade guide (B10) is written in this arc from the seam inventory and does not
wait for plan 3; plans 1–3 each append their seams to it.

## 13. Known issues recorded here, not fixed here

- The persona's mechanics paragraphs (dispatch protocol, subagent habits) and its 3 KB size:
  the next round (B6), with dsh's three homes for them — the tool's own description, a section
  the face adds only where it applies, an on-demand skill.
- The style pack: `doctrine` is 12,971 bytes and the tool-result pruner trims any tool result
  above 8,192 characters to head and tail once compaction triggers, so under context pressure
  Gravit keeps the first third and the last tenth of the operator's doctrine. The memory round
  owns this.
- Rooms, from the 2026-10-10 trace: answers reach Gravit unattributed (the voice's name is only
  in `source`); bots run at effort `high` because `selectionFor` copies provider and model
  only; bot prompts carry tool sections for tools the mask hides.
- Gravit's tool roster: 32,003 tokens of schemas per request, attribution owed (§7).
- `x-deepseek-harness-user-id` is sent on every request regardless of the telemetry rows;
  `web_search` hard-codes `deepseek-v4-flash`; an `agent_<bin>` cut-off throws where
  `DEVELOPMENT.md` §6.5 says partial result. Not this design's; listed so the guide carries them.
