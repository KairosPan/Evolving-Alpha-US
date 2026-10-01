# kairos-face — the chat-light face as an in-process dsh host

One Node 22 process. It boots the DeepSeek Harness — dsh `0.2.0-rc.2`, pinned in
`src/version.ts` — from the `face` profile (bundles: `@deepseek-ai/dsh-base`
only), composes its policy defaults below the operator's patch layer and its own
host rows on top of it, and serves the operator's chat UI — and the two
read-only instrument pages below — at http://127.0.0.1:3090/, behind the
tokenized sign-in URL it prints at start. No build step — `tsx` runs the
TypeScript directly. Specs: `../docs/superpowers/specs/2026-08-30-face-chat-light-design.md`
and `../docs/superpowers/specs/2026-08-31-face-instruments-design.md` — dated
design history, written against dsh 0.1.1-rc.2; this file and
`../DEVELOPMENT.md` carry the mechanism as it stands.

## Deploy the product landing page to Vercel

Production: [evolving-alpha.vercel.app](https://evolving-alpha.vercel.app).
Project: `kairospans-projects/evo-alpha`.

The public site is Gravit's English product introduction page for investors
and partners, built from `face/landing/`. Its
product gallery contains three screenshots of the existing client, staged with
illustrative public data and English presentation labels. Images can be enlarged
or opened at full resolution; they are not live account or market views. The
local workbench in `face/client/` still runs with `npm start`.

Use `face/` as the Vercel project root. `vercel.json` runs the dependency-free
`node scripts/build-static.mjs` build and publishes `dist/`; locally, run
`npm run build`. The build and `.vercelignore` explicitly allow only the nine
public landing files: `index.html`, `styles.css`, `main.js`, `favicon.svg`,
`social-card.svg` (editable sharing artwork) and `social-card.png` (social
preview), plus `demo-research.webp`, `demo-market.webp` and `demo-account.webp`.
No API keys, backend, workbench files or runtime data are
published. The previous public `/market` and `/account` URLs permanently
redirect to the landing page's `/#product` section.

Screenshot fixtures are isolated from the local host. Run
`node scripts/serve-research-demo.mjs` to serve the real channel renderer with
a fictional English research record at `http://127.0.0.1:4182` (1440 × 1080).
Capture that preview separately at 1440 × 1080 into `landing/demo-research.webp`.
From `face/`, run `node scripts/capture-demo-assets.mjs --capture` to regenerate
the Market and Account images at the same size. It serves the actual clients
with in-memory fictional responses on port 4181, uses an installed Playwright
CLI from the npm cache (or `PLAYWRIGHT_CLI_PATH`), then closes the fixture.
Omit `--capture` to inspect the preview manually. These capture helpers are
not included in the Vercel upload or public build.

To deploy again after signing in with `vercel login`:

```bash
cd face
vercel link --yes --project evo-alpha --scope kairospans-projects
vercel deploy --prod --yes --scope kairospans-projects
```

## Run

```bash
cd face
npm install
npm run setup            # creates $DSH_HOME/profiles/face (never overwrites)
source ../.env.deepseek  # DEEPSEEK_API_KEY - see below
# Optional market credentials, exported to the server process:
set -a
[ ! -f ../.env.alpaca ] || source ../.env.alpaca
[ ! -f ../.env.ifind ] || source ../.env.ifind
set +a
npm start                # prints http://127.0.0.1:3090/?token=…  (profile: face)
```

Open the URL `npm start` prints — the one carrying `?token=` — not the bare
address (see "Sign-in" below). A face that came up prints:

```
kairos-face: agent presets: aqr-audit, aqr-data, aqr-method, drill-bear, drill-bull, kairos, news-scout (default kairos; bots under …/bots)
kairos-face: http://127.0.0.1:3090/?token=… (profile: face)
kairos-face: the ?token= is a per-process secret: it mints a 30-day cookie for this host:port; later visits to the plain URL work
kairos-face: rooms: dispatch registered; caps {…}
```

preceded by `kairos-face: order gate armed for …` when order tools are
registered (the order-approval drill below). A bot the face could not declare
is reported on stderr (`kairos-face: bot "<id>" is not declared - <reason>`),
and the `agent presets` line then ends `; N bot(s) not declared, see above`.

Without the key the face still boots and serves: sessions list, the UI works,
and the first prompt fails with a missing-credential error from the LLM route.
`../.env.deepseek` is gitignored and not loaded automatically. Equivalently, put
`DEEPSEEK_API_KEY` in `$DSH_HOME/.env` — `bootFace` runs dsh's layered env load
before composing, so the harness home's `.env` reaches the tree too.

The model is whatever dsh-base's `agent-default-model` row says —
`deepseek-official/deepseek-flash` — unless the profile patch overrides that
row (upgrade decision D2; the row to add is in "The profile" below). Nothing
else moves it: the face reads no `$DSH_HOME/settings.yaml` (D1: it provides no
`profileContext`), and a client's `session/selectModel` "save as default"
persists nothing here, because dsh saves a default only through a config
editor this tree does not mount.

A session's project directory is the **workbench repo root**, not `face/`: the
entry `chdir`s there before booting (spec section 3.2), because dsh's
`SessionController` takes that default from `process.cwd()`
(`new SessionCommandController(ctx, this.agents, process.cwd())`) and offers
no config key. The sandbox resolves each session's workspace root from that
session's own `cwd`, falling back to the same directory — so for a session
created outside any channel, "outside the session workspace" below means
outside the whole repo.

| Env | Default | What |
|---|---|---|
| `FACE_PORT` | `3090` | webserver port. `0` asks the OS for a free one |
| `FACE_PROFILE` | `face` | profile directory name — honored by BOTH `npm run setup` and `npm start` |
| `DSH_HOME` | `~/.dsh` | the harness home: profiles, sessions, storages, credentials — the browser-session signing secret included |
| `DEEPSEEK_API_KEY` | — | resolved per request through the credential seam, then the environment |
| `DSH_TELEMETRY_DISABLED` | unset | the telemetry row is already off by the face's policy layer (D3); this switch matters only once an operator patch re-enables it, and then still wins — ANY non-empty value (`0` and `false` included) disables it again |
| `DSH_PERMISSION_MODE` | `workspace-write` | sandbox mode. `danger-full-access` also sets the approval policy to `never` — it DISARMS the Gate-2 surface below (the order gate then refuses orders rather than running them) |
| `FACE_AKSHARE_MCP_COMMAND` | `~/.local/bin/akshare-mcp` (expanded absolute path) | AKShare MCP executable; no shell command or arguments |
| `HTTP_PROXY` / `HTTPS_PROXY` | — | not applied inside the face process — neither to its own quote and Alpaca fetches nor to dsh's requests: the face does not install dsh 0.2.0's proxy policy (D10), matching 0.1.1, which had none. Tool subprocesses still inherit the variables |

`FACE_PORT` and `FACE_PROFILE` read an empty value as unset, not as a literal:
`FACE_PROFILE=""` would otherwise resolve to `$DSH_HOME/profiles` itself, and
`FACE_PORT=""` is `Number("") === 0` — a face whose URL silently moves on every
restart. `"0"` is a non-empty string, so deliberately asking for an OS-assigned
port still works.

Ctrl-C (SIGINT) leaves 130, SIGTERM leaves 0; both dispose the tree first. A
startup failure dsh reports itself — a required row that did not activate, such
as `webserver` on a port already in use (`… webserver (required) …
EADDRINUSE`) — prints dsh's grouped diagnostic and exits 1. Every refusal in
"What boot refuses" below reaches app-boot's `installFailLoud`, which prints it
labelled `kairos-face` and exits 1.

### Sign-in: the tokenized URL

dsh 0.2.0 puts `/api` and the `/api/remote.mux` WebSocket behind a browser
session, and the face's `/` is where that session starts (`src/static.ts`,
dsh's `connection.authorizeIndex`):

| Request | Answer |
|---|---|
| `GET /?token=<the printed token>` | `303 ./` plus `Set-Cookie: dsh-auth-<hash>=…` — `HttpOnly`, `SameSite=Strict`, `Path=/`, 30 days, and no `Secure` (loopback HTTP) |
| `GET /` with that cookie | the chat page |
| `GET /?token=…` again, already signed in | `303 ./` |
| `GET /` without the cookie | `401` |
| `/api/*` and the `/api/remote.mux` upgrade without the cookie | `401`; a forged `Host` gets `403` even WITH a valid cookie — the loopback fence runs first |

- The token is per process: 32 random bytes, new on every start, printed on
  stdout and stored nowhere.
- The cookie is per **authority**: `127.0.0.1:3090` and `localhost:3090` are
  two sign-ins, and another `FACE_PORT` is another.
- It survives restarts for its 30 days because its signing secret is
  persistent: the first boot on a harness home writes a
  `client-connection/browser-session` grant record into
  `$DSH_HOME/.credentials.yaml`, beside the API keys. Removing that record and
  restarting mints a new secret, which signs every browser out.
- A tab whose cookie expired reads `not signed in - open the URL kairos-face
  printed when it started (…/?token=…)` on its status line.
- `/market`, `/account` and `/client/*` stay public files, and every `/data/*`
  route keeps only its own loopback Host/Origin fence (`isTrustedDataRequest`,
  `src/data.ts`) — no cookie, exactly as at 0.1.1 (upgrade decision D8). The
  instrument pages therefore work without a sign-in; the chat page does not.

### What boot refuses

dsh 0.2.0's own boot fails only when one of its required rows (in this tree:
`agent-loop`, `webserver`, `connection`) does not activate, and merely warns
about every other row. The face keeps 0.1.1's stricter contract: `bootFace`
(`src/boot.ts`) disposes the tree, never opens the browser streams, and throws,
naming the cause, when:

- the profile skipped a bundle (dsh-base failed to load);
- any enabled row is not ACTIVE once boot resolves — the strict row audit lists
  each as `id (package): state`: a pending row with the services it waits for,
  a failed row with its error, a throwing `disabled:` expression as a failure.
  A row naming a package the tree cannot import is refused here, where dsh
  itself would only have warned;
- a service the gates and rooms route through is missing — `approval`,
  `userQuestions`, `typertGateway`, `permissionPresets` — each refusal naming
  what its absence would silently cost;
- no ACTIVE `@deepseek-ai/dsh-api-remotes` row exists: the approval answerer.
  Without it the tree boots clean and passes every other check, and then every
  order is denied `no approval channel is available` and every question is
  refused `NO_PROVIDER`, with no card anywhere;
- `ask_user_question` is not in the live tool registry;
- a tool marked `(operator-gated)` would not stop at the order gate (a renamed
  tool or MCP server);
- the preset registry is missing, its default is not `kairos`, its roster
  cannot be read, the default preset is absent or broken, or a bot the face
  declared is not listed;
- `../dsh/profile/persona.md` is not a valid strict template, or
  `../bots/kairos/agent.cordis.yml` is missing or not YAML — both caught at
  compose time, before anything mounts.

`main.ts` adds two: the `connection` service must exist (it is what mints the
cookie), and the browser streams open only once every face route is mounted —
it boots with `deferReady` and calls `commitReady()` last, which refuses a tree
that stopped in the meantime. A tab still holding its cookie reconnects the
moment the gateway admits it, so it must never find `/data` half-mounted.

## AKShare MCP — A-share queries in Kairos

The project mounts AKShare through `src/akshare.ts` on each boot. This is a dsh
connection, independent of any Codex MCP configuration. The installed executable
can be shared by both clients; each client starts its own stdio server process.

Install the selected community implementation once with uv:

```bash
uv tool install --python 3.12 --with 'mcp<2' \
  'git+https://github.com/xiaozhozho/akshare-mcp.git@9b6a22b6d83cce2a996a5072743bb06686040ce0'
```

The Git source is intentional: PyPI's normalized `akshare-mcp` package name
belongs to a different implementation. This revision uses the MCP SDK 1.x
FastMCP API, so retain the `mcp<2` constraint. Startup does not install or update
packages. A missing executable is logged without taking down the chat host.

After starting/restarting the face, **Plugin → akshare** shows the live tool
roster. `/data/plugins.json` should list `server: "akshare"` with 14 tools,
including `mcp__akshare__akshare_discover` and `mcp__akshare__akshare_stock_a`.
Use discovery first; the Tencent A-share snapshot call is:

```json
{"method":"stock_zh_a_spot_tx"}
```

Pass that to `mcp__akshare__akshare_stock_a`. This fetches the whole vendor
snapshot before returning at most 500 rows; inspect `truncated` and `row_count`
before drawing whole-market conclusions. Calls have a 120-second timeout.
These public-source queries have no PIT guard and are for interactive research;
they do not supply historical replay or the `/market` page's US PIT instruments.
Data timestamps and retrieval time are different, and source errors must remain
visible (the Eastmoney and Xueqiu quote tests failed on 2026-09-15).

The `mcp-akshare` row is composed after the base bundle and the face's policy
defaults, and before the operator's profile/home patches. An operator patch can
replace its config or disable it with `- { id: mcp-akshare, disabled: true }`.
No installed profile patch is rewritten to add this connection.

**What dsh 0.2.0 changed for every MCP row** — this one and the operator's
`mcp-alpaca-kit` alike; no config key changed (`src/akshare.ts` records it):

- The client moved to `@modelcontextprotocol/client` 2.0 with version
  negotiation, and stdio negotiation starts a temporary probe process before
  the serving one: each server is spawned **twice** per connect, which doubles
  alpaca_kit's import cost at boot.
- A connected server's `instructions` enter the system prompt as a section
  named `mcp:<serverName>`, with no switch. akshare-mcp sets them, so Kairos's
  prompt — and every bot's, because prompt sections are not masked the way
  tools are — gains an `mcp:akshare` section. Instructions over
  `maxInstructionBytes` (32 KiB by default) now fail the connection.
- The three MCP resource tools dsh-base 0.2.0 adds (`list_mcp_resources`,
  `list_mcp_resource_templates`, `read_mcp_resource`) are off by the face's
  policy layer (D7).
- `failOnStartupError` stays `false`: a server that cannot start leaves its row
  ACTIVE with no tools, so the boot audit cannot see it. The check is
  `/data/plugins.json` (or **Plugin → <server>**): `akshare` with its 14 tools,
  and `mcp__alpaca-kit__*` tools under the operator's alpaca-kit row. A
  one-tool FastMCP server on the operator's interpreter (`mcp` 1.28.1)
  negotiated with the 0.2.0 client in a 2026-09-30 probe; the real alpaca-kit
  and AKShare servers are live-drill items of the go-live runbook
  (`../docs/superpowers/runbooks/2026-09-30-dsh-0.2.0-rc.2-go-live.md`).

