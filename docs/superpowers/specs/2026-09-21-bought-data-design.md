# Bought Data — Design

**Status:** built 2026-09-21 (face `feat/bought-data`; agentpay `market-surface` @ `2177984`, the
submodule pin). Planned 2026-09-21 as the B arc of the team's direction (*from strategy, erode
outward into market/exchange*); the plan record is the operator's `b-nifty-patterson` plan. The
as-built truth is consolidated in `DEVELOPMENT.md` (§2.3–2.5, §3.6, §4.5, §7.4, §9 R-W8, §10 item
11, Appendix A). Extends the agent-wallet design (`2026-09-20-agent-wallet-design.md`, whose §4.3
points here) and amends the charter (§5). The first purchase is simulated: a Massive-shaped payee
on the local chain, because the real vendor sells on Base mainnet only and the operator decided
(2026-09-21) that this round stays on testnet.
**Pins:** face `feat/bought-data` @ `0a24acf`; agentpay `market-surface` @ `2177984` (the
submodule pin); dsh `0.1.1-rc.2`, cordis `4.0.2` unchanged.
**Language of citations:** as in the A spec — `pay:…` cites the agentpay repository (the
submodule); bare paths are this repository. Every substrate claim below was read from source on
2026-09-21 and the drill in §7 was run in the browser the same day.

---

## 1. Context and decision history

The A arc gave Kairos a wallet that could pay, but the only payee was `payment/`'s own example
service, `wallet_pay` truncated every body at 8 KB, the Python side (`alpaca_kit`) could not touch
a bought byte, and the hosted facilitator failed most concurrent settlements. The research layer's
standing gap list names *pre-2021 daily history from a second vendor* (ROADMAP item 5; the
multi-source spec of 2026-06-22 named Polygon/Tiingo). That vendor exists in the x402 ecosystem:
Massive (`agent.massive.com`, Polygon lineage, $0.01 per call, OHLCV / snapshots / news / SEC
index) — on Base **mainnet** only. On testnet there are echo services, Hyperliquid snapshots and an
`upto` simulator, none of them US equities.

This arc is therefore the whole road — *discover → one budget → confirm the price → sequential
pays that land as files → a PIT bed → replay* — run on testnet against a payee **shaped like the
real vendor**, so that going to mainnet later changes a URL and a network and nothing else.

Decisions, in the order taken:

1. **Testnet only.** No mainnet float, no mainnet key, no real Massive purchase (charter §8: a
   mainnet key in the wallet home is a trigger, not a configuration step). This is item C of the
   payment gap list and stays there.
