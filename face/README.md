# kairos-face — the chat-light face as an in-process dsh host

One Node 22 process. It boots the DeepSeek Harness from the `face` profile
(bundles: `@deepseek-ai/dsh-base` only), inserts its own host rows on top, and
serves the operator's chat UI — and the two read-only instrument pages below —
at http://127.0.0.1:3090/. No build step — `tsx` runs the TypeScript directly.
Specs: `../docs/superpowers/specs/2026-08-30-face-chat-light-design.md` and
`../docs/superpowers/specs/2026-08-31-face-instruments-design.md`.

## Run

```bash
cd face
npm install
npm run setup            # creates $DSH_HOME/profiles/face (never overwrites)
source ../.env.deepseek  # DEEPSEEK_API_KEY - see below
npm start                # http://127.0.0.1:3090/  (profile: face)
```

Without the key the face still boots and serves: sessions list, the UI works,
and the first prompt fails with a missing-credential error from the LLM route.
`../.env.deepseek` is gitignored and not loaded automatically. Equivalently, put
`DEEPSEEK_API_KEY` in `$DSH_HOME/.env` — `bootFace` runs dsh's layered env load
before composing, so the harness home's `.env` reaches the tree too.

A session's project directory is the **workbench repo root**, not `face/`: the
entry `chdir`s there before booting (spec section 3.2), because the pinned
`ApiProxyService` takes that default from `process.cwd()` and offers no config
key. It is also the sandbox's workspace root — so "outside the session
workspace" below means outside the whole repo.

| Env | Default | What |
|---|---|---|
| `FACE_PORT` | `3090` | webserver port. `0` asks the OS for a free one |
| `FACE_PROFILE` | `face` | profile directory name — honored by BOTH `npm run setup` and `npm start` |
| `DSH_HOME` | `~/.dsh` | the harness home: profiles, sessions, storages, credentials |
| `DEEPSEEK_API_KEY` | — | resolved per request through the credential seam, then the environment |
| `DSH_TELEMETRY_DISABLED` | unset | ANY non-empty value (`0` and `false` included) disables the telemetry row |
| `DSH_PERMISSION_MODE` | `workspace-write` | sandbox mode. `danger-full-access` also sets the approval policy to `never` — it DISARMS the Gate-2 surface below |

`FACE_PORT` and `FACE_PROFILE` read an empty value as unset, not as a literal:
`FACE_PROFILE=""` would otherwise resolve to `$DSH_HOME/profiles` itself, and
`FACE_PORT=""` is `Number("") === 0` — a face whose URL silently moves on every
restart. `"0"` is a non-empty string, so deliberately asking for an OS-assigned
port still works.

Ctrl-C (SIGINT) leaves 130, SIGTERM leaves 0; both dispose the tree first.

## The profile

`npm run setup` writes THREE files into `$DSH_HOME/profiles/<name>/`, and
refuses a directory that already exists — it prints `exists, untouched: <dir>`
and changes nothing. Profiles are operator territory.

| File | What |
|---|---|
| `package.json` | the profile manifest: `dsh.profile.bundles: ["@deepseek-ai/dsh-base"]` |
| `cordis.patch.yml` | the operator's patch layer — a header plus a load-bearing `[]` (an empty array, not an empty file: dsh-app-boot throws on anything that is not a top-level YAML array) |
| `pnpm-workspace.yaml` | pnpm settings, verbatim from dsh's own `initProfile`, so `dsh plugin add` can install into this profile later |

Mount the workbench toolset — the `alpaca_kit` MCP server and the two skill
roots — into `cordis.patch.yml` per `../dsh/README.md` steps 3-6. The face boots
with or without it.

Two things about that directory are NOT yours:

- **`<profile>/cordis.yml` is face-managed.** `composeFace` rewrites it on every
  boot. The whole tree is composed as patch layers, and the root exists only as
  an empty entry list anchoring the loader's `baseUrl`; anything you put there
  is gone at the next start. Edit `cordis.patch.yml`.
- **The face's own host rows compose LAST and win silently.** They are applied
  after your patch layer and after the machine-local `$DSH_HOME/cordis.patch.yml`
  — the inverse of the dsh CLI's layering, and deliberate: loopback-only binding
  surviving an operator patch is the point. A patch of yours aimed at
  `webserver`, `connection`, `api-gateway`, `directory-picker`,
  `cordis-host-runner`, `tool-ask-user`, the storage chain (`storage`,
  `storage-json`, `storage-domain`, `workspace`), or the `hmr` / `session-telemetry-otel`
  switches is accepted, overridden, and NEVER reported. Change those in
  `src/overlay.ts`. The same warning is in the patch file's own header, which is
  where an operator would actually look.

## Instruments

Two read-only pages beside the chat, reached from the primary navigation rail
and from each other: **`/market`** (above strategy) — the composite tape, the
bed's maturity rail, breadth, and both screens — and **`/account`** (at the
bottom of the rail) — balances, positions, Alpaca's most recent 50 orders
(all statuses, not just the open ones). Account uses a compact trading-console
layout: total equity first, then cash, buying power and unrealized P&L, with
positions and orders in tabs. Symbol search and order-status filters narrow the
loaded rows only; they do not query a complete order history. Unrealized P&L is
shown only when every position reports its amount. Account and order-gate
details stay collapsed until opened. Both pages remain read-only: refresh
re-reads the snapshot, and no control places or cancels an order, changes an
account, or operates a gate. The account environment badge follows the actual
read hostname: only `paper-api.alpaca.markets` is labelled Paper.

Each page fetches one endpoint — `/data/market.json`, `/data/account.json` —
and each endpoint is a thin cache in front of ONE producer: `scripts/face_data.py`,
spawned with no shell and a FIXED argv (the script path and a mode word; no
request data ever reaches the child). Those routes carry the same loopback
`Host` fence the harness applies to `/api`, restated in `src/data.ts` because
that one covers `/api` only and `/data/account.json` carries the operator's
positions.

| Env | Default | What |
|---|---|---|
| `FACE_PYTHON` | `python3` | the producer's interpreter — it must be able to `import alpaca_kit`, so `pip install -e .` at the repo root, in whichever environment this names |
| `ALPHA_PIT_ROOT` | `data/pit/2yr` | the PIT bed `/market` is assembled from |
| `APCA_API_KEY_ID` / `APCA_API_SECRET_KEY` | — | `/account`'s paper credentials: `source ../.env.alpaca` BEFORE `npm start` |

The account keys are inherited by the face process, not read per request — the
same trust posture as the dsh MCP mount. Without them `/account` is not an
error page: the producer answers `available: false` with the reason AND the
real computed gate state, because the gate reads the environment and stays
computable with no broker client at all. The redesigned account view presents
this as an unconnected account rather than a zero balance, with the gate state
available in its collapsed details. `ALPACA_KIT_ENABLE_ORDERS` stays
unset, so Gate 1 reads unregistered; Gate 2 reads not-validated and points at
the drill below — the details state that intent rather than claiming a
validation only a live run can give.

**Timings.** A COLD `/market` — the first assembly ever, or the first after the
cache is invalidated — walks the whole bed: **~284 s, measured**. Warm it is a
file read, **under a second**. The spawn budgets are sized for exactly that:
market gets 10 minutes, account 30 s (a few REST calls, plus the market stack's
import cost on every spawn). So a cold first request SITS for minutes rather
than failing, and a budget short enough to kill it would fail forever — a
killed run never writes the cache that would have made the next one fast.

**The cache** is the producer's own, on disk under `data/.face_cache`
(gitignored, and deliberately outside any bed, whose identity is its
`CHECKSUMS` manifest). One file per bed + producer version + as-of day: the key
hashes the RESOLVED bed path AND the source of `face_data.py`, so editing the
assembler invalidates every cached payload instead of serving one built by code
that no longer exists. Delete the directory to force a full reassembly — and
budget the ~284 s again. In front of it each endpoint holds the last good
payload in memory for its own TTL: **market 15 minutes, account 60 seconds**.

**Stale.** Once an endpoint has served a good payload, a later producer failure
re-serves THAT payload flagged `stale: true` rather than blanking the
instrument, and the page stamps it `STALE`. With nothing to fall back on the
endpoint answers 503 carrying the producer's own `{ok:false,error}` JSON, and
the page says `no reading — <error>`. Either way an honest state, never a
half-drawn one. `/market` carries two stamps because a payload can be older
than its serve: `assembled` is when the bed walk ran, `served` is when this
process handed it over.

**The maturity rail** on `/market` renders the shipped 2yr bed's warmup
boundaries (200DMA from 2025-03-20, 52-week from 2025-06-04, trend_template
names from 2025-06-05 — the CLAUDE.md gotcha, drawn). Point `ALPHA_PIT_ROOT` at
any other bed and the rail is replaced by "warmup boundaries unknown for this
bed": those dates describe THAT capture, and drawing them over a different one
would be a lie.

## Channels (src/channels.ts + src/roster.ts + the session picker)

A channel is one directory, given an identity by the host and a roster by the
operator. Three layers, split by who may write them:

