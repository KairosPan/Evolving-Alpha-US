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
  `cordis-host-runner`, the storage chain (`storage`, `storage-json`,
  `storage-domain`, `workspace`), or the `hmr` / `session-telemetry-otel`
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

## Strategy workspaces (src/strategies.ts + the session picker)

A session's dsh workspace IS a strategy: a new session starts with a picker —
the `strategies/*` directories (each with its status.yaml badge), `workbench`
(the repo root, for non-strategy chores), and a create field that births a new
strategy from `strategies/_template` on the spot. The first prompt creates the
session with the picked directory as `cwd`, and the sidebar groups sessions by
strategy (derived from each session's `cwd`; foreign directories group by
basename). Two loopback-fenced routes feed it: `GET /data/strategies.json` and
`POST /data/strategies` (validated name, template copy, never overwrites).
The picker's `choose a local folder…` row opens the OS's own directory dialog
through `host.pickDirectory` (the directory-picker-auto row the overlay
mounts); the chosen path becomes the session's workspace and groups by its
basename. Cancel returns null and changes nothing.

Groups fold (chevron on the header; view state per browser), and each row
carries four hover actions: rename and fork are the host's own RPCs
(`session.rename`, `session.fork` — a fork opens immediately); archive and
delete are face routes, because the host has neither at this pin. Archive is
metadata in `$DSH_HOME/face/archived.json` — the session still exists, folded
into an `archived` group at the bottom, reversible. Delete removes the
session's persistence directory permanently (confirm-gated, never offered on
a running session, no undo) and tombstones the id: a session deleted while
its agent is still attached keeps listing from host memory until the next
face restart — and write-behind can even re-persist its directory — so the
sidebar hides tombstoned ids unconditionally and the ghost dies with the
restart.

The sandbox boundary follows the workspace — deliberately: a strategy session
writes its own `strategies/<name>/` freely, and anything outside (the repo's
`.git` included) only through a Gate-2 escalation card. The write map's
"Kairos works strategies/ freely" becomes code, and a `git commit` from a
strategy session is an approval the operator answers — accepted trade,
2026-09-01.

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
  `$DSH_HOME/face/agents.json`. The `+ connect` row opens a handshake page —
  detected candidates (the panels.ts suggestion list, probed and not yet
  connected) one click away, anything else by name — and
  `POST /data/agents/connect` admits a binary ONLY if it answers
  `<bin> --version` (execFile, no shell; the name is fenced to one bare PATH
  token, so a request body can never steer the probe to a path). Probes cache
  per bin for a minute, but connect probes fresh. Rows disconnect from a
  hover `×` or the agent's own page (`POST /data/agents/disconnect`); a
  connected binary that stops answering stays listed greyed rather than
  vanishing. Each agent's page is its directory entry (status / binary /
  version). *A2A network* is a declared placeholder page — network agents
  land there when that opens.
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

All panel routes are loopback-fenced like the rest of `/data`; the roster's
connect/disconnect are the only writes, and they touch nothing but the
face's own metadata file. `panelDeps` fails loud at boot when
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
