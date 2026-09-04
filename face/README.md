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

Two read-only pages beside the chat, reached from the sidebar footer and from
each other: **`/market`** — the composite tape, the bed's maturity rail,
breadth, and both screens — and **`/account`** — balances, positions, Alpaca's
most recent 50 orders (all statuses, not just the open ones), and the
order-gate strip. The only interaction on either page is `refresh`: nothing
here places, cancels, or changes anything, and the gate strip DISPLAYS what the
two order gates compute to rather than operating them.

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
real computed gate strip, because the gate reads the environment and stays
computable with no broker client at all. `ALPACA_KIT_ENABLE_ORDERS` stays
unset, so Gate 1 reads unregistered; Gate 2 reads not-validated and points at
the drill below — the strip states that intent rather than claiming a
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
| **Roster** (runtime) | `$DSH_HOME/face/channels.json` | the operator, on the channel page |

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
`+ new` still opens the same picker (`showStrategyPicker`,
`client/chat.js:1291`), but its rows come from `/data/channels.json` instead
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
   `logRosterWrite`, called from `src/channels.ts:524`), naming the
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

A narrow icon rail at the far left picks which face the sidebar shows:
**strategy** (the working face — everything above), **agent**, **memory**,
**plugin**. One pattern across all four (operator direction): the sidebar is
always an INDEX — rows, never content — and clicking a row opens that item's
page in the RIGHT pane, in place of the chat (`.main.detail-mode` hides the
flow + composer; the topbar names the open item; picking a session or
"+ new" always brings the chat back). Strategy's "content" is the chat
itself. The three instrument faces are read-only, refetch on every open, and
split by data source:

- **agent** indexes three sections. *Main agent* is Kairos — the dsh runtime
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
  tokens, so it stays a directory entry until its provider is pinned. *A2A
  network* is a declared placeholder page — network agents land there when
  that opens.
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

## Chat rendering (client/render.js + the collapsed process rows)

The transcript renders dsh-style calm: every tool call and every injected
user-role message (AGENTS.md context, skill catalog, file notices, cron
wake-ups) is ONE collapsed line — chevron · kind · one-line summary · status —
expanding on click. A failed call's error is in the line itself, no click
needed. Prose bubbles and the answerable gates (approval / question) keep
their full shape: only what the operator must read or act on is loud.

Thinking follows dsh's design: while a reasoning block is OPEN, the flow's
tail carries one ephemeral indicator — a spinning mark and elapsed time,
NEVER content — and the status line reads "Kairos is thinking…". Only when
the message settles does the thinking itself appear, as a collapsed `think`
row above its bubble (a reasoning-only step is a think row with no bubble).
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
FACE_SMOKE=1 npm test     # + the one real boot (throwaway $DSH_HOME, no LLM call)
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
Gate 1 to do it. Any harmless denied-then-escalated file write proves the same
seam.

Until this drill passes on a live face, the face does not claim Gate 2.

**Drilled and PASSED 2026-08-31** on the live face with the workbench toolset mounted:
deny (command did not run; the model saw a rejection result, never the card) and approve
(`allowed-once`, one-shot) both exercised, with paired `approval/asked` +
`approval/decided` records in the session log. Re-run after any face or dsh change, per
the heading above.

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
`$DSH_HOME` with a real model. Exercised end to end: the tool reached the model
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