| Layer | Lives in | Writer |
|---|---|---|
| **Body** (content) | `strategies/<dir>/`, or the repo root | Kairos, freely |
| **Identity** (container) | the dsh workspace registry (`~/.dsh/storages/workspace.json`) | host-owned, only through `/api/workspace.*` |
| **Roster** (runtime) | `$DSH_HOME/face/channels.json` — `agents[]` (local CLIs Kairos may call) and `bots[]` (the voices a room may dispatch) | the operator, on the channel page |

The directory is the truth of existence, not the registry: `listChannelDirs`
(`src/channels.ts:43`) walks `strategies/*`, skipping `_template` and any name
starting `.` or `__`, and adds the repo root by hand (it has no `strategies/`
parent, so it stays the `workbench` entry). `workspaceRegistry.create` is
idempotent — canonical path, at most one record per path, a repeat call
returns the existing title unchanged — so a channel Kairos makes with a plain
`mkdir` becomes a channel on the very next listing.

**The reconcile** (`reconcileChannels`, `src/channels.ts:303`) runs on every
listing — both the `GET` that feeds the sidebar and picker and the `POST`
that feeds a channel's own page — and is idempotent by construction: `create`
is a no-op past its first call, `attachSession` early-outs on membership
before validating anything, and seeding a roster (`seedRoster`) is a no-op
once the channel has one. A steady-state listing performs no writes at all.
Because it CAN write on a `GET`, `channels.json`'s two writers — the
reconcile's seed and the operator's roster edit — both go through
`withFileLock` + `writeFileAtomic`, reading the file *inside* the lock, so a
sidebar poll racing an operator's toggle cannot silently revert it. A
workspace whose directory has vanished is reported greyed (`missing-dir`),
never deleted; its sessions stay attached and reachable.

**The picker and the sidebar are registry-driven now, not directory-scanned.**
`+ new` still opens the same picker (`showStrategyPicker` in
`client/chat.js`), but its rows come from `/data/channels.json` instead
of guessing from `cwd`s, plus a `choose a local folder…` row through the OS's
own dialog (`host.pickDirectory`) for anything outside a channel. The sidebar
groups sessions by channel MEMBERSHIP, not by path prefix: a session no
channel claims folds into a counted `ungrouped` bucket — never dropped,
charter Rule 5 — and the archive fold is the UNION of the face's own
reversible set (`archived.json`) and the host's one-way
`workspaceRegistry.archivedSessionIds`, because the two already disagree on
disk and neither alone is honest about what is archived.

Groups fold (chevron on the header; view state per browser), and each session
row carries four hover actions: rename and fork are the host's own RPCs
(`session.rename`, `session.fork` — a fork opens immediately); archive and
delete are face routes, because the host has neither at this pin. Archive is
metadata in `$DSH_HOME/face/archived.json` — the session still exists, folded
into an `archived` group at the bottom, reversible. Delete removes the
session's persistence directory permanently (confirm-gated, never offered on
a running session, no undo) and tombstones the id: a session deleted while
its agent is still attached keeps listing from host memory until the next
face restart — and write-behind can even re-persist its directory — so the
sidebar hides tombstoned ids unconditionally and the ghost dies with the
restart. `deleteSession` also now constrains itself to sessions whose `cwd`
resolves inside this repo, not merely to an id it happens to find, closing a
pre-existing gap where the delete button could reach another project's
session directory.

Deleting a session does NOT detach it from its channel: the id stays in the
registry's `sessionIds`, because the host's workspace RPC at this pin offers
`create` / `delete` / `rename` / `archiveSession` / `insertBefore` /
`insertSessionBefore` / `list` and no way to remove one session from a
workspace. The orphan is inert — nothing resolves it, so nothing renders it,
and the sidebar counts rendered rows rather than `sessionIds` — but
`/data/channels.json` does carry dead ids, and a reader counting that array
will over-count. Drilled 2026-09-04: deleting a session left its id under
`storage-chain` with its persistence directory gone.

The sandbox boundary follows the workspace — deliberately: a channel session
writes its own `strategies/<name>/` freely, and anything outside (the repo's
`.git` included) only through a Gate-2 escalation card. The write map's
"Kairos works strategies/ freely" becomes code, and a `git commit` from a
channel session is an approval the operator answers — accepted trade,
2026-09-01.

Four routes feed all of this, every one behind the same `isTrustedDataRequest`
fence as `/data` everywhere else — read "the honest limits" below before
treating that fence as authentication:

| Route | What |
|---|---|
| `GET /data/channels.json` | the reconciled list, the `ungrouped` bucket, the archive set |
| `POST /data/channels/overview` | one channel's landing-page payload — `{workspaceId}` in |
| `POST /data/channels/agents` | the operator's roster write — `{workspaceId, agents}` in |
| `POST /data/channels` | create — `{name}`, copies `strategies/_template`, then reconciles |