## The profile

`npm run setup` writes THREE files into `$DSH_HOME/profiles/<name>/`, and
refuses a directory that already exists — it prints `exists, untouched: <dir>`
and changes nothing. Profiles are operator territory.

| File | What |
|---|---|
| `package.json` | the profile manifest: `dsh.profile.bundles: ["@deepseek-ai/dsh-base"]` |
| `cordis.patch.yml` | the operator's patch layer — a header plus a load-bearing `[]` (an empty array, not an empty file: dsh-app-boot throws on anything that is not a top-level YAML array) |
| `pnpm-workspace.yaml` | pnpm settings, verbatim from dsh's own `initProfile`, so `dsh plugin add` can install into this profile later |

The header is written once, at setup, so a profile created before the
0.2.0-rc.2 upgrade still carries the 0.1.1 wording, which names rows that no
longer exist. The current text is `PATCH_HEADER` in `src/setup.ts`; refreshing
the comment is optional and the operator's to do.

Mount the workbench toolset — the `alpaca_kit` MCP server and the two skill
roots — into `cordis.patch.yml` per `../dsh/README.md` steps 3-6. The face boots
with or without it.

**The default model is a row here (upgrade decision D2).** dsh-base's
`agent-default-model` row says `deepseek-official/deepseek-flash`, and with no
`profileContext` (D1) the face reads neither `$DSH_HOME/settings.yaml` nor any
saved selection, so this row is the only way to change it:

```yaml
- id: agent-default-model
  config: { provider: deepseek-official, model: deepseek-v4-pro, reasoningEffort: max }
```

A patch that names `config` replaces the row's whole config, so give all three
keys. dsh 0.2.0's DeepSeek catalog is `deepseek-flash` and `deepseek-v4-pro`;
`deepseek-v4-flash` is gone. The agent panel's model card shows what took.

**How the tree is composed** (`composeFace`, `src/boot.ts`), in order:

1. the bundle layer — dsh-base, which now includes the storage chain
   (`storage`, `storage-json`, `storage-domain`) and `session-projection-cache`,
   rows the face mounted itself at 0.1.1;
2. the face's policy defaults (`src/policy.ts`; "The policy layer" below);
3. the project's AKShare connection (`mcp-akshare`);
4. this profile's `cordis.patch.yml`;
5. the machine-local `$DSH_HOME/cordis.patch.yml` — then, for a tool only, an
   in-memory layer (`bootFace`'s `extraPatches`; `scripts/check-home.ts` uses
   it, `npm start` never does);
6. the face's switches: the telemetry opt-out (only while
   `DSH_TELEMETRY_DISABLED` is set), `hmr` disabled, and Kairos's persona;
7. the face's own host rows (`src/overlay.ts`), last.

A row of yours therefore wins over layers 1–3 — the storage chain, the
projection cache and every policy row are yours to patch — and loses to 6–7.

Two things about that directory are NOT yours:

- **`<profile>/cordis.yml` is face-managed.** `composeFace` rewrites it on every
  boot. The whole tree is composed as patch layers, and the root exists only as
  an empty entry list anchoring the loader's `baseUrl`; anything you put there
  is gone at the next start. Edit `cordis.patch.yml`.
- **The face's own host rows compose LAST and win silently.** They are applied
  after your patch layer and after the machine-local home layer — the inverse
  of the dsh CLI's layering, and deliberate: loopback-only binding surviving an
  operator patch is the point. A patch of yours aimed at one of the twelve
  overlay rows — `webserver`, `connection`, `api-remotes`, `file-upload`,
  `workspace`, `session-controller`, `workspace-controller`,
  `settings-controller`, `directory-picker`, `tool-ask-user`,
  `agent-preset-registry`, `preset-kairos` — or at the `hmr` switch, at
  `system-prompt`'s `personaPrefix`, or (while `DSH_TELEMETRY_DISABLED` is set)
  at `session-telemetry-otel` is accepted, overridden, and NEVER reported.
  Change those in the face — `src/overlay.ts`, `src/boot.ts`,
  `../dsh/profile/persona.md`. The same warning is in the patch file's own
  header, which is where an operator would actually look.

The persona is narrower than it was. dsh 0.2.0 renamed the key: the face sets
`system-prompt.personaPrefix` (section `deployment:persona-prefix`, order 0,
right after the harness identity line) from `../dsh/profile/persona.md`, and
that key is ALL it owns on the row: its patch restates every other key the
layers below left there, so an operator's `includeRuntimeContext`,
`includeHarnessIdentity`, `personaSuffix` or `toolOrder` survives. At 0.1.1
the face replaced the row's whole config and discarded them without a word.

## The policy layer (src/policy.ts)

dsh-base 0.2.0 changed several product defaults that decide what Kairos can do
and what leaves the machine. The face restores the 0.1.1 posture in one
reviewable file, composed directly above the bundle layer and BELOW the
operator's layers — so, unlike the overlay rows, each of these is a default the
operator overrides with one same-id row (three for `web_fetch`) in
`$DSH_HOME/profiles/face/cordis.patch.yml` (`tests/policy.test.ts` pins that an
operator row wins). Every row is an upgrade decision, named by its id:

