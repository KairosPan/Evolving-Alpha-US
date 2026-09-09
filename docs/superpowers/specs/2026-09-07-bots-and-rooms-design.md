# Bots and Rooms — Design

**Status:** design, awaiting operator review. Not built. Extends the channels design
(`2026-09-03-channels-design.md`) and amends the charter (§10). Revised 2026-09-07 after a
three-verifier pass (83 citations confirmed, 25 corrected, 6 contradictions and 11 ambiguities
resolved — the record is in §15).
**Pins:** face at `feat/order-approval-gate` @ `989ead5` working tree; dsh `0.1.1-rc.2` (the face's
two pins); the research input is `docs/research/2026-09-05-bot-mode-designs.md` (frozen, verified).
**Language of citations:** `pkg/…:line` cites the vendored dsh package under
`face/node_modules/@deepseek-ai/`; `cli:…` cites the installed dsh CLI under
`~/.local/lib/node_modules/@deepseek-ai/dsh/`; bare paths are this repository. Every substrate claim
is cited to source or marked **[spike Sn]** — a claim the plan verifies before code depends on it.

---

## 1. Context and decision history

The channels design gave every strategy directory a channel: many sessions, a landing page, and a
roster of local CLIs that Kairos may call as tools. The operator's next request, on 2026-09-06, was
the effect the channel does not yet produce: *"我对某只股票感兴趣，开一个 channel，拉几个 agent
进来，我会希望这些 agent 都能给出自己的观点，然后我再和他们讨论。"* Several distinct agents in one
room — a Buffett-type, a speculator-type — each speaking in its own voice, the operator arguing with
them, and Kairos organizing the exchange.

The decisions were taken one at a time, each after the substrate had been read, and are recorded in
the order taken because later ones depend on earlier ones.

1. **Multi-session per channel stays.** No canonical "forever conversation" per channel (research
   doc 9.3-1: closed, no). Kairos remains the principal agent.
2. **"A + C": one hand, many voices, Kairos moderates.** Kairos is the only agent whose composition
   carries the account tools and whose sessions may write a strategy directory; it is also the
   room's organizer. Other bots are peers in discussion, may be addressed directly by the operator,
   and never adjudicate.
3. **Runtime is dsh.** Bots are dsh agents, not external CLIs. The existing `agent_<bin>` tools
   stay what they are — callable tools, not voices.