**The landing page** (`client/channels.js`) opens on clicking a channel's
title in the sidebar's group header — the chevron still only folds it. Seven
blocks, every one quietly skipped when its source is absent: header (title,
inline-rename, status badge, a `missing-dir` warning, the roster's agent
chips, the directory path); the optional `status.yaml` headline (`one_line`,
`next`, `numbers` — see `AGENTS.md`); the thesis (`THESIS.md`, with an
untouched `_template` copy detected byte-exact and shown as "no thesis yet"
rather than presented as content); latest evidence (the newest
`backtests/*.json`, flattened to a summary table, with the FULL json always
reachable in a collapsed `<details>` alongside it — nothing is dropped
because nothing is hidden); the journal (`journal.md`'s `- YYYY-MM-DD:` lines
as a timeline); files (one level of the directory, `__pycache__` filtered);
and sessions (the channel's own, joined against `session.list`, plus "new
round").

**The roster**, `$DSH_HOME/face/channels.json` (`src/roster.ts`), keyed by
workspace id so a directory rename never loses it:
`{"version":1,"channels":{"<workspaceId>":{"agents":["codex"]}}}`. A newly
adopted channel is seeded from whichever agents are connected at that
moment — there is no "absent means everything" rule; a channel's roster is a
definite, visible set at every moment. The enforcement point is
`agent_<bin>`'s own `execute` (`src/agents.ts:458-488`): it reads the calling
session's cwd, resolves its channel, and on a miss THROWS — naming the
channel and its current roster verbatim. The tool pipeline (`dsh-tools`)
catches a thrown `execute` and turns it into an `isError` result carrying
that message, so what Kairos actually sees is a tool result, never a crash —
but the mechanism at the cited lines is a thrown `Error`, not a returned
value. That refusal message IS the roster's contract; it is deliberately not written
into the channel's own `AGENTS.md`, which is Kairos-writable and would drift
from the operator-owned file. A channel with no roster entry yet (created
straight through the registry, before a listing has seeded it) reads as "no
roster yet" and refuses; an unparseable `channels.json` reads as "no rosters"
and refuses every call — fail CLOSED, *within a resolved channel*. What
happens when there is no channel to resolve in the first place is honest
limit 2, below.

**Deleting a channel** needs no new route and no button: remove the
directory (Kairos's own write map, or the operator's shell), then call
`/api/workspace.delete` — there is no UI for this second step yet, it is a
raw RPC call, not wired to a click. Order matters: `workspaceRegistry.create`
rejects a nonexistent path, so once the directory is gone the reconcile can
no longer resurrect the record. `delete` never touches the directory or the
session logs; the channel's sessions simply fall into `ungrouped`.

### The honest limits — the roster is a menu, not a fence

Charter Rule 3 requires recording a residual rather than shipping a guarantee
that fails at code level. In the same register as the Gate-2 note further
down this file:

1. **dsh tool registration is tree-wide.** There is no per-session scoping
   seam — `tools.register` (`src/panels.ts:345`) publishes one flat name per
   bin (`agent_<bin>`, `toolNameFor` at `src/agents.ts:84`) that every session
   sees. A non-member agent's SCHEMA is still visible in every channel; only
   the call is refused.
2. **The roster check only runs inside a resolved channel — a session in NO
   channel is not roster-checked at all.** `agent_<bin>`'s `execute` reads
   `const channel = await deps.channelFor(cwd)` and gates the entire roster
   read behind `if (channel !== null)` (`src/agents.ts:469-470`); when
   `channel` is `null` there is no `else`, and control falls straight through
   to `runAgentRecipe` — every connected agent callable, unconditionally. This
   is deliberate, not an oversight: `channelFor`'s own docstring says "the
   caller fails open either way" (`src/panels.ts:349-353`), because there is
   no roster to consult and tools are registered tree-wide regardless of
   channel. It is also cheap to reach, not a rare edge case: the picker's
   **`choose a local folder…`** row creates a session straight from a raw
   `cwd`, never a `workspaceId` (`client/chat.js:1311-1336`), so that session
   resolves to no channel and is never roster-checked; a channel directory
   that exists on disk but has not yet been through a reconcile lands in the
   same place.
3. **Kairos has a shell.** One shell turn can invoke `claude` directly. This
   roster is a MENU, not a fence — it reduces noise and states intent; it
   does not contain.
4. **One un-escalated shell turn can `curl` `POST /data/channels/agents` or
   `/api/workspace.*` — no approval card, no git diff, no session event.**
   The sandbox confines FILE effects only: the emitted Seatbelt profile is
   `(allow default) (deny file-write*)` plus write allow-lists
   (`node_modules/@deepseek-ai/dsh-sandbox-local/lib/index.js:66-72`), and
   `dsh-bash-sandbox`'s own README says outright "Network stays unrestricted."
   Both loopback surfaces are REACHABILITY FENCES, not authentication:
   `src/data.ts:116-117` — "A request with no Origin (curl, the tests, …)
   passes on Host alone" — and `dsh-client-connection`'s README — "The fence
   is a reachability policy, not authentication." Verified against the
   running face: a `curl` POST to `/data/strategies` (this route's name
   before the rename to `/data/channels`; the fence itself is unchanged)
   cleared the 403 and the 415 and reached the handler, refused only by name
   validation, while a forged `Host` still 403'd; a `curl` RPC
   `workspace.list` returned the real registry, HTTP 200. This is not
   introduced here — `POST /data/agents/connect` (`src/panels.ts:670-679`)
   already writes `$DSH_HOME/face/agents.json` and registers a tool live by
   the same path, and predates this design entirely. **The mitigation is
   visibility, not prevention**: a roster write appends a dated line to a
   durable face log, `$DSH_HOME/face/roster.log` (`src/roster.ts`'s
   `logRosterWrite`, called from the `POST /data/channels/agents` handler in
   `src/channels.ts`), naming the
   workspace, the resulting agent list and an ISO timestamp, so a change is
   SEEN even though it cannot be stopped. Building a token would be new
   security machinery against the charter's §7.4; recording this is what
   Rule 3 actually asks for instead.

**Two residuals, out of scope, recorded per Rule 3 (spec §10).** Neither is
caused by this change; both are recorded because it touches their
neighbourhood:

1. **The alpaca-kit MCP server is a child of the face PROCESS, not of a
   session**, so its writes never pass `ctx.sandboxPolicy`. Evidence on disk:
   `data/.screen_cache/` was written at the repo root during 2026-09-02
   strategy work, with no approval card.
2. **`system-prompt.persona` is empty.** It is `''` in `dsh-base` and set by
   neither `src/overlay.ts` nor the operator's `cordis.patch.yml` — the model
   is never told it is Kairos. "Kairos" is a UI literal and a directory name,
   not a composed property.

## The master rail (src/panels.ts + the sidebar's four faces)

A narrow icon rail at the far left opens **market** above the sidebar switches
and **account** at the bottom. Chat, Market and Account share the same
`client/navigation.js` rail and its fixed 56px layout: all six entries keep
their icons, order and positions while only the active highlight changes.
The four chat links (`/#strategy`, `/#agent`, `/#memory`, `/#plugin`) also work
from either instrument page, and browser history restores the selected panel.
The four switches pick which face the sidebar shows:
**strategy** (the working face — everything above), **agent**, **memory**,
**plugin**. One pattern across all four (operator direction): the sidebar is
always an INDEX — rows, never content — and clicking a row opens that item's
page in the RIGHT pane, in place of the chat (`.main.detail-mode` hides the
flow + composer; the topbar names the open item; picking a session or
"+ new" always brings the chat back). Strategy's "content" is the chat
itself. The three instrument faces are read-only, refetch on every open, and
split by data source:

- **agent** indexes four sections. *Main agent* is Kairos — the dsh runtime
  this face hosts; its page is a card grid over RPC the client already
  reaches: `host.describe` (provider/model, cwd, attached count),
  `settings.describe` (the `agent-default-model` namespace carries
  `reasoningEffort`), and `credentials.describe` (key configured/source —
  never values). Its *session usage* card is fed by the `session/projection`
  mux frames the host was already broadcasting (tokenUsage / contextPressure,
  from dsh-token-meter's projection units) — the mapper surfaces them, a
  per-session store keeps whole values with higher seq winning, and
  history-tail / list-row projection blocks seed a session opened cold. The
  context bar turns danger-colored at 80%. *Local agents* is an
  OPERATOR-CURATED roster, not a fixed list: it starts empty and lives in
  `$DSH_HOME/face/agents.json`. The `+ connect` row opens the roster page,
  three parts: what is *connected* (each row deletable); what auto-discovery
  *detected on this machine* — the panels.ts suggestion list, fifteen
  coding-agent CLIs by their PATH names, each probed with `<bin> --version`
  (execFile, no shell, scrubbed env, 3 s kill; absent, hung and nonzero all
  read as "not here"), offered in list order when it answers and is not yet
  connected, one click to connect, with a ↻ refresh that forgets the
  one-minute probe cache and looks again (`POST /data/agents/rescan`); and
  connect-by-name for anything the list does not know.
  `POST /data/agents/connect` admits a binary ONLY if it answers `--version`
  (the name is fenced to one bare PATH token, so a request body can never
  steer a probe to a path) and probes fresh; rows also disconnect from a
  hover `×` in the index or the agent's own page
  (`POST /data/agents/disconnect`); a
  connected binary that stops answering stays listed greyed rather than
  vanishing. Each agent's page is its directory entry (status / binary /
  version / signed-in state — read through the agent's OWN status command,
  `claude auth status`, `codex login status` or `hermes status`, the last a
  config report rather than a login gate, so a pinned provider reads as
  signed in — never its credential store) and names the tool it became.

  **What a connection is FOR.** The face has no run box of its own: a
  connected agent the face has a recipe for is registered in the dsh tree as
  a tool, `agent_<bin>` (`ctx.tools.register`, synced at boot and after every
  roster write, disposed on disconnect), so **Kairos calls it from any
  channel that offers it on its roster** (see "Channels" above) —
  `agent_claude(prompt, resume?)`. The tool spawns the
  operator's own UNMODIFIED CLI as a child in the calling session's directory
  (`exec.agent.session.header.cwd` — the strategy's workspace), forwards the
  call's cancellation to the child, and hands the answer back as the tool
  result with the CLI's session id, so Kairos can continue the conversation
  with `resume`. These are the GREEN rows of
  `docs/research/2026-09-01-agent-connection-survey.md`: the child performs
  its own sign-in and the face handles no credential at any point, which is
  what keeps it on the permitted side of Anthropic's terms (the survey quotes
  the line and its source); the Hermes-style reuse of
  `~/.claude/.credentials.json` against the raw API is the bright line and is
  never ported. Recipes: Claude Code = `claude -p --output-format json
  --restricted --strict-mcp-config --disallowedTools "Read(./.env)"
  "Read(./.env.*)"` (no command/code tools, no WebFetch, user/project
  settings and every MCP config ignored, file tools confined to the run's
  directory, the workbench's key files unread — a READER, not an actor);
  Codex = `codex exec --sandbox read-only --json --skip-git-repo-check -o
  <scratch> -` (the sandbox is PINNED — the operator's `~/.codex/config.toml`
  says workspace-write and a recipe must not inherit its posture from a file
  the face does not own). The prompt always travels on stdin (an argv
  beginning with `-` would parse as a flag); the child's env is scrubbed of
  every credential override and endpoint redirect that would move a CLI off
  its own sign-in (`ANTHROPIC_API_KEY`, `ANTHROPIC_AUTH_TOKEN`,
  `ANTHROPIC_BASE_URL`, `OPENAI_API_KEY`, `CODEX_API_KEY`, `OPENAI_BASE_URL`,
  the Bedrock / Vertex / Foundry switches) and of the workbench's own secrets
  — probes run under the same scrub, so the auth card observes what a call
  will get. Runs are one at a time per agent (a second call is refused while
  one is in flight), ten-minute kill with SIGKILL after a five-second grace,
  16 MB output cap. A tool call runs under the session's normal policy — like
  the alpaca-kit tools it raises no approval card; a `tools/pre-execute`
  `ask` hook is the knob if the operator ever wants one per delegation.
  Hermes deliberately has NO recipe: its default provider config reuses those
  tokens, so it stays a directory entry until its provider is pinned. *Bots*
  indexes the operator's own voices, one directory each under `bots/`, plus a
  `+ new bot` row (see "Bots" below). *A2A network* is a declared placeholder
  page — network agents land there when that opens.
- **memory** indexes the skill catalog — Kairos's standing knowledge. The
  wire `skill.list` needs an attached session and drops source/path/body, so
  two face routes read `ctx.skills` in-process: `GET /data/memory.json`
  (grouped by pack — the directory under `dsh/skills/`, mechanics first) and
  `POST /data/memory/skill` (`{name}`, kebab-validated). A skill's page is
  the full SKILL.md body at document width, rendered with the same
  client/markdown.js the bubbles use.
- **plugin** indexes the MCP servers and the composed row tree:
  `GET /data/plugins.json` projects `ctx.loader.entries()` (the same
  12-line projection `dsh-host-plugin-inventory` would make — that row is NOT
  mounted at this pin, and mounting it would land on the typert gateway
  anyway) plus `ctx.tools.schemas()` grouped under each `dsh-mcp-client`
  row's `serverName`. A row's `options.config` is never serialized — the MCP
  row's env block carries the APCA keys; `serverName` is the one field read.
  A server's page is its live tool table; the tree's page is the full ~90-row
  module/id/phase table, its index row calling out any `failed` count.

Every `/data` route — the panels', the instruments', the strategy and session
routes — stands behind the same browser-trust fence the harness puts on
`/api` (`isTrustedDataRequest`): a loopback Host, no Fetch-Metadata
`cross-site`, and a present `Origin` that matches the Host; every `/data` POST
additionally requires `application/json` (415 otherwise), so a cross-site
page cannot reach a side-effectful route with a "simple" request that needs
no preflight. The roster's connect/disconnect are the only writes to face
state (its own metadata file); an agent tool spawns that agent's own CLI
with a fixed argv and writes nothing durable of its own — a Codex call gets a
`mkdtemp` scratch directory under the OS tmpdir for `-o`, read once and
removed when the run ends. `panelDeps` fails loud at boot when
`skills`/`tools`/`loader` are missing from the tree — a dead panel with
nothing on stderr is the failure mode it exists to prevent.

## Bots (src/bots.ts + plugins/bot.js + bots/)

A bot is a dsh **agent preset**: one directory under `bots/` holding `agent.cordis.yml`
(the composition dsh mounts), `preset.yml` (`name`, `description`), `SOUL.md` (the persona
SOURCE), `skills/` (its stance pack, a dsh skill root) and `journal/` (the one directory it
may write, from its home). The face mounts `@deepseek-ai/dsh-agent-presets` with `bots/` as
its only root (`faceOverlay`, `AGENT_PRESETS_ROW_ID`, `includeUserRoot: false` — a bot the
repository does not carry cannot exist) and `kairos` — an EMPTY composition — as the default
every session joins when it names none, so Kairos's own sessions keep the host's flat roster
unchanged (`bots-smoke.test.ts` pins the two tool sets equal). `bootFace` refuses to start if
the roster service is missing, if the roster cannot be read, or if the default preset is
absent or broken: every `session.create` resolves a preset, so a roster that cannot supply
one would fail every session instead of the boot.

**Kairos is the host plane; a bot is a mask.** Kairos is told who it is by the
`system-prompt` row's `persona`, set from `dsh/profile/persona.md` by `composeFace`
(D11 closed; a malformed template refuses the boot with the file named — `readPersona`).
A bot's composition names one face-owned plugin, `plugins/bot.js` (`kairos-bot`), which
registers the bot's persona section — shadowing Kairos's for that preset's agents — and an
**allow-list** `tools.restrict`. Allow, not deny: dsh admits later-registered globals through
a deny mask and excludes them through an allow mask, and the two tools a voice must never see
that are registered *after* the mount — `agent_<bin>` on connect, `dispatch` in the rooms arc —
are excluded by the allow form without being named. `mcp__…__place_order` is not one of them:
the operator's MCP row mounts at boot, so an order tool is already in the tree when a bot
mounts and is excluded by OMISSION from the list. `mcp__*__<raw>` in the list expands
against the live tree (`expandAllow`), so the operator's server name does not matter; a name
the tree does not have is warned and dropped, and a list that survives to nothing at all
throws rather than mounting a bot with no hands.

**The mask is visibility, not authority.** dsh says so of every scope ("live visibility
composition, not an authority boundary"). What a bot may write is its session's sandbox mode;
what it may order is Gate 2, which is tree-wide. Neither changes when a bot is masked, and
neither is containment.

**Authoring is the face's own copy.** The **New bot** form (agent face → bots → `+ new bot`;
`POST /data/bots`) copies `bots/_template`, writes `preset.yml` and `SOUL.md`, and RENDERS
`agent.cordis.yml` so the persona row's text is the soul's (`renderComposition`) — dsh's
`!!js` cannot read a sibling file. A soul saved on the bot page (`POST /data/bots/soul`,
`updateSoul`) rewrites both. `renderComposition` writes the same two rows every time — the
`kairos-bot` row and the bot's own skill root — so a third row the operator added by hand does
not survive a soul save, and a composition `js-yaml` cannot parse is regenerated from
`DEFAULT_ALLOW`, its hand-edited mask discarded. A hand edit to `SOUL.md` reaches nothing
until the face saves it again, and a running session keeps the prompt it started with: the
preset's generation is keyed on `agent.cordis.yml` alone and never reclaimed until restart
(dsh-agent-presets README, "A superseded generation is never reclaimed"). No `{{` anywhere in
a soul: the prompt is a strict template with no escape, and both write paths (`rejectSoul`, on
the way in) and the plugin itself (`validateBotConfig`, at mount) refuse it.

**A bot's home** is a session created with `cwd = bots/<id>/journal` and `agentPreset = <id>`
— the client's `openBotHome` arms the next prompt exactly as a channel's "new round" does,
and the gateway's own `session.create` mounts the preset (no in-process agent creation).
The sidebar buckets a bot's sessions under its name from the session summary's `agentPreset`
(`grouping.js` `bucketFor`, `BOT_KEY_PREFIX`); the strategy picker never offers a journal as a
"local folder" (`knownFolders` skips every cwd under `bots/`). Reading the same `agentPreset`,
the transcript names the voice: in a bot's session its display name stands over every reply, its
ask cards read `<bot> asks` and the composer says `Message <bot>…`, while Kairos's own sessions
stay `Kairos` (`speaker.js` `speakerFor`). Ids are dsh's preset grammar
`[a-z0-9][a-z0-9-]*`, bounded here to 64 code points (`BOT_ID_RE`); the form proposes one from
the display name (`botId.js` `proposeBotId`, the browser twin of the server's — `botId.test.ts`
pins that a non-empty proposal is always an id `isBotId` accepts) and the server refuses anything
else — `kairos` by name (`RESERVED_IDS`) and `_template` by the grammar, which admits no leading
underscore (both through `isBotId`).

| Route | What |
|---|---|
| `GET /data/bots.json` | every directory in the grammar under `bots/`, with dsh's roster merged in: `broken` reasons shown, a directory the roster does not report flagged `listed: false` (Rule 5) |
| `POST /data/bots` | create — `{name?, id?, description?, soul?}`, the id the one given or `proposeBotId(name)`; 400 an id outside the grammar or a soul carrying `{{`, 409 exists, 500 `_template` missing. The returned row always reads `listed: false` (it is built without the roster); the next GET reports the bot, because dsh re-scans on every `list()` |
| `POST /data/bots/soul` | `{id, soul}` — rewrites `SOUL.md` and the composition together; 400 a bad id or a soul carrying `{{`, 404 unknown bot |

All three stand behind `isTrustedDataRequest` (403), the two POSTs behind 405 / 415 / 400 for
method, content type and body, with a 64 KiB body cap because a soul is prose.

**Deleting a bot** is `git rm -r bots/<id>`; there is no button. Its sessions remain history.
The roster is mounted `trust: "system"`, so the gateway's own `agentPreset.copy` / `remove` /
`openDocument` RPCs refuse it ("it ships with the deployment") — the face's three routes are the
only authoring path, and no connected client can reach around them into a git-tracked directory.

**A bot in a room** — dispatched by Kairos, addressed by the operator's `@`, its answers in the
room's transcript in its own voice — is the next section. What is still not built (spec §11, on
purpose): bot-to-bot messaging outside a room, cross-channel memory for a bot, a delete button, a
channel-scoped 1:1 with a bot.

## Rooms (src/room.ts + src/room-rules.ts + src/room-projection.ts + client/room.js)

A room is an ordinary channel session whose agent is Kairos and which has **members**: one
session per bot the channel rosters, created lazily the first time that bot is named. Nothing
is created to make a session a room. The operator checks bots into a channel on its page
("bots in this channel", `POST /data/channels/bots`, at most six — `ROOM_CAPS.maxMembers`); the
roster stays a menu, not a fence (the channels section's honest limits apply verbatim).

**Kairos organizes the room through one tool, `dispatch`** (`to`, `mode` parallel or serial,
`brief`, `reason`). It is registered globally on the root context (`installRoom` in `main.ts`),
so it is in Kairos's roster; every bot's allow-list mask excludes it without naming it. The
call validates `to` against the channel's bot roster (the refusal names the roster), starts
the round, and returns at once — the result text names who was called, how, **who was not
called**, and tells the model to end its turn. Kairos is woken once per round, by a
`followup` that names who answered and who passed.

**A member session** is created in-process by the engine (`ctx.agents.create`) with the
channel directory as `cwd`, `parentSession` = the room, `agentPreset` = the bot, the bot's
`preset.yml` `model:` when the tree serves it (else the default, with a line in the dispatch
result), and — inside the same creation `setup`, before the session is published — the
**`read-only`** permission preset: a bot in a room does not write files, by sandbox mode, not
by mask (D12). A member that already exists is resumed, never recreated. Members are runtime
roots (created from the root context, not from Kairos's), which is what lets a member ask the
operator a question.

**What a member sees** each turn: the room delta — every operator prompt, Kairos reply and
member answer since it last spoke, one attributed line each (`操作员:`, `Kairos:`, `<bot> (you):`,
`<bot>:`) — the brief, and four standing rules carried in the prompt (reply with your view or
exactly `(pass)`; your text goes to the room verbatim; you remember this room only; address the
operator directly when the judgment is theirs, write `@<bot>` to pull a peer in). Its cursor is
the delta prompt in its own log (`source.form === 'delta'`, `messageIds`), so a member never
re-reads what it saw. Parallel: everyone answers on the same delta and sees no peer this round.
Serial: each later member sees the earlier answers.

**How a room fact is recorded — no `room/*` events.** dsh's persistence refuses to reload a log
carrying an event type outside its catalog (`KNOWN_SESSION_EVENT_TYPES`), so every room fact
rides a known event: membership is the member's header; the dispatch is the tool's own
call/result; an answer is a `user/message` on the room session with `source: { kind: 'room',
form: 'answer', bot, name, sessionId, turn, round }`; the round end is the waking
`user/message` with `form: 'round-end'` and every turn's state. Answers are **appended straight
onto the room log** while no Kairos turn is open (a bubble at once, a seq now, in the next
request's history) and held in a per-room outbox otherwise, flushed at the next `turn/end` and
before the round-end wake. The `room` projection unit folds these events into the coarse state
the strip shows (`called`, `answered`, `passed`, `failed`, `timed-out`, the round, `organizing`);
it rides `session/projection` frames, the `session.list` row and — now that the face mounts
`dsh-session-projection-cache` — the cold row too (R13 closed by the same row).

**Caps, deadlines, endings** (`ROOM_CAPS`, one block): 3 rounds and 10 bot messages per
operator send, 2 peer continuations per round, 180 s base per member turn extended while the
member runs or has a gate pending, 1200 s hard cap → `agent.cancel` (inbox kept) → `timed-out`.
A member whose model fails is `failed` and counts as a pass; the round continues. A round ends
`settled`, `capped` (a cap stopped it) or `superseded` (the operator spoke mid-round: running
turns finish and land, nothing further starts) — three words for three facts. Every operator
send resets the caps.

**The operator's `@`** is deterministic and never passes through Kairos: the composer sends a
text containing `(^|\s)@` to `POST /data/rooms/say`, which resolves mentions against the roster
by id (by display name only when it is one token), appends the message to the room as the
operator's own (`kind: 'user'`, `mention: [...]`) without waking Kairos, and turns each named
member — one mid-turn is queued behind that turn, never refused. A text that names nobody comes
back `addressed: []` and the client sends it as an ordinary prompt. `POST /data/rooms/state`
answers the roster, the members the engine drove this boot, and the caps left.

**The client.** A member's answer renders as a bubble in the bot's own voice — its display name
and an avatar glyph — never as a context row (`client/room.js`, `mapper.js`); the round end is a
room line; the dispatch card reads as the who-was-called line. The **participants strip** above
the transcript shows Kairos (`organizing` while its turn is open) and every rostered voice:
coarse states from the projection, fine states (`thinking` / `writing` / `tool`) from the member
sessions' own pulses, `waiting for you` when a gate is pending on the member, `left` for a member
the roster no longer carries. A member's question or escalation card renders **inline in the
room**, headed with the bot's name, and is answered against the member's own session. Member
sessions have **no separate Members dropdown** in the sidebar. Each member answer has the same
bottom-right **思考轨迹** disclosure as Kairos. Opening it reads the exact member session and
turn recorded on that answer, paging older history as needed; it does not resume or prompt
the member. Context, thinking and tool results stay scoped to that turn, with visible loading,
empty and retry states. Membership still follows the header: `parentSessionId` set, no
`origin`, a bot preset, the parent running the host. A
pending gate on a session or its members marks the session row, the channel header and the
landing page (needs-you at the index level).

**The honest limits, in the register of the channels section.** Dispatch grants nothing and the
mask is visibility; a member's write fence is its sandbox mode, its order fence is Gate 2,
tree-wide (both proven from a bot session in `room-smoke.test.ts` and `bots-smoke.test.ts`).
Four voices on one model will tend to converge (R3); parallel first answers are the mitigation,
not a cure. Dispatch is Kairos's judgment (R2): it may under- or over-call; the "not called"
clause and the operator's `@` are the answer. A member's pending gate with no client connected
blocks until the hard cap (R6). A bot does not remember across channels (R5).

| Route | What |
|---|---|
| `POST /data/channels/bots` | `{workspaceId, bots[]}` — the channel's bot roster, at most six ids; 400 a bad id or over the cap, 404 no such channel, 409 a corrupt roster file; a dated `bots` line to `roster.log` |
| `POST /data/rooms/say` | `{sessionId, text}` → `{addressed: [...]}`; 400 a bad id or empty text, 404 not in a channel, 409 a corrupt roster |
| `POST /data/rooms/state` | `{sessionId}` → `{roster, members, caps, round?}`; never resumes a session |

## Chat rendering (client/render.js + client/answer-traces.js)

Context, thinking and tool calls preceding an answer live in its closed
**思考轨迹** disclosure, opened from the bottom-right of the answer bubble.
The count includes each process row once; a tool result updates its original
call. Expanded traces retain the individual rows' summaries and detail/raw
toggles. Pending or unanswered traces have a standalone closed disclosure;
operator messages, room replies and turn endings close their association so
they cannot leak into the next answer. Approval and question cards stay
visible outside the disclosure. History and live events use the same path.

Thinking follows dsh's design: while a reasoning block is OPEN, the flow's
tail carries one ephemeral indicator — a spinning mark and elapsed time,
NEVER content — and the status line reads "Kairos is thinking…". Only when
the message settles does the thinking enter the answer's trace as a `think`
row (a reasoning-only step waits in the pending disclosure).
The stream's deltas themselves stay log-only.

Kairos's own bubbles render markdown (client/markdown.js, DOM-built, no
innerHTML): headings, bold, inline code, links, lists, fenced code, quotes,
and GFM tables — tables reuse the .viz-table instrument styling, numeric
columns right-align, and signed percent cells color up/down with the sign
kept in the text. An answer with document structure widens its lane; the
operator's own messages render exactly as typed.

### Market-data renderers

Recognized alpaca-kit tool results render as instruments instead of raw JSON:
market_snapshot as a Δ%-sorted table (sign always printed — the red/green pair
is never the only carrier of direction), screen/positions/orders/earnings as
generic tables, breadth/account as stat tiles or a kv grid, daily_bars as an
inline SVG close line + volume strip with a crosshair tooltip. The card head's
`raw` becomes a pretty ⇄ raw toggle when a pretty view exists. Anything
unrecognized — a shape surprise, an error, a foreign tool — keeps the raw pre;
the renderer never dresses up what it cannot parse. dsh spills tool results
over ~50 KB (head + tail with an elision seam + a note naming the full-output
file): the parser first tries the complete text, then the text up to the note,
then salvages whole row objects one by one — the one row cut at the seam is
dropped and the table's meta line says so.

## Tests

```bash
npm test                  # offline unit tests - no keys, no network, no port
npm run typecheck         # strict tsc against the pinned .d.ts - the contract test
FACE_SMOKE=1 npm test     # + the five real boots (throwaway $DSH_HOME, no LLM call)
```

`npm test` works on seams: the composed patch stack, a recorder standing in for
the webserver, a recorded event stream, the version pins. The smoke test is the
only place a composition that typechecks but does not MOUNT gets caught — it
boots the real plugin tree into a `mkdtemp` home, then drills the surface: `/`
serves the client, `/client/chat.css` is served with the right content type,
`POST /api/session.list` returns a real `items` array (proof the api gateway
reached the session store behind it), a plain `GET /api/events.mux` answers 426
with an `upgrade: websocket` hint, and the same request with a forged
`Host: evil.example.com` answers 403 — the DNS-rebinding fence, drilled rather
than assumed. Then the instruments: `/market` and `/account` serve, and
`/data/market.json` answers a STUB producer's payload through the real
route/cache/spawn chain (no Python, no bed — the producer has its own suite),
with a forged `Host` on that route drilled to 403 as well, because `/data` is
fenced by its own predicate rather than by the harness's.

## Upgrading dsh — TWO pins, not one

`src/version.ts` holds both, and they move independently:

- **`DSH_PIN` = `0.1.1-rc.2`** — the entire `@deepseek-ai/dsh-*` family, pinned
  EXACT. Lockstep only: these packages are tested only against each other at one
  version, and a mixed set breaks the rpc-map wire contract. `tests/version.test.ts`
  sweeps every `@deepseek-ai/dsh-*` entry across `dependencies` and
  `devDependencies` PROGRAMMATICALLY and asserts declared range == installed
  version == `DSH_PIN`, so a dependency added later is covered without anyone
  remembering to extend a list.
- **`CORDIS_PIN` = `4.0.2`** — `@deepseek-ai/cordis` rides its own 4.x track. The
  dsh packages peer-depend on it at `^4.0.1`, and the cordis-plugin family
  currently peers `^4.0.2`. It is bumped separately and deliberately.

Not pinned at all: the five `@deepseek-ai/cordis-plugin-*` packages (`group`,
`hmr`, `include`, `loader`, `timer`). They arrive transitively on caret ranges
declared by `dsh-app-boot` and `dsh-base`; only `package-lock.json` holds them
still. Keep the lockfile committed, and read a lockfile-only change to those
five as a real upgrade that deserves the drill below.

**The drill.** Bump `package.json` AND the matching constant in `src/version.ts`
together — both pins if both tracks moved — then:

1. `npm install` — first, and not optional: the pin sweep reads the INSTALLED
   tree as well as the manifest, so running it against a stale `node_modules`
   fails on the old versions rather than on anything about the upgrade.
2. `npm test` — the pin sweep fails first when the manifest, the installed tree,
   and either constant disagree. A green sweep is the precondition for the rest,
   not evidence the upgrade is good.
3. `npm run typecheck` — the contract test. A renamed config key, a narrowed
   value, a changed exported signature: they surface here, because the overlay's
   row configs are `satisfies`-checked against the plugins' OWN exported config
   types rather than against a local `Record<string, unknown>`.
4. **Re-diff `src/boot.ts` against the CLI's current `profile-boot-*.js` chunk.**
   At this pin that is `@deepseek-ai/dsh` 0.1.1-rc.2,
   `lib/profile-boot-DG5t9aNs.js` — functions `prepareProfile`, `composeProfile`,
   `resolveTelemetryPatch`, `runProfile`. The chunk name is content-hashed and
   changes on every release; the CLI is not a dependency of this package, so
   fetch it (`npm pack @deepseek-ai/dsh@<new>`) to read it. This is the one
   private piece the face mirrors: it is unexported, so nothing type-checks it,
   and a composition that has drifted boots a DIFFERENT tree while still
   compiling clean. `boot.ts`'s header lists the divergences that are deliberate
   (no `--patch` overlays, no HMR reload, no `installFailLoud`, no shipped
   agent-presets graft, the face's own install anchor) — anything else is drift.
5. **Re-check the frame shapes**: `client/mapper.js` and
   `tests/fixtures/events.jsonl` against the pinned
   `@deepseek-ai/dsh-host-apiproxy/lib/types/api/*.d.ts` — `events.d.ts`
   (`MuxFrame`), `rpc.d.ts` (`ServerRequest`), `rpc-map.d.ts` (the closed method
   list), `approvals.d.ts` and `questions.d.ts` (the two answerable frames).
   The client is untyped JavaScript talking to a typed wire, so `tsc`
   does not cover this hop — the fixture is the contract, and a fixture that no
   longer matches the wire makes the mapper tests green against a stream nobody
   sends.
6. `FACE_SMOKE=1 npm test` — the only step that proves the new tree MOUNTS.
7. Run the Gate-2 drill below.

Only then trust it.

## The Gate-2 drill (run after any face or dsh change)

A guard never pulled is presumed broken.

**What actually holds Gate 2 here.** dsh-base marks no tool `ask` per-tool.
It mounts `@deepseek-ai/dsh-user-approval` with a session-wide policy — `ask`
unless `DSH_PERMISSION_MODE=danger-full-access` — and
`@deepseek-ai/dsh-permission-presets`, whose `read-only` and `workspace-write`
presets both carry `approval: ask` while `danger-full-access` carries
`approval: never`. The default session is `workspace-write` + `ask`. What
actually RAISES a card is a **sandbox escalation**: under `workspace-write` the
sandboxed bash executor and the sandboxed fs write/edit tools are denied outside
the session workspace, and their one permitted retry carrying
`sandbox_permissions` + `justification` resolves `ctx.approval` before running.
An `ask` decision with no answerer degrades to DENY, and `bootFace` refuses to
start a tree missing the `approval` or `userQuestions` service for exactly that
reason — otherwise the tree would come up healthy and every approval would fail
closed with nothing on screen saying why.

**The drill**, with the face live and a session open:

1. Prompt Kairos to write a file OUTSIDE the session's workspace — the path
   shown on the session's sidebar row, the workbench repo root unless you gave
   the session a project of its own — and to escalate when the sandbox denies
   it. `touch ~/face-gate2-drill` from the bash tool does it, unless that
   workspace IS your home directory, in which case pick any path outside it. Do
   NOT use `/tmp`: `workspace-write` already permits the platform temp areas, so
   a write there is allowed and asks nobody.
2. PASS, part one: the approval card renders in the face — headed `approval`,
   the tool's name beside it, the host's reason when it gave one, and exactly
   two buttons. Two outcomes and only two: `cancelled` and `unavailable` are
   host-side and no client may send them.
3. **Deny.** The card settles to `answered · deny` and the command does NOT run.
   The model sees a denial result, never the card.
4. Prompt again and **Approve**. The command runs. The grant is one-shot
   (`allowed-once`) and applies to that call alone — there is no `allow-always`,
   no remembered rule, no grant store.
5. Both decisions are in the session log under `$DSH_HOME/sessions` as paired
   `approval/asked` + `approval/decided` records. Those are log-only: the audit
   is for you, not for the model.
6. Clean up: `rm ~/face-gate2-drill` (or whatever path step 1 used).

The escalation retry is capped at ONE per turn: after a denial the model may
retry that same command once, in that same turn, with a wider mode and a
justification — and that retry is what raises the card. If it answers with prose
instead of retrying, that turn is spent; prompt again, more bluntly, rather than
concluding the seam is broken.

**Never drill with the order tools.** `ALPACA_KIT_ENABLE_ORDERS` stays unset.
Gate 1 — registration — is what keeps `place_order` / `cancel_order` out of the
toolset entirely, and a drill that arms the flag to exercise Gate 2 has disarmed
Gate 1 to do it.

**And a file-write drill does not stand in for one.** What it proves is the
approval CHANNEL — request → answerer → card → outcome → audit pair — which is
real and in daily use. It does not prove a PRODUCER for an MCP tool call, and
this tree has none. What raises the card is a *sandbox escalation*; an MCP call
never takes that path. Four checks, each independent, re-run 2026-09-04: no
`dsh-hooks*` package under `face/node_modules`; no `{kind:'ask'}` producer in
any composed package; `dsh-permission-presets` registers only `session/created`
(preset application) and an `internal/dispatch` event *validator*, neither of
which can ask for a tool call; and `dsh-mcp-client` carries zero references to
approval, sandbox or pre-execute.

So until 2026-09-04, for orders Gate 2 was not unproven — it was **absent**.
Arming `ALPACA_KIT_ENABLE_ORDERS=1` would have run `place_order` with no card and
no `approval/asked` event, with a registration flag the only thing in the way.
Charter Rule 3 forbids publishing a guarantee that fails at code level, which is
why this paragraph exists rather than being quietly deleted once the hole was
filled. **The producer now exists** — see "The order-approval drill" below —
but it is a `tools/pre-execute` listener this repo registers, not something the
harness provides, so it is exactly as durable as that registration.

Until the channel drill passes on a live face, the face does not claim even that
half.

**The approval-channel drill: PASSED 2026-08-31, re-run and PASSED 2026-09-08** on the live face with the workbench toolset mounted:
deny (command did not run; the model saw a rejection result, never the card) and approve
(`allowed-once`, one-shot) both exercised, with paired `approval/asked` +
`approval/decided` records in the session log. Re-run after any face or dsh change, per
the heading above.

## The order-approval drill (run before ever arming ALPACA_KIT_ENABLE_ORDERS)

Since 2026-09-04 a per-order gate exists (`face/src/orders.ts`, registered in
`bootFace`). Two registrations, because neither alone suffices: a
`tools/pre-execute` listener returning `{kind:'ask'}` is the only thing that can
RAISE a card (a `ToolGuard` returns `string | undefined` — deny-only), and a
guard is the only thing that is MONOTONIC, evaluated on every allow including
the one `allowed-once` becomes. The listener is registered `prepend` so it is
outermost; the guard denies any gated tool that reached dispatch without a
logged `allowed-once` for that exact `callId` and tool name in the session's own
event log. Deliberately not "without the listener seeing it": `prepend` is
last-registrant-wins, so a listener mounted after boot sits OUTSIDE this one and
could take its `ask` and return `allow` — a guard that trusted its own sighting
would wave that through. Only the log proves a human said yes.

**The automated half runs in CI-ish form already:** `FACE_SMOKE=1 npm test`
boots a real tree and fires `tools/pre-execute` at `mcp__drill__place_order`,
asserting it is claimed, that `mcp__drill__orders` is not, and that a renamed
server (`mcp__whatever_they_call_it__place_order`) is still caught. Drilled
2026-09-04, mutation-proven: removing the registration fails it.

**What is NOT drilled, and it matters.** The POSITIVE path — a grant logged,
the guard finding it, the order dispatching — has no automated test. Everything
above proves the gate REFUSES; nothing proves it lets an approved order through.
So if `approval/asked` ever stopped carrying `callId`, or carried a different
`toolName`, every approved order would be silently denied and the suite would
stay green. This is drillable (a test answerer on the `approval/request`
waterfall would do it) and is simply not done yet; it is the highest-value
missing test here, and the manual drill below is currently the only thing
covering it.

**The manual half — the card — needs your eyes** for the part no answerer can
stand in for: whether a human can actually READ the card and decide from it. An
ask with no connected browser blocks rather than denying, so the live path needs
a client anyway. With the face live and a session open:

1. Arm Gate 1 in a **scratch** harness home, never your real one: an
   `ALPACA_KIT_ENABLE_ORDERS: "1"` line in that home's alpaca-kit row plus the
   paper keys. Boot the face against it. The boot log prints
   `kairos-face: order gate armed for mcp__alpaca-kit__place_order, ...` — if it
   does not, the tools did not register and there is nothing to drill.
2. Ask Kairos to place one paper order.
3. PASS, part one: an `approval` card renders **naming the order, not just the
   tool** — symbol, side and quantity have to be on it. A card that says only
   `place_order` is a click-through, not a decision, and this step is what would
   catch that regression. **Deny it.** The order does not go out; the model sees
   a rejection result, never the card.
4. PASS, part two: `approval/asked` and `approval/decided` appear paired in the
   session log.
5. Only if you want the approve path: repeat and approve. That places a real
   PAPER order — your call, not the drill's.
6. Tear down the scratch home. Your real harness keeps
   `ALPACA_KIT_ENABLE_ORDERS` unset.

**The one setting that disarms every other approval does not disarm this one.**
Under `DSH_PERMISSION_MODE=danger-full-access` — or a runtime switch to the
`danger-full-access` preset — `ApprovalService` short-circuits to `rejected`
before any answerer runs, and `dsh-tools` renders that as `the user rejected
tool "..."`, which is false: nobody was asked. The gate denies in its own words
instead, and says so.

**A cancel is gated too, and that cuts the other way.** `cancel_order` changes
exposure, so it asks — but under policy `never`, or on a call with no session,
the gate DENIES it. The one action that reduces risk is refused in exactly the
session where prompting was switched off. That is the right trade (the paper pin
bounds the stakes, and you can cancel from Alpaca's own console out of band), but
it is a surprise worth knowing before you meet it.

**The shell can answer its own card.** `POST /api/respond` carries no token —
the same-origin check in front of it is a browser fence, and a `curl` sets any
header it likes (the roster route has the same property, and it was demonstrated
with a bare `curl` on 2026-09-04). The pending `rpcId` is readable off the mux
stream. So one un-escalated shell turn can approve the order it just asked for,
and what lands in the log is a REAL `approval/asked` + `approval/decided`
(`allowed-once`) pair. The guard is satisfied — correctly, because a genuine
grant was recorded. Nothing here is broken; the gate asked, and the wrong party
answered. This is the specific hole in the property the guard was rebuilt
around, so it is stated rather than left for someone to find.

**And this is a gate, not containment.** `tools/execute` runs AFTER the guard,
is handed the execution as mutable, and the body re-resolves the tool by its
current name — so a `tools/execute` wrapper could rename a guard-approved call
into `place_order`. Kairos also has an unrestricted shell. Per charter Rule 2,
this stops the model's ordinary tool calls; it is not a boundary that holds
against code trying to get around it.

Gate 1 — not registering the tools at all — remains the sturdier layer, but be
precise about what it holds: the MCP tool *surface*, not the *account*. A shell
turn can import `alpaca_kit.account` directly and never touch either gate. What
stands in its way there is smaller than it sounds and worth knowing: dsh does
not hand credentials to shell children — `scrubbedParentEnv` drops every name
matching `/KEY|PASSWORD|SECRET|TOKEN/i` — so the shell has to go and read
`.env.alpaca` itself first. The paper-hostname pin is what actually bounds the
damage.

## The ask-user drill (run after any face or dsh change)

The same rule, for the seam that carries Kairos's own questions.

**What actually holds it here.** dsh-base mounts the `user-questions` SERVICE
and NO model-facing tool for it. The tool is a separate package,
`@deepseek-ai/dsh-tool-ask-user`, and upstream it reaches a session through an
agent PRESET — dsh-web-app disables dsh-base's tool rows and mounts presets
instead, and the shipped `standard` preset carries `ask_user`. The face grafts
no presets (`boot.ts`, divergence 4), so it keeps dsh-base's flat tool roster
and inherits its one hole. The face fills it with its own overlay row,
`tool-ask-user`, face-owned for the same reason `webserver` is: this layer
composes last, so an operator patch aimed at it is accepted, overridden, and
never reported — and an agent silently losing its voice is the failure the row
exists to prevent.

**The two halves fail INDEPENDENTLY, and that is the whole point.** A tree with
the service and no tool comes up perfectly healthy, passes `bootFace`'s Gate-2
service check, offers the model its full toolset, and simply never asks
anything. No error, no card, no pending question — just an agent that guesses.
That is what shipped from 2026-08-31 until 2026-09-02: one real session offered
35 tools, none of them this one, and ran 83 steps on a one-line brief.
`bootFace` now refuses to start a tree in which `ask_user_question` did not
register, checked against the live registry rather than the composed row list —
an unsatisfied inject leaves the row pending with the entry list unchanged.

**Unlike Gate 2 this is not a gate.** Kairos asks because it chose to, and the
answer returns as an ordinary tool RESULT — model-visible, in the context, the
exact opposite of an approval decision, which the model never sees.

**Step 0, no model, no key.** `FACE_SMOKE=1 npm test` boots the real tree and
asserts `ctx.tools.schemas()` carries `ask_user_question`. Run it first; if it
fails, stop — nothing below can pass and the cause is composition, not the
model.

**Step 0b, if you changed anything under `client/`.** `registerStatic` sets no
cache headers, so the browser caches the ES modules heuristically and a restarted
face happily serves an old `chat.js` to an open tab. Hard-reload the page before
drilling: a stale client produced two false failures while this drill was being
written.

**The drill**, with the face live and a session open:

1. Open the **plugin** panel → the composed row tree. `dsh-tool-ask-user` is
   listed as `include:tool-ask-user`, phase **active**. A row stuck at
   `pending` means its inject (`tools`, `userQuestions`) was never satisfied —
   the one failure a composition test cannot see.
2. Prompt Kairos to ask, naming the tool: *"Use ask_user_question to ask me
   which PIT bed to use, 2yr or broad. Ask nothing else and read no files."*
   Naming it is deliberate — this step drills the SEAM, not the judgement.
3. PASS, part one: the question card renders, headed `kairos asks`. ONE card for
   the whole batch, whatever the number of questions, and one Send: one `ask()`
   is one card and one answer, never split per question.
4. **Answer it.** The card settles to `answered`, the turn continues, and the
   answer is back in Kairos's context as a tool result. On a
   single-select question a typed answer and a picked option replace each other
   — the host rejects an answer carrying both, as a bare `bad-response`.
5. **Press Stop on a fresh question instead of answering it.** The card settles
   to `closed · cancelled` and the sidebar's `waiting` chip clears. A card that
   stays live after a cancel means the `question/resolved` frame is being
   dropped again (`client/mapper.js`), and it will be re-drawn on every session
   switch from then on.
6. PASS, part two — the instruction half, in a FRESH session: ask for a new
   strategy with a deliberately thin brief ("build me a strategy for storage
   names"). Kairos asks before it builds, per `AGENTS.md`. This half is
   behavioural, not mechanical: a turn that answers with prose is not proof the
   seam is broken. Re-prompt once before concluding anything.
7. The log, under `$DSH_HOME/sessions/<workspace>/session-<id>/session.jsonl.zstd`
   (zstd-compressed JSONL). A question records as an ORDINARY TOOL PAIR —
   `tool/call` with `data.name == "ask_user_question"` and its `tool/result` on
   the same `callId`. There is no `question/asked` audit record and there is not
   meant to be: `KNOWN_SESSION_EVENT_TYPES` carries `approval/asked` and
   `approval/decided` and no question member at all, because a question is not a
   gate. `question/requested` / `question/resolved` exist only as wire frames on
   the mux stream. The durable proof the tool was OFFERED is `request/header`,
   whose `header.tools` lists every schema sent that turn:

   ```bash
   zstd -dc "$F" | python3 -c 'import json,sys
   for line in sys.stdin:
       e = json.loads(line); d = e.get("data") or {}
       if e["type"] == "request/header":
           print("offered:", "ask_user_question" in [t["name"] for t in d["header"]["tools"]])
       if e["type"] == "tool/call" and d.get("name") == "ask_user_question":
           print("called:", d["callId"])'
   ```

Until this drill passes on a live face, the face does not claim Kairos can ask.

**Drilled and PASSED 2026-09-03**, on a live face booted against a throwaway
`$DSH_HOME` with a real model, and again 2026-09-08 on the operator's own face
(34 tools offered). Exercised end to end: the tool reached the model
(`request/header` offered 26 tools including this one); Kairos called it; the
card rendered with its options; the answer returned as the tool result
`{"answers":[{"id":"pit_bed","selected":["2yr"]}]}` and the turn continued on it.
Answered here the card reads `answered`; killed with Stop, `closed · cancelled`
with the sidebar chip cleared and no resurrection on a session switch; and the
Gate-2 approval card still reads `answered · deny`, which the settle path had to
be taught to keep. Step 6 — the AGENTS.md instruction — is the operator's to run.

**Known residuals, deliberately not fixed here.** The card has no Dismiss
button, so the host's `ASK_CANCELLED` path is unreachable from this UI and
plan-mode's "the user dismissed the review to speak instead" branch is dead;
Stop is the only exit. And a question BLOCKS the turn, so an answer typed into
the composer instead of the card is queued for the next turn rather than
delivered — it says `sent` and nothing happens. Answer in the card.

## The bots drill (run after any face or dsh change)

A mask never pulled is presumed decorative.

**Step 0, no model, no key.** `FACE_SMOKE=1 npm test` boots the real tree three extra times.
`bots-smoke.test.ts` proves the roster lists a broken fixture with its reason and never
`_template`, that a session created with `agentPreset` carries it on its header, that the bot
sees exactly its allow-list ∩ the tree while Kairos sees the host's whole roster unchanged, that
the bot's prompt opens with its own persona while Kairos's opens with `persona.md`, and that a
session naming the broken preset is refused at `session.create` with dsh's own `agent-preset`
error code.
`bot-sandbox-smoke.test.ts` and `askuser-noclient-smoke.test.ts` print one `observed:` line each
(S4, S7); their findings are recorded in the spec's amendments block.

**Step 0b, if you changed anything under `client/`.** Hard-reload; `registerStatic` sets no
cache headers.

**The drill**, with the face live:

1. Agent face → **bots** → `+ new bot`. Type a display name with spaces and capitals; PASS,
   part one: the id field shows the folded proposal, lowercase with dashes.
2. Create. PASS, part two: the bot page opens; `bots/<id>/` exists with `agent.cordis.yml`,
   `preset.yml`, `SOUL.md`, `README.md`, `skills/README.md`, `journal/notes.md`; the boot line
   of a restart, `agent presets: …`, lists the id.
3. `open home`, say something. PASS, part three: the sidebar shows the session under the bot's
   name, not under `ungrouped`; the reply speaks in the bot's persona, not Kairos's.
4. Ask the bot to list its tools. PASS, part four: it names the shell, file and web tools and
   `ask_user_question`, and does not name `subagent`, `place_order`, or any `agent_<bin>` — and
   if the alpaca-kit MCP server is connected, it names the market-data reads and not `orders`.
5. On the bot page, edit the soul to include `{{` and save. PASS, part five: refused with the
   strict-template message; the file is unchanged.
6. Clean up: `git rm -r bots/<id>` (or keep it — it is yours).

**Drilled and PASSED 2026-09-07 and again 2026-09-08** on the operator's own face (real
`$DSH_HOME`, the alpaca-kit server connected; `main` @ `b6dbce0` the second time). Second run:
`Growth Momentum Scout` folded to `growth-momentum-scout`; six files; the restart's boot line
listed it; the home session bucketed under the bot; the reply opened in its persona; the tools it
named were exactly the allow-list ∩ the tree — 18 offered in `request/header`, the seven
market-data reads among them and no `subagent`, `agent_<bin>` or order tool; the `{{` soul was
refused with both files byte-identical. The speaker label (R12) held on the `who` element, the
composer, the topbar and the status pulse across session switches, a reload and a restart. One
observation → R13 in `DEVELOPMENT.md` §9: every cold session lists as `untitled`.

## The room drill (run after any face or dsh change)

A room whose strip never moved is presumed decorative.

**Step 0, no model, no key.** `FACE_SMOKE=1 npm test` boots `room-smoke.test.ts`: a stub model
route, three bots in a temp channel, one operator prompt → Kairos dispatches all three in
parallel → alpha answers, beta passes, gamma's model fails → the answer is on the room log before
the round-end wake, the wake is one turn, Kairos's synthesis is in it; every member is parented,
preset-joined, `read-only` as its first event, carries the channel's `AGENTS.md` chain and lacks
`dispatch`; the `room` value rides the session row and the cache file; an `@` turns alpha, whose
write into the channel is refused inside the tool content (D12) and never woke Kairos; a home
session writes its journal and is refused on `../SOUL.md`.

**Step 0b, if you changed anything under `client/`.** Hard-reload.

**The drill**, with the face live, on the tracked fixtures — the voices `drill-bull` (看多派) and
`drill-bear` (看空派) on the channel `room-drill` — or on two template bots you create on the agent
face (the bots drill, steps 1–2) and a fresh channel:

1. Channel page → **bots in this channel** → check both in. PASS, part one: two chips read
   on; `$DSH_HOME/face/roster.log` gained a dated `bots` line; `channels.json` carries `bots`.
2. `new round`, ask a question that invites two views ("X 值得买吗？各说各的"). PASS, part
   two: the strip appears with Kairos and both voices; Kairos's dispatch card reads
   `Dispatched <A>, <B> (parallel) … Not called: none.`; both chips go `called` → `thinking` /
   `writing` → `answered` or `passed`; each answer is a bubble in the bot's own voice with its
   glyph; the round line reads `round 1 · settled · …`; Kairos wakes once and names the
   disagreement.
3. Sidebar and answer traces. PASS, part three: the room row has no Members dropdown;
   each bot's answer has a closed `思考轨迹` control at its bottom-right. Expanding it
   shows that member turn's context, thinking and tool records in place.
4. `@<bot> …` in the composer. PASS, part four: the status line reads `@ → <bot>`; the bot's
   chip moves and its bubble lands; Kairos does not speak (no new Kairos turn until you prompt
   it); the `@` shows as your own bubble.
5. Make a bot ask: `@<bot> 先问我一个问题再回答`. PASS, part five: the card appears inline in
   the room headed `<bot> asks`; the chip reads `waiting for you`; the channel header and the
   landing page's session row show the needs-you mark; answer it; the mark clears and the
   bot's answer lands.
6. Make a bot write: `@<bot> 在当前目录写一个 test.txt`. PASS, part six: no file appears; the
   bot's answer trace (or its own session, opened from the strip) shows the bash result with
   `[sandbox: file access denied under read-only mode]`; the bot reports the refusal in the
   room.
7. Un-check one bot on the channel page and come back. PASS, part seven: its chip reads
   `left`; `@` to it resolves nobody (the text goes to Kairos as a prompt); re-check it and
   `@` it again: the same member session answers.
8. Restart the face, open the room. PASS, part eight: the strip's coarse states survive
   (the projection cache); each answer's trace still loads its recorded member turn.

**PASS criteria are observations.** Record the run below with the date and the commit.

**Drilled and PASSED 2026-09-09** on the operator's own face (real `$DSH_HOME`, the alpaca-kit
server connected, DeepSeek as the model; `feat/rooms` @ `31b2e68`), two fresh template bots
(`看多派`, `看空派`) on a fresh channel `room-drill` (all three kept since as the tracked fixtures), the question "SanDisk (SNDK) 现在值得买吗？请各说
各的". Part one: the check-in went through the channel-bots route the chips call (the landing page
is reachable only once the channel has a session); `roster.log` gained the dated `bots` line and
`channels.json` carried `bots`; the chips read on once the page existed. Part two: Kairos read the
channel, pulled the point-in-time record, then called `dispatch` — the card read `Dispatched 看多派,
看空派 (parallel), round 1 of this operator message; 2 rounds left after it. Not called: none.` —
ended its turn, both answers landed as attributed bubbles with their glyphs, the line read `round 1 ·
settled · answered: 看空派, 看多派`, and the one wake produced a synthesis that named the
disagreements first; the log order was `turn/end` → both answers → one `turn/start` → the round-end
prompt → the synthesis. The strip stayed hidden on this first round — the create path fetched no
room state (drill finding F1, fixed the same day in `31b2e68` and re-verified: a fresh round shows
`Kairos organizing · 看多派 · 看空派` with the first prompt). Part three: the room row folded `2
members`; a member's own transcript opened with its `context · room` delta row, its reply under its
own name, `Message 看空派…` in the composer, and no strip. Part four: `@看多派` read `@ → 看多派`, the
chip went `writing` then `answered`, the answer landed, and Kairos's turn starts stayed at two.
Part five: `@看空派 先用 ask_user_question 问我一个问题` raised the card inline headed `看空派 asks`, the
chip read `waiting for you`, the channel header and the landing page's session row carried the
mark; answering cleared the mark and brought the answer. Part six: `@看多派 …写一个 test.txt` — the
member's `bash` was refused inside the tool content under `read-only`, its retry with
`sandbox_permissions` raised the escalation card inline (`approval 看多派 · bash`), denied; the bot
reported the refusal in the room; no file. Part seven: un-checked, the chip read `left` and an `@`
to it went to Kairos as a prompt; re-checked, the same session answered (still `2 members`), and
the answer sent while Kairos's turn was open landed right after its `turn/end`. Part eight: after a
restart the cold listing carried the room's title and its `room` value from the cache, the fold and
the strip's coarse states survived. Three observations, none a failure: the landing page lists the
member sessions as plain `untitled` rows (shown and counted, not yet labelled by voice); Kairos,
handed an un-rostered `@` as a prompt, assumed the voice would answer — `AGENTS.md` should say that
such an `@` named nobody (the sentence landed the same day, in its Rooms paragraph); the peer-`@` continuation was superseded by the operator's next `@` before
it ran (by design), so that path stands on the engine tests, not on this drill.