| Decision | dsh-base row | The face's default (0.1.1 parity) | dsh-base 0.2.0 default | Following upstream instead |
|---|---|---|---|---|
| D3 session telemetry | `session-telemetry-otel` | disabled | `FEEDBACK_ONLY`: after a `/feedback`, a session-log prefix goes to `dsh-otel-collector.deepseeksvc.com` with the home's `.anonymous-user-id` | `- { id: session-telemetry-otel, disabled: false }` (D15; `DSH_TELEMETRY_DISABLED`, when set, still wins) |
| D4 session-log upload | `session-log-deepseek` | disabled | up to 8 MiB of session events in every official DeepSeek request (`dsh_session_log`) | `- { id: session-log-deepseek, disabled: false }` |
| D5 package inventory | `plugin-package-inventory-deepseek` | disabled | the active plugin-package list in every DeepSeek request | `- { id: plugin-package-inventory-deepseek, disabled: false }` |
| D6 `web_fetch` | `tool-web`, `web`, `web-fetch-http` | `tool-web: {fetch: false, searchTimeoutMs: 60000}`, `web: {searchProvider: deepseek-official}`, `web-fetch-http` disabled | `web_fetch` on, served by `web-fetch-http` | `- { id: tool-web, config: { fetch: true, searchTimeoutMs: 60000 } }`, `- { id: web, config: { searchProvider: deepseek-official, fetchProvider: http } }` and `- { id: web-fetch-http, disabled: false }` |
| D7 MCP resource tools | `mcp-resources` | disabled | `list_mcp_resources`, `list_mcp_resource_templates`, `read_mcp_resource` and a prompt section, once any MCP server registers | `- { id: mcp-resources, disabled: false }` |
| D9 `ralph` | `tool-ralph` | enabled (`disabled: false`; dsh-base's config kept) | disabled | `- { id: tool-ralph, disabled: true }` |
| D9 `str_replace_editor` | `tool-str-replace-editor` — dropped from dsh-base; the face inserts it, configless (`maxOutputChars` now defaults to 0.1.1's 16000) | mounted | absent | `- { id: tool-str-replace-editor, disabled: true }` |

Two patch rules decide how such rows are written: a row that names `config`
replaces that row's WHOLE config (hence the full restatements for D6), while
`{ id, disabled }` keeps it. A policy target missing from the bundle — a row
renamed upstream — is reported on stderr at boot (`kairos-face: warning:
policy D…: dsh-base composes no "<id>" row …`), never skipped silently.

The effect is measured, not assumed: on a profile with no MCP server the live
tool roster equals 0.1.1's name for name (26 tools), and the smoke asserts that
`str_replace_editor` and `ralph` are registered while `web_fetch` and the three
MCP resource tools are not. Turning `web_fetch` on opens a new outbound path
for the model, with no PIT guard on what it reads; the shipped bot allow list
(`DEFAULT_ALLOW`, `src/bots.ts`) does not name it, so voices stay without it
either way.

### Every decision the upgrade defaulted

The upgrade to 0.2.0-rc.2 was planned around decisions D1–D18 — the ids the
code comments cite as "PLAN D…". The charter and the design specs number their
own decisions in separate series (the persona's D11, the bots spec's D12 for
read-only room members), so this file says "upgrade decision" where it means
these. Each has a default in the code and is the operator's to revisit:

| Id | Default | Where |
|---|---|---|
| D1 | No `profileContext`: no settings service (`settings/describe` has none), `$DSH_HOME/settings.yaml` unread, no config editor, plugin manager or `dsh-hmr` | `src/boot.ts` header, divergence 2 |
| D2 | Default model = the profile's `agent-default-model` row, else `deepseek-official/deepseek-flash` | above |
| D3–D7, D9, D15 | The policy rows | above |
| D8 | No browser cookie outside `/` and `/api`: `/data/*` keeps only its loopback fence, `/market` and `/account` stay public | "Sign-in" |
| D10 | No HTTP proxy policy | "Run", env table |
| D11 | Pre-0.2 room logs stay on disk untouched; a legacy member session becomes that member's failed turn | "Sessions written before 0.2.0" |
| D12 | The 0.1.1 CLI and the pre-upgrade face do not run on a home 0.2.0 has written — an operator practice, not code | "Upgrading dsh" |
| D13 | `$DSH_HOME/profiles/node_modules`, the 0.1.1 link farm, goes once D12 holds — the operator deletes it | "Upgrading dsh" |
| D14 | The face never un-archives a host archive (409) | "Channels" |
| D16 | A cold session opens page-only, never activated by a view | "The wire and the transcript" |
| D17 | Three descriptor-v2 subagent children and one seq-gap log stay unreadable on disk, like D11 | "Sessions written before 0.2.0" |
| D18 | The tool-result spill budget stays at dsh-base's `maxInlineTokens: 12500` | "Market-data renderers" |

## Market and Account

The primary navigation opens **`/market`**, a personal watchlist spanning US
stocks, A shares and cryptocurrency pairs, and **`/account`**, the read-only
account console. These pages never place or cancel orders.

### Market watchlist

The top search button (also **Cmd/Ctrl K**) queries an on-demand instrument
search API by name or code. Search supports market filters, keyboard
navigation and adding/removing selections. The list supports market tabs,
addition-order/code/percentage-change sorting and undoing the most recent
removal. Missing prices remain em dashes and sort after available prices.
Quotes retain their own currency, source and observation date; green means a
rise and red a fall across all three markets.

A first visit starts empty. Selections are stored under
`kairos.market.watchlist.v1` in this browser's `localStorage`, with
market-qualified identifiers such as `us:AAPL`, `cn:600519` and
`crypto:BTC/USD`. They are independent of the broker account and are not
synchronized across devices. Same-origin browser tabs synchronize through
storage events. Storage failures are shown explicitly.

The live Market page uses `GET /data/quotes/stream?ids=us:AAPL,cn:603986,crypto:BTC/USD`
for Server-Sent Events (SSE). Each named `quotes` event contains the current
selected-set snapshot; named `heartbeat` events arrive every 15 seconds.
`GET /data/quotes?ids=...` provides the same JSON contract for manual refresh
and a 15-second browser fallback when SSE is unavailable. Only selected
identities are requested, with at most 100 per page. Empty selections make
no upstream requests. Adding/removing a selection updates subscriptions;
hidden pages release their connections and reconnect when visible.

The server shares one Alpaca and one Coinbase socket across active pages,
subscribing to their union without whole-market wildcards. A latest-value
cache stays in RAM (at most 512 identities), with no market-directory download
or disk quote cache. Browser events are coalesced to 500ms; identical snapshot
reads share work and use a five-second cache. Upstream REST bodies, timeouts,
Coinbase request starts and browser connections are bounded. Slow/disconnected
SSE clients release their subscriptions. Provider failures preserve the last
known quote with its original timestamp and an explicit stale status.

| Market | Provider and update path | Coverage and interpretation |
|---|---|---|
| US stocks/ETFs | Alpaca snapshots, trades and daily-bar WebSocket updates | `iex` by default, covering only IEX. Its stream subscribes to at most 30 symbols; remaining selected symbols use periodic snapshots. `sip` requires its entitlement; `delayed_sip` is explicitly labelled 15-minute delayed. Changes use the previous session's close. |
| A shares | iFinD `real_time_quotation`, only requested codes | Requires an iFinD access or refresh token. Without one the page says the source is unconfigured. Polling defaults to 30 seconds while selected. Event timestamps are interpreted as Beijing time. Volume stays unavailable until its provider units can be verified with an account. |
| Cryptocurrency | Coinbase Exchange ticker/heartbeat WebSocket, per-product REST ticker/stats | Public USD pairs supported by Coinbase; a search result is not a guarantee of Coinbase coverage. Changes and volume use a rolling 24-hour window, and are labelled accordingly. |

Snapshots initialize the display and refresh US/crypto baselines every 60
seconds while streaming, or every 15 seconds while their socket is unavailable.
Market state distinguishes connection status from data availability. Alpaca's
clock describes the regular session; closed does not rule out extended-hours
trades. Quote time always comes from a provider event, never local retrieval
time. Old or missing data is not replaced by historical PIT prices. These
live, interactive reads are not guarded replay/backtest evidence.

The legacy `GET /data/watchlist.json` remains available and runs the fixed, read-only
`scripts/face_watchlist.py` producer, then merges the shared reference directory
from `client/market-catalog.js`. The producer reads the latest captured US
snapshot through `GuardedSource` and `AsOfGuard`; the face's former breadth
walk is not needed to open Market. The shipped 2yr bed currently supplies 797
US rows dated **2026-07-09**, with raw daily closes and changes relative to the
previous close. These are historical snapshots, not live quotations, and the
live Market page no longer requests this route.

`GET /data/symbols/search?q=兆易创新&market=all` queries Tencent smartbox for
A shares and Yahoo Finance search for US stocks/ETFs and USD cryptocurrency
pairs. `market` accepts `all`, `us`, `cn`, or `crypto`. Search does not download
or save a whole-market directory. The backend caches up to 128 successful
queries in memory for 60 seconds, shares duplicate in-flight requests, and
bounds each provider request to six seconds. The API uses the same browser
trust checks as the other data routes and requires a running local backend
with outbound HTTPS access to the providers.

The frontend debounces input, cancels superseded requests and ignores late
responses. Provider outages appear as search errors or explicitly partial
results; they are not reported as a successful empty search. A blank query
shows saved selections and 35 built-in suggestions (12 US instruments, 15
A shares, 8 cryptocurrency pairs); these do not limit online search coverage.
On a static deployment or disconnected backend, these suggestions and
watchlist management remain available, while online search reports an error.

Online search returns instrument identities, not prices. Results can be saved
even when the selected quote provider does not cover them; missing prices stay
em dashes. Search and live quotes operate independently.

#### Market credentials

| Environment variable | Default | Purpose |
|---|---|---|
| `APCA_API_KEY_ID`, `APCA_API_SECRET_KEY` | — | Existing Alpaca credentials, held only by the backend. |
| `ALPHA_DATA_FEED` | `iex` | `iex`, `sip`, or `delayed_sip`; no silent entitlement downgrade. |
| `IFIND_ACCESS_TOKEN` | — | iFinD token, preferred when set. |
| `IFIND_REFRESH_TOKEN` | — | Alternative: obtain the current access token through the official token endpoint; cache it only in memory. |
| `FACE_IFIND_POLL_MS` | `30000` | iFinD refresh period while selected; minimum 15000ms. Set according to the account's data quota. |

Copy `market-env.example` to the repo's gitignored `.env.ifind`, enter the
credentials locally, export it before starting the server, then restart.
No token is sent to the browser or returned in errors. Coinbase public market
data needs no credential. iFinD's adapter is covered by mocked tests, but A-share
live validation remains pending until an account is configured.

Provider references: [Alpaca streams](https://docs.alpaca.markets/us/docs/real-time-stock-pricing-data),
[Alpaca coverage](https://docs.alpaca.markets/us/docs/about-market-data-api),
[Coinbase channels](https://docs.cdp.coinbase.com/exchange/websocket-feed/channels),
[iFinD manual](https://quantapi.10jqka.com.cn/gwstatic/static/ds_web/quantapi-web/help-center/manual.html),
[iFinD quotas](https://quantapi.10jqka.com.cn/gwstatic/static/ds_web/quantapi-web/help-center/permission.html).

### Account console

`/account` reads `/data/account.json`: balances, positions and Alpaca's latest
50 orders (all statuses). Equity comes first, with cash, buying power and
unrealized P&L, then positions/orders tabs. Search and order-status filters
narrow the loaded rows only. Unrealized P&L is shown only when every position
reports its amount. Connection and order-gate details remain collapsed until
opened. The environment badge follows the actual read hostname: only
`paper-api.alpaca.markets` is labelled Paper.

| Env | Default | What |
|---|---|---|
| `FACE_PYTHON` | `python3` | interpreter able to import `alpaca_kit`; install the project into that environment |
| `ALPHA_PIT_ROOT` | `data/pit/2yr` | captured bed for US watchlist quotes and the legacy market data endpoint |
| `APCA_API_KEY_ID` / `APCA_API_SECRET_KEY` | — | account credentials inherited at startup; source `../.env.alpaca` before `npm start` |

Without account credentials the page shows an unconnected account, not a zero
balance. The actual computed gate state is still available in details.
`ALPACA_KIT_ENABLE_ORDERS` stays unset; these views do not operate either gate.

### Data routes and caches

All producer, search and quote routes retain the loopback Host/Origin fence from `src/data.ts`,
and need no browser cookie: dsh 0.2.0's sign-in covers `/` and `/api` only, and
the face keeps `/data`, `/market` and `/account` as they were (upgrade decision D8).
Request data never enters the child process arguments. A successful payload
is cached in memory: **watchlist 15 minutes, legacy market 15 minutes, account
60 seconds**. Concurrent cache misses share one producer process. Watchlist
and account producers have a 30-second timeout; the old market producer has
a 10-minute timeout. Refresh re-reads the relevant endpoint and respects its
cache. After a later read failure, the previous good payload is returned with
`stale: true`; the watchlist marks it as a retained snapshot.

The original **`/data/market.json` remains available for compatibility**, with
its tape, breadth, screens, warmup metadata and two assembly/serve timestamps.
It is no longer the `/market` page's data source. A cold legacy assembly walks
the whole bed (~284 seconds measured); later runs read its disk cache under
`data/.face_cache`. That cache key includes the resolved bed path, producer
source and as-of day. `scripts/face_data.py` still produces both this legacy
payload and account data.

## Channels (src/channels.ts + src/roster.ts + the session picker)

A channel is one directory, given an identity by the host and a roster by the
operator. Three layers, split by who may write them:

| Layer | Lives in | Writer |
|---|---|---|
| **Body** (content) | `strategies/<dir>/`, or the repo root | Kairos, freely |
| **Identity** (container) | the dsh workspace registry (`~/.dsh/storages/workspace.json`) | host-owned, only through the registry — the host's `workspace/*` Remotes, and the face's reconcile calling it in-process |
| **Roster** (runtime) | `$DSH_HOME/face/channels.json` — `agents[]` (local CLIs Kairos may call) and `bots[]` (the voices a room may dispatch) | the operator, on the channel page |

The directory is the truth of existence, not the registry: `listChannelDirs`
(`src/channels.ts`) walks `strategies/*`, skipping `_template` and any name
starting `.` or `__`, and adds the repo root by hand (it has no `strategies/`
parent, so it stays the `workbench` entry). `workspaceRegistry.create` is
idempotent — canonical path, at most one record per path, a repeat call
returns the existing title unchanged — so a channel Kairos makes with a plain
`mkdir` becomes a channel on the very next listing.

**The reconcile** (`reconcileChannels`, `src/channels.ts`) runs on every
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
own dialog (`directoryPicker/pick`, which answers a bare path or `null`) for
anything outside a channel. The sidebar
groups sessions by channel MEMBERSHIP, not by path prefix: a session no
channel claims folds into a counted `ungrouped` bucket — never dropped,
charter Rule 5 — and the archive fold is the UNION of the face's own
reversible set (`archived.json`) and the host's one-way
`workspaceRegistry.archivedSessionIds`, because the two already disagree on
disk and neither alone is honest about what is archived.

Groups fold (chevron on the header; view state per browser), and each session
row carries four hover actions: rename and fork are the host's own Remotes
(`session/rename`, `session/fork` — a fork opens immediately; a rename resumes
the session first, so on a cold one it is a write like a prompt, see "The wire
and the transcript"); archive and delete are face routes. dsh 0.2.0-rc.2 has no
session delete Remote at all, and its archive (`workspace/archiveSession`) is
not presentation: a host-archived session runs no model step until the host
restores it. So the face keeps its own fold — metadata in
`$DSH_HOME/face/archived.json`; the session still exists, folded into an
`archived` group at the bottom, reversible — and never un-archives a host
archive: that click answers 409 with the reason (upgrade decision D14). Delete
removes the session's persistence directory permanently (confirm-gated, never
offered on a running session, no undo) and tombstones the id: a session
deleted while its agent is still attached keeps listing from host memory until
the next face restart — and write-behind can even re-persist its directory —
so the sidebar hides tombstoned ids unconditionally and the ghost dies with the
restart. Opening a cold session no longer attaches it (it is paged, not
followed — D16), so viewing and then deleting stays off that path; the
attached case is a session this face run prompted, renamed or `@`-addressed.
`deleteSession` also constrains itself to sessions whose `cwd` resolves inside
this repo, not merely to an id it happens to find, closing a pre-existing gap
where the delete button could reach another project's session directory. It
reads that `cwd` from the directory's highest canonical log generation —
`session.v4.jsonl.zstd` for a session born or written under 0.2.0, else the
0.1.1 `session.jsonl.zstd` — and the `rm -r` takes every generation, the lock
and any staging file with it.

Deleting a session does NOT detach it from its channel: the id stays in the
registry's `sessionIds`, because the host's `workspace/*` Remotes at 0.2.0-rc.2
— `create`, `initializeDefault`, `rename`, `delete`, `insertBefore`,
`insertSessionBefore`, `archiveSession`, `unarchiveSession`, `pinSession`,
`unpinSession`, and the `follow` stream — offer no way to remove one session
from a workspace. The orphan is inert — nothing resolves it, so nothing renders it,
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
and sessions (the channel's own, joined against `session/list`, plus "new
round").

**The roster**, `$DSH_HOME/face/channels.json` (`src/roster.ts`), keyed by
workspace id so a directory rename never loses it:
`{"version":1,"channels":{"<workspaceId>":{"agents":["codex"]}}}`. A newly
adopted channel is seeded from whichever agents are connected at that
moment — there is no "absent means everything" rule; a channel's roster is a
definite, visible set at every moment. The enforcement point is
`agent_<bin>`'s own `execute` (`agentToolDefinition`, `src/agents.ts`): it
reads the calling session's cwd, resolves its channel, and on a miss THROWS —
naming the channel and its current roster verbatim. The tool pipeline
(`dsh-tools`) catches a thrown `execute` and turns it into an `isError` result
carrying that message, so what Kairos actually sees is a tool result, never a
crash — but the mechanism there is a thrown `Error`, not a returned value.
That refusal message IS the roster's contract; it is deliberately not written
into the channel's own `AGENTS.md`, which is Kairos-writable and would drift
from the operator-owned file. A channel with no roster entry yet (created
straight through the registry, before a listing has seeded it) reads as "no
roster yet" and refuses; an unparseable `channels.json` reads as "no rosters"
and refuses every call — fail CLOSED, *within a resolved channel*. What
happens when there is no channel to resolve in the first place is honest
limit 2, below.

**Deleting a channel** needs no new route and no button: remove the
directory (Kairos's own write map, or the operator's shell), then call the
host's `workspace/delete` Remote with `{request: {workspaceId}}` — there is no
UI for this second step yet. `/api` needs the browser cookie now, so the
simplest caller is the signed-in chat page's developer console:
`(await import("/client/api.js")).call("workspace/delete", { request: { workspaceId: "<id>" } })`.
Order matters: `workspaceRegistry.create` rejects a nonexistent path, so once the
directory is gone the reconcile can no longer resurrect the record. `delete` never
touches the directory or the session logs; the channel's sessions simply fall into
`ungrouped`.

### The honest limits — the roster is a menu, not a fence

Charter Rule 3 requires recording a residual rather than shipping a guarantee
that fails at code level. In the same register as the Gate-2 note further
down this file:

1. **dsh tool registration is tree-wide.** There is no per-session scoping
   seam — `tools.register` (`registerTool` in `panelDeps`, `src/panels.ts`)
   publishes one flat name per bin (`agent_<bin>`, `toolNameFor` at
   `src/agents.ts:84`) that every session sees. A non-member agent's SCHEMA is
   still visible in every channel; only the call is refused.
2. **The roster check only runs inside a resolved channel — a session in NO
   channel is not roster-checked at all.** `agent_<bin>`'s `execute` reads
   `const channel = await deps.channelFor(cwd)` and gates the entire roster
   read behind `if (channel !== null)` (`src/agents.ts:469-470`); when
   `channel` is `null` there is no `else`, and control falls straight through
   to `runAgentRecipe` — every connected agent callable, unconditionally. This
   is deliberate, not an oversight: `channelFor`'s own comment says "the
   caller fails open either way" (`panelDeps`, `src/panels.ts`), because there
   is no roster to consult and tools are registered tree-wide regardless of
   channel. It is also cheap to reach, not a rare edge case: the picker's
   **`choose a local folder…`** row creates a session straight from a raw
   `cwd`, never a `workspaceId` (`showStrategyPicker`, `client/chat.js`), so
   that session resolves to no channel and is never roster-checked; a channel directory
   that exists on disk but has not yet been through a reconcile lands in the
   same place.
3. **Kairos has a shell.** One shell turn can invoke `claude` directly. This
   roster is a MENU, not a fence — it reduces noise and states intent; it
   does not contain.
4. **One un-escalated shell turn can `curl` `POST /data/channels/agents` —
   no approval card, no git diff, no session event.** The sandbox confines
   FILE effects only: the emitted Seatbelt profile is `(allow default) (deny
   file-write*)` plus write allow-lists (`seatbeltProfileArgs`,
   `node_modules/@deepseek-ai/dsh-sandbox-local/lib/index.js`), and
   `dsh-bash-sandbox`'s own README says the modes "govern file effects only —
   network stays unrestricted". `/data` is a REACHABILITY FENCE, not
   authentication: `src/data.ts` — "A request with no Origin (curl, the
   tests, …) passes on Host alone" — and it stays fence-only at 0.2.0-rc.2
   (D8). Verified against the running face at 0.1.1: a `curl` POST to
   `/data/strategies` (this route's name before the rename to
   `/data/channels`; the fence itself is unchanged) cleared the 403 and the
   415 and reached the handler, refused only by name validation, while a
   forged `Host` still 403'd; a `curl` RPC `workspace.list` returned the real
   registry, HTTP 200. dsh 0.2.0 closed that second half against a bare
   `curl` — `/api` now answers 401 without the browser cookie — but not
   against a determined shell turn: the cookie is an HMAC over its payload,
   keyed by the signing secret in `$DSH_HOME/.credentials.yaml`, and the
   sandbox lets a shell READ that file (dsh-client-connection's
   `browser-auth`; stated from the code, not drilled). This is not
   introduced here — `POST /data/agents/connect` (`src/panels.ts`) already
   writes `$DSH_HOME/face/agents.json` and registers a tool live by the same
   path, and predates this design entirely. **The mitigation is visibility,
   not prevention**: a roster write appends a dated line to a durable face log,
   `$DSH_HOME/face/roster.log` (`src/roster.ts`'s `logRosterWrite`, called
   from the `POST /data/channels/agents` handler in `src/channels.ts`), naming
   the workspace, the resulting agent list and an ISO timestamp, so a change
   is SEEN even though it cannot be stopped. Building a token for `/data`
   would be new face security machinery against the charter's §7.4; dsh now
   ships one for `/api`, and putting `/data` behind it too is D8's open
   alternative. Recording this is what Rule 3 actually asks for instead.

**Two residuals, out of scope, recorded per Rule 3 (spec §10).** Neither is
caused by this change; both are recorded because it touches their
neighbourhood:

1. **The alpaca-kit MCP server is a child of the face PROCESS, not of a
   session**, so its writes never pass `ctx.sandboxPolicy`. Evidence on disk:
   `data/.screen_cache/` was written at the repo root during 2026-09-02
   strategy work, with no approval card.
2. **`system-prompt.persona` was empty** — `''` in `dsh-base` and set by
   neither `src/overlay.ts` nor the operator's `cordis.patch.yml`, so the
   model was never told it was Kairos. Closed since: `composeFace` sets it
   from `dsh/profile/persona.md` (at 0.2.0 the key is `personaPrefix`; see
   "The profile").

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
  this face hosts; its page is a card grid over three reads:
  `session/modelCatalog`'s `default` (provider, model and reasoning effort —
  the selection a new session starts from, i.e. the D2 row), the face's own
  `/data/host.json` (`{cwd, home, attachedSessions, version}` — dsh 0.2 has no
  `host.describe`), and `credentials/describe` (each key `set · <source>` or
  `not set`, never a value; an absent entry reads `unknown`, a malformed
  answer an error). `settings/describe` is not called: it needs the
  `profileContext` the face does not provide (D1). Its *session usage* card is
  fed by the `session/control` stream's projection items (tokenUsage /
  contextPressure, from dsh-token-meter's projection units) — a per-session
  store keeps whole values with higher seq winning, seeded by the control
  baseline, a follow's snapshot or a paged session's `session/projections`
  read; a list row's `cached` block never seeds it, because its watermark is
  not comparable with a live session's. The context bar turns
  danger-colored at 80%. *Local agents* is an
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
  wire `skills/list` is addressed by a session and carries no SKILL.md body or
  pack, so two face routes read `ctx.skills` in-process: `GET /data/memory.json`
  (grouped by pack — the directory under `dsh/skills/`, mechanics first) and
  `POST /data/memory/skill` (`{name}`, kebab-validated). A skill's page is
  the full SKILL.md body at document width, rendered with the same
  client/markdown.js the bubbles use.
- **plugin** indexes the MCP servers and the composed row tree:
  `GET /data/plugins.json` projects `ctx.loader.entries()` (the same short
  projection `dsh-host-plugin-inventory` makes — at 0.2.0 a
  `pluginInventory/list` Remote and an exported `readPluginInventory(ctx)`,
  mounted only by dsh-web-app; the face restates it rather than mount a row)
  plus `ctx.tools.schemas()` grouped under each `dsh-mcp-client` row's
  `serverName`. A row's `options.config` is never serialized — the MCP row's
  env block carries the APCA keys; `serverName` is the one field read. A
  server's page is its live tool table; the tree's page is the full
  module/id/phase table — about 110 rows at 0.2.0-rc.2, ids of the form
  `include:<row id>` — its index row calling out any `failed` count.

Every `/data` route — the panels', the instruments', the strategy and session
routes — stands behind a browser-trust fence modelled on the one the harness
puts in front of `/api` (`isTrustedDataRequest`): a loopback Host, no
Fetch-Metadata `cross-site`, and a present `Origin` that matches the Host —
and, unlike `/api`, behind nothing else: no browser cookie (D8). Every `/data` POST
additionally requires `application/json` (415 otherwise), so a cross-site
page cannot reach a side-effectful route with a "simple" request that needs
no preflight. The roster's connect/disconnect are the only writes to face
state (its own metadata file); an agent tool spawns that agent's own CLI
with a fixed argv and writes nothing durable of its own — a Codex call gets a
`mkdtemp` scratch directory under the OS tmpdir for `-o`, read once and
removed when the run ends. `panelDeps` fails loud at boot when
`skills`/`tools`/`loader`/`workspaceRegistry`/`agents` are missing from the
tree — a dead panel with nothing on stderr is the failure mode it exists to
prevent.

## Bots (src/bots.ts + src/bot-presets.ts + plugins/bot.js + bots/)

A bot is a dsh **agent preset** the FACE declares: one directory under `bots/`
holding `agent.cordis.yml` (its composition), `preset.yml` (`name`,
`description`, optional `model`), `SOUL.md` (the persona SOURCE), `skills/` (its
stance pack, a dsh skill root) and `journal/` (the one directory it may write,
from its home). dsh 0.2.0 scans no directory and reads none of these files —
its preset registry (`@deepseek-ai/dsh-agent-preset-registry`, the overlay's
`agent-preset-registry` row) takes only the definitions a plugin hands it — so
the face builds each definition from `bots/<id>/` itself (`src/bot-presets.ts`),
and the declaration only ever READS those files; the authoring routes below are
their only writer.

- **`bots/kairos` is the default** every session joins when it names none: an
  EMPTY composition, so Kairos's own sessions keep the host's flat roster
  unchanged (`bots-smoke.test.ts` pins the two tool sets equal). It is the
  overlay's static `preset-kairos` row, built by `definitionFor` at compose
  time, so it exists before the first `session/create` resolves it.
- **Every other bot is declared after the tree has settled** — after the MCP
  rows' first discovery and the boot audit — by `declareBots`, one child plugin
  of the root per bot, which is the registry's own declaration model. The
  timing matters because a declaration activates AT ONCE: declared any earlier,
  `plugins/bot.js` would mount before the host's late tools existed. Only
  directories whose names pass `isBotId` are declared, so never `_template`,
  and a bot the repository does not carry cannot exist: nothing else the
  face composes declares one.
- **Rebasing.** dsh resolves a preset's rows against the DECLARING context's
  base — the profile directory — where 0.1.1 resolved them from the preset's
  own directory. `definitionFor` therefore rebases every `./` or `../` row and
  every absolute path row to an escaped `file:` URL against `bots/<id>/`
  (recursively inside `group: true` rows), and a relative `customSkillDirs`
  entry of a `@deepseek-ai/dsh-skill-filesystem` row to a path under
  `bots/<id>/`. The last one changes behaviour: at 0.1.1 `./skills` resolved
  against the process cwd, `face/`, and scanned a directory that does not
  exist; it now scans `bots/<id>/skills`, which today holds only a README.
- **`preset.yml` is read exactly as 0.1.1's dsh read it**: `name`,
  `description` and `order`, trimmed, a blank value omitted; an absent or
  malformed file is empty metadata, and the bot still declares. `model` stays
  face-only — a dsh preset carries no route.
- **A composition the face cannot read** — missing, unreadable, not YAML —
  leaves the bot undeclared: the reason, with the file path, goes to stderr
  and `/data/bots.json` shows the bot `broken`. A readable composition that is
  not a list IS declared, and the registry lists it broken in its own words.

`bootFace` refuses to start if the registry service is missing, its default is
not `kairos`, the roster cannot be read, the default preset is absent or
broken, or a bot the face declared is not listed: every `session/create`
resolves a preset, so a roster that cannot supply one would fail every session
instead of the boot. A bot that merely fails to declare does not stop the boot
(0.1.1 listed a broken bot and started too).

**Saving re-declares.** dsh 0.2.0 never re-reads `bots/<id>/` (0.1.1 re-read it
on every mount), so every create, settings or soul save re-declares that bot's
preset — dispose, then declare, serialized per bot — before the route answers.
Conversations already running keep the revision they joined; new ones get the
saved files, with no restart. A superseded revision is disposed by the
registry once no live agent uses it. Two edges:

- **The redeclare window.** Between the dispose and the new declaration, a
  `session/create` or a room member naming that bot fails
  `agent-preset/not-found`. That is upstream's model — the registry refuses a
  duplicate id, so the old declaration has to go first.
- **A failed re-declaration** answers `500 bots/<id> was saved, but the
  running face could not re-declare it (…); restart the face to load the
  saved files`: the files ARE saved, and a restart declares them.

**Kairos is the host plane; a bot is a mask.** Kairos is told who it is by the
`system-prompt` row's `personaPrefix`, set from `dsh/profile/persona.md` by
`composeFace` (charter decision D11, closed; a malformed template refuses the
boot with the file named — `readPersona`). A bot's composition names one
face-owned plugin, `plugins/bot.js` (`kairos-bot`), which registers the bot's
persona as a scoped `deployment:persona-prefix` section — shadowing Kairos's
for that preset's agents; the face sets no persona suffix — and an
**allow-list** `tools.restrict`. Allow, not deny: dsh admits later-registered
globals through a deny mask and excludes them through an allow mask, and the
two tools a voice must never see that are registered *after* the mount —
`agent_<bin>` on connect, `dispatch` in the rooms arc — are excluded by the
allow form without being named. `mcp__…__place_order` is excluded by OMISSION
from the list. `mcp__*__<raw>` in the list expands against the live tree
(`expandAllow`), so the operator's server name does not matter.

Because a preset activates when it is declared, not at its first session, the
mask FOLLOWS the tree: `bot.js` re-expands the allow list after every burst of
`tools/change`, one coalesced pass per burst (a synchronous pass per event
blocked the event loop for about a second on an unregister burst with 10 bots
and 45 tools). An allow-listed tool that registers later — an MCP server that
connects late, or reconnects under the same names — is admitted; a tool no
allow list names never is. Names the tree does not have are warned once, at
the mount. A bot whose FIRST mask is empty throws, and the registry marks that
revision broken for good ("a mount failure is final"); a save or a restart
recovers it. A later re-expansion that fails keeps the mask in force.

**The mask is visibility, not authority.** dsh says so of every scope ("live visibility
composition, not an authority boundary"). What a bot may write is its session's sandbox mode;
what it may order is Gate 2, which is tree-wide. Neither changes when a bot is masked, and
neither is containment. At 0.2.0 a `read-only` session's refused write also carries dsh's
escalation hint (`[sandbox: escalation available — retry this exact command once with
sandbox_permissions …]`), inviting a voice to retry once and raise an approval card — which
only the operator can grant.

**Authoring is the face's own copy.** The **New bot** form (agent face → bots → `+ new bot`;
`POST /data/bots`) copies `bots/_template`, writes `preset.yml` and `SOUL.md`, and RENDERS
`agent.cordis.yml` so the persona row's text is the soul's (`renderComposition`) — dsh's
`!!js` cannot read a sibling file. The settings page edits name, description, default model,
and SOUL together. Its optional role guide builds a local draft from the operator's
perspective, evidence standard, revision criteria, participation rules, and style.
Creating without a SOUL replaces the template's `<bot name>` with the chosen name.
Saving updates the persona inside the existing composition, preserving other plugin rows,
paths, allow patterns, and skill configuration. The legacy soul endpoint remains supported.
The parser uses the Loader's own entry-list schema (`entryListSchema`) so `!!js`
expressions round-trip without evaluation. An entirely dynamic bot config must be edited by
hand; SOUL saving refuses it with 409. An unparseable composition retains the legacy repair
behavior of rebuilding template rows. Same-bot reads and writes serialize; the UI supplies a
saved-file revision, and a stale save returns 409 without losing the editor draft. Files are staged before
replacement, with rollback on ordinary I/O failure; this is not a crash-safe multi-file
transaction. A hand edit to `SOUL.md` reaches nothing until the face saves it again. The
page flags source/persona drift and placeholder text. No `{{` anywhere in a soul: the
prompt is a strict template with no escape, and both write paths (`rejectSoul`, on the way
in) and the plugin itself (`validateBotConfig`, at mount) refuse it.

**A bot's home** is a session created with `cwd = bots/<id>/journal` and `agentPreset = <id>`
— the client's `openBotHome` arms the next prompt exactly as a channel's "new round" does,
and the host's own `session/create` mounts the preset (no in-process agent creation).
The sidebar buckets a bot's sessions under its name from the session's preset, which
0.2.0's `session/list` rows no longer carry: `client/summaries.js` `summaryOf` restores it
from the row's `agentPreset` projection first, then from `/data/channels.json`'s `presets`
(built from the persisted and live session headers), and leaves it absent rather than
guess (`grouping.js` `bucketFor`, `BOT_KEY_PREFIX`); the strategy picker never offers a
journal as a "local folder" (`knownFolders` skips every cwd under `bots/`). Reading the same
preset, the transcript names the voice: in a bot's session its display name stands over
every reply, its ask cards read `<bot> asks` and the composer says `Message <bot>…`, while
Kairos's own sessions stay `Kairos` (`speaker.js` `speakerFor`). Ids keep the retired 0.1.1
preset grammar `[a-z0-9][a-z0-9-]*`, bounded to 64 code points (`BOT_ID_RE`) — dsh 0.2.0
asks only for a non-blank id, so this is the face's own gate. The form proposes an id from
the display name (`botId.js` `proposeBotId`, the browser twin of the server's —
`botId.test.ts` pins that a non-empty proposal is always an id `isBotId` accepts) and the
server refuses anything else — `kairos` by name (`RESERVED_IDS`) and `_template` by the
grammar, which admits no leading underscore (both through `isBotId`).

**Default model and inspection** (`src/bot-runtime.ts`). **New test conversation** uses
saved settings, with the actual session created on the first message. Unsaved edits disable
that button. A bot's `provider/model` seeds its home session's first request without changing
the host default; subsequent requests inherit their own logged model, and a saved route the
tree does not serve fails that first request (`Bot model <route> is unavailable. Update the
saved route and start a new conversation.`). Room model
selection stays with the room engine. The face seeds through its own prompt-assembly and
request hooks, never through dsh's `session/selectModel`, whose default save persists nothing
in this tree anyway (D2). A model selected over the wire (`session/selectModel`) before a
bot's first request is superseded by that bot's saved initial route; the face has no such
model-switch control.
Which preset a session runs is read from dsh's `agentPreset` projection, which follows an
`agent-preset/selected` re-selection, not from the header's creation-time value.

The page lists configured tool patterns and local skill declarations separately from
**Session inspection**. An idle live session is assembled under `runMaintenance` to show
its mounted persona, model and tool schemas; its last actual request is labelled separately
and read from `request/header`. During a turn, inspection reads captured persona and logged
request facts without assembling. Cold sessions are never resumed just to inspect them.
The saved revision and startup revision are diagnostics, not claims that every part of a
request is frozen. Resuming after a host restart mounts the bot's current declaration.

**Journal context** (`src/bot-journal.ts`). Before every bot request, the runtime reads that
bot's own `journal/notes.md`, in both home and room sessions. It is a separate `bot-journal`
context section, not part of SOUL: historical notes to check against current evidence, not
new instructions. Reads are bounded to 12 KiB, reject symlinks, and report missing, empty or
unavailable notes without blocking the request. Inspection shows the status, content revision
and truncation flag. dsh 0.2.0 persists the assembled context as a runtime-context snapshot —
a `user/message` whose source is `{kind: 'runtime-context', form: 'snapshot', sections}` —
with a `bot-journal` section. An edited journal refreshes on the next request; this hook
neither writes notes nor retrieves other channels' conversations.

| Route | What |
|---|---|
| `GET /data/bots.json` | every directory in the grammar under `bots/`, with dsh's roster merged in: `broken` reasons shown — dsh's, or the face's own when it could not declare the bot — and a directory the roster does not report flagged `listed: false` (Rule 5) |
| `POST /data/bots` | create — `{name?, id?, description?, model?, soul?}`, the id the one given or `proposeBotId(name)`; 400 an id outside the grammar or a soul carrying `{{`, 409 exists, 500 `_template` missing. The new bot is declared before the route answers (a failed declaration: 500, files kept); the returned row itself reads `listed: false` (it is built without the roster), and the next GET reports it listed |
| `POST /data/bots/soul` | `{id, soul}` — rewrites `SOUL.md` and the composition together, then re-declares; 400 a bad id or a soul carrying `{{`, 404 unknown bot |
| `POST /data/bots/settings` | `{id, revision?, name?, description?, model?, soul?}` — omitted fields stay unchanged, `model:null` inherits the default; re-declares; 409 on a stale revision |
| `GET /data/bots/runtime?id=…&sessionId=…` | live mounted preview or last-request facts, with a separate saved-SOUL comparison; unattached sessions return unavailable |

All stand behind `isTrustedDataRequest` (403), the POSTs behind 405 / 415 / 400 for
method, content type and body, with a 64 KiB body cap because a soul is prose.

**Deleting a bot** is `git rm -r bots/<id>`; there is no button. The running face keeps the
declaration until its next restart; after that the preset is gone, its sessions remain
readable history, and resuming one fails `agent-preset/not-found`.

**No client can author a bot.** dsh 0.2.0's registry exposes three Remotes —
`agentPresets/list`, `agentPresets/read`, `agentPresets/select` — and no authoring one, so
the face's routes are the only way into `bots/`, and the 0.1.1 `trust: "system"` setting,
which disarmed dsh's own copy/remove/openDocument RPCs, has nothing left to disarm. What a
signed-in client CAN do: `agentPresets/read` returns a preset's composition YAML — the bot's
persona and this install's absolute, rebased paths — and `agentPresets/select` re-points a
session that has not started its first turn to another preset (`agent-preset/locked`
after). The face offers neither in its UI, and the room's `dispatch` refuses a session whose
header OR `agentPreset` projection names a bot.

**A bot in a room** — dispatched by Kairos, addressed by the operator's `@`, its answers in the
room's transcript in its own voice — is the next section. What is still not built (spec §11, on
purpose): bot-to-bot messaging outside a room, cross-channel conversation retrieval, automatic
journal writing, a delete button, a channel-scoped 1:1 with a bot.

## Rooms (src/room.ts + src/room-rules.ts + src/room-contract.ts + src/room-projection.ts + client/room.js)

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

The brief accepts the existing string or an object with `question` and optional `context`,
`evidence` requirements, `falsification` terms and desired `output`. `src/room-contract.ts`
validates and formats both forms; the tool schema prefers the object for research questions.

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
`<bot>:`) — the brief, and standing rules carried in the prompt (reply with your view or
exactly `(pass)`; your original answer is retained in the room; this transcript covers this
room and any own journal is historical context; address the operator directly when the
judgment is theirs, write `@<bot>` to pull a peer in). Its cursor is
the delta prompt in its own log (`source.form === 'delta'`, `messageIds`), so a member never
re-reads what it saw. Parallel: everyone answers on the same delta and sees no peer this round.
Serial: each later member sees the earlier answers.

Members answer in their own voice, then are asked to append one terminal `room-view` JSON
fence: `position`, `evidence`, `uncertainties`, `changeConditions`, and `disagreements`
(`with` another roster id and `point`). Evidence remains a speaker's claim, not a verified
source. A member may name only disagreements with peer views it has actually seen; initial
parallel answers cannot invent them. Valid fields are extracted for display, while the raw
answer stays intact. Missing or malformed blocks fall back to the full text. Mentions inside
a valid structured block do not call peers. At round end, Kairos receives an attributed,
bounded comparison and instructions to distinguish factual, interpretive and risk-preference
disagreements before giving its conclusion and next check. An empty disagreement list does
not establish consensus.

**How a room fact is recorded — no `room/*` events.** dsh's persistence refuses to reload a log
carrying an event type outside its catalog (`KNOWN_SESSION_EVENT_TYPES`), so every room fact
rides a known event: membership is the member's header; the dispatch is the tool's own
call/result; an answer is a `user/message` on the room session with `source: { kind: 'room',
form: 'answer', bot, name, sessionId, turn, round }`; the round end is the waking
`user/message` with `form: 'round-end'` and every turn's state. Answer sources can also carry
`view`, `displayText` or `viewIssue`; the round-end source carries the structured `discussion`
with its brief, attributed views and unstructured speakers. These fields survive history
reload without introducing new event types — at 0.2.0 `kind: 'room'` is a native message
source of log format v4, so logs this engine writes reload. Logs it wrote under 0.1.1 do
not: 0.2.0's migration refuses a message source it cannot classify, and those room and
member sessions no longer open (upgrade decision D11; "Sessions written before 0.2.0"
below). Answers are **appended straight onto the room log** while no Kairos turn is open (a
bubble at once, a seq now, in the next request's history) and held in a per-room outbox
otherwise, flushed at the next `turn/end` and
before the round-end wake. The `room` projection unit folds these events into the coarse state
the strip shows (`called`, `answered`, `passed`, `failed`, `timed-out`, the round, `organizing`);
it rides the `session/control` stream's projection items, the follow snapshot and the
`session/list` row; for a cold room, `session/projections` answers it from dsh-base's
projection cache — at 0.2.0 one record per session,
`$DSH_HOME/storages/session_projcache/sessions/<id>.json` — without activating the room
(R13, cold rows listed `untitled`, stays closed: the list row's title comes from the same
cache).

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
back `addressed: []` and the client sends it as an ordinary prompt. An `@` into a cold room
resumes it first, through dsh's own `sessionController.resolveAgent` (the host's composition
path, never one the face assembles); a room dsh cannot open answers 409 with dsh's code and
message — for a pre-0.2 log, followed by `it looks like a log written before dsh 0.2, whose
room messages the 0.2 migration refuses - the file stays on disk untouched`.
`POST /data/rooms/state` answers the roster, the members the engine drove this boot, and the
caps left.

**The client.** A member's answer renders as a bubble in the bot's own voice — its display name
and an avatar glyph — never as a context row (`client/room.js`, `mapper.js`); the round end is a
room line followed by a **本轮讨论对照** card when discussion data exists. The card shows the
brief, each speaker's position and supporting details, declared disagreements and speakers
who supplied plain text only. Member bubbles expose evidence, uncertainty and change conditions
in a disclosure and keep the valid JSON fence out of the prose. Old logs still render as before.
The dispatch card reads as the who-was-called line. The **participants strip** above
the transcript shows Kairos (`organizing` while its turn is open) and every rostered voice:
coarse states from the projection, fine states (`thinking` / `writing` / `tool`) from the
members' own pulses, `waiting for you` when a gate is pending on the member, `left` for a member
the roster no longer carries. The pulses come from one `session/follow` (assistant stream, a
one-message window) per LIVE member of the room on screen — opened from the list's
`agentAvailable`, the host's `api-session/added` and the room projection's members — and a
member that is not followed reads `thinking` from `api-session/status`. A cold member is never
followed, because following a cold session activates it ("The wire and the transcript"); the
residual is a member that goes cold between its `agentAvailable` snapshot and the follow's
open, which that open activates. A member's question or escalation card renders **inline in the
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
blocks until the hard cap (R6). A bot can read its own shared journal, but does not retrieve
other channels' conversations or automatically maintain those notes (R5 remains partial).

**A member session dsh 0.2 cannot open** — one written under 0.1.1 — fails only that
member's turn, recorded `failed` with the reason `<bot>'s member session <id> is unreadable
under dsh 0.2 (legacy format: …); it looks like a log written before dsh 0.2, whose room
messages the 0.2 migration refuses - the file stays on disk untouched; deleting that member
session gives <bot> a fresh one in this room (archiving does not: an archived session is
still found)`. Kairos reads it in the round-end text, the round's `turns[].reason` carries it,
and the face's console logs it; the round goes on with the other voices and still wakes
Kairos. The engine never creates a fresh member behind the operator's back — that would fork
the voice's memory (upgrade decision D11).

| Route | What |
|---|---|
| `POST /data/channels/bots` | `{workspaceId, bots[]}` — the channel's bot roster, at most six ids; 400 a bad id or over the cap, 404 no such channel, 409 a corrupt roster file; a dated `bots` line to `roster.log` |
| `POST /data/rooms/say` | `{sessionId, text}` → `{addressed: [...]}`; 400 a bad id or empty text, 404 not in a channel or no such session, 409 a corrupt roster or a room dsh cannot resume (dsh's code and message) |
| `POST /data/rooms/state` | `{sessionId}` → `{roster, members, caps, round?}`; never resumes a session |

## Temporary subagents (client/subagents.js)

A temporary subagent is a delegated task with its own durable child conversation. It is
separate from the operator's named bots and the room roster: creating one writes no bot
profile or journal. Its label describes the work. The face uses the subagent stack already
mounted by `dsh-base`, with no second task registry or execution queue.

Kairos's native `subagent` tool starts a fresh context and defaults to a continuable background
child. It returns an id as soon as the first prompt is admitted. `send_message` queues a later
turn in that same child, `list_agents` inspects existing children, and `interrupt_agent` stops
the target's current turn. dsh 0.2.0 deleted the `report` tool: a resident continuable child
now messages its direct parent with the same `send_message`, which lands in the parent as an
`agent-message` relay naming the child; the runtime separately sends a settlement notice
(`subagent-settled`) with the outcome and any final answer. Relays run both ways — a parent's
`send_message` reaches its child the same way.
Kairos can continue independent work or end its turn to await that notice. A foreground
`subagent` call (`run_in_background: false`) waits and returns a one-shot result;
`subagent_fork` also remains one-shot and copies a prefix of its parent's history.

The session's **临时子任务** panel lists its direct children, including one-shot history and
catalog diagnostics. **委派子任务** prepares a prompt for the operator to complete and send to
Kairos. **查看最近输出** reads a labelled snapshot; reopening it reads the latest log again.
Opening a child follows its durable subagent address, which dsh never activates. The child page
uses its task label, links back to its direct parent, and routes continuations and
interruption through the native parent/child address. Nested work is reached through each
child's own panel. A child's message and the runtime's settlement notice are distinct
transcript items, with their original text and source retained on replay; in a child's own
transcript a message from its parent reads **父会话消息**, with a **返回父会话** button,
never as a child report.

dsh 0.2.0 has no subagent catalog or history Remote any more; the face composes both from
the session Remotes:

| Remote | What the face uses it for |
|---|---|
| `session/projections` on the parent | The direct-child catalog (`values.subagentCatalog`: durable mode and label), joined in the client with the `session/list` rows for the parent's availability (`agentAvailable`) and each child's activity (`running`); no activation |
| `session/follow` / `session/page` on a subagent address `{kind: "subagent", parentSessionId, childSessionId, mode}` | A child's transcript (followed), and **查看最近输出** (the child's own `session/projections` cut, then one `session/page` of 12 messages); neither activates anything |
| `subagents/prompt` | Human follow-up to a continuable child, through its exact live parent (`requestId`, `delivery: "queue"`); acceptance returns a message id |
| `subagents/interruptByParent` | Request interruption of a continuable child's current turn; acceptance does not mean it has stopped yet |

Refusals arrive as the host's own codes — `subagent/unauthorized`,
`subagent/parent-unavailable`, `subagent/not-found`, `subagent/catalog-diagnostic`.

**State and limits.** **运行中** means the child is mid-turn (its list row's `running`) and
**未运行** (`inactive`) that it is not — which proves neither success, completion nor
failure. At 0.1.1 **运行中** meant resident in the host, so an idle resident child now reads
**未运行** and offers no interrupt. A child the list does not show reads **运行状态未知**. A
child the 0.2.0 migration could not classify (catalog mode `unknown`) shows as the
`unsupported` diagnostic: visible, never controllable. One-shot children are read-only
history in this panel. A cold parent
cannot authorize a continuation: send a message in the parent conversation first, then retry.
Merely viewing the parent's history does not reactivate it. Interruption preserves unclaimed
queued messages and published descendants; it neither deletes the child nor stops its whole
tree. A later send can resume parked work. The native runtime owns permission inheritance,
ownership checks and cold resume. The face grants no additional tools or filesystem access.

The deployment persona in the repository's `dsh/profile/persona.md` explains when to consult
room voices and when to delegate a bounded task, how to wait for results, and how to report
uncertainty. Named bots retain their existing delegation mask.

## The wire and the transcript (client/api.js + client/mapper.js + client/chat.js)

dsh 0.2.0 deleted the wire the 0.1.1 face spoke — `POST /api/<dotted.method>`,
`POST /api/respond`, the downlink-only `/api/events.mux` — and every byte of it now 404s.
The page speaks Typert Remote through `client/api.js`, and nothing else:

- `call(endpoint, args)` — `POST /api/<namespace>/<method>`, body
  `{type: "client-request", rpcId, method, payload: {args}}`. A business failure rejects
  with the host's `code` (`session/not-found`, `gateway/arguments-invalid`,
  `agent-preset/locked`, …), a carrier failure with the HTTP `status` (401: not signed in).
  A dotted 0.1.1 name is refused before any request leaves the page.
- `openMux(…)` — ONE WebSocket, `/api/remote.mux`, carrying every stream:
  - `$events`, internal to `api.js`, one per socket generation: `ready` first, with the
    `clientId` every answer is bound to; then host facts (`api-session/added|removed|status|activity|error`,
    `agent-preset/selected`), gates (`waterfall` items for `approval/request` and
    `user-questions/request`) and their withdrawal (`cancel`);
  - `session/control`: a baseline of every attached session's projections, then one
    `projection` item per change — titles, token usage, the room strip, the subagent catalog;
  - `session/follow`: one session's transcript — a snapshot, then gap-free events, plus
    assistant-stream frames (the pulses) when asked for.
- `answer(eventId, value)` — the only way to answer a gate: `POST /api/$events/result`
  under the CURRENT generation's `clientId`.

**Reconnects** wait a fixed 1.5 s. There is no resume cursor: each new socket re-opens every
registered stream under fresh ids, and the status line reads `disconnected - <reason>;
reconnecting…` until it reads `connected` again. A socket close, a frame outside the
protocol, and an `$events` end or error all lose the generation the same way. Pending gates
are re-delivered after `ready` under their original `eventId`; one that is not re-delivered
shortly after (1 s in `api.js`, 4 s as the page's backstop) was settled while the page was
away, and its card closes. A follow re-opened after a drop REPLACES the drawn window rather
than appending a second copy.

**Gates are keyed by the `$events` `eventId`**, not by an audit id — none rides the wire any
more; the card's `raw` tooltip shows `eventId · callId`. Every connected tab receives the
same gate; the first answer settles it and every other tab receives `cancel`. Gates bypass
the transcript queue, so a card is never hidden behind a session read that failed. The card
says how it ended:

| The card reads | Meaning |
|---|---|
| `answered · approve`, `answered · deny`, `answered` | this tab's answer settled it (a question's outcome is simply `answered`) |
| `closed` | withdrawn — another tab answered, the turn was stopped, the session went away; a `cancel` carries no outcome, so the card claims none |
| `closed · no longer pending` | this connection does not hold the gate any more: answered elsewhere, withdrawn, or settled while the page was disconnected |
| `closed · settled elsewhere` | this answer lost a race — another answer or a Stop settled the gate first — and was NOT applied. The host treats a late answer as a silent no-op; `api.js` turns that race into a refusal instead of an `answered` |

An approval card sends only `allowed-once` or `rejected`. At 0.2.0 that is the face client's
rule — `api.js` refuses anything else as `bad-value` — no longer the host's, which would
accept any value in its vocabulary.

**Opening a session: follow or page (upgrade decision D16).** Following a COLD session
activates it: dsh resumes its agent, and a resume write-opens the log — publishing
`session.v4.jsonl.zstd` and taking `session.lock` before anything is appended,
irreversibly. 0.1.1's history read was read-only, so the chat keeps it that way
(`activeView`, `client/chat.js`):

- a LIVE ordinary session (its list row says `agentAvailable`) and every subagent child — a
  subagent address is never promoted — is FOLLOWED, with pulses;
- a COLD ordinary session is PAGED: `session/projections` fixes the cut and `session/page`
  reads the tail window through it, the same 50 messages 0.1.1 showed, and neither call
  activates anything;
- a paged session becomes a follow once it is live — this tab prompts it, sends it a
  command or an `@`, or the host reports it came alive. A list refresh never downgrades a
  live follow; a socket drop suspends every follow a re-open could turn into an activation,
  and the reconnect re-decides each one from the fresh list.

What still activates a cold session is WRITING to it: a prompt, a slash command, a rename,
an `@` into a room, a `dispatch` to a room member. Under 0.2.0 the first such write to a
session 0.1.1 wrote publishes `session.v4.jsonl.zstd` beside its byte-preserved
`session.jsonl.zstd`, never rolled back. A view does not write-open the log — which also
keeps delete clean (Channels, above). Stop on a paged session answers `session/not-found …
(not attached)`: there is no turn to stop.

**A new conversation** is followed before its first prompt, so the reply streams without a
click on its sidebar row. **Slash lines** go to `commands/execute` first — 0.2.0's prompt
would hand them to the model as text — and only a line no command claims continues as a
prompt; the command's result is its only feedback, on the status line (red for an error).
Every prompt carries a client-minted `requestId`.

**Face routes that fill what 0.2.0 dropped.** `GET /data/host.json` →
`{ok, cwd, home, attachedSessions, version}`, 0.1.1 `host.describe`'s host facts;
`/data/channels.json` gains `presets`, sessionId → the `agentPreset` its header names,
because `session/list` rows lost that field (`client/summaries.js` reads it). Both are
fence-only like every `/data` read.

**Against a 0.1.1 host** the page renders nothing — the mapper maps every 0.1.1 frame to
`ignore` and `call` refuses dotted names — rather than something half-right.

## Chat rendering (client/render.js + client/answer-traces.js)

Context, thinking and tool calls preceding an answer live in its closed
**思考轨迹** disclosure, opened from the bottom-right of the answer bubble.
The count includes each process row once; a tool result updates its original
call. Expanded traces retain the individual rows' summaries and detail/raw
toggles. Pending or unanswered traces have a standalone closed disclosure;
operator messages, room replies and turn endings close their association so
they cannot leak into the next answer. Approval and question cards stay
visible outside the disclosure. History and live events use the same path.
A tool card is headed by the tool's name and reads `running…`, then `done` or
`failed`: host presenters no longer reach the client at 0.2.0, so the host's
own card titles (the `Ask <label>` kind) are gone.

Thinking follows dsh's design: while a reasoning block is OPEN, the flow's
tail carries one ephemeral indicator — a spinning mark and elapsed time,
NEVER content — and the status line reads "Kairos is thinking…". Only when
the message settles does the thinking enter the answer's trace as a `think`
row (a reasoning-only step waits in the pending disclosure).
The pulses come only from a follow opened with the assistant stream — the
session on screen, and the live members of the room on screen — and the
stream's deltas themselves are never drawn.

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
the renderer never dresses up what it cannot parse. dsh spills a tool result
over its inline budget into head + tail with an elision seam and a note naming
the full-output file. At 0.2.0 that budget is dsh-base's `spill-policy`
`maxInlineTokens: 12500`, estimated as characters ÷ 4 — about 50 000
characters of ASCII, where 0.1.1 counted 50 000 bytes — so CJK-heavy AKShare
results now stay inline about three times longer in bytes. The face keeps
dsh-base's default (upgrade decision D18); a `spill-policy` row in the profile
patch changes it. The parser first tries the complete text, then the text up
to the note, then salvages whole row objects one by one — the one row cut at
the seam is dropped and the table's meta line says so.

## Tests

```bash
npm test                  # offline unit tests - no keys, no network, no port
npm run typecheck         # strict tsc against the pinned .d.ts (skipLibCheck: false) - the contract test
FACE_SMOKE=1 npm test     # + the 11 isolated real boots; local stubs, no external model calls
```

Offline, `npm test` skips the 12 real boots listed below; `FACE_SMOKE=1` runs
them too. The typecheck includes the dependencies' own `.d.ts`, so a green one
means the face compiles against the installed dsh, not just against itself.

`npm test` works on seams: the composed patch stack, a recorder standing in for
the webserver, a recorded event stream (`tests/fixtures/events.jsonl`, in
0.2.0's v4 wire shapes), the version pins. The real boots are the only place a
composition that typechecks but does not MOUNT gets caught. Each boots the real
plugin tree into its own `mkdtemp` harness home — never `~/.dsh` — and each
lives in a file of its own, because `bootFace` sets `DSH_HOME` for the process
and `node --test` gives each file its own:

| File | What it proves on a real tree |
|---|---|
| `smoke.test.ts` | the sign-in (`/` 401, token 303 + cookie, page 200); `session/list` over the new wire; `/api` 401 without the cookie and 403 on a forged `Host` even with one (the fence runs before auth); the mux upgrade has NO route until `commitReady()`, then answers 401 without the cookie and 101 with it; the Gate-2 answer channel end to end — two signed-in `$events` tabs get the same approval, one answers, the other gets `cancel`, the grant lands in the session log; `ask_user_question`, `str_replace_editor` and `ralph` registered, `web_fetch` and the MCP resource tools not; zero inactive rows; `/market`, `/account`, `/client/*` and `/data` served without the cookie, the `/data` fence drilled on its own |
| `order-gate.test.ts` (its real-tree case) | Gate 2's listener is registered: it asks for `mcp__drill__place_order` (the card naming `AAPL` and `side=buy`), `cancel_order` and a renamed server's twin, refuses an agentless call, lets `mcp__drill__orders` through; the guard refuses a marked tool the gate cannot name, and a session whose log it cannot read with its own sentence |
| `order-gate-smoke.test.ts` | Gate 2's POSITIVE path: an approved stand-in order dispatches, a rejected one does not; then the same through the real `$events` channel |
| `client-mux-smoke.test.ts` | the page's own `client/api.js` and `client/mapper.js`, unmodified, against the host: ready, calls, emits, the control baseline, a follow's snapshot and tail, an approval answered and one rejected, a second tab's `cancel` and its refused late answer, Stop withdrawing a gate, a question answered, a gate replayed to a late tab, the non-activating page and projections reads |
| `askuser-noclient-smoke.test.ts` | with no browser connected, an agent's question BLOCKS (parked for the next client); an agentless one is refused `NO_PROVIDER` |
| `bots-smoke.test.ts` | the roster (a broken fixture listed with its reason, never `_template`); the shipped relative plugin path rebased onto the real `plugins/bot.js`; a bot sees allow ∩ tree while Kairos sees the whole roster; a tool registered after the declaration is admitted; the bot's persona shadows Kairos's; a session naming a broken preset is refused with dsh's `agent-preset/*` code; Gate 2 holds for a bot |
| `bot-runtime-smoke.test.ts` | a saved route reaches the real request without changing the host default; a save re-declares — the old conversation keeps the old soul, a new one gets the new; the journal as a runtime-context snapshot; `agentPresets/select` |
| `bot-sandbox-smoke.test.ts` | a `read-only` session's write is refused inside the tool's content (`[sandbox: file access denied under read-only mode]`), never silently |
| `room-smoke.test.ts` | a round on a stub model: dispatch to three bots, answers on the room log before the one wake, the synthesis; every member parented, preset-joined, `read-only` from its first event, without `dispatch`; the `room` value in the list row and in the per-record cache file; the operator's `@` and its refused write; a home session's journal write |
| `room-discussion-smoke.test.ts` | a structured serial round: peer context, declared disagreements, the malformed-answer fallback, each member's own journal, Kairos's synthesis request, metadata surviving a flush and a re-read |
| `subagents-smoke.test.ts` | the native subagent tools and Remotes: creation, child messages kept apart from settlement notices, permission inheritance, parent ownership, ordinary writes to managed children refused, and — after a reboot — catalog and history reads that activate neither side |

`bot-sandbox-smoke.test.ts` and `askuser-noclient-smoke.test.ts` also print one
`observed:` line each (S4, S7), the measurements the bots spec's amendments were
worded from.

## Upgrading dsh — three pins, not one

`src/version.ts` holds them, and they move independently:

- **`DSH_PIN` = `0.2.0-rc.2`** — the entire `@deepseek-ai/dsh-*` family, pinned
  EXACT. Lockstep only: these packages are tested only against each other at one
  version, and a mixed set breaks the Remote wire and the session format between
  them. `tests/version.test.ts` sweeps every `@deepseek-ai/dsh-*` entry across
  `dependencies` and `devDependencies` PROGRAMMATICALLY and asserts declared
  range == installed version == `DSH_PIN`, so a dependency added later is
  covered without anyone remembering to extend a list. It also refuses the
  three packages 0.2.0 retired (`dsh-agent-presets`, `dsh-host-apiproxy`,
  `dsh-cordis-host-runner`), so a partial revert cannot pass the sweep on a
  mixed tree.
- **`CORDIS_PIN` = `4.0.4`** — `@deepseek-ai/cordis` rides its own 4.x track.
  Every dsh package, and the CLI, peer-depends on it with a TILDE range
  (`~4.0.4`), so a 4.1 would not satisfy them. Bumped separately and
  deliberately.
- **`CORDIS_INCLUDE_PIN` = `1.0.9`** — `@deepseek-ai/cordis-plugin-include`,
  the one cordis plugin the face imports itself (`entryListSchema`, to read bot
  compositions in the Loader's own dialect).

Not pinned by the face: `cordis-plugin-loader` and `cordis-plugin-group` arrive
as `dsh-app-boot` peers (`~1.0.5`, `~1.0.4`), and `cordis-plugin-timer` through
`dsh-base` (`~1.1.6`); the 0.1.1 `cordis-plugin-hmr` is gone. Only
`package-lock.json` holds them still. Keep the lockfile committed, and read a
lockfile-only change to those three as a real upgrade that deserves the drill
below.

**The drill.** Bump `package.json` AND the matching constant in `src/version.ts`
together — every pin whose track moved — then:

1. `npm install` — first, and not optional: the pin sweep reads the INSTALLED
   tree as well as the manifest, so running it against a stale `node_modules`
   fails on the old versions rather than on anything about the upgrade.
2. `npm test` — the pin sweep fails first when the manifest, the installed tree,
   and a constant disagree. A green sweep is the precondition for the rest,
   not evidence the upgrade is good.
3. `npm run typecheck` — the contract test. `skipLibCheck` is `false`, so the
   dependencies' own `.d.ts` are checked too (clean under TypeScript 5.9 at
   0.2.0-rc.2). A renamed config key, a narrowed value, a changed exported
   signature: they surface here, because the overlay's row configs are
   `satisfies`-checked against the plugins' OWN exported config types rather
   than against a local `Record<string, unknown>`.
4. **Re-diff `src/boot.ts` against the CLI's current `profile-boot-*.js`
   chunk.** At 0.2.0-rc.2 that is `@deepseek-ai/dsh`
   `lib/profile-boot-BZ2ZjNWi.js` — functions `prepareProfile`,
   `composeProfile`, `runProfile` (upstream `apps/cli/src/profile-boot.ts`).
   The chunk name is content-hashed and changes on every release; the CLI is
   not a dependency of this package, so fetch it
   (`npm pack @deepseek-ai/dsh@<new>`) to read it. The CLI now also publishes
   the same functions as `@deepseek-ai/dsh/profile-boot` — a reading aid, not
   something to import: `runProfile` would bring `profileContext`, the CLI's
   own signal handlers and an `appReady` committed before Gate 2 exists. This
   is the one private piece the face mirrors, and a composition that has
   drifted boots a DIFFERENT tree while still compiling clean. `boot.ts`'s
   header lists the ten divergences that are deliberate — no `--patch` files,
   no `profileContext`, no proxy install, no signals, shutdown or fail-loud
   inside `bootFace`, `appReady` committed last, the face's own install anchor,
   a skipped bundle as a hard failure, the strict row audit, the policy
   layer, and Gate 2 armed inside `prepare` (before any row mounts, because
   dsh's unary `/api` is live during `boot()` and is not readiness-gated) —
   and anything else is drift. Runtime module resolution
   (`createRuntimeResolution` plus the `PluginPackages` service, installed
   inside `prepare`) replaced 0.1.1's `$DSH_HOME/profiles/node_modules` link
   farm; without it no dsh-base row resolves at all.
5. **Re-check the frame shapes.** `client/api.js`, `client/mapper.js` and
   `tests/fixtures/events.jsonl` against the installed `.d.ts`:
   `@deepseek-ai/dsh-api-gateway/lib/types/stream-protocol.d.ts` (the mux
   frames, the `$events` items, `$events/result`),
   `@deepseek-ai/dsh-api-remotes/lib/types/remote-events.d.ts` (what `$events`
   forwards), `@deepseek-ai/dsh-api-session-controller/lib/types/types.d.ts`
   (follow, control and page frames, `SessionSummary`),
   `@deepseek-ai/dsh-session/lib/types/types.d.ts` (session events,
   `SurfaceOp`), `@deepseek-ai/dsh-llm/lib/types/message.d.ts` and `types.d.ts`,
   and the two answerable gate requests in
   `@deepseek-ai/dsh-user-approval/lib/types/types.d.ts` and
   `@deepseek-ai/dsh-user-questions/lib/types/types.d.ts`. The client is untyped
   JavaScript talking to a typed wire, so `tsc` does not cover this hop — the
   fixture is the contract, and a fixture that no longer matches the wire makes
   the mapper tests green against a stream nobody sends.
6. `npm run check:fixture` (`scripts/validate-fixture.mjs`) — runs the fixture
   through the INSTALLED dsh's own acceptance code: the session controller's
   `assertSessionWireEvent`, which the upstream client applies to every follow
   and page record, and the gateway's frame parser and `$events` id
   predicates. A frame kind with no upstream validator (assistant-stream,
   projection) is counted and named, never passed silently; 0.1.1 shapes are
   rejected. At 0.2.0-rc.2: 26 lines, 23 validated, 0 rejected.
7. `FACE_SMOKE=1 npm test` — the only step that proves the new tree MOUNTS,
   that the page's own transport works against it (`client-mux-smoke`), and
   that an APPROVED order still dispatches (`order-gate-smoke`). That last test
   exists because 0.2.0 removed `Session.events`: the Gate-2 guard read
   `undefined` and denied every approved order, failing closed with nothing
   looking wrong. `snapshotEvents()`, which the guard and the room engine read
   now, is deprecated upstream for new callers — a later pin that drops it
   fails them closed, loudly, and this step says so.
8. Run the drills below — Gate 2, ask-user, transport, bots, room — on a face
   booted against a SCRATCH `DSH_HOME` first.

Only then trust it — and only then point it at the real harness home.

### The harness home across the upgrade

0.2.0 writes things into `$DSH_HOME` that 0.1.1 never did, and none of them is
rolled back. The go-live procedure — the backup, a read-only dry run of every
session on a COPY of the home, the D2 row, the first live boot, the exact
restore — is `../docs/superpowers/runbooks/2026-09-30-dsh-0.2.0-rc.2-go-live.md`.
Its dry run is `scripts/check-home.ts`: it refuses the live home, and any
directory without the runbook's `DRY-RUN-COPY` marker, before it loads
anything; boots the face on the copy with every MCP row disabled in memory
(`bootFace`'s `extraPatches`, never by writing the copy's files); read-opens
every session; and writes `<copy>.check-home.json` beside the copy. The facts
the runbook stands on:

- **The first boot on a home writes** the `client-connection/browser-session`
  grant into `.credentials.yaml`, and per-record projection-cache files under
  `storages/session_projcache/sessions/` (0.1.1's single `session_projcache.json`
  is left in place). `settings.yaml` stays untouched (D1).
- **The first write to each pre-0.2 session** — a prompt, a command, a rename,
  an `@` or a room dispatch; never a view (D16), and not a fork, which reads its
  source cold — publishes `session.v4.jsonl.zstd` and takes `session.lock`
  beside the byte-preserved `session.jsonl.zstd`.
- **The 0.1.1 CLI and the pre-upgrade face do not run on a home 0.2.0 has
  written (D12).** 0.1.1 reads only `session.jsonl.zstd`, so any resume there
  forks history away from the v4 file; it never takes `session.lock`; and any
  workspace write it makes prunes every session it cannot see — every session
  born under 0.2.0 — from its channel in `storages/workspace.json`,
  permanently. The only safe rollback is a full restore of the backed-up home.
- **Then `$DSH_HOME/profiles/node_modules` goes (D13).** It is 0.1.1's link
  farm into its own packages: nothing writes it now, but 0.2.0's runtime
  resolution still falls through to it for a row naming a package outside the
  face's dependency closure — a mixed-version hazard. The 0.1.1 CLI re-heals
  it, which is why this waits for D12.

## Sessions written before 0.2.0

dsh 0.2.0 reads a 0.1.1 log by migrating it in memory, format v0 to v4, on
each open until a first 0.2 write publishes the v4 file, and refuses what the
migration cannot classify. Measured on
2026-09-30 against a COPY of the operator's harness home: 14 of its 39 sessions,
holding 64.8% of all logged events, do not open.

| Sessions | Why | dsh's refusal |
|---|---|---|
| 10 — 4 under `strategies/aqr-r1000`, 6 under `strategies/room-drill` | their logs carry `room` messages, a source the v2→v3 step does not know (upgrade decision D11) | `SessionFormatUnsupportedError`: `cannot safely transform unclassified message source` |
| 3 — every subagent child in that home, two of them under a refused AQR room | a version-2 `subagent/descriptor` (D17) | `subagent/descriptor 0 uses unsupported descriptor version 2` |
| 1 ordinary Kairos session | a corrupt log (D17) | `SessionPersistenceCorruptionError`: `… has seq gap (expected 3455, got 3427)` |

The two format refusals add `source v0 artifact remains unchanged`, and the face
keeps every one of the 14 that way — nothing here rewrites an operator log:

- Opening one fails: the read (a page for a cold session, D16; a follow for a
  subagent child) is refused, the status line shows the host's error, and
  nothing is drawn or written.
- `POST /data/rooms/say` into a legacy room answers 409 with dsh's code and
  message and the legacy hint ("Rooms", above).
- A legacy MEMBER session fails only that member's turn; the round goes on.
- Delete still works on them: the face reads the header itself.

Whether to export those transcripts while the pre-upgrade face can still render
them, leave them unreadable, or wait for an upstream migration step is the
operator's decision (D11, D17), taken in the go-live runbook.

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
the session workspace, the denial tells the model it may retry once, and that
one permitted retry carrying `sandbox_permissions` + `justification` resolves
`ctx.approval` before running.

**The answerer is `@deepseek-ai/dsh-api-remotes`** — the overlay's
`api-remotes` row. It forwards the `approval/request` waterfall into the Typert
gateway, which hands it to every connected tab as an `$events` item keyed by
`eventId`; the first `$events/result` settles it and every other tab receives
`cancel`. With no tab connected the ask BLOCKS — the gateway keeps it pending
and replays it to the next tab that connects — rather than denying. Without the
row at all, every ask resolves `unavailable` at once and dsh-tools denies it
`no approval channel is available`, with no card anywhere: the tree comes up
healthy and every approval fails closed with nothing on screen saying why. That
is why `bootFace` refuses a tree with no ACTIVE `dsh-api-remotes` row, and one
missing the `approval`, `userQuestions`, `typertGateway` or `permissionPresets`
service ("What boot refuses").

**Step 0, no model, no key.** `FACE_SMOKE=1 npm test`: `smoke.test.ts` drives
the answer channel over the real socket (two signed-in tabs, one answers, the
other gets `cancel`, the grant lands in the log), `client-mux-smoke.test.ts`
does the same with the page's own `client/api.js`, and
`order-gate-smoke.test.ts` proves an approved call dispatches while a rejected
one does not. If step 0 fails, stop: the cause is the composition or the wire,
not the model.

**Step 0b, if you changed anything under `client/`.** Hard-reload the page:
`registerStatic` sets no cache headers.

**The drill**, with the face live and a session open:

1. Prompt Kairos to write a file OUTSIDE the session's workspace — the path
   shown on the session's sidebar row, the workbench repo root unless you gave
   the session a project of its own — and to escalate when the sandbox denies
   it. `touch ~/face-gate2-drill` from the bash tool does it, unless that
   workspace IS your home directory, in which case pick any path outside it. Do
   NOT use `/tmp`: `workspace-write` already permits the platform temp areas, so
   a write there is allowed and asks nobody.
2. PASS, part one: the approval card renders in the face — headed `approval`,
   the tool's name beside it, the host's reason (a sandbox escalation always
   sends a display text; the card adds the audit reason when the two differ),
   and exactly two buttons. Two outcomes and only two: the face sends
   `allowed-once` or `rejected`. At 0.2.0 that is the client's rule, not the
   host's — the host would accept `cancelled` or `unavailable` from any
   answerer — so `client/api.js` refuses anything else before it is sent.
3. **Deny.** The card settles to `answered · deny` and the command does NOT run.
   The model sees a denial result, never the card.
4. Prompt again and **Approve**. The command runs. The grant is one-shot
   (`allowed-once`) and applies to that call alone — there is no `allow-always`,
   no remembered rule, no grant store.
5. With a second tab open on the face, raise one more card: both tabs show it.
   Answer it in one; the other's card settles to `closed`.
6. Both decisions are in the session log under `$DSH_HOME/sessions` as paired
   `approval/asked` + `approval/decided` records. Those are log-only: the audit
   is for you, not for the model.
7. Clean up: `rm ~/face-gate2-drill` (or whatever path step 1 used).

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
dsh ships none: at 0.2.0-rc.2 no installed `@deepseek-ai` package returns a
`tools/pre-execute` `ask` — `dsh-tools` only consumes one. What raises the card
is a *sandbox escalation*; an MCP call never takes that path. On 2026-09-04,
against the 0.1.1 tree, four independent checks said so: no `dsh-hooks*`
package under `face/node_modules`; no `{kind:'ask'}` producer in any composed
package; `dsh-permission-presets` registering only `session/created` (preset
application) and an `internal/dispatch` event *validator*, neither of which can
ask for a tool call; and `dsh-mcp-client` carrying zero references to approval,
sandbox or pre-execute.

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

**The approval-channel drill: PASSED 2026-08-31, re-run and PASSED 2026-09-08** on the live
0.1.1 face with the workbench toolset mounted: deny (command did not run; the model saw a
rejection result, never the card) and approve (`allowed-once`, one-shot) both exercised,
with paired `approval/asked` + `approval/decided` records in the session log. **On
0.2.0-rc.2: step 0 passes at `8f0dedb`, and the deny half was drilled live the same day**
(2026-09-30, a face at `8f0dedb` on a scratch `DSH_HOME` with the operator's MCP rows and a real
model): `touch ~/face-gate2-drill` escalated, the card rendered headed `APPROVAL bash` with the
host's `displayReason` and the audit `reason`, Deny settled it to `answered · deny`, the file was
never created, and the model reported the rejection in prose. The approve half is automated on a
real tree (`order-gate-smoke`, `smoke.test.ts` 7b) and still owed a live run — a step of the
go-live runbook. Re-run after any face or dsh change, per the heading above.

## The order-approval drill (run before ever arming ALPACA_KIT_ENABLE_ORDERS)

Since 2026-09-04 a per-order gate exists (`face/src/orders.ts`, armed by
`boot.ts`'s `armOrderGate` inside boot's `prepare` — since 2026-09-30, before
any row mounts, each half on its own `inject` fiber, because dsh 0.2's unary
`/api` serves turns while `boot()` is still pending and a post-boot
registration left a window; `order-gate-midboot-smoke` pins it closed). Two
registrations, because neither alone suffices: a
`tools/pre-execute` listener returning `{kind:'ask'}` is the only thing that can
RAISE a card (a `ToolGuard` returns `string | undefined` — deny-only), and a
guard is the only thing that is MONOTONIC, evaluated on every allow including
the one `allowed-once` becomes. The listener is registered `prepend` so it is
outermost; the guard denies any gated tool that reached dispatch without a
logged `allowed-once` for that exact `callId` and tool name in the session's own
event log. Deliberately not "without the listener seeing it": `prepend` is
last-registrant-wins, so a listener that a row registers `prepend` during boot,
or anything mounted later, sits OUTSIDE this one and could take its `ask` and
return `allow` — a guard that trusted its own sighting would wave that through
(at 0.2.0-rc.2 the only such row is `tool-jobs`, which always calls `next()`). Only the log proves a human said yes. The card's text is
the order itself — `PAPER order - <tool>: side=… qty=… symbol=…`, sent as both
the audit `reason` and the display text, so whichever a client draws, it names
the order.

The guard reads the log through `snapshotEvents()`, because 0.2.0 removed the
`Session.events` getter it used to read — and that removal failed silently: the
read went `undefined`, and every APPROVED order was denied as though nobody had
approved it. A log the guard cannot read now gets its own sentence —
`<tool>: cannot read this session's log to verify an allowed-once approval (dsh
Session API changed: …)` — never the no-grant one (`<tool> reached dispatch
without a logged allowed-once approval for this call`).

**The automated half runs with `FACE_SMOKE=1 npm test`.** `order-gate.test.ts`
boots a real tree and fires `tools/pre-execute` at `mcp__drill__place_order`,
asserting it is claimed with a card naming the order, that `cancel_order` asks
too, that `mcp__drill__orders` is not claimed, that a renamed server
(`mcp__whatever_they_call_it__place_order`) is still caught, and that the guard
refuses a marked tool the gate cannot name. Drilled 2026-09-04,
mutation-proven: removing the registration fails it.

**The positive path is automated too** (`order-gate-smoke.test.ts`, since
`8f0dedb`) — a grant logged, the guard finding it, the order dispatching. An
`approval/request` answerer on a booted tree returns `allowed-once` and the
stand-in order's body RUNS; `rejected`, and it does not, with dsh's own `the
user rejected tool "…"`. Its last step drops the stand-in answerer and does the
same through the real `$events` channel a browser uses. This is the test that
would have caught the 0.2.0 regression above; run it after every pin bump.

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
   tool** — symbol, side and quantity have to be on it
   (`PAPER order - mcp__alpaca-kit__place_order: side=… qty=… symbol=…`). A card that says
   only `place_order` is a click-through, not a decision, and this step is what would
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

**The shell can answer its own card.** At 0.1.1 that took one `curl`:
`POST /api/respond` carried no token, only a same-origin check a `curl` walks
past (the roster route has the same property, demonstrated with a bare `curl`
on 2026-09-04), and the pending `rpcId` was readable off the mux stream. At
0.2.0 the answer is `POST /api/$events/result`, and it needs three things a
shell turn can still get: a browser cookie — not from the printed URL, which
only the face's stdout carries, but signed with the secret in
`$DSH_HOME/.credentials.yaml`, a file the sandbox lets it read (it confines
writes, not reads); its own `$events` generation on `/api/remote.mux`, to which
the gateway delivers every pending gate; and the gate's `eventId`, which
arrives on that same stream. With them, one un-escalated shell turn can
approve the order it just asked for, and what lands in the log is a REAL
`approval/asked` + `approval/decided` (`allowed-once`) pair. The guard is
satisfied — correctly, because a genuine grant was recorded. Nothing here is
broken; the gate asked, and the wrong party answered. The 0.2.0 path is stated
from the code, not drilled. This is the specific hole in the property the
guard was rebuilt around, so it is stated rather than left for someone to
find.

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
agent PRESET — dsh-web-app disables dsh-base's tool rows and carries
`ask_user_question` inside each shipped preset's composition. The face keeps
dsh-base's flat tool roster (its `kairos` preset is empty), so it inherits the
one hole, and fills it with its own overlay row, `tool-ask-user` — configless,
which at 0.2.0 means the blocking `legacy` mode 0.1.1 shipped (the package also
has a `timed` mode the face does not use). It is face-owned for the same reason
`webserver` is: this layer composes last, so an operator patch aimed at it is
accepted, overridden, and never reported — and an agent silently losing its
voice is the failure the row exists to prevent.

A question reaches the browser the way an approval does: a
`user-questions/request` waterfall that `api-remotes` forwards to every
`$events` tab, keyed by `eventId`, answered with the whole batch —
`{answers: [{id, selected, custom?}]}` — through `$events/result`.

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
asserts `ctx.tools.schemas()` carries `ask_user_question`;
`askuser-noclient-smoke.test.ts` asserts that a question with no browser
connected BLOCKS (parked for the next tab) rather than failing, and
`client-mux-smoke.test.ts` answers a real question with its batch through the
page's own `client/api.js`. Run it first; if it fails, stop — nothing below can
pass and the cause is composition or the wire, not the model.

**Step 0b, if you changed anything under `client/`.** `registerStatic` sets no
cache headers, so the browser caches the ES modules heuristically and a restarted
face happily serves an old `chat.js` to an open tab. Hard-reload the page before
drilling: a stale client produced two false failures while this drill was being
written.

**The drill**, with the face live and a session open:

1. Open the **plugin** panel → the composed row tree. `dsh-tool-ask-user` is
   listed as `include:tool-ask-user`, phase **active**. A row stuck at
   `pending` — its inject (`tools`, `userQuestions`) never satisfied — no
   longer reaches this screen: the strict row audit refuses such a boot.
2. Prompt Kairos to ask, naming the tool: *"Use ask_user_question to ask me
   which PIT bed to use, 2yr or broad. Ask nothing else and read no files."*
   Naming it is deliberate — this step drills the SEAM, not the judgement.
3. PASS, part one: the question card renders, headed `kairos asks`. ONE card for
   the whole batch, whatever the number of questions, and one Send: one `ask()`
   is one card and one answer, never split per question.
4. **Answer it.** The card settles to `answered`, the turn continues, and the
   answer is back in Kairos's context as a tool result. On a single-select
   question a typed answer and a picked option replace each other on the card.
   At 0.2.0 that rule is the card's alone — nothing between the card and the
   asking tool checks the batch any more; at 0.1.1 the host refused a mixed
   answer as a bare `bad-response`.
5. **Press Stop on a fresh question instead of answering it.** The card settles
   to `closed` — the Stop ends the turn, the gateway withdraws the gate with a
   `cancel`, and a `cancel` carries no outcome — and the sidebar's `waiting`
   chip clears. A card that stays live after a Stop means the `cancel` is being
   dropped (`client/api.js` `onGateGone` → `client/chat.js`
   `acceptGateResolved`), and it will be re-drawn on every session switch from
   then on.
6. PASS, part two — the instruction half, in a FRESH session: ask for a new
   strategy with a deliberately thin brief ("build me a strategy for storage
   names"). Kairos asks before it builds, per `AGENTS.md`. This half is
   behavioural, not mechanical: a turn that answers with prose is not proof the
   seam is broken. Re-prompt once before concluding anything.
7. The log, in the session's directory
   `$DSH_HOME/sessions/<project-slug>/<session-id>/`: `session.v4.jsonl.zstd` for
   a session created or written under 0.2.0 (a pre-0.2 session keeps its
   `session.jsonl.zstd` beside it) — zstd-compressed JSONL whose first record is
   the header, `type: "session"`. A question records as an ORDINARY TOOL PAIR —
   `tool/call` with `data.name == "ask_user_question"`, and the `tool/result`
   whose `data.message.toolCallId` is that call's `callId`. There is no
   `question/asked` audit record and there is not meant to be:
   `KNOWN_SESSION_EVENT_TYPES` carries `approval/asked` and `approval/decided`
   and no question member at all, because a question is not a gate. On the wire
   a question is a `user-questions/request` waterfall and its end a `cancel`,
   both on `$events`, neither logged. The durable proof the tool was OFFERED is
   `request/header`, whose `header.tools` lists the schemas of that request:

   ```bash
   F="${DSH_HOME:-$HOME/.dsh}/sessions/<project-slug>/<session-id>/session.v4.jsonl.zstd"
   zstd -dc "$F" | python3 -c 'import json,sys
   for line in sys.stdin:
       e = json.loads(line); d = e.get("data") or {}
       if e.get("type") == "request/header":
           print("offered:", "ask_user_question" in [t["name"] for t in d["header"].get("tools", [])])
       if e.get("type") == "tool/call" and d.get("name") == "ask_user_question":
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
Those runs were on the 0.1.1 face, where a stopped question read `closed ·
cancelled`. **On 0.2.0-rc.2: step 0 passes at `8f0dedb`; the live run is still
owed** (go-live runbook).

**Known residuals, deliberately not fixed here.** The card has no Dismiss
button, so Stop is the only exit, and plan-mode's "the user dismissed the review
to speak instead" branch — it keys on `ASK_CANCELLED` — stays unreachable from
this UI. At 0.2.0 a Dismiss is implementable: `$events/result` accepts a
`rejected` outcome, and upstream's own question panel dismisses a blocking
question by rejecting it with `ASK_CANCELLED`; the face's `answer()` sends
results only, so it is simply not built. And a question BLOCKS the turn, so an
answer typed into the composer instead of the card is queued for the next turn
rather than delivered — it says `sent` and nothing happens. Answer in the card.

## The transport drill (run after any client or dsh change)

Every byte between the page and the host is new at 0.2.0 ("The wire and the
transcript"). `client-mux-smoke.test.ts` proves the page's own modules against a
real host without a browser; this drill is the browser half. Hard-reload first —
`registerStatic` sets no cache headers. With the face live:

1. In a browser not yet signed in to this host:port (a private window will do), open
   the bare `http://127.0.0.1:3090/`. PASS, part one: `401`. Open the printed
   `?token=` URL: the chat loads and the address bar is back to the bare URL, which
   now loads by itself; `http://localhost:3090/` still answers `401` until its own
   token visit.
2. Open a COLD session written before the upgrade and not prompted since. PASS, part
   two: the transcript renders, and its session directory gains NO
   `session.v4.jsonl.zstd` and no `session.lock`. Prompt it: pulses appear — it is
   followed now — and only now do the v4 file and the lock appear.
3. Open a LIVE session, then restart the face mid-view. PASS, part three: the status
   line reads `disconnected - …; reconnecting…`, then `connected`; the window is
   redrawn once, with no duplicated bubbles; the tab needs no new sign-in.
4. **+ new**, first prompt. PASS, part four: the reply streams without a click on its
   sidebar row.
5. Send `/compact`. PASS, part five: the status line shows the command's result and no
   model turn starts; a failing command shows in red.
6. Agent face → *Main agent*. PASS, part six: provider, model and effort (the D2 row);
   cwd, attached and home (`/data/host.json`); each key `set · <source>` or `not set`.
7. In a session with a temporary subagent: the **临时子任务** panel lists the child;
   **查看最近输出** reads it; **续派** and **中断当前轮** are accepted; in the child's own
   transcript a message from its parent reads **父会话消息** with **返回父会话**. PASS, part
   seven.
8. Rename a session, fork one, pick a folder through `choose a local folder…`, rename a
   channel. PASS, part eight: each lands, and the sidebar follows.

The approval endings — `answered · approve|deny`, a second tab's `closed`, a lost
race's `closed · settled elsewhere`, a stale card's `closed · no longer pending` —
belong to the Gate-2 drill; the last two need a socket dropped mid-answer, which the
go-live runbook stages by hand (§7 A) and `tests/api.test.ts` plus the page harness in
`tests/subagents.test.ts` cover in code. **Not yet run on 0.2.0-rc.2**: a headless load
of the page on a scratch home reached `connected` with no console errors; the live run
is the runbook's §7 A, on a copy of the real home.

## The bots drill (run after any face or dsh change)

A mask never pulled is presumed decorative.

**Step 0, no model, no key.** `FACE_SMOKE=1 npm test` boots isolated real trees.
`bots-smoke.test.ts` proves the face declares every bot directory and never `_template`, that
the roster lists a broken fixture with its reason, that the shipped relative plugin path is
rebased onto the real `plugins/bot.js`, that a session created with `agentPreset` carries it on
its header, that the bot sees exactly its allow-list ∩ the tree — including a tool registered
after the declaration — while Kairos sees the host's whole roster unchanged, that the bot's
prompt carries its own persona and not Kairos's while Kairos's carries `persona.md`, and that
a session naming the broken preset is refused at `session/create` with dsh's own
`agent-preset/*` error code.
`bot-runtime-smoke.test.ts` proves the saved route reaches an actual stub request without
changing the host default, that a save re-declares the preset — existing live sessions keep
their persona and model, new sessions load the new settings — and that runtime inspection
does not drive or interrupt turns.
`bot-sandbox-smoke.test.ts` and `askuser-noclient-smoke.test.ts` print one `observed:` line each
(S4, S7); their findings are recorded in the spec's amendments block.

**Step 0b, if you changed anything under `client/`.** Hard-reload; `registerStatic` sets no
cache headers.

**The drill**, with the face live:

1. Agent face → **bots** → `+ new bot`. Type a display name with spaces and capitals; PASS,
   part one: the id field shows the folded proposal, lowercase with dashes.
2. Create. PASS, part two: the bot page opens; `bots/<id>/` exists with `agent.cordis.yml`,
   `preset.yml`, `SOUL.md`, `README.md`, `skills/README.md`, `journal/notes.md`; the bot is
   usable at once — the route declared it before answering — and the boot line of a restart,
   `agent presets: …`, lists the id.
3. **New test conversation**, say something. PASS, part three: the sidebar shows the session under the bot's
   name, not under `ungrouped`; the reply speaks in the bot's persona, not Kairos's.
4. Ask the bot to list its tools. PASS, part four: it names the shell, file and web tools and
   `ask_user_question`, and does not name `subagent`, `place_order`, or any `agent_<bin>` — and
   if the alpaca-kit MCP server is connected, it names the market-data reads and not `orders`.
5. On the bot page, edit the soul to include `{{` and save. PASS, part five: refused with the
   strict-template message; the file is unchanged.
6. Edit the soul to something you can recognise and save. PASS, part six, with no restart:
   a **New test conversation** answers in the new persona, while the conversation from step 3,
   continued, still answers in the old one — it keeps the revision it joined — and its
   **Session inspection** reads `SOUL vs saved: Differs from saved SOUL`.
7. Clean up: `git rm -r bots/<id>` (or keep it — it is yours). The running face keeps the
   declaration until its next restart.

**Drilled and PASSED 2026-09-07 and again 2026-09-08** on the operator's own face (real
`$DSH_HOME`, the alpaca-kit server connected; `main` @ `b6dbce0` the second time). Second run:
`Growth Momentum Scout` folded to `growth-momentum-scout`; six files; the restart's boot line
listed it; the home session bucketed under the bot; the reply opened in its persona; the tools it
named were exactly the allow-list ∩ the tree — 18 offered in `request/header`, the seven
market-data reads among them and no `subagent`, `agent_<bin>` or order tool; the `{{` soul was
refused with both files byte-identical. The speaker label (R12) held on the `who` element, the
composer, the topbar and the status pulse across session switches, a reload and a restart. One
observation → R13 in `DEVELOPMENT.md` §9: every cold session lists as `untitled`. Both runs
were on the 0.1.1 face; **on 0.2.0-rc.2 step 0 passes at `8f0dedb`, and the live run —
step 6 included — is still owed** (go-live runbook).

## The room drill (run after any face or dsh change)

A room whose strip never moved is presumed decorative.

**Step 0, no model, no key.** `FACE_SMOKE=1 npm test` boots `room-smoke.test.ts`: a stub model
route, three bots in a temp channel, one operator prompt → Kairos dispatches all three in
parallel → alpha answers, beta passes, gamma's model fails → the answer is on the room log before
the round-end wake, the wake is one turn, Kairos's synthesis is in it; every member is parented,
preset-joined, `read-only` as its first event (and its only permission pin before its first
turn), carries the channel's `AGENTS.md` chain and lacks `dispatch`; the `room` value rides the
session row and the per-record cache file (`storages/session_projcache/sessions/<id>.json`); an
`@` turns alpha, whose write into the channel is refused inside the tool content (D12) and never
woke Kairos; a home session writes its journal and is refused on `../SOUL.md`.

**Step 0b, if you changed anything under `client/`.** Hard-reload.

**The drill**, with the face live, on the tracked fixtures — the voices `drill-bull` (看多派) and
`drill-bear` (看空派) on the channel `room-drill` — or on two template bots you create on the agent
face (the bots drill, steps 1–2) and a fresh channel. Start a NEW round either way: the room
sessions the 2026-09-09 run left in `room-drill` were written under 0.1.1, and 0.2.0 cannot open
them ("Sessions written before 0.2.0") — they fail to open, and an `@` into one answers 409.

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
   `[sandbox: file access denied under read-only mode]` — and, at 0.2.0, dsh's escalation hint
   beside it; if the bot retries with `sandbox_permissions`, an escalation card appears inline:
   deny it — and the bot reports the refusal in the room.
7. Un-check one bot on the channel page and come back. PASS, part seven: its chip reads
   `left`; `@` to it resolves nobody (the text goes to Kairos as a prompt); re-check it and
   `@` it again: the same member session answers.
8. Restart the face, open the room. PASS, part eight: the strip's coarse states survive
   (the projection cache, read by `session/projections` without activating the room); each
   answer's trace still loads its recorded member turn; no member chip moves until the room
   runs again — cold members are not followed.

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
it ran (by design), so that path stands on the engine tests, not on this drill. That run was on
the 0.1.1 face; **on 0.2.0-rc.2 step 0 passes at `8f0dedb`, and the live run is still owed**
(go-live runbook).