4. **Symmetric substrate, asymmetry as configuration, account guarded by Gate 2.** Every bot runs
   on the tree Kairos runs on; what differs is per-bot configuration (tool mask, sandbox mode,
   persona). Hermes does this per profile; Grok describes it ("It has its own computer and
   tools"); neither has a privileged bot. Gate 2's `tools.guard` is tree-wide, so a bot's order
   attempt meets the same card and the same log check as Kairos's.
5. **A bot is a global entity.** One Buffett across every channel, with a home (a 1:1 conversation
   attached to no channel). Its memory is its own dsh sessions — no new store (§7 records where
   this falls short of the decision's letter).
6. **Bots are authored by the operator only.** A bot is a git-versioned directory in this
   repository, copied from a template, the way strategies are. Kairos may propose a bot in prose; it
   never creates or edits one (Rule 7).
7. **Kairos is the host plane; a bot is an agent-plane plugin composition — a dsh *preset*.** dsh
   has the primitive (`dsh-agent-presets`); the face does not mount it today. Kairos keeps the
   tree's global tool roster and gets the global deployment persona; a bot's preset *shadows* that
   persona and *masks* those tools. "Kairos is the default; a bot is a mask."
8. **Kairos organizes the room through one tool, `dispatch`.** Who answers, in what mode
   (parallel or serial), in what order, with what brief — Kairos decides. The face executes the
   decision and records it. The operator's `@` bypasses Kairos deterministically.
9. **The room log is Kairos's session in the channel.** Bot utterances enter it as sourced
   user-role messages; room facts enter it as room events. No face-owned room file (Rule 8; dsh's
   log-is-truth).
10. **The client shows who is preparing an answer**: a participants strip fed by a projection unit
    on the room session.
11. **Charter §7.1 is amended** ("No second agent" → "No privileged second agent"), merged wording
    in §10, agreed 2026-09-07.

Two research findings shaped the shape rather than the decisions. Hermes's group room is a
client-owned log plus one hidden session per member, driven by the client — and dsh forces the same
shape on us for a different reason: an agent's identity is fused with its session
(`dsh-agent/lib/index.js:603`: ``agent id "${id}" does not match session id``), so N bots in one
room are N sessions by construction. And Hermes's bot-to-bot messaging went from a shell recipe in
`SOUL.md` (injectable through `$(...)`) to a typed, title-gated tool in five days; we start on the
typed side.

## 2. What a bot is

### 2.1 On disk

```
bots/
  _template/                # the copy source (leading underscore: invisible to dsh discovery, see below)
  buffett/
    agent.cordis.yml        # the composition: persona row, mask row, skill root — the dsh preset
    preset.yml              # display metadata: name, description (+ face-only keys, §2.1.1)
    SOUL.md                 # who this bot is — the SOURCE of the persona text (§2.2, S1)
    skills/                 # the bot's stance pack (operator-authored; a dsh skill root)
    journal/                # the only directory the bot may write, and only from its home (§7)
      notes.md
```

- The directory name is the bot id and must match dsh's preset-id grammar `[a-z0-9][a-z0-9-]*`
  (`dsh-agent-presets/README.md:11`). `_template` therefore never appears on any roster — the same
  line says a directory outside the grammar "is skipped outright". The face's "New bot" form takes a
  **display name** (any script, stored in `preset.yml`) and an **id** it proposes from the name by
  lowercasing, transliterating nothing, and dropping every character outside the grammar (a name
  with no ASCII letters yields an empty proposal and the field must be typed); this is *in the
  spirit of* the channel create box's space fold (`face/client/channelName.js:39-44`), not the same
  function — that one folds whitespace only and admits Chinese.
- `bots/` is a `dsh-agent-presets` root with `trust: user`; the face mounts the roster with
  `includeUserRoot: false` so the operator's harness home cannot add a bot the repository does not
  carry (`dsh-agent-presets/README.md:89, 100`). A directory that appears while the face runs is
  visible on the next listing (`:11`, "Discovery is unmemoized").
- A broken directory (unparsable YAML, missing composition) is **listed with its reason, not
  skipped** — dsh does this itself (`:11`) and the roster page shows it (Rule 5).
- Authoring is copy-only: the form copies `bots/_template` with the face's own filesystem write
  and rewrites `preset.yml`, `SOUL.md` and — see S1 — the persona row's text. Not
  `ctx.agentPresets.copy()`: that service copies within *its* roots and re-tightens the tree to
  owner-only permissions (`README.md:55, 61`), wrong for a git-tracked directory.
- Deleting a bot is `git rm -r bots/<id>` by the operator. No delete button in v1: a bot with
  sessions behind it is history, and git is the ledger and the rollback (charter §7.2). A member
  session whose preset is gone is reported on resume with a visible refusal line, never silently
  skipped (§4.7).

#### 2.1.1 `preset.yml` schema

```yaml
name: 巴菲特型            # display name (dsh reads this)
description: 一句话立场   # dsh reads this
model: deepseek-official/deepseek-v4-flash   # face-only, optional (§2.5)
```

dsh's reader keeps only `name`, `description`, `order` and drops every other key
(`dsh-agent-presets/lib/index.js:60-69`), so the face-only `model:` is harmless to dsh; `README.md:80`
("display text ONLY") describes what dsh consumes, not what the file may contain.

### 2.2 The composition (`agent.cordis.yml`)

Modeled on the CLI's shipped `standard` preset (`cli:config/agent-presets/standard/agent.cordis.yml`,
persona row at `:24-28`), reduced to what a *voice* on an already-composed tree needs:

```yaml
# Persona: shadows the deployment persona (Kairos) for agents joined to this preset.
# `text` is WRITTEN BY THE FACE from SOUL.md on every save (S1); do not hand-edit.
- id: persona
  name: '@deepseek-ai/dsh-persona'
  config:
    text: |
      <contents of SOUL.md, with `{{` escaped — see S1>

# Mask: what this bot does NOT see of the global tool roster. Visibility, not authority (D12).
- id: mask
  name: 'kairos-face/bot-mask'
  config:
    deny: [...]            # the template's default list, §2.2.1

# The bot's own skills (its stance), layered on the tree's global skill catalog.
- id: skills
  name: '@deepseek-ai/dsh-skill-filesystem'
  config:
    customSkillDirs: ['./skills']   # relative paths resolve from the preset directory (dsh-agent-presets/README.md:67)
    includeDefaultRoots: false       # the host row already scans project and user roots
```

The `agent-instructions` row is **not** copied from `standard`: it is a host-plane row in dsh-base
(`dsh-base/cordis.patch.yml:232-233`), so every bot inherits the `AGENTS.md` chain for its `cwd`
without a preset row.

#### 2.2.1 The template's default mask

The mask is a **capability menu**; file writes are governed by the sandbox mode (§2.4), not by the
mask, so filesystem tools are *not* denied. Denied by default (exact names are read from
`ctx.tools.schemas()` at spike time and pinned by test):

- `dispatch` — orchestration is Kairos's (§4.3).
- every account/order tool the `alpaca-kit` MCP row exposes under `mcp__<server>__` (`place_order`,
  `cancel_order`, `orders`, the account and positions reads) — a voice reads the market, not the
  account.
- `subagent`, `subagent_fork`, the subagent control/list tools, `workflow`, `ralph`, `goal`, `todo`
  — no delegation or long-running machinery for a voice in v1.
- every `agent_<bin>` tool — a bot does not spend the operator's CLI subscriptions.

Kept: the shell, the filesystem read and edit tools, search, web, skills, `ask_user_question`, the
market-data MCP tools. The mask applies to **every session of that bot** (home and room alike) — it
is a preset-layer registration (S2) — which is why writes are fenced by the sandbox, not the mask.

#### 2.2.2 Spikes this file depends on

- **[spike S1] Persona text from `SOUL.md`.** The verifier's reading makes the `!!js` route
  unlikely: the loader evaluates `!!js` as `new Function("ctx","expr", with(ctx){ return eval(expr) })`
  over the loader Context (`cordis-plugin-loader/lib/index.js:289-293`) inside an ESM package, so
  neither `require` nor `__dirname` is in scope. **The design therefore takes the fallback as
  primary**: the "New bot" form (and every later save of `SOUL.md` through the face) writes
  `SOUL.md`'s contents into the persona row's `text`. `SOUL.md` is the source; the YAML carries a
  derived copy, labeled as such in the template. Two consequences: (a) `text` is a strict
  `{{…}}` template with no escape (`dsh-system-prompt/README.md:13, 88`), so the form rejects a
  `SOUL.md` containing `{{` (a bot's persona has no business interpolating variables); (b) a hand
  edit to `SOUL.md` outside the face reaches nothing until the face rewrites the YAML — recorded
  in R4. S1 remains a spike only to confirm the negative and close the door.
- **[spike S2] `ctx.tools.restrict()` from a preset row masks every joined agent.** Supporting
  evidence beyond the README: `restrict()` requires only a scoped context
  (`dsh-tools/lib/index.js:2780-2781`), and the agent's view admits an inherited tool only if every
  layer on its scope chain admits it (`:2846-2858`); preset rows register "into the calling
  context's scope layer — so the standing mount's contributions land in the PRESET's layer"
  (`dsh-agent-presets/README.md:7`). `kairos-face/bot-mask` is a ~20-line face-owned cordis plugin
  whose body is `ctx.tools.restrict({ deny })`; dsh ships no config-driven mask row. Pass:
  `ctx.tools.schemas(botAgentScope)` omits every denied name; `ctx.tools.schemas(kairosAgentScope)`
  includes them.
- **[spike S3] The `kairos` default preset is inert.** `dsh-agent-presets` requires a `default`
  (`README.md:88`). An empty composition is **not** `broken` at discovery (`lib/index.js:173-183`
  loops over rows with no length check), so `bots/kairos/agent.cordis.yml` may be `[]`. But once a
  roster is mounted the plugin warns on every `agent/created` that did not join a preset
  (`lib/index.js:863-867`), so **every Kairos session must actually join `kairos`** — see S6. Pass:
  `tools.schemas(kairosAgent)` before and after the mount are identical sets (the count is
  re-measured at spike time; the "35 tools" in `face/src/overlay.ts:75` predates `tool-ask-user` and
  the `agent_<bin>` rows).
- **[spike S6] How the face composes a bot session in-process.** `meta.agentPreset` on
  `CreateSessionOptions` only **records** the preset on the header
  (`dsh-session/lib/types/types.d.ts:98`); the **join** is `ctx.agentPresets.mount(agentCtx, id)`
  called from the `setup` hook passed to `ctx.agents.create` — "the one supported call site"
  (`dsh-agent-presets/README.md:31`) — which the gateway does in its `composeAgent`
  (`dsh-host-apiproxy/lib/index.js:1754-1767, 2109-2117`), where it also installs the model
  selection. The room plugin must either reach the gateway's own create path in-process or
  replicate that `setup` (mount + model selection + the permission-preset pin of §2.4). Pass: a bot
  session created by the plugin shows the bot's persona section and mask in its first assembled
  prompt, `agentPreset` on its header, and no "published without joining" warning.

Reference plugins not in the face's bundle today: `@deepseek-ai/dsh-persona` (absent from
`face/node_modules`; present in the CLI's tree at `0.1.1-rc.2`, `cli:node_modules/@deepseek-ai/dsh-persona/package.json:4`;
its README notes it must mount inside an agent scope or it collides with the registry's own
`deployment:persona`) and the face's own `kairos-face/bot-mask`. `dsh-agent-presets` and
`dsh-skill-filesystem` are already in the bundle.

### 2.3 Kairos: the host plane, finally named

Kairos is the tree — dsh-base's tool rows, the operator's `alpaca-kit` MCP row, the face overlay's
`tool-ask-user`, order gate and `dispatch`. Decision 7 adds one config value: the `system-prompt`
row's `persona` — "The global deployment-persona default: the ONE config-authored prompt fragment,
rendered as the order-0 `deployment:persona` section unless an agent-scoped contribution shadows it"
(`dsh-system-prompt/README.md:13`). Its text is `dsh/profile/persona.md`, read by the face overlay
at boot (the same `{{` caveat as S1). **This closes D11** — the model has never been told it is
Kairos (`face/README.md:343-346`) — and it is the same mechanism a bot uses to be told who *it* is:
"creator plugins may register agent-scoped shadows" (`README.md:87`), which is what a bot's
`dsh-persona` row does.

### 2.4 Per-session configuration a bot session gets at creation

| Field | Bot **room** session | Bot **home** session | Kairos session (unchanged) |
|---|---|---|---|
| `meta.agentPreset` (`types.d.ts:98`) + the S6 join | the bot id | the bot id | `kairos` (S3) |
| `meta.cwd` (`:92`) | the channel directory | **`bots/<id>/journal/`** | channel dir or picked cwd |
| `meta.parentSession` (`:93`; header `:54`; folded by the store `:81-82`) | the room session id | absent | absent |
| permission preset — set by the face **immediately after creation** via `ctx.permissionPresets.set(session, name)`, a durable log event (`dsh-permission-presets/README.md:7`) | **`read-only`** (dsh-base's table: sandbox `read-only` + approval `ask`, `dsh-base/cordis.patch.yml:196-199`) | `workspace-write` | `workspace-write` (today's default) |
| model | `preset.yml` `model:` if a configured route serves it, else the default (§2.5) | same | default |

There is no per-session permission selector at creation — `CreateSessionOptions.meta` carries
none (`types.d.ts:91-99`) and creation pins only the deployment/user default
(`dsh-permission-presets/README.md:9`) — hence the explicit `set()` right after; the window between
create and `set` is closed by not delivering the first prompt until `set` has logged.

The permission row is the load-bearing one. Under `read-only` the sandbox is `(deny file-write*)`
plus allow-lists (`dsh-sandbox-local/README.md:15`); the mode is resolved per call from the
session's own `sandbox/mode` events (`dsh-sandbox-policy/README.md:18, 29`). **A bot in a room does
not write files** — not by mask but by the sandbox mode logged into its session, enforced below the
shell (Rule 2). One honest edge, **[spike S4]**: `dsh-sandbox-policy/README.md:18` says "An explicit
approved mode outranks the session's last `sandbox/mode` event", and tool owners "retain
operation-specific denial and escalation guidance" (`:20`) — under approval policy `ask` a denied
write may surface as an **escalation card** the operator can grant. That is acceptable and stays
inside Rule 2 (the exception is a logged human decision, on the same wire as every other card, §5);
what is not acceptable is a silent write. S4 pass: a write from a bot room session yields either the
sandbox's denial or a card, and never a changed file without a logged `allowed` decision.

The home session's `cwd` is the bot's **`journal/`** subdirectory, not `bots/<id>/`: `workspace-write`
grants exactly the session's `cwd` (`dsh-sandbox-policy/README.md:14, 18`), and a bot that could
write `bots/<id>/` could rewrite its own `SOUL.md`, mask and skills — bots authored by bots (decision
6, §11). The `AGENTS.md` chain still reaches a `journal/` cwd from the repository root.

**Room membership is a room fact, not a header fact.** `parentSession` is also set by `session.fork`
(`dsh-host-apiproxy/lib/index.js:2703-2705`) and by subagent children (with `origin: 'subagent'`,
`types.d.ts:96`), so it cannot discriminate members by itself. The room plugin appends a
`room/member { bot, sessionId }` event to the **room session's log** when it creates a member session
(§4.1); the channel listing folds a child under its parent only when the parent's log names it, and
counts it there (Rule 5). Forks and subagent children keep today's treatment.

### 2.5 Model diversity — a warning, not a mechanism

Every bot runs on the routes the tree exposes. Today that is one: `dsh-llm-deepseek`'s
`deepseek-official` (`dsh-base/cordis.patch.yml:451`; default model `deepseek-v4-flash`, `:64-67`).
`dsh-llm-pi-ai` is mounted **dormant with zero routes** (`:88-96`); a second model is an
`llm-pi-ai:` section in `$DSH_HOME/settings.yaml` (`:76-77`) with its own key — not a cordis row —
and Codex's OAuth is refused by that adapter (`dsh-llm-pi-ai/README.md:112`); the charter's
subscription-not-API stance for Claude stands. Four voices on one model with four personas will tend
to converge; the design's mitigation is structural — parallel independent first answers (§4.4)
remove anchoring on the first speaker. `preset.yml`'s `model:` is honored via `session.selectModel`
(`dsh-host-apiproxy/README.md:37`) when a route serves it and falls back to the default with a
visible line otherwise. Not built here beyond that.

## 3. Substrate — what is used, what is verified, what is not

| Need | Mechanism | Status |
|---|---|---|
| A bot as a mounted composition | `dsh-agent-presets`: `roots`, `default`, `includeUserRoot` | cited (`README.md:5-11, 84-100`) |
| A session joined to a preset | `agentPresets.mount(agentCtx, id)` in the agent factory `setup`; `meta.agentPreset` records it | cited (`README.md:31`; `types.d.ts:98`) — **[S6]** for the face's own create path |
| Per-bot persona shadowing Kairos's | `dsh-persona` row in the preset; global `persona` config on `system-prompt` | cited (`dsh-system-prompt/README.md:13, 87`) |
| Per-bot tool mask | `ctx.tools.restrict` from the preset's plugin | **[S2]** (lib evidence `dsh-tools/lib/index.js:2780-2781, 2846-2858`) |
| Per-bot file-write fence | `permissionPresets.set(session, 'read-only')` after create; sandbox resolves per call | cited (`dsh-permission-presets/README.md:7`; `dsh-sandbox-policy/README.md:18, 29`) — **[S4]** for the escalation edge |
| Room membership | `room/member` event on the room log + `meta.parentSession` back-pointer | new event; `types.d.ts:93` |
| Bot speech into the room log without waking Kairos; waking it once | `agent.inject` / `agent.followup` | cited (`dsh-agent/README.md:68-70`) — **[S5]** for the "pre-step already claimed" edge (`:70`) |
| Attribution | `MessageSource` is merge-extensible; the room plugin declares `{ kind: 'room', bot, form }` | cited (`dsh-llm/lib/types/message.d.ts:118`) — new code |
| A member's turn end and final text | `turn/end` on the member feed (`dsh-agent/README.md:59`); `assistant/message` events (`dsh-session/lib/types/types.d.ts:279`) | cited; final-text rule in §4.6 |
| Participants state for the client | a `room` projection unit on the room session | cited (`dsh-session-projection/README.md:11, 14, 26`; process-wide unit table `:47`) |
| `dispatch` as a tool only Kairos sees | `ctx.tools.register` from a plain context; bot masks deny it | cited (`dsh-tools/README.md:20, 22`) |
| Gate 2 applies to bots | `tools.guard` from a plain context is global | cited (`dsh-tools/README.md:25`; `face/src/boot.ts:331-338`) |
| Cancel a runaway member turn | `agent.cancel(cause, options?)` | cited (`dsh-agent/README.md:71`) |
| N bots = N sessions | agent id ≡ session id | cited (`dsh-agent/lib/index.js:603`) |

What the substrate refuses, and the design does not attempt: a bot as a **continuable subagent** of
Kairos. Follow-up authority is "the exact live direct parent recorded in the child's durable header"
(`dsh-subagent/README.md:31, 149`), so a global bot reachable from many Kairos sessions cannot be one
Kairos session's child. Subagents stay Kairos's own delegation inside a turn.

## 4. Rooms

### 4.1 What a room is

A room is **an ordinary channel session whose agent is Kairos and which has members.** Nothing is
created to make a session a room. Member sessions are created **lazily, per bot, the first time
that bot is named** — by a `dispatch` or by an operator `@` — with the §2.4 configuration, and a
`room/member { bot, sessionId }` event lands in the room log at that moment. A roster bot never named
has no session; it is a chip in the strip (§6) and a name in the "not called" clause (§4.3), nothing
more. The sidebar shows one session; its members fold under it.

Members are the channel roster's bots. The roster (`$DSH_HOME/face/channels.json`, channels spec §5)
gains `bots: string[]` beside `agents: string[]`; the channel page lists every preset
`ctx.agentPresets.list()` reports and lets the operator check them in. The roster remains **a menu,
not a fence** (channels spec §5, honest limits 1–4 apply verbatim): it decides whom `dispatch` may
name and whom `@` resolves; it contains nothing. A bot id in the file that the mount does not report
is shown as such, not dropped.

### 4.2 What a member sees, and does not

A member's turn receives, as its prompt, the **room delta**: every room-log *message* (operator
prompts, Kairos replies, member answers — not room events) appended since the last one it saw, one
line per entry, attributed —

```
操作员: …
Kairos: …
巴菲特型 (you): …
投机型: …
```

— followed by the brief `dispatch` carried (or nothing, on an `@` turn), and, standing in every
member turn, four rules carried in the turn payload rather than in `SOUL.md` so any bot joins without
a profile edit (Hermes's choice, research doc §4.1):

1. Reply with your view; reply with exactly `(pass)` if you have nothing to add.
2. Your reply text goes to the room verbatim — no preamble, no meta-commentary.
3. You remember this room only; do not claim knowledge of other channels.
4. Address the operator directly when a judgment is theirs to make; write `@<bot>` to pull a peer in.

The cursor "the last one it saw" is a room-log fact: each member turn's start and end are room events
(`room/turn { bot, sessionId, fromSeq, toSeq, ... }`, §4.6), and `fromSeq` for the next turn is the
previous `toSeq`. No face-side cursor file.

A member sees the channel's files through its own tools (its `cwd` is the channel directory, so
`dsh-agent-instructions` hands it the same `AGENTS.md` chain Kairos gets — `dsh-agent-instructions/README.md:5`),
its own member-session history (persistent; resumed on every turn), and nothing else: **not**
another member's tool calls (only final text enters the room log), **not** Kairos's tool calls,
**not** any home conversation.

### 4.3 `dispatch` — the one orchestration handle

Registered by the room plugin in the face overlay, globally, so it is in Kairos's roster; every
bot template's mask denies it. Schema:

```
dispatch({
  to:     string[],                 // bot ids; must be on this channel's roster
  mode:   "parallel" | "serial",
  brief:  string,                   // the question or task for this batch
  reason: string                    // why these, why this mode — lands in the transcript
})
```

Behavior:

- Validates `to` against the roster (a miss returns a structured error naming the roster — the
  `agent_<bin>` refusal's shape, `face/src/agents.ts:457-490`).
- **Returns immediately.** The result text tells the model the batch is running and that it should
  end its turn; a tool result cannot end a turn by itself, so Kairos *may* keep talking or dispatch
  again — that is allowed and counted against the caps. Kairos does not wait.
- **`parallel`**: the face starts every named member's turn at once; each gets the same delta and
  brief and sees none of the others' answers this round.
- **`serial`**: the face runs members in `to` order; each later member's delta includes the earlier
  members' answers this round. Kairos that wants to interject between two speakers dispatches one bot
  per call — each round completion wakes it.
- Every member answer enters the room log as a `user/message` with `source: { kind: 'room', bot,
  form: 'answer' }` via `inject` (non-waking) as it lands, so the operator sees bubbles appear while
  Kairos sleeps.
- **Round end** = every dispatched turn has ended (answered, passed, failed or timed out) **and** the
  peer-`@` continuation queue is drained (§4.4). Then the face appends one `room/round-end
  { outcome: settled | capped, spoke: [...], passed: [...] }` event and `followup`s Kairos once with a
  short user-role message naming who spoke and who passed (continuation answers included; the
  answers themselves are already in the log). If Kairos's turn is still running at that moment, the
  `followup` is a `next-turn` message and lands after its `turn/end` — dsh's own semantics
  (`dsh-agent/README.md:68`), added to S5.
- The dispatch is a `tool/call` event already; the face renders it as one transcript line —
  **"Kairos called 巴菲特型, 投机型 (parallel) — reason. Not called: 宏观型."** "Not called" is roster
  minus `to` (Rule 5).

Dispatch **grants nothing**: a bot's tools are its mask and its sandbox mode; who called it changes
neither. Dispatch is also **not a standing permission**: a member speaks only when dispatched,
operator-`@`'d, or peer-`@`'d (one continuation, §4.4 rule 2).

### 4.4 Who speaks when — the rules that are not Kairos's

Three things are deterministic in the face and never pass through Kairos:

1. **The operator's `@`.** An operator message containing `@<token>` is resolved against the roster
   **by id always, and by display name only when the name is a single token** (a multi-word display
   name is reached by id); unknown tokens and anything not preceded by start-of-line or whitespace
   (an e-mail address) pass through untouched — this design's own rule, patterned on the composer
   anchor `(^|\s)@` in Hermes (research doc §6.1). The message is `inject`ed into the room log as an
   operator-sourced message (non-waking: Kairos is **not** prompted), and each named member's turn
   starts with the **standard delta** (everything since it last saw, ending with this message). A
   message that names a bot is addressed to that bot even if it also contains other text. Kairos
   sees the exchange on its next wake and gets no `followup` for it. If the message names no one, it
   is an ordinary prompt to Kairos's session. An `@` to a member whose turn is running is **queued**
   behind that turn and shown as a pending line, never refused silently. Every operator send — `@`
   or not — resets the caps.
2. **A peer's `@`.** A member answer containing `@<bot>` queues that member for **one continuation
   turn** after the dispatched turns of the round have ended — up to `ROOM_MAX_CONTINUATIONS` per
   round (§4.6), a continuation consuming a message but not a round. Kairos is woken after the
   continuations, not before (§4.3 round end).
3. **Caps.** §4.6.

Everything else — whether to dispatch at all, whom, parallel or serial, the brief — is Kairos's,
guided by its persona and the `dispatch` description. The default the persona carries: *on a fresh
question in a room, let every present member state a view independently before you synthesize.*
Kairos may deviate; the transcript shows it did.

### 4.5 Kairos's synthesis

When the `followup` wakes Kairos it has the whole round in its context as attributed user-role
messages. Its persona asks for the one thing a moderator is for: **name the disagreements**. Its
reply is an ordinary assistant message in the room log. It may dispatch again, within caps.

### 4.6 Caps, timeouts, endings, and the room events

Constants live in one block in the room plugin — one seam for later per-room overrides (Hermes's
practice, research doc §4.1):

| Constant | Value | Meaning |
|---|---|---|
| `ROOM_MAX_ROUNDS` | 3 | dispatch rounds per operator send |
| `ROOM_MAX_CONTINUATIONS` | 2 | peer-`@` continuation turns per round |
| `ROOM_MAX_BOT_MESSAGES` | 10 | member answers (dispatched, continuation, or operator-`@`) per operator send |
| `ROOM_MAX_MEMBERS` | 6 | bots on one channel's roster |
| `ROOM_TURN_TIMEOUT_MS` | 180 000 | base per member turn |
| `ROOM_TURN_HARD_CAP_MS` | 1 200 000 | the deadline extends while the member session reports running **or has a pending gate**, up to this |

- **Final text** of a member turn = the concatenation of the turn's assistant text segments after
  its last tool result (or the whole turn's text when it used no tools). An empty final text is
  `passed`; the `(pass)` regex (`/^\(?\s*pass\s*\)?\.?$/i`, Hermes's) is applied to the final text.
- A member whose turn exceeds the hard cap is **cancelled** (`agent.cancel`, `dsh-agent/README.md:71`)
  and recorded `timed-out`; no late-reply harvest is built.
- A member turn that fails is recorded `failed` with its error class and counts as a pass; the
  round continues. It never becomes a room error.
- Reaching a cap ends the round with outcome **`capped`** — distinct from **`settled`** — because
  "the discussion ended" and "we stopped the discussion" are different facts (Rule 5).
- An operator message that arrives mid-round: running member turns finish (their answers land); no
  further dispatch or continuation from the superseded round is executed; the new message starts
  fresh caps.

**Room events** the plugin appends to the room session's log (whole-value, per
`dsh-session-projection/README.md:26`): `room/member`, `room/dispatch` (mirrors the tool call for
the fold), `room/turn { bot, sessionId, fromSeq, toSeq, state: started | answered | passed | failed |
timed-out, gate?: pending | answered }`, `room/round-end`. Coarse state is therefore in the log;
**fine state** (a member is reasoning / writing / calling a tool) is read live from member-session
feeds by the plugin and never logged. "The room's whole truth is the log" holds for everything a
later reader needs; the strip's fine states are presence, not truth.

### 4.7 Roster changes with sessions behind them

- **Un-checking a bot** from the roster: its member session stays folded and counted under the
  room (Rule 5) with chip state `left`; `dispatch` and `@` no longer resolve it; re-checking resumes
  the same session.
- **A bot whose preset is gone** (`git rm`): resuming its member session is refused with a visible
  line in the room naming the missing preset; the session stays folded and counted.

## 5. The human in the room

- **The operator speaks to the room** by writing in the room session — a prompt to Kairos, or an
  `@` to a member (§4.4).
- **A member asks the operator a question** with the ordinary `ask_user_question`. The card is a
  gate on the *member's* session. Today another session's gate is a `waiting` chip on its sidebar row
  (`face/client/chat.js:588-598`); the room view renders a member's gate **inline in the room,
  attributed**, and answers it against the member's session — Hermes's mirrored clarify (research
  doc §5.1), on dsh's existing gate wire. A pending gate suspends the base timeout but not the hard
  cap (R6), and counts as "running" for the extension rule.
- **A sandbox escalation card from a member** (S4) renders the same way, attributed; a grant is a
  logged decision on that member's session.
- **Gate 2 for a bot.** The order gate has two outcomes, both tree-wide: a call whose raw name
  matches `ORDER_RAW_NAMES` from a session raises the **ask card** (`face/src/orders.ts:107-124`)
  and, without a logged `allowed-once` for that `callId` + tool, is refused by the guard with
  "reached dispatch without a logged allowed-once approval" (`:299-306`); a tool marked
  `(operator-gated)` whose name the gate does not recognise is refused with the `ORDER_RAW_NAMES`
  message. A bot's mask should have denied both; the guard does not rely on the mask. The drill
  gains both cases from a bot session (§8).
- **Needs-you at the index level.** A pending member or Kairos gate marks the **channel row** and
  the **landing page's sessions block**, not only the session row (research doc 9.1-4; Rule 5, P5);
  it clears when answered.

## 6. The client

Everything the client shows about a room derives from the room session's log and one projection
unit; no client-side retention of other sessions' frames is added.

- **Attributed bubbles.** A `user/message` whose `source.kind === 'room'` renders as a bubble with
  the bot's display name and an avatar glyph (a deterministic shape from the id — Grok's and
  Hermes's "recognize a bot peripherally", at the cheapest tier), **not** as the centred note the
  client uses for other non-operator sources (`face/client/chat.js:18-21`).
- **The dispatch line and the round-end line** render as system rows.
- **The participants strip** at the top of a room: one chip per roster member **plus one for
  Kairos**, states read from the `room` projection unit. The unit is registered process-wide, so its
  key appears in every session's snapshot (`dsh-session-projection/README.md:47`); its empty value
  means "not a room" and the strip does not render. States and their sources:

  | State | Source |
  |---|---|
  | idle | roster member, not in the current round (no session, or no `room/turn` open) |
  | organizing (Kairos's chip) | Kairos's turn is running |
  | thinking / writing / tool (member chips) | live: the member session's `reasoning` / `text` / `tool-call` pulses, folded by the plugin into the unit — not logged |
  | waiting for you | `room/turn.gate = pending` |
  | answered / passed / timed-out / failed | `room/turn.state` |
  | left | roster un-checked with a session behind (§4.7) |

  Grok's six-state vocabulary reduced to what dsh emits.

- **No "with whom" column in the channel session picker.** A bot has exactly two session kinds
  (§2.4): room sessions, reached through the room, and its **home**, reached from the roster page.
  A channel-scoped 1:1 with a bot is not a kind this design defines.
- **The roster page** (agent face → Local agents, `face/README.md:360-372`) gains a **Bots**
  section: the presets the mount reports (id, name, description, `broken` reason if any), the **New
  bot** form (display name, proposed id, one-line stance, persona text; copies `bots/_template`,
  writes `preset.yml`, `SOUL.md`, and the persona row — S1), and a link to each bot's home.
  Per-channel check-in stays on the channel page beside the CLI roster.

## 7. Memory — where decision 5 is met, and where it is not

- **Within a channel**, a bot remembers: its member session persists and is resumed on every turn
  (found through the room log's `room/member`). It remembers what it said in this room and what it
  was told.
- **At home**, a bot remembers its home conversations, and may write under
  `bots/<id>/journal/` — its home session is `workspace-write` with that directory as `cwd`, so the
  sandbox grants exactly it. Writes to `../SOUL.md`, `../agent.cordis.yml`, `../skills/` are
  refused by the sandbox (tested, §8). The journal is git-tracked and the operator reads it like any
  other file.
- **Across channels**, a bot does **not** remember. Its persona, stance pack and journal are the only
  cross-channel state, and the first two are the operator's words. dsh has no memory tool; Hermes
  gives each profile a `memories/` directory (research doc §1.1) — a place, which dsh-base does not
  ship.

This is short of decision 5's letter ("remembers arguing about leverage in the other channel").
Recorded as R5 rather than built, per Rule 8: after the rooms have run for some weeks the logs will
show whether a bot's cross-channel recollection was ever *needed*; a bounded `inject` of
`journal/notes.md` at the start of a room turn is the smallest next step and is not taken here.
(Rule 3 of §4.2 is worded for this state; it says nothing about a home the room session cannot see.)

## 8. Testing and drills

**Unit (`node --test`, no boot):**
- `@` resolution: by id; by single-token display name; multi-word display name not matched; unknown
  token and e-mail pass through; several `@` in one message; roster miss.
- `dispatch` argument validation: roster miss names the roster; empty `to`; unknown mode.
- The dispatch transcript line: names `to`, mode, reason, and **roster minus `to`** as "not
  called" (mutation: drop the clause, test fails).
- Delta formatting: attribution lines, `(you)`, `fromSeq`/`toSeq` cursoring from `room/turn`
  events; **serial** accumulation (later member sees earlier answers); **parallel** isolation (no
  member sees another's answer this round).
- Final-text rule and `(pass)` detection: text-only turn; tool-using turn (text after last tool
  result); tool-only turn → `passed`.
- Caps: rounds, continuations, messages, members; operator-`@` counts toward messages only;
  `settled` vs `capped`; superseded round; mid-round operator `@` to a running member is queued.
- Deadlines with a fake clock: base timeout; extension while running; extension while a gate is
  pending; hard cap → `agent.cancel` → `timed-out`; `failed` counts as pass and the round continues.
- Peer-`@` continuation: queued, bounded by `ROOM_MAX_CONTINUATIONS`, Kairos woken after.
- The `room` projection fold: whole-value state per member and for Kairos from a synthetic event
  sequence; same-reference rule for unrelated events; empty value on a non-room session.
- Channel listing: a child is folded under a parent only when the parent's log has `room/member`
  for it; a fork with `parentSession` and no such event is not; folded members are counted.
- Roster file: `bots[]` beside `agents[]`; an id the mount does not report is shown, not dropped;
  un-check keeps the session folded with state `left`.
- Bot-id proposal from a display name (ASCII lowercase, grammar-only, empty when nothing survives);
  `SOUL.md` containing `{{` is rejected by the form.

**Smoke (`FACE_SMOKE=1`, one boot, own file):**
- Presets mount: `ctx.agentPresets.list()` reports fixture bots from a temp `bots/` root; a broken
  fixture is listed with a reason; `_template` is absent.
- S2 as a permanent test: a bot session's `tools.schemas()` lacks every denied name; Kairos's has
  them; Kairos's set before and after the mount is identical (S3).
- S6: a bot session created by the plugin carries `agentPreset` on its header, shows the bot's
  persona section in its first assembled prompt, and emits no "published without joining" warning.
- A bot room session logs `permissionPresets/preset = read-only`; a file write from it is refused
  or raises a card, never lands silently (S4). A bot home session writes `journal/notes.md` and is
  refused on `../SOUL.md`.
- A member session is **resumed**, not recreated, across two operator sends (same session id; one
  `room/member`).
- `preset.yml` `model:` naming an unserved route falls back with a visible line; naming the served
  route selects it (`session.models`).
- A member's first turn carries the channel's `AGENTS.md` in its instruction chain.
- `dispatch` is absent from a bot session's schemas and present in Kairos's.
- Gate 2 from a bot session, both outcomes: the stand-in `mcp__drill__place_order` raises the ask
  card and is refused by the guard without a logged approval; a marked unknown-name stand-in is
  refused with the `ORDER_RAW_NAMES` message.
- The whole round in-process with a stub model route: operator prompt → Kairos `dispatch(parallel,
  2 bots)` → two member turns → two `room`-sourced messages → `room/round-end settled` → one
  `followup` → Kairos's synthesis turn. Assert the log sequence and the projection state at each
  step. A variant with a failing stub for one bot: `failed`, round continues, `settled`.
- S5: two `inject`s on an idle Kairos then one `followup` → one turn with three user-role messages
  in order; and a `followup` issued while Kairos's turn is running lands after `turn/end`.

**Live drill (operator, documented in `face/README.md` beside the existing three):** two template
bots on a fresh channel; a question; watch the strip; read the dispatch line; `@` one bot directly;
make a bot ask a question and answer it in the room; make a bot attempt a file write and see the
denial or card; confirm the channel row's needs-you mark appears and clears. PASS criteria are
written as observations.

Mutation checks apply to every load-bearing assertion above: remove the mask and the schema test
fails; remove the `read-only` set and the write test fails; drop "not called" and the line test
fails; drop the `room/member` check and the fold test admits a fork.

## 9. Code changes

| Where | What |
|---|---|
| `face/package.json` | add `@deepseek-ai/dsh-persona` at the pin |
| `face/src/overlay.ts` | mount `@deepseek-ai/dsh-agent-presets` (`roots: [{ path: <repo>/bots, trust: user }]`, `includeUserRoot: false`, `default: kairos`); set `system-prompt.persona` from `dsh/profile/persona.md`; add the `room` plugin row |
| `face/src/room.ts` (new, a cordis plugin) | `dispatch`; member-session create/resume through the S6 path (`permissionPresets.set`, model selection); deltas and cursors; rounds, continuations, caps, deadlines; `inject`/`followup`; the room events; the `room` projection unit; the `room` `MessageSource` |
| `face/src/bot-mask.ts` (new, `kairos-face/bot-mask`) | `ctx.tools.restrict({ deny })` |
| `face/src/roster.ts` | `bots[]` in `channels.json`; reported-but-unlisted ids |
| `face/src/channels.ts` | fold `room/member` children under their room; needs-you mark on the overview |
| `face/src/panels.ts` | Bots section on the agent face; New bot form route (copies `bots/_template`, writes `preset.yml`/`SOUL.md`/persona row, rejects `{{`) |
| `face/client/chat.js`, `render.js` | `room`-sourced bubbles; dispatch/round-end rows; inline member gates and escalation cards; participants strip from the projection; pending-`@` line |
| `face/client/channels.js` | roster check-in for bots; needs-you mark |
| `bots/_template/` (new) | `agent.cordis.yml`, `preset.yml`, `SOUL.md`, `skills/README.md`, `journal/notes.md` |
| `bots/kairos/` (new) | the inert default preset (S3) |
| `dsh/profile/persona.md` (new) | Kairos's deployment persona text |
| `AGENTS.md` | `bots/` joins the never-edit list; what Kairos is told about rooms and `dispatch` |
| `Kairos-Design.md`, `CLAUDE.md`, `DEVELOPMENT.md`, `face/README.md` | §10; the mechanism reference; the drill |

## 10. Charter conformance and the amendment

**§7.1 replaces "No second agent" with (agreed wording, 2026-09-07):**

> - **No privileged second agent.** Teaching, review, and adjudication belong to the operator. One
>   hand, many voices: Kairos is the one agent whose composition carries the account tools and the
>   write to a strategy directory; the operator may roster other agents on a channel — local CLIs as
>   callable tools, operator-authored dsh bots as **discussants** that speak in the room — but a bot
>   is a voice, not a reviewer: what it says is evidence the operator and Kairos weigh, never a
>   verdict, and the conclusion is written by Kairos. Bots run on Kairos's substrate with their tool
>   sets masked by configuration; the mask is a menu (a bot with a shell writes whatever its sandbox
>   mode allows — D12), and the fence around the account is Gate 2, tree-wide, the same for every
>   agent. Kairos's `dispatch` orders the room but grants nothing, and the operator's `@` bypasses
>   it. Bots are authored by the operator, never by Kairos (Rule 7). A voice need not run on this
>   machine: an agent reached over A2A is a voice too — untrusted text in the room log, never a hand
>   in this tree; the moment anything outside this machine can call *in*, §8's last row applies. A
>   reviewer entity with authority would add a plane of machinery to buy safety that already comes
>   from P1.

**Collateral edits, same commit:**
- §1: `one operator, one machine, one agent` → `one operator, one machine, one principal agent`;
  after "The agent, also called Kairos, …" add: "The operator may author further agents — bots — as
  discussants (§7.1); they are voices on Kairos's substrate, not hands."
- `CLAUDE.md:8`: mirror ("one operator, one principal agent (Kairos), and operator-authored bots").
- §5, new **D12**: "Bot tool masks are visibility, not authority. dsh scopes and `tools.restrict`
  are 'live visibility composition, not an authority boundary'; a bot with a shell writes whatever
  its session's sandbox mode allows and reaches whatever the network allows. Held by: the
  `read-only` permission preset logged into every bot room session right after creation (file
  effects, subject to an operator-granted escalation card), the `journal/`-scoped `cwd` of every bot
  home session, Gate 2 tree-wide (the account), and the room transcript naming every dispatch and
  every member not called. Not held by the mask, and not held for the network."
- §5, new **D13**: "Kairos's sessions may have a picked `cwd` at the repository root, which includes
  `bots/`; 'Kairos never edits a bot' is therefore a Rule-7 commitment carried by `AGENTS.md`'s
  never-edit list and review, not by the sandbox."
- §8, new trigger: `A bot's composition is given the account tools, a bot room session is created
  other than read-only, or a bot home session's cwd widens past its journal/` → `§7.1 · D8 · D12 ·
  run the order drill under that bot's preset`.

**How the design meets the rules it touches:**
- **Rule 2:** the write asymmetry for room sessions is the sandbox mode logged per session; the
  account asymmetry is Gate 2's tree-wide guard; the mask is explicitly *not* claimed as
  enforcement, and the escalation edge (S4) is a logged human decision.
- **Rule 3:** §12.
- **Rule 5:** the dispatch line names who was *not* called; `capped` ≠ `settled`; member sessions are
  folded and counted, never hidden; `passed`, `failed`, `timed-out`, `left` are all visible; a
  reported-but-unlisted roster id is shown; a missing preset refuses visibly.
- **Rule 6:** no LLM router in the face, no memory store, no late-reply harvest, no delete button,
  no channel-scoped 1:1 — each deferred until use shows the need.
- **Rule 7:** bots are operator-authored directories; a bot cannot reach its own composition
  (journal-scoped home); Kairos's non-edit is D13.
- **Rule 8:** the room's truth is the session log; the roster stays the existing JSON; no room
  store, no bot memory store.
- **P1:** no bot gets a key; the account gate is unchanged; the harness-home patch stays outside the
  workspace.
- **P2:** bots are teaching material the operator writes; a stance pack is the same kind of thing
  as `style-kairos`.
- **P5:** caps bound what one operator message can cost (≤ 10 bot messages, 3 rounds, 2
  continuations per round); the strip and the needs-you marks put every pending ask where the
  operator looks.

## 11. Not building (this design)

- Bot-to-bot messaging outside a room (Hermes's `message_agent`); a bot's home is the operator's.
- Cross-machine bots, `hermes peer`-style gateways, or any inbound A2A (§8's last row).
- Bots authored or edited by Kairos or by bots.
- A memory store for bots (§7).
- An LLM router in the face; the face's routing is `@` and caps, nothing else.
- Late-reply harvesting after a hard-cap cancellation.
- Room state anywhere but the room session's log.
- A delete-bot button; a bot rename that changes its id.
- A channel-scoped 1:1 session with a bot.
- Model diversity beyond honoring `preset.yml`'s `model:` against configured routes.
- Moving the three face JSON files (`channels.json`, `agents.json`, `archived.json`) into a plugin
  storage domain — a known "not everything is a plugin" remainder, left as is (Rule 6).

## 12. Residuals (Rule 3)

- **R1 — The mask is visibility.** D12. A bot can `curl` the face's loopback routes exactly as
  Kairos can (channels spec §5 honest limit 3; `POST /api/respond` carries no token,
  `face/README.md:734-743`). Bots multiply D10's exposure by N; they do not change its nature.
- **R2 — Dispatch is judgment.** Kairos may under-call or over-call a bot. Mitigations: the
  operator's `@`, the "not called" clause, the persona default. Not eliminated.
- **R3 — Same model, four voices** (§2.5). Convergence risk; mitigated by parallel independent
  first answers; observed, not solved.
- **R4 — Composition edits propagate only through the composition file.** The mount's generation
  stamp watches `agent.cordis.yml` alone (`dsh-agent-presets/README.md:149`), and a superseded
  generation is never reclaimed until restart (`:150`). Because the face writes `SOUL.md` into the
  YAML on every save (S1), a save through the face reaches new sessions; a hand edit to `SOUL.md`
  or `skills/` does not until the face rewrites the YAML or the process restarts. Documented in
  `face/README.md`.
- **R5 — No cross-channel memory** (§7).
- **R6 — A member's pending gate with no client connected** blocks until the hard cap cancels it.
  The approval card's no-client behavior was already documented ("blocks rather than denying");
  S7 measured the question seam and found it identical: `userQuestions.ask()` from an agent-owned
  session with no client neither answers nor rejects, it parks until the caller aborts. It does not
  fail loud. (An agentless *host* ask is the other branch and is rejected up front — no member ever
  takes it.) Recorded in `DEVELOPMENT.md` §9 R11.
- **R7 — The three face JSON files are not plugins** (§11).
- **R8 — Escalation cards** (S4) let the operator grant a room bot a file write; every such grant is
  logged on the member's session. The asymmetry is enforced-with-a-human-exception, not absolute.

## 13. Spikes the plan runs first

| Spike | Question | Pass criterion |
|---|---|---|
| S1 | Confirm `!!js` cannot read a sibling file from a preset composition (expected: cannot) | Negative confirmed → the face-writes-YAML path is the design; positive → note it, keep the face-writes path anyway (the `{{` rejection is needed either way) |
| S2 | Does `tools.restrict` from a preset row mask every joined agent? | `schemas(botAgent)` lacks denied names; `schemas(kairosAgent)` has them |
| S3 | Can `kairos` be an empty composition, and is every Kairos session joined to it? | Face boots; no "published without joining" warning; Kairos's schema set unchanged before/after |
| S4 | Under `read-only` + `ask`, what does a bot's file write produce? | Sandbox denial or an escalation card; never a silent write |
| S5 | `inject` × 2 then `followup` on idle Kairos; `followup` while Kairos runs | One turn, three ordered user-role messages; the running-case `followup` lands after `turn/end` |
| S6 | How does the room plugin create a *composed* bot session in-process? | Header `agentPreset`, persona section present, mask applied, model selected, `read-only` logged before first prompt |
| S7 | Does a pending `ask_user_question` with no client block (like the approval card) or deny? | Recorded in the ask-user drill; R6 worded accordingly |

A failed spike upgrades the path: stop, record, redesign the affected section. None failing
invalidates decisions 1–11; each has a named fallback above.

## 14. Plan decomposition

One spec, four plans, in this order — each independently reviewable and mergeable:

1. **Bots without rooms**: S1–S4, S6, S7; mount presets; Kairos persona (D11 closed); `bot-mask`;
   `bots/_template` and `bots/kairos`; Bots roster page and New bot form; **home sessions**; the
   smoke tests of §8 that need no room. After this plan the operator can create a bot and talk to it
   at home.
2. **The room engine (server)**: `room.ts` — `dispatch`, member sessions, deltas, rounds,
   continuations, caps, deadlines, room events, projection unit; the in-process round smoke; S5.
3. **The room in the client + drills**: bubbles, lines, strip, inline gates, roster check-in,
   needs-you marks; the live drill; `face/README.md`.
4. **The charter and document commit**: §10's amendment and collateral edits; `AGENTS.md`;
   `DEVELOPMENT.md`; `CLAUDE.md`. (Written last so it describes what shipped; the wording is fixed
   now.)

## 15. Verification record

Three verifiers on 2026-09-07 (dsh citations, repository citations, self-review): 83 confirmed;
corrected — 5 misquotes (the `dsh-system-prompt:5` "shadows" quote lived at `:13/:87`; the Grok
"own computer" phrase; `ctx.agentPresets.list()`; the Gate-2 refusal message attribution; the
presets "PRESET's layer" quote), 4 wrong lines (`types.d.ts:93`; channels spec honest limit **3**;
`dsh-agent/README.md:59, 71`; §4.5→§4.4 cross-reference), 10 overstatements (permission preset is
`set()` after create, not a create field; `parentSession` is not exclusive to members; the LLM route
picture; "35 tools"; Kairos "never writes under `bots/`"; R6's citation; the channelName fold;
Hermes's memory "tool"; the e-mail rule's attribution; the immediate-return wording), 6 unsupported
(`dsh-skill-filesystem` config key; untested claims now in §8; `preset.yml` unknown keys, now cited;
the deny list, now enumerated). Contradictions resolved: home write scope (now `journal/`), round-end
vs continuations, `@` delta, strip states vs log truth (coarse events logged, fine states live),
channel-scoped 1:1 (dropped), gate-pending vs hard cap. New spikes from the pass: S6 (the join is not
the header field) and S7. The scope finding produced §14.

---

## 16. Post-build amendments (plan 1)

Plan 1 of §14 — **bots without rooms** — is built (branch `feat/bots-1`, 224 face tests, typecheck
clean). Plans 2–4 are unbuilt and this section does not touch them. What follows is what the build
changed about the design, and what the spikes measured. Everything else in this document stands as
written.

**Deviations from the design.**

1. **One face-owned plugin instead of `@deepseek-ai/dsh-persona` + `kairos-face/bot-mask`.**
   `dsh-persona` is not in the face's bundle; the mask needs a face plugin anyway; and dsh's own
   `dsh-subagent` composes a child exactly this way — a scoped `deployment:persona` section plus
   `tools.restrict`. So `face/plugins/bot.js` (`kairos-bot`) does both, in one row of the
   composition. §2.2's `!!js` reading `SOUL.md` is moot: the face writes the persona text into
   the composition (`renderComposition`), which the spec's own fallback already allowed.
2. **The mask is an `allow` list, not a `deny` list.** dsh-tools: deny masks admit later unnamed
   globals, allow masks exclude later names. TWO of the tools a bot must never have are
   registered *after* the mount — `agent_<bin>` on connect, `dispatch` in plan 2 — and the allow
   form excludes them without naming them, which is the reason for the choice. The third,
   `mcp__…__place_order`, is NOT one of them: the operator's MCP row mounts at boot, so an order
   tool is already in the tree when a bot mounts and is excluded by OMISSION from the list, the
   same way a deny list would have to name it. `mcp__*__<raw>` entries expand against the live
   tree (`expandAllow`), matching dsh's minting exactly — three `__`-separated segments, so a
   longer name merely ending in `__<raw>` does not answer the star; a name the tree does not have
   is warned and dropped rather than passed to `restrict`, which rejects unknown names.
3. **S6 was not needed.** The gateway's `session.create` accepts `agentPreset` and performs the
   mount in its own `setup`, so a home session rides that path straight from the client
   (`openBotHome` → `session.create({ cwd: <journal>, agentPreset })`) with no in-process agent
   creation. S6 moves to plan 2, where member sessions need `parentSession` and the `read-only`
   pin.
4. **The home-scope sandbox test is not in plan 1.** A home session is `workspace-write` with
   `cwd = journal/`, which the sandbox grants by construction; proving that a write to
   `../SOUL.md` is refused needs a bash write through the real sandbox from such a session. S4
   exercises the `read-only` case only. The home-scope case goes to plan 2, beside the
   member-session pin.
5. **The roster root is `trust: "system"`, not §2.1's `user`.** The face authors bots by its own
   filesystem write, so it needs no writable root; `user` trust would arm nothing the face uses
   and three RPCs it does not want — `agentPreset.copy`, `.remove` and `.openDocument`, which the
   gateway serves on `/api` for any connected client, over a git-tracked directory whose delete
   path §2.1 says is `git rm`. Under `system` each refuses with "it ships with the deployment"
   and `authorable` reads false. Trust gates nothing else: `scanRoot` stamps it on the row, and
   mounting never reads it — the roster, the broken reasons and every preset session are
   unchanged (`bots-smoke.test.ts` passes across the flip).

**Spike outcomes** (`FACE_SMOKE=1 npm test`, 2026-09-07).

- **S1 — the path form works, and is what shipped.** The plugin row is a PATH, not a package
  specifier. Real presets carry the relative `../../face/plugins/bot.js` (`BOT_PLUGIN_RELATIVE`),
  which the preset mount resolves from the preset's own directory. BOTH forms are now drilled:
  the smoke's bots root is `mkdtemp`'d inside the repository (`.bots-smoke-*`, gitignored, removed
  in `finally`) so a bot created with an untouched composition mounts through the shipped relative
  path, while one fixture bot keeps an absolute path (`PLUGIN_ABS`) — a temp root two levels above
  nothing cannot reach `face/plugins/`. Mutation-proven: pointing `BOT_PLUGIN_RELATIVE` at a
  missing file fails the smoke with dsh's own `agent-preset-invalid`. The package-specifier
  fallback the spec kept in reserve was never needed. The persona text the face wrote into the
  composition reaches the assembled prompt.
- **S2 — the mask holds, and is exactly `allow ∩ tree`.** The fixture's
  `["bash","read","ask_user_question","no_such_tool"]` yields `[ask_user_question, bash, read]` on
  a bot session. **S3** — Kairos's set equals the host's global view: the inert `kairos` default
  adds and removes nothing.
- **S4 — a sandboxed write is refused inside the tool's content, not as an error.** Observed:

      SANDBOX-DENIED (tool call ok, write refused in content); approval/asked in log: false;
      result: [stderr] bash: <tmp>/s4-should-not-exist.txt: Operation not permitted
      [sandbox: file access denied under read-only mode] [sandbox: escalation available — retry
      this exact comman…

  (the printed result is truncated). So: under `read-only` the call itself is not an error, no
  `approval/asked` is logged, the file does not exist, and the content advertises an escalation
  retry. **D12 in plan 2 must be worded off the tool CONTENT** — "refused in content, escalation
  offered" — not off `isError` and not off a card. Recorded as `DEVELOPMENT.md` §9 R10.
- **S7 — a question with no client blocks.** Observed: `timeout`. `userQuestions.ask()` from an
  agent-owned session with no client connected parks like the approval card until the caller
  aborts; it never answers and never rejects. Also observed: an agentless (host) ask is rejected
  up front with `UserQuestionError: web user interaction requires an agent-owned session`. R6
  above is reworded from this. Recorded as `DEVELOPMENT.md` §9 R11.
- **S5** belongs to the room engine and was not run; it moves to plan 2 with S6.

**Also proven in plan 1: Gate 2 from a bot session** (§8's smoke list), both outcomes, inside
`bots-smoke.test.ts`'s single boot. A fixture bot whose allow list NAMES the stand-in
`mcp__drill__submit_order` — registered before its session so the mask really admits it — still
comes back `isError` with the `ORDER_RAW_NAMES` message and its body never runs; and
`mcp__drill__place_order` fired at the `tools/pre-execute` waterfall with that bot's agent
returns `ask` with a card naming the symbol. So the gate is tree-wide, and the refusal cannot be
credited to the mask. The card itself is still unproven — an ask with no connected client blocks
rather than denying — which is why the ask half goes through the waterfall and not `execute`,
exactly as `order-gate.test.ts` does for Kairos.

**Where the as-built truth now lives.** `face/README.md` "Bots" and "The bots drill";
`DEVELOPMENT.md` §3.7 (the bot directory contract), §4.2/§4.3/§4.4/§4.5 (modules, the
`agent-presets` overlay row, the three routes, `bots/<id>/` as written state), §5.1 (the client
files and the bucket precedence), §7.3/§7.4 (the suite and the drill rows), §8 (the never-edit
list and the mask-is-visibility rule), §9 R6/R10/R11, §10 item 9 (rooms). `AGENTS.md`'s never-edit
line now carries `bots/`. The charter's D11 and §7.1 amendment ride plan 4, as §14 says.

### Plan 2 — the room engine (server)

Built 2026-09-08 on `main` (`face/src/room.ts`, `room-rules.ts`, `room-projection.ts`; 290 face tests, 6 under `FACE_SMOKE=1`; typecheck clean). Plans 3–4 are unbuilt and this block does not touch them.

**Deviations from the design, each forced by a substrate fact measured while planning.**

1. **No `room/*` session events.** `Session.append` accepts any type, but every persistence read runs the log through the generated closed set `KNOWN_SESSION_EVENT_TYPES` and refuses a type outside it unless the event carries `ignorable: true` — which `append` cannot set (`dsh-session-persistence/lib/index.js`, `assertEventsSupported`; `dsh-session/lib/index.js`, `append`). One `room/member` would make the room session unresumable and its cold listing throw. So §2.4's "room membership is a room fact" became a header fact plus the log: a member is a session whose header carries `parentSession = <room>`, no `origin`, and a bot `agentPreset` (forks carry the source's preset, subagent children carry `origin`); the dispatch is the tool's own `tool/call` + `tool/result` (the result text names who was NOT called); a member's answer is a `user/message` on the room session with `source: { kind: 'room', form: 'answer', bot, name, sessionId, turn, round }`; the round end is the waking `user/message` with `form: 'round-end'` carrying every turn's state; the member's cursor is the delta message in ITS log (`form: 'delta'`, `messageIds`). §4.6's event list is retired; the `room` projection unit folds these known events instead (`face/src/room-projection.ts`).
2. **Answers are appended, never injected.** §4.3's "every member answer enters the room log via `inject` as it lands, so the operator sees bubbles appear while Kairos sleeps" does not hold: `inject` splices the inbox, and the `user/message` the client renders lands only when Kairos's next step claims it; an inject on a running driver forces an extra step or opens a stray turn. The engine appends the answer straight onto the room session's log (`surfaceOp: 'append'`) while the log is quiet — no open turn — and otherwise holds it in a per-room outbox flushed at the next `turn/end`. Kairos is woken only by the round-end `followup`, sent in the same synchronous block as the last flush, so the claim is one turn with every answer already above it. S5 was restated for this: proven in `room-smoke.test.ts` (answer before round-end, one `turn/start` for the wake, synthesis inside it).
3. **The `read-only` pin runs inside creation `setup`.** §2.4's create-then-`set` window and its "do not deliver the first prompt until `set` has logged" rule are unnecessary: `permissionPresets.set` on `agentCtx.agent.session` inside `setup` logs `permission/preset` + `sandbox/mode` + `approval/policy` before publication, and `pinInitialPermission` fills only missing facts. The pin is every member session's first event (asserted; a fresh session carries no `session/end-seed` marker — dsh appends it only over a seed).
4. **Fine states are the client's.** The projection registry has no out-of-fold write, so §6's "thinking / writing / tool … folded by the plugin into the unit" cannot be done. The unit carries coarse state (`called`, `answered`, `passed`, `failed`, `timed-out`, the round, `organizing`); plan 3 derives the fine states from the member sessions' own `assistant/chunk` block starts, which the mux already forwards for every live session.
5. **`preset.yml` `model:` is honored through `installModelSelection`, not `session.selectModel`** — the RPC saves the selection as the host-wide default. The route is validated with `llm.resolveCallConfig`; an unserved route falls back to `agentDefaultModel.currentSelection()` with a line in the dispatch result.
6. **A round cut short by a new operator message ends `superseded`**, a third outcome beside `settled` and `capped` (Rule 5).
7. **The hard-cap cancel keeps the inbox** (`cancel(cause, { keepInbox: true })`); dsh clears it by default.
8. **A pending gate is read from the member's log** — an `ask_user_question` call with no result, or an `approval/asked` with no `approval/decided` — because questions leave no session event.
9. **The engine is installed on the root context by `main.ts`, not as a cordis row** (the spec's "room plugin row"): a root-created member is a runtime root, which is what lets it ask the operator a question (`userQuestions.ask` refuses a runtime-owned child with `DELEGATED_CALLER`) and keeps the gateway from fencing its gates as subagent-owned. `dispatch` is registered globally through `ctx.tools.register`; the bots' allow masks exclude it without naming it (plan 1, deviation 2).
10. **The operator's `@` is a face route**, `POST /data/rooms/say`: the client sends a message containing `@` there first; the route resolves mentions deterministically against the roster (by id; by display name only when one token), appends the message to the room as the operator's own (`kind: 'user'`, `mention: [...]`) without waking Kairos, and turns the named members; a message that names nobody comes back `addressed: []` and the client then sends it as an ordinary prompt. A cold room is made live through the gateway's own composition (`apiProxy.sessions.models`), never composed by the face.

**Spike outcomes** (`FACE_SMOKE=1 npm test`, 2026-09-08, `room-smoke.test.ts`).

- **S5** — restated per deviation 2 and proven: two answers appended to a quiet room log, one `followup`, one turn, the synthesis inside it; a `followup` issued while Kairos ran (the dispatch turn) landed after its `turn/end`.
- **S6** — a member created in-process with `meta: { cwd, parentSession, agentPreset }` and a `setup` of `installModelSelection` + `agentPresets.mount` + `permissionPresets.set` carries `agentPreset` and `parentSessionId` on its `session.list` row, shows the bot's persona in its first assembled prompt, lacks `dispatch` in its schemas, and logs `read-only` as its first event; no "published without joining" warning.
- **S4 for a member** — a bash write from a member into its channel directory came back `isError: false` with `[sandbox: file access denied under read-only mode]` in the content and no file (R10 holds in a room).
- **Plan 1's deferral 4 (home scope)** — closed, measured: a home session's bash write to `../SOUL.md` came back `[sandbox: file access denied under workspace-write mode]`, and the file was byte-identical afterward.
- **R13** — with the `session-projection-cache` overlay row, `$DSH_HOME/storages/session_projcache.json` carries the room session after Kairos's first `turn/end`; the `room` value rides the `session.list` row for the room and the members.
- **S8 (new)** — the persistence catalog is closed (deviation 1). Recorded here because the spec's §13 table did not know to ask.

**Where the as-built truth now lives.** `face/src/room.ts` (module header), `room-rules.ts`, `room-projection.ts`; the smoke; plan 3 adds the client and `face/README.md`; plan 4 the reference documents and the charter.

### Plan 3 — the room in the client, and the drills

Built 2026-09-09 on `feat/rooms` (313 face tests; the live drill passed 2026-09-09, recorded in
`face/README.md`). Deviations, each decided by the wire plan 2 left: (1) the dispatch line is the
`dispatch` tool card's own collapsed row — the result text plan 2 wrote carries the spec's facts
(who was called, the mode, who was not) in the engine's own wording (`dispatchResultText`,
`face/src/room-rules.ts`), not the §4.3 line's words; (2) fine states are derived from the member
sessions' own `assistant/chunk` block starts and `turn/*` boundaries, which the mux forwards for
every live session — the unit carries coarse state only; (3) the fold rule is the header rule
(§16 plan-2 block, deviation 1); (4) a member's gate renders inline when its room is on screen,
headed with the bot's name, answered against the member's own session — the wire already
required that. §6's "no with-whom column" holds. The drill's eight parts and the PASS line are
in the README.

### Plan 4 — the charter and the documents

Written 2026-09-09 after plans 2–3 shipped: §10's amendment landed in `Kairos-Design.md` §7.1
verbatim; D11 marked resolved, D12 and D13 added, the §8 trigger added; `CLAUDE.md`, `AGENTS.md`,
`DEVELOPMENT.md` (§3.7, §4.2–4.5, §5.1–5.3, §6.8, §7.3–7.4, §8, §9 R6/R13/R14–R19, §10) and
`ROADMAP.md` describe the tree as built. This document is frozen: its Status line stays as written
and its truth now lives where §16's blocks point.