2. **The first purchase is simulated on a Massive-shaped payee.** `pay:packages/payee/examples/vendor-sim/`
   serves Polygon's aggregates route (`GET /v2/aggs/ticker/:ticker/range/1/day/:from/:to`, $0.01)
   and news route (`GET /v2/reference/news`, $0.01) behind the paywall, with a deterministic price
   path per ticker (FNV-1a seed + mulberry32; `(AAPL, 2019-03-04)` is the same bar forever),
   weekends skipped, no holidays, `adjusted` echoed (default `true`, as Polygon's), `t` at 05:00 UTC
   (Polygon's ET-midnight convention), and a bazaar discovery declaration on both routes. Its header
   states every way it differs from the real vendor (mainnet, rate limits, pagination, holidays,
   real prices).
3. **A bought file lands under the channel that paid for it: `<channel>/vendor`.** `wallet_pay`
   gains `save_to`, a relative path; the root it is resolved against is not an argument but a
   fact the face reads off the session header (`ToolCallMeta.saveRoot` = `join(channel.dir,
   'vendor')`), so a file lands where its spend is attributed. A session in no channel — the root
   session, the unattributed bucket — is given **no root**: agentpay answers `save_to` with its
   usage envelope before paying, and the payment itself is unaffected.
4. **The write is Kairos's.** The face process writes the file, but it authors nothing: the path is
   Kairos's argument, the root is the channel Kairos is working in, the bytes are the payee's.
   That is the same posture as the mandate store and the ledger (A spec decision 7): a write the
   face performs on Kairos's tool call. The charter's write map gains a row for it (§5) and the
   residual that the face process writes outside the sandbox gains a member, R-W8 (§6).
5. **The envelope carries a receipt, not the body.** With `save_to`, the tool value has
   `saved {path, bytes, sha256, content_type}` and a `preview` of at most 1 KB; the body never
   enters the context. The `sha256` is the receipt Kairos records in `journal.md` beside the `tx`.
   The ledger row's `context.label` defaults to the `save_to` path, so the `/wallet` payments table
   can show a file column without a new ledger field.
6. **Capture gates corp actions on the source's probe.** `capture_window` used to call
   `corporate_actions_known(end)` unconditionally and always write `corp_actions.parquet` — for a
   source that cannot check, an empty frame, which replays as `has_corp_actions() → True`: "checked,
   clean", a lie. It now consults `corp_actions_available()` (a source lacking the probe defaults
   True, as `GuardedSource` does) and writes nothing when it answers False, so the bed is honestly
   MISSING and the MCP `corp_actions` tool answers `artifact missing`.
7. **The calendar is the union of bar dates.** `MassiveFilesSource.trading_calendar()` is the sorted
   union of every ticker's bar dates unless an explicit calendar is given. Consequence, recorded
   on purpose: a bed captured from bought files has the bought window as its calendar — a day no
   file covers is not a trading day to the bed, a symbol's missing day inside the window is a gap
   (rule 5: skipped, never interpolated), never a holiday. A real XNYS calendar
   (`ALPHA_MASSIVE_CALENDAR_BED`) is a later step.
8. **News is deferred.** A `news_known` feed would touch the Protocol and five more files and has
   no consumer. Bought news is interactive evidence with no PIT guard, like an AKShare read: cited
   in a journal, never as replay evidence. vendor-sim keeps the route; the skill says what it is.
9. **`upto` is recorded, not built.** Every US-equities seller found is `exact`; the metered
   scheme's design (Permit2 ceiling, `setSettlementOverrides`, the wallet and ledger changes) is
   `pay:docs/upto-design.md`, one page, and nothing more.
10. **Discover only reads the catalogue.** `wallet_discover` queries the CDP Bazaar's
    `/discovery/search` (public, no key; `FACE_AGENTPAY_BAZAAR_URL` overrides the default) and
    returns at most 20 rows the wallet could actually pay — the offer must pass `isPayableOffer`
    (scheme `exact`, the wallet's network and asset) and its timeout must fit the wallet's
    authorization validity — sorted by 30-day unique payers. It never returns the catalogue's
    `output.example`, `schema` or `iconUrl`. Its note says catalogue prices can be stale; the
    concrete URL's `wallet_offer` is the price. Listing vendor-sim in the catalogue needs one
    settlement through the CDP facilitator and is not done.
11. **The order of operations is budget → offer → pay** (learned in the drill, §7, and written into
    the skill). In the face every host-touching tool, `wallet_offer` included, is pre-flighted
    against a held mandate naming the host (`requireMandateHost`, A spec decision 9); an offer
    before any budget is refused `mandate_required`. So the catalogue price (or the vendor's
    documented price) sizes the budget, the offer confirms it once before the first pay, and a
    quote above `per_call_usd` means stop and re-budget.
12. **Pays are sequential.** R-W4 stands (the hosted facilitator fails most concurrent
    settlements); agentpay's payee gained a per-facilitator settle lock and one retry for its own
    side, but the face does not queue and the skill forbids fanning buys out to child tasks.

## 2. What the operator sees

- **The pay card** for a `wallet_pay` with `save_to` reads `$0.010000 · settled · 127.0.0.1:4022 ·
  saved 28.0 KB`: paid for AND kept, at a glance. The kv block below it carries the path, the
  bytes, the short sha256 and the 1 KB preview. A body that was paid for but could not be saved
  (over 32 MiB, or a write failure) shows `saved.error` in the danger colour: the money moved, the
  file did not.
- **`/wallet`'s payments table** gains a *file* column, the ledger row's `context.label` — the
  `save_to` path by default — so a bought file names its row.
- **A discover table** inside the answer trace for every `wallet_discover`: resource · price ·
  network · payTo · payers (30 d), plus the envelope's `matched / payable` counts and its note.
  Against the real catalogue on the local chain it reads `ok`, 0 payable resources — nothing on
  `eip155:31337` is listed, which is the honest answer.
- **The budget card** is the A arc's, sized by the skill from the catalogue price:
  `BUDGET - "vendor-sim bars AAPL,MSFT 2016-2017" · limit $0.05 · per call $0.01 · valid 24h ·
  hosts 127.0.0.1:4022 · from no channel by principal`.
- **On disk**, under the strategy: `strategies/<name>/vendor/massive/<TICKER>/<from>_<to>.json`,
  gitignored (`strategies/*/vendor/`; the sha256 in the ledger is the receipt, the bytes are not
  ours), and later the bed the operator captures under `data/pit/massive-<from>-<to>` with no
  `corp_actions.parquet` in it.

## 3. What Kairos sees

Nine tools, all registered by the face; the eight of the A spec unchanged except `wallet_pay`,
plus one:

| tool | who may call | what it does |
|---|---|---|
| `wallet_discover {query, max_usd?, limit?}` | principal, child | Searches the x402 catalogue for the wallet's network and returns `{ok, query, network, bazaar, matched, payable, partial, resources[], note}` — each resource `{resource, method, service, description ≤ 200, price_usd, network, pay_to, max_timeout_s, payers_30d, calls_30d, last_called, input?, tags}`; at most 20, payable ones only; `{ok:false, error:'discovery_unavailable'}` when the catalogue does not answer. Read-only, no host pre-flight (the catalogue is not a payee). |
| `wallet_pay {url, method?, body?, headers?, mandate_id?, save_to?, overwrite?}` | principal; a child with a held sub-mandate | As before; with `save_to` (relative, ≤ 200 chars, no absolute path, no `..`, no symlink escape, refused through an existing file or an existing path unless `overwrite`) a 2xx body is written under the channel's `vendor/` and the value carries `saved {path, bytes, sha256, content_type}` + `preview` (≤ 1 KB, `preview_truncated`) instead of `body`. Without a channel, `save_to` is refused before paying. |

The other seven — `wallet_offer`, `wallet_budget_request`, `wallet_budget_delegate`,
`wallet_budget_disable`, `wallet_budgets`, `wallet_report`, `wallet_reconcile` — are the A spec's
§3. The order the skill imposes: `wallet_discover` (or the vendor's documented price) → ONE
`wallet_budget_request` with `per_call_usd` = that price → `wallet_offer` the concrete URL once →
sequential `wallet_pay` with `save_to` → the operator captures → `replay_days`.

Guidance for the model: the wallet paragraph of `AGENTS.md` (nine tools, `save_to` only from a
strategy channel, the sha256 as receipt, bought news as interactive evidence) and the mechanics
skill `dsh/skills/mechanics/bought-data/SKILL.md` (the six steps, what the reader refuses, the
drill targets).

## 4. Substrate and mechanism

### 4.1 agentpay — branch `market-surface`

- **Payee hardening** (`pay:packages/payee`): `/settle` calls to one facilitator URL are serialized
  (`serializeSettle`, default on; a `Map<url, Lock>`), and a settle that fails
  `invalid_exact_evm_transaction_failed` is retried once after the chain reader confirms the
  authorization is still unused (`chainReader`, `settleRetryDelayMs` 1500). Demo scenario 7 (20
  concurrent) still passes.
- **Save** (`pay:packages/cli/src/save.ts`): `resolveSavePath(saveRoot, rel)` and `writeSaved`
  (`mkdir -p`, `.tmp-<pid>` + rename, sha256); `MAX_SAVE_BYTES` 32 MiB, `PREVIEW_BYTES` 1024. The
  CLI's `pay --save <rel> [--overwrite]` uses `process.cwd()` as the root; the tool table's
  `wallet_pay` takes `save_to`/`overwrite` and the host's `ToolCallMeta.saveRoot`; a missing root is
  a usage error before any request; a save path through an existing file is refused before paying
  (`2177984`); a failed write after a paid fetch is an envelope (`saved.error`), never a throw.
  With `save_to` and no `context.label`, the label becomes the path.
- **Discover** (`pay:packages/cli/src/bazaar.ts`, `commands/discover.ts`): a small typed fetch of
  `GET /discovery/search?query&network&limit&type=http[&maxUsdPrice]` with a 10 s timeout and a
  4 MiB response cap; `isPayableOffer` extracted from the wallet into `pay:packages/wallet/src/offers.ts`;
  the row projection, the sort, the envelope and the `discovery_unavailable` failure as in decision
  10. `agentpay discover <query> [--max-usd --limit --bazaar]`; `wallet_discover` in the tool
  table, kind `read`, not principal-only.
- **vendor-sim** (`pay:packages/payee/examples/vendor-sim/`): `data.ts` (the generator), `app.ts`
  (`createVendorSimApp(paywall)`, importable by tests), `main.ts` (`VENDOR_SIM_PORT` default
  4022; `npm run vendor-sim`). `ChargeOptions.discovery` lets a route declare itself for the
  catalogue (`routeTemplate`, because `charge()` mounts on `*`); `paywall.ts` emits
  `extensions.bazaar` from it.
- **Testnet interop** (`pay:packages/cli/scripts/testnet-interop.ts`): guarded to `eip155:84532`
  on an unlocked home; discover → a mandate for `x402.payai.network, omniterminal.app, 127.0.0.1`
  → offer + pay against strangers → three concurrent pays → reconcile → a JSON report in
  `pay:docs/interop/`. The 2026-09-21 run is §7.
- **`pay:docs/upto-design.md`**: decision 9.

### 4.2 alpaca_kit

- `alpaca_kit/feeds/massive_files.py` — `MassiveFilesSource(root, *, calendar=None)`: the `bars`
  and `calendar` capability groups over `<root>/<TICKER>/*.json`. Nothing in a file name is parsed;
  the body's `ticker` must match its directory. Refused, naming the file: `adjusted` not literally
  `false` (missing counts — rule 4 wants RAW and the vendor's default is adjusted), `status` not
  `"OK"`, a row missing any of `t/o/h/l/c/v`, two files disagreeing on one date's OHLCV. `t` (ms)
  is read as an `America/New_York` date; `o/h/l/c/v` map to the six RAW columns exactly as
  `alpaca.py`'s `_normalize_bars`; `vw`/`n` are dropped; files for one ticker merge and dedupe.
  `daily_snapshot`, corp actions and the P5 feeds raise `NotImplementedError` and their
  `*_available()` answer False.
- `alpaca_kit/registry.py` — `massive_files` registered, built from `ALPHA_MASSIVE_ROOT` (required);
  composable through `ALPHA_DATA_COMPOSITE` (`earnings=edgar`).
- `alpaca_kit/pit/capture.py` — decision 6: `_corp_available(source)` gates the corp-actions write.
  A bars-only bed carries `calendar.parquet`, `bars/`, the derived `snapshot/` and `CHECKSUMS`, no
  `corp_actions.parquet`, and `SnapshotSource.corp_actions_available()` reports False on it.
- Tests: `tests/data/test_massive_files.py` (column map, ET date, the refusals, the union calendar,
  rule 5, merge and conflict, `NotImplementedError` + probes), `test_registry.py` (registration and
  the required env), `test_capture.py` (no corp file from a source that cannot check; the end-to-end
  capture → replay with the guard refusing a forward read). The six US-0 meta-tests are untouched.

### 4.3 Face — branch `feat/bought-data`

- `face/src/wallet.ts`: `WalletDeps.channelFor` returns the channel's `dir`; `execute` passes
  `saveRoot = join(channel.dir, VENDOR_DIR)` for `wallet_pay` only and only from a channel session;
  `bazaarUrlOf(env)` reads `FACE_AGENTPAY_BAZAAR_URL` (empty means default) into the
  `CommandContext`; `wallet_discover` registers from `WALLET_TOOLS` with its own call and result
  titles. The module header carries the containment note (decision 4).
- Client: `wallet-model.js` `payFields`/`payLine` show `saved` (path, size, short sha256) and the
  preview, `savedFile()` handles a `saved.error`; `render.js` renders `wallet_discover` as a
  table; `/wallet`'s payments table gains the file column from `context.label`.
- Tests: `face/tests/wallet.test.ts` — nine tools; `save_to` lands under `<dir>/vendor/…` with the
  bytes and sha256 matching and the label on the ledger row; no channel, `../` and an overwrite
  refused; a big body lands whole with a ≤ 1 KB preview; `wallet_discover` against a stub
  catalogue in the CDP shape, filtered to what this wallet can pay, callable by a child.
  `wallet-model.test.ts` with the `PAY_SAVED` fixture; `FACE_SMOKE=1` `wallet-smoke.test.ts` adds
  one `save_to` through dsh's real registry. `.gitignore` gains `strategies/*/vendor/`.

### 4.4 The skill — `dsh/skills/mechanics/bought-data/SKILL.md`

A mechanics skill (law, not style): discover → one budget sized from the catalogue price → offer
the concrete URL once → sequential pays with `save_to` and `adjusted=false` → capture (the command
handed to the operator, since `data/pit/` is outside the channel's sandbox) → replay bounded to the
bought window, with THESIS.md stating the bed has no corp actions and its calendar is the bought
window. It names what the reader refuses, the drill targets, and what bought news is.

## 5. Charter conformance and amendments

- **§4 write map** gains the row: `strategies/<name>/vendor/ (bought bytes) | Kairos, through
  wallet_pay {save_to}: the face process writes the payee's bytes at the path Kairos named, under
  the channel the payment is attributed to — never outside it, never over an existing file; the
  face authors nothing | the ledger row (sha256 on the pay card, the path as the row's label);
  /wallet's file column; gitignored, so git carries the receipt and not the bytes`.
- **§5 debts** gain **D17** (or a note under D16): bought bytes are written by the face process
  outside the sandbox, bounded to one sub-directory of the channel that paid; acceptable because
  the channel session's own shell can write the same directory (nothing is widened) and the
  content is the payee's, not the face's; due if `save_to` ever resolves against anything but
  `<channel>/vendor`.
- **§7.3** unchanged: Kairos as a *seller* (a payee listening on the network) is the existing
  trigger; this arc only makes a payee route *declarable* for discovery, in the library.
- Nothing in §1, §3, §7.1 or §8 changes: the wallet's gate, holder rule and testnet float stand.

## 6. Residuals

- **R-W8 — The face process writes bought bytes outside the sandbox.** R5's class (the MCP
  server's out-of-sandbox writes, D10): `wallet_pay {save_to}` makes the face write a file the
  sandbox would also have let the channel session write itself. Bounded by agentpay's
  `resolveSavePath` to `<channel>/vendor` (no absolute path, no `..`, no symlink escape, no
  overwrite unless asked), refused for a session in no channel, and the content is the payee's
  bytes. Not widened: the channel's own bash can write the same directory. Not held for a
  `tools/execute` wrapper that renames the call (R-W6's class).
- Two nuisances, recorded: (a) a 24 h budget trips the `/wallet` **expiring** alert (mandates
  expiring within a day) the moment it is approved — the alert is right and unhelpful for a
  one-day purchase budget; (b) the budget card still reads **`from no channel`** for a channel
  session, because `bootFace` has no channel resolver (A spec, budget-card drill); the wallet
  names the channel on the tool result, the ledger row and `/wallet`.
- R-W4 stands for the face (sequential pays by rule; the payee's settle lock protects the other
  side only).

## 7. Drills

- **The bought-bed drill — Drilled and PASSED 2026-09-21** by the operator's assistant in the
  browser: Kairos `feat/bought-data` @ `0a24acf` (payment submodule at agentpay `2177984`), a
  scratch `$DSH_HOME`, the local demo stack (hardhat 8545, the self-hosted facilitator 3001, the
  example payee 4021) plus `npm run vendor-sim` on 4022, the wallet initialised with hardhat #1; the
  turn driven by the test `StubAdapter` mounted as a scratch cordis plugin row (provider `stub`),
  scripted discover → offer → budget → four pays → summary, in the `room-drill` channel. Observed:
  `wallet_discover` against the real CDP catalogue answered `ok` with 0 payable resources for
  `eip155:31337` (honest: nothing on the local chain is listed); `wallet_offer` BEFORE any budget
  was refused `refused before signing · mandate_required` — the finding that fixed the skill's
  order (decision 11); the card `BUDGET - "vendor-sim bars AAPL,MSFT 2016-2017" · limit $0.05 · per
  call $0.01 · valid 24h · hosts 127.0.0.1:4022 · from no channel by principal` → **Approve** →
  `budget im_4cdc5cd64363 · $0.050000`; four sequential `wallet_pay` cards `$0.010000 · settled ·
  127.0.0.1:4022 · saved 28.0 KB` (28.0 / 27.9 / 28.0 / 28.9 KB); the files at
  `strategies/room-drill/vendor/massive/{AAPL,MSFT}/{2016,2017}-01-01_..-12-31.json` (28 649 bytes
  for AAPL 2016, 261 bars, `adjusted: false`), gitignored; `/data/wallet.json` with the mandate at
  `0.010000` remaining of `0.050000`, four settled payments each with `file` = the save path and
  `channelName` `room-drill`, spend `by_channel` `room-drill` `0.040000`, alerts `[expiring]` (the
  nuisance of §6). Then `ALPHA_DATA_SOURCE=massive_files ALPHA_MASSIVE_ROOT=strategies/room-drill/vendor/massive
  python3 scripts/capture_window.py 2016-01-01 2017-12-31 data/pit/massive-2016-2017 AAPL MSFT`
  wrote `bars/{AAPL,MSFT}.parquet`, `snapshot/`, `calendar.parquet`, `CHECKSUMS` and **no**
  `corp_actions.parquet`; `replay_days` over 2016-01-04..2016-01-15 yielded 10 days with the guard
  refusing a read to 2017-12-29 on every day, `SnapshotSource.corp_actions_available()` False, a
  calendar of 521 days (= the bought window), a derived `daily_snapshot` of 2 rows. Torn down
  afterwards. The steps are in `face/README.md`, "The bought-bed drill".
- **The testnet interop drill** — run from agentpay's CLI on 2026-09-21 (`pay:docs/interop/testnet-interop-2026-09-21.json`,
  Base Sepolia, payer `0x2455…6501`): discover `market snapshot BTC` matched 4, payable 4
  (omniterminal first, 3 payers in 30 days); PayAI's echo (`x402.payai.network`, $0.01) offered in
  116 ms and **settled in 857 ms** — the tx's `from` is x402.org's signer, the settlement's payer
  is this wallet, 467 bytes saved through `--save`; omniterminal (`$0.005`) offered on both
  networks and refused the pay with **503 `service_unavailable`** after the authorization was
  signed (`rejected`, reserved until reconcile sees the nonce unused), the same on three concurrent
  tries; reconcile left 10 rows pending inside their 300 s validity. **From the face: not yet
  run** (a Sepolia wallet home, one `save_to` from a channel proving a stranger's bytes land
  whole, `wallet_reconcile` closing the `unknown` rows).

## 8. Not built

- No mainnet record, no real Massive purchase, no mainnet key (decision 1; gap-list item C).
- No `upto`, `batch-settlement` or Solana (`@x402/svm` is not installed; no target seller).
- Kairos as a seller (charter §7.3); vendor-sim's listing in the CDP catalogue.
- No Python news feed; `vw`/`n` are dropped; no real XNYS calendar for a bought bed
  (`ALPHA_MASSIVE_CALENDAR_BED` later).
- No streaming body cap in the wallet's fetch (`FetchOptions.maxBodyBytes`): the 32 MiB save cap
  applies after the body is in memory.
- The interop drill from the face (§7).
