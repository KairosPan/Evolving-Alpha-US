# Kairos Workbench — Development Reference

**Status:** living, as-built · **Owner:** the operator · **Last full pass:** 2026-09-22 on
`feat/paper-book` (471 pytest on a clone without the untracked `tests/strategies/`, 69 of them
`tests/paper/`; 549 face tests, 537 offline + 12 under `FACE_SMOKE=1` — five wallet tests that
bind a loopback stub payee fail under a sandbox that refuses `listen` on 127.0.0.1 and pass
outside it; typecheck clean; agentpay unchanged at `5f37b33`). The 2026-09-21 pass on
`feat/bought-data` @ `0a24acf` (402 pytest; 544 face tests) and the 2026-09-09 pass on
`feat/rooms` @ `ce07925` (313 face tests) are the ones most sections below were last read
against.

**Authority.** `Kairos-Design.md` (the charter) outranks this document on intent. This document
describes mechanism *as built*: where it disagrees with the code, the code is the fact and this
document is the bug. The per-feature specs under `docs/superpowers/specs/` are decision history —
each is frozen once its post-build amendments land — and this document is where their as-built
truth is consolidated. `face/README.md` keeps the face's operational depth (run, profile, drills);
this document points into it rather than repeating it. `AGENTS.md` is written for Kairos and
`CLAUDE.md` for coding agents — but dsh's instruction loader hands Kairos both (§3.3).

**Citation rule.** Files and named symbols, not line numbers. The 2026-09-04 drift audit found
line citations in `face/README.md` stale within days of being written; a symbol name survives an
edit above it.

**The other documents a developer will meet.**

| Document | What it is |
|---|---|
| `ROADMAP.md` | the five-item forward index from the 2026-08-29 reset plus a built log; §10 below is the ordered detail and cites its items by number — move both together |
| `docs/backtest-rules.md` | the five honest-eval rules, the bed-window table, the warmup facts |
| `docs/superpowers/specs/`, `plans/`, `runbooks/` | only the six specs and five plans dated 2026-08-29 or later (skeleton, face chat-light, face instruments, channels, bots-and-rooms, agent wallet) describe this system; the 54 earlier specs, 50 earlier plans and the one runbook are the retired product's history, filed unmarked in the same directories |
| `docs/design/prototypes/` | the face prototypes (`BRIEF.md`, rounds a/b/c and r2–r4) that §5.5 refers to; the R2 instrument grammar and the R4 palette live here |
| `docs/research/` | frozen inputs, never edited: `2026-09-03-face-composition-snapshot.md` is the ground-truth list of rows and tools the face composes, `2026-08-22-deepseek-harness-dsh-survey.md` the survey the profile template cites |
| `dsh/README.md` | the profile install path (its steps 2 and 6 predate the face and Gate 2 — §10 item 4) |
| `face/README.md` | run, profile, instruments, channels, master rail, bots, the agent wallet, upgrade order, the drills |

---

## 1. The system in one page

One long-lived process (the face) with four kinds of child, one browser tab, and three
external services on five hostnames.

```
 browser (operator) ──── http://127.0.0.1:3090 ────────────────────────────────────────┐
                                                                                        │
 ┌─ kairos-face  (Node 22, `tsx src/main.ts`, cwd = repo root) ────────────────────────┴──┐
 │  hosts DeepSeek Harness (dsh 0.1.1-rc.2) IN-PROCESS from profile `face`               │
 │  ├─ dsh-base bundle: LLM (deepseek), sessions, tools (§3.6), sandbox, approvals, skills│
 │  ├─ face overlay rows (twelve, §4.3): webserver · connection · api-gateway · storage   │
 │  │   chain · directory-picker · host-runner · ask-user · projection-cache ·            │
 │  │   agent-presets                                                                     │
 │  ├─ face routes: `/` `/market` `/account` `/wallet` `/client/*` `/data/*`              │
 │  ├─ Gates 2 and 3: registered by `bootFace` on `tools/pre-execute` + `tools.guard`;    │
 │  │   the rules live in `src/orders.ts` and `src/budgets.ts`                            │
 │  ├─ the agent wallet: nine `wallet_*` tools (`src/wallet.ts` over `payment/`),         │
 │  │   an HTTP client to x402 payees inside the face process (§3.6)                      │
 │  └─ children:                                                                          │
 │       ├─ alpaca-kit MCP server  (`python -m alpaca_kit.mcp`, stdio, operator-mounted)  │
 │       ├─ `scripts/face_data.py market|account`  (per `/data` request, fixed argv)      │
 │       ├─ sandboxed shell turns  (dsh-bash-sandbox; env less KEY|PASSWORD|SECRET|TOKEN) │
 │       └─ `claude` / `codex` runs  (`agent_<bin>` tools; roster-gated per channel)      │
 └────────────────────────────────────────────────────────────────────────────────────────┘
        │                                  │                                │
        ▼                                  ▼                                ▼
 api.deepseek.com                data.alpaca.markets (bars, corp    paper-api.alpaca.markets
 (the LLM; also `web_search`      actions; feed=iex)                 (account, positions,
  via /anthropic/v1)             data.sec.gov + www.sec.gov           orders — hostname-pinned)
                                 (EDGAR facts, submissions, CIK map)
```

Three homes on disk, and the wallet home inside the second:

| Home | What lives there | Who writes |
|---|---|---|
| the repo root | code, `strategies/`, `dsh/` (the profile *template* and skill packs), `docs/`, `payment/` (the agentpay submodule, whose `node_modules` the face imports through); also the session project directory and the sandbox workspace root | operator, coding agents, Kairos (in `strategies/`) |
| `$DSH_HOME` (default `~/.dsh`) | `profiles/face/` (the installed profile), `sessions/`, `storages/` (workspace registry), `face/` (`archived.json`, `channels.json`, `roster.log`, `agents.json`), `.env`, `.credentials.yaml` (dsh's own key store, mode 0600), `settings.yaml` (`agent-default-model`: the provider, model id and reasoning effort Kairos actually runs with; `ui-theme`, `locale`, `ui-onboarding`), `.anonymous-user-id` | the operator (the patch file, keys) and the face — including the dsh plugins it hosts (`credentials-local`, `settings-file`) — for everything else |
| `$DSH_HOME/face/agentpay` (the wallet home; `FACE_AGENTPAY_HOME` overrides) | `config.json` (the payer key, network, RPC, token; 0600), `mandates.json` (the budgets, store version 2), `ledger.jsonl` (every payment with its `context`), `wallet.lock` (the face's pid while it runs), `face-state.json` (the last balance and the ledger's settled total at that moment, for the outflow alert) | the operator writes `config.json` once (`agentpay init --home`); the face writes the rest — mandates on Kairos's card-gated request or its ungated delegate/disable, ledger rows on payment — and is the home's only writer while it holds the lock; the CLI's mutating commands refuse a locked home. Readable by every shell turn (charter D16; §9 R-W2) |
| `data/` (gitignored) | `pit/2yr`, `pit/broad` (the PIT beds), `.screen_cache`, `.face_cache` | capture scripts; the two caches |

Credentials: `.env.alpaca` and `.env.deepseek` are gitignored files at the repo root that the
operator `source`s before `npm start`; `$DSH_HOME/.env` is the equivalent placement-safe option
(dsh's layered env load reads `<cwd>/.env` then `$DSH_HOME/.env` at boot, filling only names the
process environment lacks). dsh also keeps its own writable key store,
`$DSH_HOME/.credentials.yaml` (`dsh-credentials-local`, mounted by `dsh-base`): a ref → string
map that holds the literal `DEEPSEEK_API_KEY` once anything stores it there, and that outranks
both `.env` layers (the inherited environment still wins) — so "where are the keys" has three
answers, not two. The MCP child's environment is scrubbed, so the operator's profile row passes
the APCA keys explicitly. Shell turns are scrubbed too: dsh's subprocess layer drops every
variable whose name matches `KEY|PASSWORD|SECRET|TOKEN` (case-insensitive) and every `DSH_*` name
before the spawn's explicit env is merged, so a shell child does not inherit the keys — but it
can read the key file, which is residual R1 in §9.

---

## 2. Backend: `alpaca_kit`

One Python package, two faces: an importable library (backtests import it) and an MCP server
(interactive queries go through it). Distribution `alpaca-kit` 0.1.0, Python ≥ 3.11, deps
pandas / pydantic / pyarrow / mcp; extras `[live]` (alpaca-py, pandas-market-calendars) and `[dev]`
(pytest). 4,758 lines across 41 files — 36 modules plus five empty `__init__.py` (counted
2026-09-22, the paper book included).

### 2.1 Package map

| Module | Responsibility | Names to know |
|---|---|---|
| `source.py` | the `MarketDataSource` Protocol, the in-memory `FakeSource`, the `GuardedSource` firewall wrapper | `MarketDataSource`, `FakeSource`, `GuardedSource` |
| `firewall.py` | the as-of cursor | `AsOfGuard(as_of)` with `check`, `advance`; `LookaheadError` |
| `alpaca.py` | Alpaca REST adapter: bars via alpaca-py, calendar via pandas-market-calendars, corporate actions via stdlib urllib; corp-action normalization | `AlpacaSource`, `_normalize_corp`, `_CORP_KIND` |
| `registry.py` | source selection by name or env; composite building | `make_source`, `make_composite_source` |
| `composite.py` | per-capability routing to different backends | `CompositeSource` |
| `account.py` | the Alpaca *trading* host client, paper-pinned | `TradingClient`, `PAPER_HOSTNAME`, `_require_paper` |
| `replay.py` | the backtest day iterator | `replay_days` |
| `universe.py` | daily screens (gainer / trend_template), tape breadth, squeeze legs | `build_universe`, `build_trend_template_universe`, `tape_breadth` |
| `stock.py` | the frozen per-symbol snapshot model | `StockSnapshot` |
| `integrity.py` | stdlib-only hashing, the one canonical JSON/file hasher | `sha256_file`, `canonical_json`, `sha256_canonical_json` |
| `pit/pit_store.py` | Parquet PIT bed read/write, atomic writes | `PITStore` |
| `pit/capture.py` | build a bed from a live source | `capture_window` |
| `pit/snapshot_source.py` | offline `MarketDataSource` over a bed | `SnapshotSource`, `SnapshotMissingError` |
| `pit/calendar.py` | calendar helpers over an in-memory list | `trading_days_between`, `next_trading_day`, `prev_trading_day` |
| `pit/integrity_check.py` | the `CHECKSUMS` manifest | `write_checksums`, `verify_checksums` |
| `feeds/corp_actions.py` | PIT helpers over the corp frame | `known_corporate_actions`, `has_reverse_split_pending`, `has_dilution_filing` |
| `feeds/earnings.py`, `short_interest.py`, `offerings.py`, `float_shares.py` | typed models + PIT primitives + frame converters | `EarningsFact`, `ShortInterest`, `OfferingEvent`, `FloatFact` |
| `feeds/edgar.py` | **live** SEC EDGAR backends | `EdgarSource` (earnings), `EdgarOfferingsSource` |
| `feeds/finra.py`, `feeds/float_feed.py` | **stubs** — endpoints not finalized | `FinraSource`, `FloatSource` |
| `features/trend_template.py` | Minervini eight criteria + cross-sectional RS | `evaluate_trend_template`, `trend_template_screen` |
| `features/breadth.py` | universe counts and market-wide breadth | `market_breadth`, `BreadthReading` |
| `features/short_squeeze.py`, `features/runner.py` | squeeze legs from SI + float; consecutive up-closes | `short_squeeze_signals`, `consecutive_up_days` |
| `mcp/tools.py` | the SDK-free toolset | `build_tools`, `READ_ONLY_TOOLS`, `_soft`, `_frame` |
| `mcp/server.py`, `mcp/__main__.py` | FastMCP adapter; stdio entry | `build_server` |
| `mcp/cache.py` | disk cache for `screen` / `breadth` | `CACHE_DIR`, `cache_path`, `code_hash` |
| `paper/intent.py` | the intent — what a strategy's `signal.py` answers — validated once; the by-path loader | `Intent`, `Target`, `validate_intent`, `load_signal`, `call_signal`, `IntentError` |
| `paper/book.py` | one strategy's paper book: fills, marks, corporate actions, the chained ledger, `verify` (§2.9) | `PaperBook`, `Position`, `BookError`, `DEFAULT_PARAMS`, `COUNT_KEYS` |
| `paper/home.py` | where books live (outside the workspace) and the strategy-name grammar | `paper_home`, `book_dir`, `is_strategy_name` |

### 2.2 The Protocol and the lookahead firewall

`MarketDataSource` promises normalized English columns and **RAW, unadjusted prices**. Core
methods: `trading_calendar()`, `daily_bars(symbol, start, end)`, `daily_snapshot(day)`,
`corporate_actions(start, end)` (ex-date windowed), `corporate_actions_known(as_of)`
(announce-keyed), `corp_actions_available()`. Optional capabilities, each with a `*_known(…, as_of)`
and an `*_available()` probe: earnings (PIT key `filing_date`; calendar entries keyed
`known_asof`), short interest (`publication_date`), offerings (`process_date`), float
(`knowable_date`). A source that lacks one raises `NotImplementedError`.

`AsOfGuard(as_of).check(requested)` raises `LookaheadError` when `requested > as_of`; `advance`
refuses to move backward. `GuardedSource(inner, guard)` routes every dated fetch through the
check — `daily_bars` checks `end`, `daily_snapshot` checks `day`, `corporate_actions` checks `end`,
every `*_known` checks `as_of`. `trading_calendar` and the `*_available` probes are unguarded.
The guard checks the *requested date only*; it does not adjust prices or filter rows — the
inner source's own `known_*` filter does row-level PIT. One legacy asymmetry: for an inner that
lacks the attribute, `corp_actions_available` defaults **True**, the other four probes default
**False** (fail-closed).

Six guarding tests are pinned by `(module, name)` in `tests/test_us0_firewall_surfaces.py`;
renaming or deleting any one turns that gate red: date lookahead on snapshots, corp-action
announce-date PIT, split-vintage raw bars, trailing-only RVOL ranking, the replay channel, and the
MCP layer's guard wrapping.

### 2.3 Source selection and environment

`make_source(name=None, *, pit_root=None)` — precedence explicit arg > `ALPHA_DATA_SOURCE` >
`"alpaca"`; unknown name raises `ValueError`. **It returns a RAW source**; wrapping it in
`GuardedSource(src, AsOfGuard(day))` is the caller's job (`replay_days` and the MCP tools do it
for you). Registered names: `alpaca`, `snapshot` (needs `pit_root` or `ALPHA_PIT_ROOT`),
`composite`, `edgar`, `finra`, `edgar_offerings`, `float_feed`, `massive_files` (needs
`ALPHA_MASSIVE_ROOT`).

`massive_files`: `MassiveFilesSource(root)` (`feeds/massive_files.py`) reads BOUGHT daily-bar
files — the bytes a Massive/Polygon-shaped aggregates endpoint returned to `wallet_pay({url,
save_to})` — laid out as `<root>/<TICKER>/*.json` under a strategy's `vendor/` (the `bought-data`
skill; spec `2026-09-21-bought-data-design.md`). It is a capture-side reader with the `bars` and
`calendar` groups only: `daily_snapshot`, corp actions and the P5 feeds raise `NotImplementedError`
and their `*_available()` answer False. Nothing in a file name is parsed; the body's `ticker` must
match its directory; refused, naming the file: `adjusted` not literally `false` (missing counts —
rule 4 wants RAW and the vendor's default is adjusted), `status` not `"OK"`, a row missing any of
`t/o/h/l/c/v`, two files disagreeing on one date's OHLCV. `t` (ms) is read as an
`America/New_York` date; `vw`/`n` are dropped; files for one ticker merge and dedupe.
`trading_calendar()` is the union of every ticker's bar dates unless a calendar is passed, so a
bed captured from it has the bought window as its calendar (§2.4). Composable through
`ALPHA_DATA_COMPOSITE` (`earnings=edgar`).

`composite`: `ALPHA_DATA_COMPOSITE_BASE` (default alpaca) plus `ALPHA_DATA_COMPOSITE` as
comma-separated `capability=source` pairs (`corp_actions=snapshot`, `earnings=edgar`).
`CompositeSource` routes by capability group — `calendar, bars, snapshot, corp_actions,
earnings, short_interest, offerings, float` — and each group bundles `*_known` with its
`*_available` probe so a probe cannot answer for a different backend. Pure pass-through, no
guarding.

`AlpacaSource` needs `APCA_API_KEY_ID` + `APCA_API_SECRET_KEY`. Bars are fetched with
`adjustment=RAW` on feed `ALPHA_DATA_FEED` (default `iex`; SIP 403s on free/paper keys). It has
no `daily_snapshot` (raises) and **no float methods at all** — capture, the guard and the
universe builder probe with `getattr` and treat float as absent. Corporate actions:
**`announce_date := process_date`** because Alpaca has no announce field and `process_date` is
the first retrievable day (it lags reality, never leads it); `ex_date` falls back
`ex_date → effective_date → process_date`; kinds map through `_CORP_KIND`
(`worthless_removals → delist`; 15 of the API's 16 typed arrays — `capital_gains_distributions`
is not in the map and `_normalize_corp` drops it). `corporate_actions_known(as_of)` fetches
`[as_of − 730 d, as_of]` on process date and keeps `announce_date ≤ as_of`;
`corporate_actions(start, end)` is built on the known-at-`end` set and then ex-windowed, so an
action processed after `end` is excluded even when its ex-date is in window — bar disappearance
must remain a delist signal. That announce bound is `AlpacaSource`'s alone; the bed accessor
does not apply it (§2.4).

### 2.4 PIT beds

On disk a bed is `calendar.parquet`, `bars/<SYMBOL>.parquet`, `snapshot/YYYYMMDD.parquet`,
`corp_actions.parquet`, optional feed parquets (`earnings_facts`, `earnings_calendar`,
`short_interest`, `offering_events`, `float_shares`), and `CHECKSUMS` (`sha256  relpath`, sorted,
every regular file except itself). Parquet writes are atomic temp + `os.replace`
(`_atomic_to_parquet`); `CHECKSUMS` and `broad`'s `_universe.txt` are plain `write_text`. The
`has_*()` methods are the tri-state MISSING seams: True even for an empty frame, False only when
the file is absent.

Shipped beds (gitignored; a fresh clone has none — restore from the 2026-08-29 backup or
recapture):

| bed | window | snapshots | symbols | notes |
|---|---|---|---|---|
| `data/pit/2yr` | 2024-06-03 .. 2026-07-09 | 526 | 800 | `CHECKSUMS` present |
| `data/pit/broad` | 2025-11-17 .. 2026-03-27 | 90 | 800 (liquidity-ranked, `_universe.txt`) | pre-manifest: no `CHECKSUMS` |
| `data/pit/massive-<from>-<to>` (a bought bed, captured by the operator from `strategies/<name>/vendor/massive` with `ALPHA_DATA_SOURCE=massive_files`) | = the bought window, exactly; no warmup unless bought | one derived per day | the bought tickers | **no `corp_actions.parquet`** (the source cannot check; `corp_actions_available()` False on the bed, the MCP tool answers `artifact missing`); calendar = the union of bought bar dates, not an exchange calendar; `CHECKSUMS` present. The drill bed (2016-01-01..2017-12-31, AAPL + MSFT, 521 days) is torn down, not shipped |

Neither carries feed parquets, and neither carries warmup: bars start *at* the window start.
Both calendars overhang the snapshots on both sides — back to 2016-01-04, and forward past the
last snapshot (`2yr` to 2026-07-13, two trading days after 2026-07-09; `broad` to 2026-06-22,
58 trading days after 2026-03-27), because `capture_window` stores the source's whole
`trading_calendar()` and `AlpacaSource` schedules it through the capture day. The beds fail
differently outside the window — `daily_snapshot` raises `SnapshotMissingError`, `daily_bars`
and `corporate_actions` return an **empty frame silently**, and `replay_days` checks nothing.
Bounding the replay with `start=` *and* `end=` is the only guardrail. Maturity on `2yr`: 200DMA
from 2025-03-20, 52-week metrics from 2025-06-04, first `trend_template` names 2025-06-05;
`broad` never gets there. Full statement: `docs/backtest-rules.md`.

One asymmetry between sources: only `AlpacaSource.corporate_actions(start, end)` is
announce-bounded. `SnapshotSource.corporate_actions` (and `FakeSource`) ex-window the whole
stored frame — everything known at *capture* end — so on a bed it can return an action whose
`announce_date` is after the guard's as-of; only `corporate_actions_known(as_of)` applies the
`announce_date ≤ as_of` filter on a bed. On `2yr` 4,919 of 4,987 stored rows have
`announce_date > ex_date` (Alpaca back-fills), so the two accessors disagree on most of the bed.
Use `corporate_actions_known` for anything PIT-sensitive.

`capture_window(source, store, start, end, symbols)` writes calendar, per-symbol bars, a derived
per-day snapshot (OHLCV plus previous close, `name := symbol`), corp actions known at `end`
scoped to the symbols — **only when the source's `corp_actions_available()` answers True** (a
source lacking the probe defaults True, as `GuardedSource` does; since 2026-09-21 — before that
the file was always written, and a bars-only source's empty frame replayed as "checked, clean") —
the optional feeds gated on the source's probes, then `write_checksums` last. `verify_checksums(root, fail_closed=…)` is meant for a script's `main`, never `PITStore`
construction — but nothing in this tree calls it today (only `tests/data/test_checksums.py` and
`test_capture_feeds.py`; the producers its docstring names were retired with the old product), so
a bed's manifest is written once and checked only by hand:

```bash
python -c "from alpaca_kit.pit.integrity_check import verify_checksums; print(verify_checksums('data/pit/2yr', fail_closed=True))"
```

An empty list is clean; a missing manifest (`broad`) is a warning and an empty problem list.

### 2.5 Feeds and features

| Feed | State | What it returns |
|---|---|---|
| `EdgarSource` | live (`data.sec.gov` XBRL companyconcept, no key; UA from `ALPHA_EDGAR_USER_AGENT`) | `earnings_known`: EPS (Diluted → Basic) + revenue merged by `(fy, fp, filed)`; `earnings_calendar(as_of)`: confirmed entries per filing plus one naive +91 d estimate; `estimate_eps` is always None |
| `EdgarOfferingsSource` | live (submissions) | S-1/F-1/424B1–B5/424B7 → `offering` (other 424B forms are ignored); S-3(ASR)/F-3(ASR)/S-11 → `shelf` (+ a scheduled `expired` 3 y after the shelf's earliest `EFFECT` date, falling back to its filing date when no EFFECT is on file); RW/AW → `withdrawn`; EFFECT → `effective`; grouped by file number |
| `FinraSource` | stub — URL/OAuth "finalized at live time" | `publication_date` = per-record dissemination field else settlement + 16 calendar days |
| `FloatSource` | stub — placeholder vendor URL | rows without a disclosure date dropped |
| `MassiveFilesSource` | files — bought bytes under `strategies/<name>/vendor/massive/<TICKER>/*.json` (`ALPHA_MASSIVE_ROOT`) | `daily_bars`: the six RAW columns from `o/h/l/c/v` + `t` (ET date); `trading_calendar`: the union of bar dates; everything else `NotImplementedError` / `*_available() False`; refuses adjusted, non-OK, ticker-mismatched, short-row and conflicting files by name (§2.3) |
| `feeds/corp_actions.py` | pure helpers | `has_reverse_split_pending` = announced ≤ as_of AND ex_date > as_of; `has_dilution_filing` = any announced `atm/shelf/offering`, fail-closed default when the offerings feed is absent |

Unit trap: `FloatFact.free_float` is raw shares; `StockSnapshot.free_float` is millions.

Features: `trend_template` evaluates eight criteria (RS lookbacks 126/252, SMA200-rising over
21 days, 52-week margins 1.30 / 0.75, RS threshold 70), fails closed on a missing current-day bar
and flags `insufficient_history` under 252 closes; `trend_template_screen` is two-pass (raw RS →
cross-sectional percentile → per-symbol). `market_breadth` yields `pct_above_200dma`,
`net_new_highs`, advances, declines, or None when no symbol has history. `build_universe(source,
day, …)` classifies `gainer` (≥ 10 %) / `gap_up` (≥ 5 %) / `loser` (≤ −10 %) in that order,
attaches trailing-only RVOL (window strictly before `day`), runner depth and squeeze legs, and
dispatches to the trend-template screen when `ALPHA_UNIVERSE_SCREEN` (or the `screen=` arg)
says so. `tape_breadth` counts the whole snapshot regardless of screen.

### 2.6 `replay_days`

`replay_days(source=None, *, pit_root=None, start=None, end=None)` yields
`(day, GuardedSource(source, AsOfGuard(day)))` for every day of the source's
`trading_calendar()` that falls in `[start, end]` (never a weekend or holiday; a day absent from
the calendar is skipped), a fresh guard per day, building `SnapshotSource(PITStore(pit_root))`
when no source is given. It is a
lazy generator and validates nothing about bed coverage. The five honest-eval rules that bind
every backtest — PIT channel only; delisting is a terminal −1.0; returns are gross; decide t →
enter t+1 open → exit t+N close; missing data discarded and counted — live in
`docs/backtest-rules.md`, and the `strategies/_template/backtest.py` shows the bounded call.

### 2.7 The MCP surface

`build_tools(env=None, *, source_factory=None, trading_factory=None, edgar_factory=None)` reads
three gates from the environment: `has_keys` (both APCA vars), `pit_root` (`ALPHA_PIT_ROOT`
*set*, not checked for existence), `orders_on` (`ALPACA_KIT_ENABLE_ORDERS == "1"`). Every tool
body is wrapped by `_soft`, so exceptions come back as `{"ok": false, "error": "<Type>: <msg>"}`;
frames leave through `_frame` (ISO dates, NaN → null, capped at 2,000 rows with a `truncated`
note). `as_of` defaults to **today**, never to the requested date.

| Tool | Arguments | What it reads | Registered when |
|---|---|---|---|
| `earnings` | `symbol, as_of` | EDGAR facts, PIT by filing date (EdgarSource filters itself; not guard-wrapped) | always |
| `daily_bars` | `symbol, start, end, as_of` | RAW bars through `GuardedSource(AsOfGuard)` | keys or bed |
| `calendar` | `start, end` | trading days | keys or bed |
| `corp_actions` | `symbol` (optional — omitted returns every symbol), `as_of` | announce-keyed known set, newest first; `ok:false "artifact missing"` rather than an empty frame when unavailable | keys or bed |
| `market_snapshot` | `date, as_of` | the bed's cross-section; `date` defaults to the newest captured day ≤ today | bed |
| `screen` | `date, kind, as_of` | `build_universe` on the bed (`gainer` \| `trend_template`); the guard check is hoisted above the cache read; disk-cached | bed |
| `breadth` | `date` | `market_breadth` over every snapshot symbol's bars; cached | bed |
| `account`, `positions`, `orders(status)` | — | paper account reads; `orders` without `status` is Alpaca's 50 most recent **open** orders | keys |
| `place_order(symbol, qty, side, order_type, limit_price)`, `cancel_order(order_id)` | | a PAPER order — description carries the literal `(operator-gated)` | flag **and** keys |

Measured registration matrix (2026-09-04): no env → 1 tool (`earnings`); keys only → 7; bed
only → 7; keys + bed → 10; keys + bed + flag → 12; flag alone → 1. `READ_ONLY_TOOLS` is a frozen
set that excludes the two order tools, and the suite asserts every flagless registration is a
subset of it. The "Registered when" column describes the ambient path (`python -m
alpaca_kit.mcp`, nothing injected); besides `earnings`, only the snapshot rows (`pit_root`) and
the order rows (`orders_on and has_keys`) are pure functions of the environment — an injected
`source_factory` registers the market rows and an injected `trading_factory` the account rows
regardless of keys or bed. Injection supplies a source; it cannot open Gate 1. The
`(operator-gated)` literal is load-bearing: the face's boot audit keys on it (§4.7), and a pytest
pins that the two order tools carry it and `orders` does not.

**Disk cache** (`mcp/cache.py`): `data/.screen_cache/{name}-{sha8(resolved bed path)}-{sha8(all
package source)}-{day}.json` — module-relative, outside any bed because a bed's identity is its
`CHECKSUMS`. Any `.py` edit anywhere in the package invalidates everything; **an in-place
recapture does not** — delete the directory after recapturing. Failures are never cached; an
injected `source_factory` disables the screen cache but not breadth's. Cold
`screen(kind="trend_template")` on `2yr` is ~188 s; hence `toolCallTimeoutMs: 300000` on the
operator's MCP row.

**Server**: `build_server()` creates `FastMCP("alpaca-kit")` and registers each tool by name
and description explicitly (the `_soft` closures carry no docstring); `python -m alpaca_kit.mcp`
runs it on stdio from the ambient environment.

### 2.8 The trading host and Gate 1

`TradingClient(base_url=None)` uses `base_url or APCA_API_BASE_URL or
https://paper-api.alpaca.markets`, needs both keys, and speaks JSON over stdlib urllib
(`TradingAPIError` with hints for 401/403/422/429). Reads: `get_account`, `get_positions`,
`get_orders(status)`. Writes: `place_order(symbol, qty, side, order_type, time_in_force="day",
limit_price)` and `cancel_order(order_id)`, each preceded by `_require_paper`, which compares
the **parsed hostname** to `paper-api.alpaca.markets` (a substring test would pass
`https://paper-api.alpaca.markets@api.alpaca.markets` and resolve to the live host); an
unparseable URL fails closed.

**Gate 1 is registration**, in `mcp/tools.py`: the two order tools exist in a session only when
the operator's flag AND the keys are present, and the flag lives only in the operator's home copy
of the profile row (the repo template keeps it commented out). The library functions themselves
carry no flag — the paper pin is their only guard — which is why the gates are described as
holding the MCP tool *surface*, not the account (§9, R1).

### 2.9 The paper book

`alpaca_kit/paper` keeps one simulated account per strategy — a *book* — and touches no order
path (`tests/paper/test_cli.py` greps the package and its script for one). Spec:
`docs/superpowers/specs/2026-09-22-paper-book-design.md`; the charter amendments it proposes (§5
there) are not yet accepted.

**Where.** `<home>/<strategy>/`, the home being `ALPHA_PAPER_HOME`, else `$DSH_HOME/face/paper`,
else `~/.dsh/face/paper` (`paper_home`) — outside the workspace on purpose: the sandbox denies
writes there, so Kairos reads its own book and cannot edit it (charter P1's placement argument,
applied to D1). Files: `ledger.jsonl` (append-only; every row `{seq, prev, at, day, kind, …}`
where `prev` is the sha256 of the previous row exactly as written — `integrity.canonical_json` +
`sha256_bytes`), `book.json` (the state, rewritten atomically after every step, carrying `seq`
and the chain `head`), `nav.jsonl` (one row per stepped day), `intents/<day>.json` (each intent
as validated, with `received_at` and `nav_ref`, the value it was sized on), `summary.json` (the
headline the face reads). `PaperBook.load` refuses a directory whose ledger tail and `book.json`
disagree (an interrupted step) rather than stepping on it; `verify` recomputes the chain, the
cash and the positions from the ledger's own rows and names every disagreement, `nav.jsonl`
included.

**The contract.** `strategies/<name>/signal.py` defines `signal(source, day)` — or
`signal(source, day, holdings)` when the rule wants the book's quantities and entries — and
answers `{"targets": [{"symbol", "weight"}, …], "note"?}`: weights are fractions of the book's
value, each in [0, 1], summing to at most 1, the rest cash; an empty list is flat; long only.
`validate_intent` upper-cases symbols, checks the ticker grammar, refuses duplicates, bad
weights, a gross above 1, more than 200 names and a non-string note. `load_signal` imports the
file by path under a private module name with the strategy directory on `sys.path` for the
import only, so a rule may import a sibling module and two strategies never shadow each other.
The template ships a `signal.py` that raises until written.

**One step** (`PaperBook.step(day, source, signal)`, `source` the GuardedSource for `day`), in
order: corporate actions with ex-date = `day` on held names, from `corporate_actions(day, day)`
— a forward or reverse split scales the quantity by the ratio and the cost by its inverse,
`delist` is a terminal loss (realized, removed, counted), `cash_dividend` credits quantity × rate
on the ex-date, every other kind is recorded `applied: false` with the reason and counted; a
source whose `corp_actions_available()` is false is recorded `corp_checked: false` on the day's
mark row and counted (`days_corp_unchecked`), never read as clean. Then the pending intent is
filled at `day`'s open: target quantity = ⌊weight × NAV_ref ÷ open⌋ with NAV_ref the book's value
at the intent's mark; a held name the intent leaves out targets 0; a drift below
`min_trade_weight` × NAV_ref is left alone and counted (`small_skipped`, never on an exit); sells
run before buys; a buy the cash cannot cover is cut to what it can (`cash_short`); a leg with no
usable bar (missing, NaN, non-positive) is `discard`ed and counted (rule 5). Then every held
name is marked at the close, or its stale day counted; at `presume_delisted_after` consecutive
stale days (default 5) the name is written to zero (`presumed_delisted`, rule 2). Then the
`mark` row, the `nav.jsonl` row and `book.json` are saved. Then the rule is asked: an exception
is recorded as `signal_error`, a refused answer as `intent_rejected`, both counted and re-raised
as `BookError` — the day is never read as flat and the walk stops where it stands; a good answer
is written to `intents/`, recorded as `intent` and held as pending. Days are strictly
increasing; `walk(source, start=, end=, signal=)` iterates `replay_days` (the bound is required —
rule 1's trap), skips and counts days already stepped, and so extends a book.

**Parameters** (`open`): `initial_cash`, `fees_bps` (per side, default 0 — gross, rule 3),
`presume_delisted_after`, `min_trade_weight`. Quantities are floats (a reverse split leaves a
fraction); fills are integer targets; realized P&L nets fees.

**The command** — `scripts/paper_book.py open | walk | step | verify | show <strategy>` (§3.5):
one JSON object on stdout, exit 0 iff `ok`, the `face_data.py` contract; `walk` and `step` build
the source through `make_source()` (`--source` / `--pit-root` or the `ALPHA_*` variables) after
loading the rule, so a strategy without `signal.py` fails before any market read; `step` with no
`--day` takes the source's last trading day up to today. The face shows the book (§4.4, the
overview's `paper`).

**Fixture.** `strategies/paper-drill/`: the day's five most-traded names on the snapshot
(close × volume), equal-weighted with 2% cash — a rule with no thesis that answers on every day
of any captured bed; snapshot-driven, so it runs on a bed and not on live keys.

---

## 3. Backend: the harness configuration

### 3.1 The profile — template versus installed

`dsh/profile/cordis.yml` is the *content* of the profile in indicative shape: the deepseek LLM
row, the `alpaca-kit` MCP server (`python -m alpaca_kit.mcp`, `cwd` = repo, APCA keys and
`ALPHA_PIT_ROOT: data/pit/2yr` in its env, the orders flag commented out), and the two skill
**group** roots. It is not a validated dsh config; a real profile is a list of plugin rows, and an
unrecognised key merges silently — its `permissions.always_ask` block is inert and stays as the
record of what did not work. The install path is `dsh/README.md`; the installed state is
`$DSH_HOME/profiles/face/`, created by `cd face && npm run setup` (three files: `package.json`
bundling `dsh-base` only, `cordis.patch.yml` with a load-bearing trailing `[]`,
`pnpm-workspace.yaml`; the command refuses an existing directory). The operator mounts the two
rows above into `cordis.patch.yml`; `<profile>/cordis.yml` is face-managed and rewritten to `[]`
on every boot (§4.1). `toolCallTimeoutMs: 300000` on the MCP row is required for cold screens.

AKShare is a project-owned default in `face/src/akshare.ts`: a separate stdio
`mcp-akshare` row, inserted after bundle layers and before operator profile/home
patches, which can override or disable it. It launches the separately installed
`~/.local/bin/akshare-mcp` (override: `FACE_AKSHARE_MCP_COMMAND`), passes a 500-row
response limit and uses a 120-second tool timeout. Startup failure is logged and
does not stop the host. These vendor reads have no PIT guard. Installation,
source limitations and the live-roster check are in `face/README.md`.

### 3.2 Skill packs

| Pack | Owner (charter §4) | Content |
|---|---|---|
| `dsh/skills/mechanics/backtest-rules` | operator; law, not style | the five rules, the bed-window table, warmup, the results-file contract |
| `dsh/skills/mechanics/alpaca-kit-guide` | operator | MCP-vs-import split, the registration matrix, RAW, `announce_date := process_date`, bed and warmup dates, fail-soft `ok=false` |
| `dsh/skills/style-kairos/doctrine` | operator; Kairos proposes in journal or conversation, never edits | 39 entries, 9 tagged `(red-line)` |
| `dsh/skills/style-kairos/signals` | operator | six named setups |
| `dsh/skills/style-kairos/lessons` | operator | 21 entries, 20 `(principle)`, one `(loss)` |

Every `SKILL.md` needs `name` + `description` frontmatter or dsh drops it silently. The three
style packs were emitted once by `scripts/convert_seeds.py` from the retired `seeds_v2` JSON
(kept as provenance; cannot re-run without restoring `seeds_v2/` from history). Mechanics bind:
findings never overrule them. Style yields to findings, but the conflict is reported.

### 3.3 `AGENTS.md`

The workspace map written for Kairos: the three layers, the PIT-guard rule (`replay_days` or
wrap it yourself), the strategy directory contract and lifecycle, the `status.yaml` headline
keys, the channel-name rule, the two bed windows with their failure modes and warmup dates, the
never-edit list (`data/pit/`, installed profile copies, `docs/research/`).

Discovery is dsh's, not ours: `dsh-agent-instructions` (the `agent-instructions` row `dsh-base`
mounts, 64 KiB budget) looks for `AGENTS.md` **and `CLAUDE.md`** (plus `AGENTS.local.md` /
`CLAUDE.local.md`) in every directory from the `.git` root down to the session's cwd, and for
`$DSH_HOME/AGENTS.md`. So Kairos reads `CLAUDE.md` as well — an edit there changes Kairos's
prompt — and in a channel session it also reads any `strategies/<name>/AGENTS.md` it wrote
itself. The facts `AGENTS.md` shares with `CLAUDE.md` (beds, RAW, warmup) are repeated in
`docs/backtest-rules.md`, both mechanics skills (`alpaca-kit-guide` carries the 2yr window and
the warmup dates only), `scripts/face_data.py` (`BED_INFO`, 2yr only),
`strategies/_template/backtest.py` (`BED_START`/`BED_END`, inherited by every copied strategy)
and §2.4 of this document; when a bed changes, all of them move.

### 3.4 The strategy directory contract

`strategies/<name>/` = `THESIS.md` (thesis, rules, falsification terms), `screen.py`
(`GuardedSource(make_source(), AsOfGuard(day))` over `build_universe`; resolves `ALPHA_PIT_ROOT`
against the CWD), `backtest.py` (`replay_days` bounded by `BED_START`/`BED_END`; anchors the bed
on `__file__`), `backtests/` (`YYYY-MM-DD-<label>.json`), `journal.md`, `status.yaml`, and — for a strategy that
wants a paper book — `signal.py`, the intent rule the operator's engine runs (§2.9): the template
ships one that raises until written, so an untouched copy has no book by accident.
`strategies/_template/` is the copy source. Trap: a channel session's shell runs in
`strategies/<name>/` (the `bash` tool defaults to the session cwd), so the relative
`ALPHA_PIT_ROOT=data/pit/2yr` that `AGENTS.md` prescribes points *inside* the strategy directory;
nothing validates the path at registration (§9, R8) and every read then fails per call. In a
channel session use the absolute bed path or `cd` to the repo root first; `backtest.py` is immune
because it anchors on `__file__`.

`status.yaml`: `status` ∈ `idea | researching | validated | paper | retired` (`paper` is
reserved until the order gate opens), plus optional `one_line`, `next`, `numbers` that the
channel landing page renders. The face reads `status` through a regex floor first, tolerates
malformed YAML, and does **not** validate the vocabulary — status is a badge, not a gate.

Naming: the create box accepts `NAME_RE` — first code point a letter or digit, then letters,
digits, combining marks, `_`, `-`, at most 41 code points, NFC-normalized; the browser folds
whitespace runs to one dash before posting. `_template`, dot-leading and `__`-leading
directories are never channels. Spaces stay refused on purpose: the name becomes a path Kairos
writes into shell by hand, and by the Trap above — a channel session's cwd is `strategies/<name>` —
`cd` is the command it has to write, where two words are zsh's two-argument form (word 1 replaced by
word 2 in `$PWD`), an error most of the time but exit 0 in the WRONG directory whenever the
substituted path exists.

State on 2026-09-04: three real strategies exist, all **untracked** in git — `市场情绪` (went
idea → researching → retired on 2026-09-02 by its pre-registered falsification terms; carries an
extra `sentiment.py`, a rewritten screen and backtest, and `tests/strategies/test_market_sentiment.py`
loading it by file path since `strategies/` is not a package), `storage-chain` and
`Bloom-Energy营收预期分析` (byte-identical template copies at `idea`). "git log is the audit
trail" holds nothing for them yet (§10).

### 3.5 Scripts

| Script | Purpose | Invocation |
|---|---|---|
| `scripts/capture_window.py` | build a PIT bed from the configured source | `start end root SYM…`; source via `ALPHA_DATA_SOURCE`, keys for alpaca |
| `scripts/capture_broad.py` | the one-off liquidity-ranked broad bed (top-N by median dollar volume ≥ $3 M) | `preroll_start window_end pit_root top_n` |
| `scripts/face_data.py` | the instruments' producer: `market` walks the bed through the production code path (guarded; a spy test proves every raw read has a matching guard read) and disk-caches under `data/.face_cache` keyed by bed path + producer source + as-of day — the code hash covers **`face_data.py` only**, so an `alpaca_kit` edit or an in-place recapture does not invalidate it (unlike the screen cache); delete `data/.face_cache` after either; `account` = the three read calls + the real `gate_state` (Gate 1 by the same rule as `build_tools`, Gate 2 state and note, paper pin, parsed hostname) | `market` \| `account`; JSON on stdout; exit 0 iff `ok`; read-only by construction (a test greps it for order paths) |
| `scripts/paper_book.py` | the paper book's operator command (§2.9): `open` (cash, fees, the delisting presumption, the trade band), `walk` (bounded, resumable, through `replay_days` on `make_source()`), `step` (one day, default the source's last trading day up to today), `verify` (the chain, the cash and the positions recomputed from the ledger), `show`; the book home from `--home`, `ALPHA_PAPER_HOME`, then `$DSH_HOME/face/paper`; refuses a name outside the channel grammar before any path is formed | `open \| walk \| step \| verify \| show <strategy>`; JSON on stdout; exit 0 iff `ok`; no order path (a test greps it and the package) |
| `scripts/smoke_alpaca.py` | manual live probe | `SYM start end`, keys + `[live]` |
| `scripts/convert_seeds.py` | provenance of the style packs | not re-runnable |

### 3.6 What Kairos can call

Everything below is registered tree-wide; only the alpaca-kit rows and `agent_<bin>` are
operator- or face-specific. The frozen row list is
`docs/research/2026-09-03-face-composition-snapshot.md`.

| Tool(s) | Row (`dsh-base` unless noted) | Note |
|---|---|---|
| `bash` (and `pwsh`) | `tool-bash`, `tool-pwsh` | sandboxed to the calling session's cwd (§4.1); env scrubbed as in §1 |
| file read / write / edit / search, `str_replace_editor` | `tool-fs`, `tool-fs-search`, `tool-str-replace-editor` | same sandbox boundary |
| background jobs (`job_output`, `job_list`, `job_kill`) | `tool-jobs` | a job outlives the turn that started it |
| `subagent`, `subagent_fork`, subagent control / list / report | `tool-subagent`, `tool-subagent-fork`, `tool-subagent-control`, `tool-subagent-report` (in-process spawn/fork) | Gate 2's `tools.guard` is tree-wide, so a gated tool stays gated inside a subagent |
| `ralph` | `tool-ralph` | fresh-subagent iteration, up to 64 rounds per call |
| `todo`, `goal`, `workflow`, plan mode | `tool-todo`, `tool-goal`, `tool-workflow`, `plan-mode` | |
| `skill` | `tool-skill` + `skill-filesystem` | loads one `SKILL.md` by catalog name; the catalog (name + description) is what the model chooses from |
| `web_search` | `tool-web` (`fetch: false`) over `web-search-deepseek` | outbound to `https://api.deepseek.com/anthropic/v1` with `DEEPSEEK_API_KEY`; no page fetch |
| `wallet_discover`, `wallet_offer`, `wallet_pay`, `wallet_budget_request`, `wallet_budget_delegate`, `wallet_budget_disable`, `wallet_budgets`, `wallet_report`, `wallet_reconcile` (nine) | face `wallet.ts` (in-process, registered after `bootFace` and only when the wallet home is configured) | `wallet_discover` reads the public x402 catalogue (CDP Bazaar; `FACE_AGENTPAY_BAZAAR_URL` overrides) filtered to what this wallet can pay — not a payee, no pre-flight; `wallet_pay {save_to}` writes a 2xx body under the calling channel's `vendor/` (`saveRoot` named by the face from the session header; a session in no channel is refused before paying) and returns a `saved {path, bytes, sha256}` receipt with a ≤ 1 KB preview instead of the body. The rest: the one HTTP client Kairos has, and it is not a fetch tool: before any request leaves the face the URL's host must be one a mandate the caller can spend names (agentpay's `requireMandateHost` pre-flight refuses `host_not_allowed` first); loopback, link-local, RFC 1918, unique-local, `.local` and unparsable hosts are refused outright (`isPrivateHost`; lifted only on the local chain `eip155:31337`, `LOCAL_NETWORK`); the wallet's fetch never follows a redirect (`noRedirectFetch`: a 3xx is a `host_not_allowed` refusal, since the landing host was never checked); `wallet_offer` sends no model-supplied body or headers. Absent from every bot (the allow-list mask), refused for a bot by the caller rule anyway; `wallet_budget_request` is Gate 3 (§4.7) |
| `ask_user_question` | `tool-ask-user` (face overlay) | §4.3; the answer is model-visible, so not a gate |
| `mcp__alpaca-kit__*` | the operator's MCP row | §2.7 registration matrix |
| `mcp__akshare__*` | project `mcp-akshare` row | public A-share/other market queries, unguarded; check source errors and truncation |
| `agent_<bin>` | face `agents.ts` | roster-gated per channel (§6.5) |

### 3.7 The bot directory contract

`bots/<id>/` = `agent.cordis.yml` (GENERATED by `renderComposition`: two rows — the face-owned
`kairos-bot` plugin carrying `persona` + `allow`, and `dsh-skill-filesystem` rooted at `./skills`
with `includeDefaultRoots: false`), `preset.yml` (`name`, `description` — what dsh's roster
shows), `SOUL.md` (the persona SOURCE the face copies into the composition), `README.md` (the
contract, for whoever opens the directory), `skills/` (the bot's stance pack,
`skills/<skill>/SKILL.md` with `name` + `description` frontmatter), `journal/` (the only directory
the bot may write, and its home session's cwd). `bots/_template/` is the copy source. The face is
the only writer: a hand edit to `SOUL.md` or `skills/` reaches no session until the face rewrites
`agent.cordis.yml` or the process restarts, because a preset generation is stamped on the
composition file alone (dsh-agent-presets README).

Naming: dsh's preset grammar `[a-z0-9][a-z0-9-]*`, bounded to 64 code points (`BOT_ID_RE`); the
display name folds to a proposal through `proposeBotId` (`src/bots.ts`, twinned in
`client/botId.js`) and the field stays editable. `kairos` is refused by name (`RESERVED_IDS`),
`_template` by the grammar, which admits no leading underscore — both through `isBotId`. A soul
carrying `{{` is refused twice, at `rejectSoul` and again at the plugin's `validateBotConfig`: the
system prompt is a strict template with no escape.

State on 2026-09-09: four bot directories are tracked and one is not. `bots/kairos` is the
inert default — an empty composition (`[]`) every session that names no preset joins, so Kairos's
tools stay exactly the host's — and `bots/_template` is the copy source, invisible to dsh and
refused as an id. `bots/drill-bull/` (看多派) and `bots/drill-bear/` (看空派) are the room drill's
two voices, kept as tracked fixtures with their channel `strategies/room-drill`. `bots/buffet/` is
the operator's own voice and is untracked: a created bot is the operator's to commit.

`preset.yml` may carry one key beyond `name` and `description`: `model: <provider>/<model>`
(`MODEL_ROUTE_RE`, written by `renderPresetMeta`). It is **face-only**: dsh's own metadata reader
keeps `name`, `description` and `order` and drops it. The room engine resolves it per bot, once
per room (`selectionFor` in `src/room.ts`), and falls back to the tree's default route with a
logged, model-visible note when the route is not one `provider/model` pair or the tree does not
serve it.

A bot in a room gets a member session **per room** — one per (room, bot) pair, not one per bot.
Its header is the whole membership rule: `parentSession` = the room session, `agentPreset` = the
bot, `cwd` = the channel directory, and the `read-only` permission preset pinned inside creation
setup so no create→set window exists. `src/room.ts` creates it (`materializeMember`) and resumes
it; nothing creates one by hand, and a session that only looks like one is not a member (§9, R16).

---

## 4. Frontend: the face server (`face/src`)

5,802 lines of TypeScript across 19 files, run directly by `tsx` — no build step, plus one plain
`.js` file outside `src/` (`face/plugins/bot.js`, §3.7 — a bot's composition resolves it by path,
from a directory where no `node_modules` is reachable, so it must import nothing). Pins:
`DSH_PIN = 0.1.1-rc.2` (every `@deepseek-ai/dsh-*` dependency, declared and installed) and
`CORDIS_PIN = 4.0.2` (`@deepseek-ai/cordis` rides its own track); both are asserted by
`tests/version.test.ts`. `face/README.md` carries the run table, the profile rules, the
instruments, channels, the master rail, bots, the upgrade order, and the four drills.

### 4.1 Boot sequence (`main.ts` → `boot.ts`)

1. Read `FACE_PORT` (default 3090) and `FACE_PROFILE` (default `face`) with `||`, so an empty
   export means the default rather than a moving port or the profiles root itself. Resolve the
   client directory module-relative.
2. **`process.chdir(<repo root>)`** before boot: the pinned `ApiProxyService` takes every
   session's default project directory and the sandbox's fallback workspace root from
   `process.cwd()` and offers no config key. The client directory, boot's `INSTALL_ANCHOR` and
   `data.ts`'s producer path are module-relative; the channel root, the session-delete fence
   root and the panels' cwd are read from `process.cwd()` after this chdir, so they are the repo
   root only because of it.

   `process.cwd()` is only the *fallback* boundary. `dsh-sandbox-policy` resolves the writable
   root per call from the calling session's `cwd`: a channel session is fenced to
   `strategies/<name>/` (plus platform temp areas), and a write outside it — `alpaca_kit/`,
   another strategy, `docs/` — is denied and escalates to a card; a root session (`+ new` with
   no folder chosen) is fenced to the whole repo, where `data/pit/`, `dsh/skills/` and
   `alpaca_kit/` are all writable with no card (§9, R9).
3. Install SIGINT (exit 130) / SIGTERM (exit 0) handlers and `unhandledRejection → shutdown(1)`.
4. `bootFace`: dsh's layered env load (`$DSH_HOME/.env`, `<cwd>/.env`) → `composeFace`:
   resolve `$DSH_HOME`, heal the profiles module fallback (links the face's dependency closure
   into `$DSH_HOME/profiles/node_modules`), load the profile, **rewrite `<profile>/cordis.yml`
   to `[]`** (the loader's write-back would otherwise bake composed rows in and double every
   bundle insert next boot), stack the patches — bundle layers (`dsh-base`) → project AKShare → the profile's
   `cordis.patch.yml` → the home's `cordis.patch.yml` — apply the guarded switches
   (`session-telemetry-otel` disabled when `DSH_TELEMETRY_DISABLED` is non-empty and the row is
   composed; `hmr` disabled whenever composed), then push **the face overlay last**. This
   inverts the CLI's layering deliberately: loopback-only binding must survive an operator
   patch, so face rows win silently.
5. Boot the tree; assert the `approval` and `userQuestions` services are present and that
   `ask_user_question` is in the **live** tool registry (service and tool fail independently —
   that was the 2026-08-31 → 09-02 silent outage); dispose and throw otherwise.
6. Register Gate 2 (§4.7) and audit it; log `order gate armed for …` or refuse to boot. A third
   outcome is silence: `dsh-mcp-client` defaults `failOnStartupError: false`, so an alpaca-kit
   child that cannot start (the row's `command` interpreter cannot `import alpaca_kit`, or the
   bed path is wrong) leaves the tree healthy with no `mcp__alpaca-kit__*` tools, no `order gate
   armed` line and no error from the face — only `mcp-client(alpaca-kit): connection failed …
   no tools were registered` on stdout; reconnect exhaustion unregisters the tools for the life
   of the process. Check the plugin panel's tool list or that stdout line; the fix is the row's
   `command` and a restart.
7. Mount routes: static pages, `/data/{market,account}.json`, channel routes, session routes,
   bot routes, panel routes (awaited, because their registration runs `syncAgentTools`, so every
   connected agent that has an exec recipe — `claude`, `codex` — becomes an `agent_<bin>` tool
   before the face reports up; a connected bin without a recipe stays a roster row and gets no
   tool).
8. Print `kairos-face: http://<host>:<port>/ (profile: …)` from the bound service.

One `bootFace` per process: given a `dshHome` (as the tests do; `main.ts` passes none) it sets
`process.env.DSH_HOME` permanently, which is why the six real-boot tests live in separate
files.

### 4.2 Module table

| File | Responsibility |
|---|---|
| `main.ts` | entry: chdir, signal handlers, boot, mount every route family (the room engine included), print the URL |
| `boot.ts` | the mirror of dsh CLI's private `prepareProfile / composeProfile / runProfile` against the pinned typings; the three boot assertions (the Gate 2 services, `ask_user_question` in the live registry, a resolvable default preset); Gate 2 registration |
| `overlay.ts` | the twelve host rows `dsh-base` does not mount, `satisfies`-checked against each plugin's own config type |
| `akshare.ts` | project AKShare MCP defaults, composed below operator profile/home patches |
| `orders.ts` | Gate 2 decision logic, pure: `isOrderTool`, `effectiveApprovalPolicy`, `orderApprovalDecision`, `describeOrder`, `hasApprovalGrant`, `isGatedTool`, `orderGuardReason`, `auditOrderTools`, `OPERATOR_GATED_MARKER` — depends on nothing (structural types only) |
| `budgets.ts` | Gate 3 decision logic, pure, built to Gate 2's shape: `isBudgetTool` (`BUDGET_RAW_NAME`, exact — the face registers the tool itself, so no server prefix), `requesterOf` (total: the live preset from the last `agent-preset/selected` event else the header, `origin`, `parentSession`), `classifyRequester` (the one ordered rule: `origin === 'subagent'` → child; no preset or the default → principal; else bot), `describeBudgetRequest` (purpose ≤ `PURPOSE_CHARS`, limit, per-call cap, validity, every host in full), `budgetRequestRefusal` (more than `MAX_BUDGET_HOSTS`, `*`, `*.<tld>`, malformed hosts — refused before any card), `budgetApprovalDecision` (bot or child denied in the face's words before the `never` and `ask` branches), `budgetGuardReason` (via `hasApprovalGrant`) |
| `wallet.ts` | the agent wallet: `installWallet` (synchronous through registration; `walletHomeOf`; not configured when `config.json` is absent, `resolveConfig` refuses — with an EMPTY env, the shell's `AGENTPAY_*` never consulted — or `lockedBy` names a live pid; else one `CommandContext` with `lock: true` and `requireMandateHost: true`, the nine `WALLET_TOOLS` registered through `walletToolDefinition` (`wallet_discover` included; `bazaarUrlOf` for `FACE_AGENTPAY_BAZAAR_URL`; `saveRoot = <channel dir>/vendor` passed for `wallet_pay` from a channel session only), `verifyMandates` once after registration disabling and naming what does not recover to the payer), `callerOf` (the caller rule over `requesterOf`/`classifyRequester`; throws for a bot, and for a child on a `principalOnly` tool), `isPrivateHost` + `LOCAL_NETWORK` + `privateHostRefusal`, `noRedirectFetch`, `callTitle`/`resultTitle` (the pending and completed card titles), the single-flight balance cache (`BALANCE_TTL_MS`, `BALANCE_TIMEOUT_MS`), reconcile-on-load (`RECONCILE_MIN_INTERVAL_MS`), `face-state.json`, `GET /data/wallet.json`, `spendFor` and `walletTools` seams; `WalletInstall.dispose` unregisters and releases the lock |
| `wallet-payload.ts` | `/data/wallet.json`'s body as pure functions: `usd` (atomic → six-decimal string), `mandateView`, `paymentView`, `spendOf` (by workspace id and by session; `unattributed_usd` for rows with no channel), `channelSpend` (the landing tile), `alertsOf` (every alert kind from the same inputs; `unexplained_outflow` compares the balance's fall with the ledger's settlement since the last look), `buildWalletPayload`, `nextFaceState`; `MAX_PAYMENTS` |
| `setup.ts` | one-shot `$DSH_HOME/profiles/<name>` creation; refuses to overwrite |
| `http.ts` | `HttpError`, `readBody` (4,096 B cap → 413), the fixed `FORBIDDEN` body |
| `static.ts` | `/`, `/market`, `/account`, `/client/*` with a traversal-safe resolver; the `RouteRegistrar` contract |
| `data.ts` | `/data/{market,account}.json`: fixed-argv `execFile` of the producer, TTL cache, single-flight, stale-on-error; **the trust fence every `/data` route reuses** |
| `sessions.ts` | session delete (on disk, cwd-fenced to the repo) and the reversible archive set with tombstones in `$DSH_HOME/face/archived.json` |
| `roster.ts` | `$DSH_HOME/face/channels.json`, the per-channel agent AND bot rosters: locked, atomic, fail-closed; `roster.log` append, one line kind per roster |
| `channels.ts` | channel = `strategies/<dir>` + workspace-registry identity; reconcile dirs ↔ registry ↔ sessions; `status.yaml` / `THESIS.md` / `journal.md` / `backtests/` readers; create-from-template; five routes — the overview answers `bots` (this channel's roster) and `allBots` (every preset dsh reports) beside the agent roster; `paperHomeOf` (`FACE_PAPER_HOME`, else `<dshHome>/face/paper`) and `readPaperSummary` (the engine's `summary.json` under the paper home, narrowed to `PaperTile` — absent, unreadable, malformed or missing a headline number is `null`; a name outside `NAME_RE` never reaches the filesystem), feeding the overview's `paper` key through `ChannelRouteDeps.paperHome` |
| `agents.ts` | exec recipes for `claude` and `codex` (fixed argv, prompt on stdin, scrubbed env, `--restricted` / `--sandbox read-only`), the spawn runner, the `agent_<bin>` tool with the roster check on execute, tool sync |
| `bots.ts` | bots = `bots/<id>/` agent presets: `isBotId`, `renderComposition` (the persona text written into the composition), `createBot`, `updateSoul`, `listBots` (dsh's roster merged in, `broken`/`listed`); three routes |
| `room-rules.ts` | the room's pure rules: `ROOM_CAPS`, `resolveMentions` (by id, by one-token name), `finalTextOf` + `isPass`, `validateDispatch` (names the roster), `dispatchResultText` (names who was not called), `roomLinesOf` + `formatDelta` + `memberPrompt` (the attributed delta and the four standing rules), `roundEndText`, `parseModelRoute`; the `room` message-source vocabulary |
| `room-projection.ts` | the `room` projection unit: a pure fold of the known events that carry room facts (`dispatch` calls, room-sourced messages, turn boundaries) into `{kind, round, members, organizing}`; zod schemas; `stateVersion` |
| `room.ts` | the engine on the root context: `installRoom` (the `dispatch` tool, the unit, the bus); `RoomEngine` — members created with `ctx.agents.create` (`parentSession`, `agentPreset`, the model ref, `read-only` inside `setup`) or resumed; `driveTurn` with the extending deadline and the hard-cap cancel (`keepInbox`); rounds parallel/serial, peer continuations, the three caps, `settled`/`capped`/`superseded`; answers appended to a quiet room log, the round-end `followup`; `say` (the operator's `@`), `describe`; two routes |
| `persona.ts` | Kairos's deployment persona: `readPersona` validates the strict `{{}}` template and refuses the boot on a bad file |
| `plugins/bot.js` | the `kairos-bot` composition plugin: scoped `deployment:persona` section + allow-list `tools.restrict` (`expandAllow` resolves `mcp__*__<raw>` against the live tree), dependency-free — so a preset can name it by path with nothing to install (Node would resolve a bare specifier from here, but there is nothing to resolve) |
| `panels.ts` | the master rail's feeds: local-agent roster (probe, auth, connect, disconnect), memory (skills), plugins (loader rows + tool schemas); builds `PanelDeps` from the context, whose `channelFor` answers `{workspaceId, name, dir}` — the `dir` is what the room engine gives a member as its `cwd` |
| `version.ts` | the two pins |

### 4.3 The overlay rows

Twelve rows, composed last, winning silently over the operator's patch and the home layer:
`storage`, `storage-json` (root `$DSH_HOME/storages`), `storage-domain` (json), `workspace` (the
registry `api-gateway` injects), `directory-picker`, `api-gateway` (`dsh-host-apiproxy`),
`cordis-host-runner`, `webserver` (`127.0.0.1:<port>` — loopback-only is the contract),
`connection` (`trustedHosts: []`, the `/api` Host fence), `tool-ask-user` (the model-facing half
of `userQuestions`, in no upstream bundle), `session-projection-cache` (`writeEveryEvents: 200`,
`writeIntervalMs: 5000` — the persisted projection checkpoints `session.list` reads for a cold
session, written at every `turn/end` and at disposal and throttled between by those two required
keys; the row that closes R13, and what lets a cold room keep its member states), `agent-presets`
(the bot roster, rooted at `bots/` with `trust: system`, `includeUserRoot: false` and
`default: kairos` — §3.7; `system` because the face authors by its own filesystem write, and
`user` would arm the gateway's `agentPreset.copy` / `remove` / `openDocument` RPCs over a
git-tracked directory — trust gates nothing about mounting). A patch of the operator's aimed at
any of these is accepted, overridden, and never reported; a patch matching no row is also silent
— hence the `rows.has(…)` guards around the switches.

### 4.4 Route table

All face routes register on dsh's webserver as `exact` or `prefix`; a duplicate `(kind, path)`
throws, and the fallback seat is left empty. dsh's own `/api/*` (RPC, `/api/respond`,
`/api/events.mux`) come from the `api-gateway` and `connection` rows and carry dsh's
`isTrustedApiRequest`; the face fence below is a restatement of it.

**The fence** (`isTrustedDataRequest`): loopback `Host` (`localhost`, `127.x.x.x`, `[::1]`;
missing or unparsable → refuse) AND `Sec-Fetch-Site ≠ cross-site` AND (`Origin` absent OR its
host equals `Host`). Refusal is the fixed `FORBIDDEN` string, echoing nothing. POST shells add
405 for other methods, 415 for a non-JSON content type, 400 for an unparsable body (the
sessions and panels shells also 400 a valid-JSON non-object; the channels shell reads one as `{}`
and answers by route: 404 `no such channel`, or 400 `invalid channel name`), 413 over 4,096
bytes. A request with no `Origin` passes on `Host` alone — `curl` works, which is residual R3
in §9.

| Route | Module | Does |
|---|---|---|
| `/`, `/market`, `/account`, `/wallet`; `/client/*` | `static.ts` | pages and assets; no fence, no cache headers; path containment on the resolved absolute path |
| `GET /data/wallet.json` | `wallet.ts` | fence first; `{ok:true, configured:false, reason, home}` when no wallet is installed, else the spec §4.4 body: address, network, token, balance (`{usd, at}` from a single-flight cache — one RPC read per minute, 3 s timeout — or `{unavailable}`), every mandate with its chain-effective `remaining_usd`, the newest `MAX_PAYMENTS` ledger rows with their `context`, spend by channel and session, the alerts block, and `reconcile` when loading the page ran one (only with an RPC, only when rows are `rejected`/`unknown`, at most once a minute). Never serializes the key; a store or RPC error is the fixed `request failed`. Writes `face-state.json` after a look that read the balance |
| `GET /data/market.json`, `/data/account.json` | `data.ts` | fence first, then cache, then spawn `$FACE_PYTHON scripts/face_data.py <mode>` from the repo root (market: 600 s budget, 15 min TTL; account: 30 s, 60 s); single-flight; a later failure re-serves the last good payload flagged `stale:true`; with nothing to fall back on, 503 carrying the producer's own `{ok:false}` when it wrote one, the fixed `producer failed` when it exited 0 with no output, or `producer spawn failed` + the error code (`ENOENT`, `null` for a timeout kill, an exit number) — **never the child's error text**, which carries stderr and possibly keys |
| `GET /data/channels.json` | `channels.ts` | **reconciles on every GET**: registry `create` per directory, `attachSession`, `seedRoster`; returns `{root, channels, ungrouped, archived}` |
| `POST /data/channels/overview` `{workspaceId}` | `channels.ts` | reconcile + `status.yaml`, thesis, the whole journal newest-first (the client folds entries past five), backtests newest-first with the newest dated one parsed as `latest`, file list, roster; `spend: {settled_usd, count}` through the optional `ChannelRouteDeps.spendFor` seam — present only when the wallet is configured AND the channel has a settled payment, which is why `main.ts` installs the wallet before these routes; `paper: PaperTile` through `ChannelRouteDeps.paperHome` — present only when `<paperHome>/<name>/summary.json` exists and parses, never for the repo root (§2.9; the client renders it as the paper-book card and derives nothing) |
| `POST /data/channels/agents` `{workspaceId, agents[]}` | `channels.ts` | `setRoster` → `channels.json` (409 on a corrupt file), then a dated line to `roster.log` and stdout |
| `POST /data/channels/bots` `{workspaceId, bots[]}` | `channels.ts` | `setBots` → `channels.json` (`bots[]` beside `agents[]`; 400 an id outside the bot grammar or more than `ROOM_CAPS.maxMembers` ids, 404 no such channel, 409 a corrupt file), then a dated `bots` line to `roster.log`. The overview answers `bots` (the roster) and `allBots` (every preset dsh reports, `broken` reasons included) |
| `POST /data/channels` `{name}` | `channels.ts` | `NAME_RE` + NFC; copies `_template` (409 if exists); a reconcile failure after the copy is a warning, not a 500 — the directory exists and a 500 would make the retry 409 |
| `GET /data/sessions-meta.json`; `POST /data/sessions/archive`, `/delete` | `sessions.ts` | the archive set (409 on un-archiving a host-archived id — the host is add-only at this pin); delete reads the session header's `cwd` from the first zstd frame and `rm -rf`s **only if it is inside the repo root** (ids are unique across every project under `$DSH_HOME/sessions`); an unreadable header is a 404, never "safe" |
| `GET /data/memory.json`, `POST /data/memory/skill` | `panels.ts` | the skill catalog grouped by pack; one skill's content |
| `GET /data/plugins.json` | `panels.ts` | loader rows (config never serialized) + `mcp__*` / `agent_*` tool schemas + `walletTools: [{name, description}]` from the `PanelDeps.walletTools` seam (what the FACE registered, not a prefix scan; `[]` when no wallet is configured) so money-moving tools are visible (charter Rule 5) |
| `GET /data/agents.json`; `POST /data/agents/connect`, `/disconnect`, `/rescan` | `panels.ts` | probe fifteen known CLIs (`--version` 3 s, auth 10 s, 60 s cache); connect writes `agents.json` and registers `agent_<bin>` live; disconnect disposes it |
| `GET /data/bots.json` | `bots.ts` | every directory under `bots/` in the id grammar, `listBots` merging dsh's own roster in: `broken` carries dsh's reason, `listed:false` marks a directory the roster did not report |
| `POST /data/bots` `{name?, id?, description?, soul?}` | `bots.ts` | `createBot`: id = the one given or `proposeBotId(name)`; copies `_template` and writes `preset.yml`, `SOUL.md` and the rendered composition. 400 an id outside the grammar or reserved, 400 a soul carrying `{{` or empty, 409 the directory exists (never overwritten), 500 `_template` missing. The returned row reads `listed:false` — it is built without the roster, which re-scans on the next GET |
| `POST /data/bots/soul` `{id, soul}` | `bots.ts` | `updateSoul`: rewrites `SOUL.md` and the composition's persona row together. 400 a bad id or a `{{` soul, 404 no such bot. Both POSTs take a 64 KiB body cap, not the shared 4,096 B — a soul is prose |
| `POST /data/rooms/say` `{sessionId, text}` | `room.ts` | the operator's `@`: mentions resolved against the roster (by id, by one-token display name); nobody named → `addressed: []` and the client sends an ordinary prompt; else the message is appended to the room as the operator's own (never a prompt), a cold room is resumed through the gateway's own composition (`apiProxy.sessions.models`), and each named member turns. 400 a bad id or empty text, 404 not in a channel, 409 a corrupt roster |
| `POST /data/rooms/state` `{sessionId}` | `room.ts` | the roster, the members the engine drove this boot, the caps left; never resumes |

### 4.5 Persistent state the face writes

| Path | Writer | Note |
|---|---|---|
| `$DSH_HOME/profiles/<profile>/cordis.yml` | `composeFace` | rewritten to `[]` every boot; edit `cordis.patch.yml` |
| `$DSH_HOME/profiles/node_modules` | the profiles-module heal | every boot |
| `$DSH_HOME/profiles/<profile>/{package.json, cordis.patch.yml, pnpm-workspace.yaml}` | `setupFaceProfile` | only when the profile *directory* is absent; an existing directory is left untouched even if one of the three files is missing |
| `$DSH_HOME/storages/**` | dsh's storage rows | workspace registry records (`registry.create`, `attachSession`) |
| `$DSH_HOME/storages/session_projcache.json` | dsh's projection cache (the face's overlay row) | one checkpoint record per session, written at every turn/end and at detach; what `session.list` reads for a cold session's projections |
| `$DSH_HOME/face/archived.json` | `sessions.ts` | `{archived[], deleted[]}`; plain write |
| `$DSH_HOME/face/channels.json` | `roster.ts` | `{version:1, channels:{<wsId>:{agents[], bots[]}}}`; file lock + atomic write, mode 0600; the one file that needs a cross-process lock because the reconcile writes on GET |
| `$DSH_HOME/face/roster.log` | `roster.ts` | append-only, one dated line per operator roster write |
| `$DSH_HOME/face/agents.json` | `panels.ts` | `{connected:[{bin,label}]}` |
| `$DSH_HOME/face/agentpay/config.json` | the operator (`agentpay init --home`), never the face | the payer key; its absence is the "not configured" state the face runs in |
| `$DSH_HOME/face/agentpay/mandates.json` | agentpay's store through `wallet.ts` | a root mandate on a card-approved `wallet_budget_request`; a sub-mandate on `wallet_budget_delegate` (no card); `isEnabled=false` on `wallet_budget_disable` and on a mandate `verifyMandates` cannot recover; budget counters on every payment (`adjustBudget`, chain-wide) |
| `$DSH_HOME/face/agentpay/ledger.jsonl` | agentpay's ledger through `wallet.ts` | append per payment attempt with `context` (`channel`, `channelName`, `session`, `parentSession`, `origin`, `callId`); status patched by `reconcile` |
| `$DSH_HOME/face/agentpay/wallet.lock` | `MandateWallet` (`lock: true`) | the face's pid, refreshed on save, released by `dispose`; a live pid refuses a second install and the CLI's mutating commands; a dead pid's lock is removed by `lockedBy` |
| `$DSH_HOME/face/agentpay/face-state.json` | `wallet.ts` | `{last_balance, ledger_settled_at_that_time}` after any `/data/wallet.json` look that read the balance; the outflow alert's anchor |
| `$DSH_HOME/face/paper/<strategy>/` | the operator's `scripts/paper_book.py`, **never the face** (it only reads `summary.json` for the landing page's card) | `ledger.jsonl` (append-only, hash-chained), `book.json` (atomic rewrite per step), `nav.jsonl`, `intents/<day>.json`, `summary.json` (§2.9); outside the workspace so Kairos can read and cannot write it; `ALPHA_PAPER_HOME` moves it for the engine, `FACE_PAPER_HOME` for the face — point both at the same directory |
| `$DSH_HOME/sessions/<slug>/<id>/` | `deleteSession` | removed, cwd-fenced |
| `strategies/<name>/` | `createChannel` | copied from `_template`, never overwritten |
| `strategies/<name>/vendor/<save_to>` | `wallet.ts` through agentpay's `writeSaved`, on Kairos's `wallet_pay {save_to}` | the payee's bytes, at the path Kairos named, under the channel the payment is attributed to (`saveRoot = <channel dir>/vendor`); bounded by `resolveSavePath` (no absolute path, no `..`, no symlink escape, never over an existing file unless `overwrite`), refused for a session in no channel; temp + rename; sha256 on the envelope and the path as the ledger row's `label`; gitignored (`strategies/*/vendor/`). Charter §4 row and D17; §9 R-W8 |
| `bots/<id>/` | `createBot`, `updateSoul` | copied from `_template`; `preset.yml`, `SOUL.md` and the composition's persona row rewritten together; never overwritten by create |
| `bots/<id>/journal/` | a bot's HOME session | workspace-write, cwd = the journal; the only directory a bot writes (the write to `../SOUL.md` is refused, proven in `room-smoke`) |
| `dsh/profile/persona.md` | the operator | not written by the face — read by `composeFace` into the `system-prompt` row, and a malformed template refuses the boot |
| `data/.face_cache` | the producer, not the face | |

Deleting a session does **not** detach it from its channel: `deleteSession` removes the
persistence directory and tombstones the id but never touches the registry, although in-process
the workspace entity does expose one (`WorkspaceEntity.detachSession`, reachable through
`ctx.workspaceRegistry.list()`; not a registry method, not on the RPC surface, and not declared
by the face's `WorkspaceLike`). Recorded, not fixed.

### 4.6 Environment

| Variable | Read by | Default | Effect |
|---|---|---|---|
| `FACE_PORT` | `main.ts` | `3090` | `"0"` asks the OS; `""` means default |
| `FACE_PROFILE` | `main.ts`, `setup.ts` | `face` | honored by both `setup` and `start` |
| `FACE_PYTHON` | `data.ts` | `python3` | the producer's interpreter; must `import alpaca_kit` |
| `DSH_HOME` | `main.ts`, `boot.ts`, `sessions.ts`, `panels.ts` and dsh itself via `resolveDshHome`; `setup.ts` reads it raw (`?? ~/.dsh`) | `~/.dsh` | written by `bootFace` when a test passes an override; `resolveDshHome` treats an empty or whitespace value as unset and expands `~`, `setup.ts` does neither, so such a value sends `setup` and `start` to different homes |
| `DSH_TELEMETRY_DISABLED` | `boot.ts` | unset | any non-empty value (`0`, `false` included) disables the telemetry row |
| `DSH_PERMISSION_MODE` | dsh, not the face | `workspace-write` | `danger-full-access` sets approval policy `never`: it disarms the sandbox-escalation card but **not** Gate 2, which then denies in its own words |
| `ALPACA_KIT_ENABLE_ORDERS` | the MCP child only | unset | Gate 1; the face cannot read it and consults the tool registry instead |
| `FACE_SMOKE` | tests | unset | `=1` enables the real-boot tests |
| `FACE_AGENTPAY_HOME` | `wallet.ts` (`walletHomeOf`) | `$DSH_HOME/face/agentpay` | the wallet home; `""` means default. The shell's `AGENTPAY_*` variables are NOT read by the face — its wallet is the `config.json` in the home and nothing else |
| `FACE_AGENTPAY_BAZAAR_URL` | `wallet.ts` (`bazaarUrlOf`) | agentpay's default, the CDP Bazaar | the x402 catalogue `wallet_discover` queries; `""` means default; a stub catalogue in tests |
| `FACE_PAPER_HOME` | `channels.ts` (`paperHomeOf`) | `$DSH_HOME/face/paper` | where the landing page reads paper books from; `""` means default; the engine's own default (`ALPHA_PAPER_HOME`, then `$DSH_HOME/face/paper`) resolves to the same directory unless one side is overridden |
| `DEEPSEEK_API_KEY`, `APCA_API_KEY_ID`, `APCA_API_SECRET_KEY` | dsh's credential seam; the producer; the MCP row | — | not auto-loaded from the repo's `.env.*` files |

Every child the face spawns for a local agent run or probe has these scrubbed — an enumerated
list (`SCRUBBED_ENV` in `agents.ts`), not a prefix glob: `ANTHROPIC_API_KEY`,
`ANTHROPIC_AUTH_TOKEN`, `ANTHROPIC_BASE_URL`, `ANTHROPIC_CUSTOM_HEADERS`, `OPENAI_API_KEY`,
`OPENAI_BASE_URL`, `CODEX_API_KEY`, the Bedrock/Vertex/Foundry switches, both APCA keys,
`DEEPSEEK_API_KEY`. Every other variable is inherited, `ANTHROPIC_MODEL` included; deliberately
so for `CLAUDE_CODE_OAUTH_TOKEN`, `CLAUDE_CONFIG_DIR`, `CODEX_HOME` (the CLI logs itself in; the
face never handles its credentials).

### 4.7 Gate 2: the per-order approval producer

Until 2026-09-04 nothing in the composed tree could raise an approval card for an MCP tool
call: the only producer of `{kind:"ask"}` was a sandbox escalation (a shell or file write
outside the workspace under `workspace-write`), and an MCP call never takes that path. The
approval *channel* — request, answerer, card, outcome, the paired `approval/asked` /
`approval/decided` events — was real and drilled; the producer for orders was absent.
`face/src/orders.ts` is that producer, registered by `bootFace` in two parts, because neither
alone suffices:

1. A **`tools/pre-execute` listener**, registered `prepend` so it is outermost in the waterfall
   and an inner listener cannot swallow its answer. Non-order tools pass through. For
   `place_order` / `cancel_order` — matched on the **raw name suffix**
   (`name === raw || name.endsWith("__" + raw)`), so an operator renaming the MCP server row
   cannot slip a tool past, while the read-only `orders` listing is never matched — it returns
   `{kind:"ask", reason:"PAPER order - <tool>: side=… qty=… symbol=… …"}` under policy `ask`
   (`describeOrder`: `key=value` pairs, values capped at 40 characters, unknown keys appended).
   The `approval/requested` frame carries no arguments — only the ids, the tool name and
   `reason` — and the card shows the tool name, the `reason` line and two buttons, so the order
   details reach the human only if they are inside `reason`. Under policy
   `never` (`danger-full-access`, or a runtime preset switch) it returns **`deny`** in its own
   words rather than `ask`, because dsh would otherwise render the false `the user rejected
   tool …` when nobody was asked. No `approval` service or no session → deny.
2. A **`tools.guard`**, deny-only and evaluated on *every* allow, including the allow that
   `allowed-once` becomes. It asks the calling session's **event log** — not "did my listener
   see this call" — for an `approval/asked` carrying this exact `callId` **and this tool's
   name** paired with an `approval/decided` whose outcome is `allowed-once`. A sighting is not a
   grant; only the log is. It reads the tool's *live* description (MCP servers can register
   after boot) and denies any `mcp__*` tool carrying `(operator-gated)` that the gate cannot
   name, with a fix hint.
3. A **boot audit**: if any `mcp__*` tool is marked `(operator-gated)` but not name-matched, the
   face disposes the tree and throws — a gate that covers nothing must not look healthy.

Consequences worth knowing: a card with no connected browser **blocks**, it does not deny;
grants are one-shot (`allowed-once`, no allow-always); `cancel_order` is gated identically, so
under policy `never` the risk-reducing action is refused too; and the gate binds only when dsh
runs inside the face — a dsh tree composed without the face has Gate 1 alone. **It is a gate,
not containment** (§9, R2), and the log proves a grant was recorded, not who recorded it (§9,
R3a). Drill status is in §7.4: the refusing half is automated, the admitting half is unit-tested
only, the human half has not been run.

**Gate 3, the budget card** (`face/src/budgets.ts`, registered by `bootFace` beside Gate 2 with
its own prepended listener and its own guard, 2026-09-20) is the same two-part shape applied to
one face-registered tool, `wallet_budget_request`, matched by its exact name. What differs: WHO
asks is decided before WHAT is asked — the listener reads the requester off the calling session
(`requesterOf`, the live preset outranking the header) and denies a bot ("has no wallet") or a
child task ("ask the parent to delegate") in its own words before the `never` and `ask` branches,
so the transcript never says an operator refused a card they never saw; a request that cannot be
read on one card (more than five hosts, `*`, `*.<tld>`) is denied before any card; and the `ask`
line carries the five terms and every host in full plus the requester class (the boot wiring has
no channel resolver, so the card reads `from no channel by principal`; the channel is on the
tool RESULT instead). The body (`wallet.ts`) creates the mandate in `signed` state — the
operator's click is the approval, the logged `approval/asked` + `approval/decided{allowed-once}`
pair its audit. Paying raises no card: a mandate is the pre-approval. Same residuals as Gate 2
(§9, R-W1, R-W5, R-W6).

---

## 5. Frontend: the browser client (`face/client`)

6,833 lines; ES modules served from `/client`, no bundler, no framework, no `innerHTML` anywhere
(every string lands via `textContent`).

### 5.1 Pages and files

| File | Role |
|---|---|
| `index.html` | the chat app shell: master rail (strategy / agent / memory / plugin), sidebar (brand, `+ new`, conversation list, panels), main pane (topbar, transcript, detail view, composer). Holds not one byte of host data |
| `market.html`, `account.html` | the two instruments' frames; each built entirely by its script from one endpoint |
| `api.js` | the wire envelope: `rpc(method, payload)`, `respond(rpcId, value)`, `openMux(onFrame, …)` |
| `mapper.js` | pure frame → view-model (`bubble`, `card`, `approval`, `question`, `gate-resolved`, `pulse`, `projection`, `room-line`, `turn`, `ignore`); shapes pinned to `dsh-host-apiproxy@0.1.1-rc.2`. Four of those views are the room's: a member's answer becomes a `bubble` with `role: "bot"` carrying `bot` and `name`, a round end becomes a `room-line`, a turn boundary becomes a `turn` (for every session, not only the one on screen), and the operator's `@` stays an operator bubble carrying `mention` |
| `chat.js` | the impure half: sessions sidebar, transcript, composer, gates, rail panels, detail pane, strategy picker, channel page glue; and the room: the participants strip (`renderStrip`, refetched by `loadRoomInfo`), a member's gate rendered inline in its room (`gateWho`), members folded under their room row, and the composer's `@` path |
| `render.js` | pretty renderers for alpaca-kit tool results; returns null unless both tool and payload shape are recognised, so the raw `<pre>` is always kept |
| `markdown.js` | DOM-built markdown for Kairos bubbles (inline emphasis, code, links; headings, nested lists, GFM tables, fences, quotes, rules) |
| `channels.js` | the channel landing page, assembly only — every judgement is made server-side; the **bots in this channel** chips (one per bot dsh reports, `on` when the roster carries it, `broken` with dsh's reason as the title, plus a removable chip for a rostered id no directory answers to) |
| `grouping.js`, `channelName.js`, `botId.js` | sidebar buckets keyed by `workspaceId` (never title) or by `bot:<id>`; the whitespace → dash fold; the display-name → bot-id fold |
| `room.js` | the pure room rules: `foldMembers` (the membership fold — a bot session parented by a host session, no `origin`), `isMemberSession`, `stripChips` (the strip's chips and their state precedence), `avatarGlyph`, `isMentionText` (the composer anchor), `roundEndLine`, `gateSpeaker` |
| `speaker.js` | the name the transcript writes over a turn: `speakerFor(summary, bots)` reads the session's `agentPreset` — a rostered bot's display name, its id when the roster has none, `Kairos` for the host and for no session. Per session, never per message; an unknown preset falls to the id, never to the host |
| `market.js`, `account.js` | the instruments: no state, no timer, fetch on load and on `refresh` |
| `chat.css` | one sheet for all three pages; every color a `:root` token (radii only about half — four `--r-*` tokens, the rest literal px); light only |

`speakerFor` and `botOf` read the same field, so the label over a turn and the sidebar bucket it
files under can never disagree. `chat.js` holds the answer in one module-level `speaker`, set by
`setSpeaker` before anything renders for a session — `openSession` (before the history replay),
`send` (from the summary `session.create` answers with, which always carries `agentPreset`) and
`openBotHome` (armed, before a session exists) — and reset at the three other sites that clear
`pendingAgentPreset`: `newSession`, the strategy picker's row, and a channel page's new round.
`refreshSessions` re-derives it for the active session from every `session.list` that lands, which
is what makes the label survive a mux reconnect (`onOpen` reopens the active session against the
pre-reconnect snapshot) and what turns a bare id into a bot's name once `loadBotIndex` answers;
`openSession` correspondingly leaves the label alone when it reopens the session already on screen
and the list carries no row for it. Four surfaces read the answer: the `who` element over an
assistant bubble (`bubbleNode`), the ask card's head (`questionNode`) and the status pulse
(`pulse`) read `speaker` as they render, and `setSpeaker` rewrites the composer placeholder, the
one naming surface already on screen when the voice changes.

`bucketFor` orders its buckets archived → bot → channel → ungrouped, so a session whose
`agentPreset` names a bot files under that bot even when its cwd is a channel directory. Not
reachable from the client as built — `openBotHome` is the only caller that sets `agentPreset`,
and it always sets `cwd` to the bot's journal — but the precedence is written down rather than
relied on.

### 5.2 Wire contracts

**RPC** — `POST /api/<method>` with `{type:"client-request", rpcId, method, payload}`; the reply
is `{result:{ok:true,value}}` or `{ok:false,error:{code,message}}`; `content-type:
application/json` is load-bearing (the host 415s anything else). Methods the client uses:
`session.list`, `session.history`, `session.create` (`{workspaceId}`, `{cwd}`, or `{}` when
neither was picked — the host then uses its default project directory, the repo root; never
both; `agentPreset` rides beside `cwd`, never beside `workspaceId`, when the prompt opens a
bot's home session), `session.prompt` (`mode:"queue"`, content parts, client time zone),
`session.cancel`, `session.rename`, `session.fork`, `workspace.rename`, `host.pickDirectory`,
and the three `describe` calls (`host`, `settings`, `credentials` for the three key names) that
feed the agent page. The surface is closed by design.

**Respond** — `POST /api/respond` with `{type:"client-response", rpcId, result:{ok:true,value}}`
→ `{accepted:true}` or `{accepted:false, reason}`. `rpcId` is taken **verbatim** from the mux
envelope; a minted one answers nothing. Approval value `{sessionId, approvalId,
outcome:"allowed-once"|"rejected"}`; question value the whole batch of answers, never split.

**Event stream** — `WebSocket /api/events.mux`, downlink only (the host closes 1008 on any client
send), fixed 1.5 s reconnect. Envelope `{type:"server-request", rpcId, method, payload:
MuxFrame}`; frame types `session/event` (`user/message`, `assistant/message` with
`interrupted` and `thinking`, `tool/call`, `tool/result`, `assistant/chunk` block starts,
`turn/start`, `turn/end`), `approval/requested`, `question/requested`, `approval/resolved`,
`question/resolved`, `session/projection`; the rest are ignored. The two turn boundaries are
surfaced for **every** session, not only the one on screen — that is what lets a member's fine
state on the strip end with its turn. The projection frame carries `tokenUsage`,
`contextPressure`, `title` and the `room` unit's whole value. Each event carries a `surfaceOp` — `append`, or
`{op:"replace", start, end}` at a compaction checkpoint, which removes every rendered node in
that seq range. On open the host replays every pending approval and question with its original
`rpcId`; `since` is unimplemented, so open refetches the list and reopens the active session's
history.

**Approval card flow** — `approval/requested` → the mapper lifts the envelope `rpcId` into the
view → `acceptGate` stores it (across sessions; a card for another session becomes a `waiting`
chip on that sidebar row) → the card renders an `approval` kind label beside the tool name (two
spans, no separator glyph; the ids sit in a `raw` tooltip), the reason line, and exactly two
buttons → click disables, `respond`, settle. The host broadcasts `approval/resolved` before
the HTTP receipt returns, so the client claims the wording first (`answering`), otherwise an
approved card would read `closed · allowed-once`. For Gate 2 the reason is the whole order
description; the drill explicitly does not prove the card is readable by a human (§7.4).

**Room routes** — `/data/rooms/say` is called **before** `session.prompt` whenever the composer's
text carries `(^|\s)@` and the session is in a channel; an answer of `addressed: []` means the text
named nobody on the roster and it goes out as an ordinary prompt instead. `/data/rooms/state` is
called on session open (before the gate replay, so a member's gate is attributed), on a new
session's first prompt, when the channel page's bot roster changes, and when no session is
selected (which hides the strip).

**`/data` routes** — the client calls every route in §4.4; market and account fetch once on load
and on `refresh` (button disabled in flight), render `STALE ·` with an amber class when the
server re-served an old payload, and show two clocks on market (`assembled`, `served`) because a
payload can be older than its serve. Only the sidebar list is re-polled: trailing-edge 1.2 s
after any rendered event, and after any gate settlement (which may render nothing — another
session's gate — but must rebuild the row's `waiting` chip).

### 5.3 Rendering pipeline

Frame → `acceptFrame` (queued while a history backfill is loading) → `mapFrame` → dispatch:
pulses to the status line and an ephemeral `◐ thinking…` row; projections into a per-session
store (token usage, context pressure); approvals and questions to the gate handlers; other
sessions' frames dropped; a `sessionId:seq` set dedupes backfill against stream. Then
`honourSurfaceOp`, then bubble or card. Pulses and turn boundaries of the room's MEMBER sessions
feed the strip's fine states; a `user/message` whose source is `room`/`answer` renders in the
bot's own voice, `room`/`round-end` as a room line, and `room`/`delta` (in a member's own session)
as a `context · room` row. History backfill wraps each `session.history` entry as
a synthetic `session/event` through the same path.

Operator text renders verbatim; injected user-role events from a plugin, tool or model become a
collapsed `context · <source>` row; Kairos bubbles get an optional collapsed `think` row and
DOM-built markdown (a bubble with headings, tables or fences widens to `doc`); an interrupted
answer is cut-marked, never shown complete. `tool/call` opens a collapsed card indexed by
`callId`; `tool/result` fills the same node — pretty renderer when both tool and shape are
recognised (`market_snapshot` table, `daily_bars` SVG with volume and crosshair, calendar,
breadth tiles and an account key-value grid — one flat-object renderer, tiles up to eight
fields, a grid beyond — generic eight-column tables), raw `<pre>` always appended, `.danger` on
error, spill-elided results salvaged row by row with a `truncated` note.

### 5.4 State

In memory: the active session, the seen/seq/card indexes, the gate map (all sessions), the
projection store, the channel index, the archived/deleted sets, generation tokens for list /
open / detail. `localStorage` holds exactly one key, `face.collapsed-groups` (bucket keys;
legacy title-keyed entries dropped by a UUID regex; every access in try/catch). A reload
restores only that key — the transcript comes back from the host on the next open.
Archive/delete metadata lives host-side so it survives any browser.

### 5.5 Styling

Light only: no `prefers-color-scheme`, no `data-theme`; the only media query is
`prefers-reduced-motion`. Two type stacks, `--sans` and `--mono` — the prototypes' three-voice
rule (mono for machine fact, serif for argued prose, sans for the operator) did not carry into
the live sheet, so Kairos prose renders in sans. The R4 palette is overridden lower in the file
by the 2026-09-01 neutral-grey + blue-accent block, which also adds the chart tokens. Instruments
share the shell by `.inst-*` classes plus the bare `.mono` cell utility; `body.inst-body` turns
the fixed two-pane app into a
scrolling document; the gate strip is drawn as a circuit (`.inst-gate-node.on/.off`,
`.inst-gate-wire.severed`). Client assets carry **no cache headers**: hard-reload after any
client edit, or you drill a stale `chat.js` (two false drill failures came from exactly that).

---

## 6. Paths end to end

**6.1 A paper order.** Operator arms Gate 1 in the home copy of the MCP row (flag + keys) →
the MCP child registers `place_order` with `(operator-gated)` in its description → the face's
boot audit name-matches it and logs `order gate armed` → Kairos calls it → the prepended
listener returns `ask` naming the order → dsh's `ApprovalService` raises the card and logs
`approval/asked{callId}` → the operator answers → `approval/decided{outcome}` is logged →
the guard admits the call only on a logged `allowed-once` for that `callId` →
`TradingClient.place_order` → `_require_paper` → `POST /v2/orders` on the paper host.
Deny: the model sees a rejection result and the card never reached the broker. Under
`danger-full-access` the listener denies outright.

**6.2 A dated market read.** In a backtest: `replay_days` yields `(day, GuardedSource)`; a
read for a later date raises `LookaheadError`. Through MCP: the tool builds
`GuardedSource(source, AsOfGuard(as_of or today))`, and for `screen` the guard check precedes
the cache read so a cached answer can never bypass it. The instrument producer takes the same
path, and a spy test proves every raw read has a matching guard read.

**6.3 An instrument read.** Browser → `GET /data/market.json` → fence → memory cache (15 min)
→ single-flight spawn of `face_data.py market` (600 s budget) → the producer's own disk cache
under `data/.face_cache` (cold assembly ~284 s measured; warm under a second) → JSON → served
with two stamps, `assembled_at` (when the bed walk ran; every disk-cache hit carries the same
value) and `generated_at` (when the producer last ran; a memory-cache hit re-serves it
unchanged) — the client labels them `assembled` / `served`; a later producer failure re-serves
the last good payload as `stale: true`.

**6.4 A channel listing.** Browser → `GET /data/channels.json` → the repo root first (always
a channel, named `workbench`, `isRoot: true`, listed even when `strategies/` does not exist),
then walk `strategies/*` (directories only, skipping `_template`, dot- and `__`-prefixed) → for
each directory, `registry.create` (create-or-reuse by real path) → attach every session whose
header `cwd` is that directory (persisted ∪ live, live wins) → seed a roster entry if absent
(inside the file lock) → report missing directories rather than deleting channels →
`{channels, ungrouped, archived}`.

**6.5 A local agent call.** Operator connects `claude` on the agent page (probe → `agents.json`
→ `agent_claude` registered tree-wide) and rosters it on a channel → Kairos calls `agent_claude`
in a session → `execute` resolves the session's channel by `cwd`; on the roster → spawn with a
fixed argv, prompt on stdin, scrubbed env, the session's cwd, one run per bin at a time (hard
limits: prompt ≤ 32,000 characters, 600 s per run — SIGTERM, then SIGKILL 5 s later — 16 MiB of
collected output, and a resume id must be a UUID; a run cut by any of these comes back to Kairos
as a flagged partial result, not an error); not on the roster → refused; **no channel → fails
open**. `channelFor` is a real-path lookup of the session's `cwd` over the registered workspaces
(`resolveByPath`, never `create`), so a `choose a local folder…` session is roster-checked only
when the picked folder is itself an adopted channel directory (the repo root — always the
`workbench` channel — or a reconciled `strategies/<name>`); any other folder resolves to no
channel and every connected agent is callable there. The CLI logs itself in; the face never
reads its credentials.

**6.6 The loopback fence.** `webserver` binds `127.0.0.1`; `connection` trusts no extra hosts;
every `/data` route and dsh's `/api` refuse a non-loopback `Host`, a cross-site fetch, or a
mismatched `Origin`. This is a reachability policy, not authentication (§9, R3).

**6.7 Pins and upgrades.** Bump `DSH_PIN` / `CORDIS_PIN` together with `package.json`; `npm
install` → `npm test` → `npm run typecheck` → re-diff `boot.ts` against the CLI's
`profile-boot` chunk → re-check the frame shapes — `client/mapper.js` and the hand-kept
`tests/fixtures/events.jsonl` — against the pinned `dsh-host-apiproxy/lib/types/api/*.d.ts`
(there is no generator; correct the fixture by hand when the wire changed) → `FACE_SMOKE=1 npm
test` → the drills. The five `cordis-plugin-*` packages are unpinned and held only by the
lockfile.

**6.8 A room round.** Operator checks two bots into a channel (`POST /data/channels/bots` →
`channels.json` `bots[]`) → asks a question in a channel session → Kairos calls `dispatch`
(`tool/call`) → the engine validates against the roster, starts the round and returns at once
(`tool/result` naming who was not called) → per bot: find or create the member session
(`ctx.agents.create`, `parentSession` = the room, `agentPreset` = the bot, `read-only` pinned
inside `setup`, attached to the channel workspace) → `followup` the delta prompt (its
`messageIds` are the member's cursor, in its own log) → await that turn's `turn/end` under the
extending deadline → final text after the last tool result; empty or `(pass)` → `passed`; an
error → `failed` → an answer is appended to the room log while no Kairos turn is open (else held
until its `turn/end`) → peer `@`s queue continuations (≤ 2) → round end: every held answer
flushed, then ONE `followup` naming who answered and who passed → Kairos's synthesis turn. Every
step is a known event; the `room` projection folds them; the client renders each answer in the
bot's voice as it lands and the strip from the projection plus the members' own pulses.

**6.9 A budget and a payment.** Operator runs `agentpay init --home $DSH_HOME/face/agentpay
--from-deployment <name> --key …` → the face boots, `installWallet` finds `config.json`, takes
`wallet.lock`, registers the nine tools before the first `await` and logs `wallet: 9 tools
registered, home …` → Kairos, in a channel session, calls `wallet_budgets` (nothing held) → calls
`wallet_budget_request {purpose, limit_usd, hosts}` → the prepended Gate 3 listener classifies the
requester as principal, finds the hosts readable, returns `ask` with the `BUDGET - …` line →
dsh raises the card and logs `approval/asked{callId}` → the operator answers →
`approval/decided{outcome}` → the guard admits only on a logged `allowed-once` for that `callId`
→ the body re-derives the terms from `exec.arguments` and creates a root mandate in `signed`
state (Deny: an error result the model reads, nothing in the store) → Kairos calls `wallet_pay
{url}` → `callerOf` reads the session header (principal), `channelFor(cwd)` names the channel →
`isPrivateHost` (refused on any network but the local chain) → agentpay's `requireMandateHost`
pre-flight → `MandateWallet.fetch` with `context` and `caller`: the 402, the policy gate over the
whole chain, a single-use EIP-3009 authorization, the retry, the settlement in the payee's
response → a ledger row carrying the channel, session and `callId` → the tool value is the
envelope, rendered as a pay card (`$0.001 · GET <host>/predict · settled · tx 0x…`, under the collapsed row's shorter title `$0.001000 · settled · <host>`; a refusal carries
`payment_model_context` and renders in the danger colour) → `/wallet` lists the mandate and the
payment, attributed; the channel landing page gains its `spend` tile. A child task of that
session pays only from a sub-mandate its parent delegated with `wallet_budget_delegate
{for: {children: true}}` (signed at once, no card, bounded by the parent, its spend counted up the
chain); a bot is refused by the caller rule and never sees the tools.

---

## 7. Tests and drills

### 7.1 Commands that work

| Command | From | Needs | Measured 2026-09-21 |
|---|---|---|---|
| `python -m pytest` | repo root | nothing — offline, no keys, no bed | 388 passed, ~4 s (2026-09-09) |
| `cd face && npm test` | `face/` | `payment/node_modules` installed (`(cd payment && npm ci)`); no port, no key | 541 tests, 529 pass, 12 skipped |
| `cd face && npm run typecheck` | `face/` | | clean |
| `cd face && FACE_SMOKE=1 npm test` | `face/` | boots real trees into `mkdtemp` homes, binds ports; the wallet smokes run a stub payee on loopback; still no LLM or key | the twelve skipped tests; 541/541 |
| `cd payment && npm test` | `payment/` | spawns its own hardhat nodes | 196 |

### 7.2 The Python suite

388 tests: `tests/data/` (the data layer — Protocol, guard, Alpaca normalization, PIT store,
snapshot source, registry, composite, EDGAR, FINRA, float, capture and checksums),
`tests/features/`, `tests/kit/` (MCP tools, server, cache, trading host, replay),
`tests/paper/` (the paper book, 2026-09-22: the intent grammar and every refusal, the by-path
loader, the home grammar, the book's accounting under the five rules on `FakeSource` — the next
open, sizing, sells before buys, the band, discards, stale marks and presumed delisting, a
`delist` row, a split's continuity, a dividend and an ignored kind, an unchecked bed, fees and
`cash_short`, a raising rule and a malformed intent, the guard inside the rule, `holdings`,
monotonic days, resume — the chain and `verify` catching an edited row, the CLI end to end, the
order-path fence, the template's refusal and the fixture's answer),
`tests/universe/`, the root files (the instrument producer, integrity, the firewall meta-gate,
capture wiring), and `tests/strategies/` (12 tests, untracked alongside the untracked
`strategies/市场情绪/` it loads by file path — a clean checkout has neither and collects 376; a
tree with the tests but not the strategy fails collection there rather than skipping).
`conftest.py` redirects the screen cache suite-wide so no test writes `data/.screen_cache`, and
provides a two-symbol `FakeSource` fixture; every network seam is mocked at the source's own
transport method (`_get_json` on `AlpacaSource` and the feeds, `_request` on the trading host),
with `urllib.request.urlopen` patched only in those methods' error-surface tests; no test reads
`data/pit`.

Capability-absence and parity gates beyond the six firewall surfaces: the flagless
registration ⊆ `READ_ONLY_TOOLS` for every env row; the flag without keys registers nothing; an
injected trading factory cannot open Gate 1; the `(operator-gated)` marker on both order tools
and not on the read-only `orders` listing (the near-miss name; `account` and `positions` are not
asserted); every registered source exposes `corp_actions_available`;
`gate_state` agrees with `build_tools` for every env row; the producer's source contains no
order path.

### 7.3 The face suite

541 tests (529 pass, 12 skipped without `FACE_SMOKE=1`; 313 at the 2026-09-09 pass this
paragraph was written against — the market, subagent and wallet suites came after) across
`channels`, `orders` (pure gate
logic: raw and minted names, renamed server caught, read-only listing not gated, deny under
`never`, one-shot grants for this `callId` only, marker only on `mcp__` tools, the guard reasons),
`panels`, `data` (TTL, single-flight, stale, 503 bodies never leak, fence), `mapper` (against
recorded wire frames — five of them the room's: a member's answer as a bot bubble with its id and
name, the round-end line with every turn's state, the operator's `@` still an operator bubble
carrying `mention`, a member's delta as a `context · room` row, and a turn boundary carried for a
session other than the one on screen), `roster` (seed-once, fail-closed on corruption,
append-only log), `api`, `sessions`, `channelName`, `agents` (fixed argv, scrubbed env, roster refusal, fail-open with no
channel, fail-closed on a corrupt roster), `static`, `boot`, `setup`, `overlay` (exactly twelve
rows, loopback config), `grouping`, `http`, `version`, `bots` (the id grammar and reserved names,
the rendered composition, create-never-overwrites, the soul rewrite and its `{{` refusal, the
roster merge), `botId` (the browser twin proposes only ids the server accepts), `speaker` (the transcript's
name for a session: the host for no preset, for `kairos` and for a blank one, a rostered bot's
display name, the id when the roster has no name for it or never loaded at all — and the FALLBACK
is never the host, though a roster that names a bot `Kairos` is obeyed), `bot-plugin` (both
registrations ride `ctx.effect` and return disposers; `expandAllow`), `persona`, the four room
suites, the wallet suites, and the `FACE_SMOKE` boots.

The wallet suites are `budgets` (pure, like `orders`: the exact-name match, `requesterOf` reading
the header and the LAST `agent-preset/selected` event, total on a missing header; the three
requester classes; the card line carrying every term and every host un-elided, the purpose
bound visible; the refusals — six hosts, `*`, a bare top-level wildcard with or without a port,
malformed hosts; a bot and a child denied in the face's words BEFORE the request is looked at
and before `never`; `never` denying itself; the guard satisfied only by this call's and this
tool's `allowed-once`), `wallet` (offline, over a fake context on a temp home with the wallet
package's stub payee: `walletHomeOf`, `isPrivateHost` over every range and the fail-closed
parse, the card titles, the payload builders and every alert kind, `installWallet` not
configured with no `config.json` or a refusing config and the shell's `AGENTPAY_*` ignored,
then on a stub payee: nine tools registered, the caller rule for a bot and for a child on a
principal-only tool, `context` from the header, holder routing, the page, `spendFor`, the lock
refusing a second install; on `eip155:84532` a loopback payee refused before any request and a
public host reaching agentpay's own pre-flight; a 3xx refused as `host_not_allowed`),
`wallet-model` (the client's pure model: usd strings, tx links only on Base Sepolia, the
not-configured body, alerts grouped by level, mandate rows with holder and effective remaining,
status precedence, payment attribution, spend grouping, the pay line for settled / refused /
402), `panels` (`walletTools` is the seam's list, `[]` when absent), `channels` (`spend` on the
overview only when the seam answers), `static` (the `/wallet` route pin), and under
`FACE_SMOKE=1`: `budget-gate` (Gate 3 on a real tree through a stand-in registered AFTER boot
under the exact name: the principal is asked with every host on the line, a bot preset denied,
an agentless call denied, the guard refusing the body without a grant), `wallet-smoke`
(`installWallet` on a booted tree with the stub payee on the local network: a gateway-created
principal session pays through dsh's own `tools.execute` and the ledger row carries that
session's id; a bot is refused) and `wallet-approve-smoke` (being written in parallel with
this pass: the positive path of Gate 3 — a test answerer granting the card, the guard admitting,
the body creating the mandate — the R-W5 twin of the order gate's missing admit test).

The room suites are `room-rules` (the caps block verbatim, `AGENTS.md`'s caps sentence pinned to
`ROOM_CAPS`, mention resolution, `isPass`, `finalTextOf`, dispatch validation and its two result
texts, the delta and the member prompt, the round-end text, the model route), `room-projection`
(each fold in isolation, a refused `dispatch` restoring exactly what it displaced, an `@` folded
into an open round, the schema accepting every state the fold produces), `room-engine` — against
a fake tree (`room-fake.ts`: a scriptable agent per member, a manual clock, a root
`session/event` bus) covering member creation and the read-only pin, resume-not-recreate,
parallel isolation and serial accumulation, continuations bounded to one turn per member per
round, the three caps, `settled` / `capped` / `superseded`, the deadline that extends while a
member runs or has a gate open and the hard cap that cancels with `keepInbox`, an `@` queued
behind a running turn, the cold-room resume through the gateway, and the two routes under the
fence — and `room-client` (the header fold, the strip and its state precedence, the glyph, the
mention anchor, the round-end line, the gate speaker).

The six boots: `smoke.test.ts` (the real tree serves the page, the RPC, the mux upgrade, the
forged-Host 403 via `node:http` because `fetch` silently drops a forged `Host`, the stub producer)
and `order-gate.test.ts` (fires `tools/pre-execute` at `mcp__drill__place_order` with a bare
session so the real approval service's policy lookup runs; asserts `ask` with a decidable reason,
`cancel_order` asked, `orders` allowed, an agentless call denied, a renamed server still caught,
`bash` and `ask_user_question` left alone; then the guard through the registry's real `execute`
path: a tool marked `(operator-gated)` and registered *after* boot, whose name the listener does
not claim, comes back `isError` with a message naming `ORDER_RAW_NAMES` and its body never runs).
The drill uses `mcp__drill__*` stand-ins so `ALPACA_KIT_ENABLE_ORDERS` is never armed. The three
bot boots are `bots-smoke.test.ts` (roster listing with a broken fixture and never `_template`;
the header's `agentPreset`; mask = allow ∩ tree; the persona shadow; the inert default's tool set
equal to the host's; the SHIPPED relative plugin path actually mounted — its bots root is
`mkdtemp`'d inside the repository as `.bots-smoke-*`, gitignored and removed in `finally`, so
`../../face/plugins/bot.js` resolves the way a real bot's does; **Gate 2 from a bot session**,
both outcomes — a bot whose own mask NAMES the `mcp__drill__submit_order` stand-in still meets the
tree-wide guard and comes back `isError` with the `ORDER_RAW_NAMES` message, and
`mcp__drill__place_order` fired at the waterfall with that bot's agent returns `ask` with the
symbol on the card, so the refusal cannot be credited to the mask; a `session.create` naming the
broken preset refused by dsh's own `agent-preset` error),
`bot-sandbox-smoke.test.ts` (S4) and `askuser-noclient-smoke.test.ts` (S7). The last two each
print one `observed:` line; S4 now PINS the shape §9's R10 records (the sandbox marker in the
tool's content, and the command having actually run) rather than accepting any of the three
outcomes the spec was willing to take, and S7 still asserts only the outcome it forbids. The
sixth is `room-smoke.test.ts`: a stub model route, three bots in a temp channel, one operator
prompt → Kairos dispatches all three in parallel → alpha answers, beta passes, gamma's model
fails → the answer is on the room log before the round-end wake, the wake is one turn, Kairos's
synthesis is in it; every member is parented, preset-joined, `read-only` as its first event,
carries the channel's `AGENTS.md` chain and lacks `dispatch`; the `room` value rides the session
row and the cache file; an `@` turns alpha, whose write into the channel is refused inside the
tool content (D12) and never woke Kairos; a home session writes its journal and is refused on
`../SOUL.md`.

### 7.4 Drills (`face/README.md`)

| Drill | Proves | Does not prove | Status |
|---|---|---|---|
| **Approval channel** (the README heading still reads "The Gate-2 drill"; its PASSED line calls it the approval-channel drill) — a file write outside the workspace escalates | request → answerer → card → outcome → paired `approval/asked` / `decided`; deny blocks, approve runs once | a producer for an MCP tool call | passed live 2026-08-31; re-run 2026-09-08 on `main`, passed (deny blocked, approve ran once, paired records) |
| **Order approval** — automated half | the listener is registered, reaches the live approval service, defaults to `ask`, catches renamed servers, leaves `orders` alone; mutation-proven (removing the registration fails it) | the positive path — a grant logged by the real approval service, the guard finding it, the order dispatching — is covered only by unit tests of `hasApprovalGrant` / `orderGuardReason` with hand-built events, never on a real tree (the README calls it the highest-value missing test); that a human can read the card; containment | passed 2026-09-04 |
| **Order approval** — manual half (arm Gate 1 in a *scratch* home, ask for one paper order, deny, see the audit pair) | the card, end to end | | **not yet run** — the condition before the flag flips in the real home |
| **Bots** — automated (`bots-smoke`, `bot-sandbox-smoke`, `askuser-noclient-smoke`) | roster listing incl. broken; header `agentPreset`; mask = allow ∩ tree; persona shadow; inert default; the shipped relative plugin path mounted; Gate 2 refusing an order tool the bot's own mask admits; the S4/S7 observations | that the approval CARD renders (no client) — a bot in a room and a home session's write to `../SOUL.md` were this row's two gaps until `room-smoke` closed both | passes as of 2026-09-07 |
| **Bots** — manual (`face/README.md`) | create → home → persona → tools named and not named → `{{` refused; the sidebar buckets the home session under the bot; a restart's boot line lists the id; the transcript names the speaker on all four surfaces (second run) | no automated test pins the four naming surfaces or the reconnect path; per-message attribution in a room is the Room rows below | passes as of 2026-09-07; re-run 2026-09-08 on `main` with the R12 fix in, passed |
| **Room** — automated (`room-smoke`) | a real round on a stub model: dispatch → three members (answered / passed / failed) → answers on the log before one wake → synthesis in one turn; members parented, preset-joined, `read-only` first, `AGENTS.md` chain, no `dispatch`; the projection on the row and in the cache; the `@` route with a member's write refused in content; a home refused on `../SOUL.md` | that a human can read the strip; a real model's behaviour on the four standing rules | passes as of 2026-09-09 |
| **Room** — manual (`face/README.md`, eight parts) | check-in → dispatch line → attributed bubbles and the strip → the fold → `@` → an inline member question with the needs-you mark → a member's write refused → `left` and re-check → a restart keeps states and titles | per-message attribution across a mux reconnect; convergence of four voices on one model (spec §12, R3); the peer-`@` continuation, which the operator's next `@` superseded before it ran (by design) — that path stands on the engine tests | **Drilled and PASSED 2026-09-09** on the operator's own face (`feat/rooms` @ `31b2e68`, two fresh template bots, DeepSeek as the model); one client finding (F1, the strip missing on a session's first round) fixed the same day and re-verified |
| **Budget card** — automated (`budget-gate`, `wallet-smoke`, `wallet-approve-smoke`) | Gate 3 is registered on a real tree and asks the principal with a decidable line; a bot and an agentless call are denied; the guard refuses without a grant; a real session's payment through dsh's registry lands on the ledger attributed to it; the approve path once `wallet-approve-smoke` lands | that a human can read the card; a real 402 payee over the network; containment (R-W1, R-W2, R-W6) | `budget-gate` and `wallet-smoke` pass as of 2026-09-21; `wallet-approve-smoke` in progress |
| **Budget card** — manual (`face/README.md`, in a scratch harness home on `payment/`'s local demo stack) | the card names purpose, limit and hosts; Deny leaves nothing on `/wallet`; Approve puts the mandate there; a paid fetch renders a pay card with a tx and `/wallet` shows the payment | | **Drilled and PASSED 2026-09-21** on `feat/agent-wallet` (`11c6d18`, submodule `73fe702`), the turn driven by the test `StubAdapter`; record in `face/README.md` |
| **Bought bed** — automated (`wallet.test.ts` `save_to` / `wallet_discover` cases, `wallet-smoke`'s `save_to`; pytest `test_massive_files`, `test_registry`, `test_capture`) | a file lands under `<channel>/vendor` with matching bytes and sha256 and the path on the ledger row; no channel, `../`, an overwrite refused; a big body whole with a ≤ 1 KB preview; discover filtered to payable rows; the reader's refusals; capture writes no corp file for a source that cannot check; capture → replay with the guard refusing a forward read | that a human sees the card and the file column; a catalogue with anything payable on the local chain | pass as of 2026-09-21 |
| **Bought bed** — manual (`face/README.md`, "The bought-bed drill": the demo stack + `npm run vendor-sim` on 4022, the `bought-data` skill's steps) | discover → ONE budget → offer → four sequential pays landing as files → capture without `corp_actions.parquet` → a bounded replay with the guard holding | a real vendor over the network; the interop row below | **Drilled and PASSED 2026-09-21** on `feat/bought-data` @ `0a24acf` (submodule `2177984`), scripted by the test `StubAdapter` in the `room-drill` channel: discover `ok` / 0 payable on `eip155:31337`; `wallet_offer` before any budget refused `mandate_required` (the skill's order fixed from it); the card `BUDGET - "vendor-sim bars AAPL,MSFT 2016-2017" · limit $0.05 · per call $0.01 · valid 24h · hosts 127.0.0.1:4022` → Approve → `im_4cdc5cd64363`; four pays titled `$0.010000 · settled · 127.0.0.1:4022 · saved 28.0 KB`, each card reading `$0.01 · GET 127.0.0.1:4022/v2/aggs/… · settled · tx 0x… · saved 28.0 KB`; files at `strategies/room-drill/vendor/massive/{AAPL,MSFT}/…`; `/data/wallet.json` `0.010000` remaining, four rows carrying the save path as `context.label` (the *file* column) and `context.channelName room-drill`, alerts `[expiring]`; `capture_window` → bars/snapshot/calendar/CHECKSUMS, no corp file; `replay_days` 10 days, the forward read refused, calendar 521 days. Torn down |
| **Paper book** — automated (pytest `tests/paper`; face `channels.test.ts`) | the five rules applied to a book, on `FakeSource`; the chain and `verify`; the CLI; the order-path fence; the face's `readPaperSummary` narrowing and null cases, and the overview carrying `paper` only for a channel with a book | execution realism (R-P3); a live-adapter step; a browser | pass as of 2026-09-22 |
| **Paper book** — the bed drill (`paper-drill` on the bought bed `data/pit/massive-2016-2017`, AAPL + MSFT, no corp file) | `open` → `walk 2016-01-04..2016-03-31` → 64 days in 0.8 s, NAV 100,000 → 111,465.54 (+11.47%), max drawdown −5.15%, 109 fills, `days_corp_unchecked 64`; `verify` ok over 301 chained rows; `step --day 2016-04-01` extended it; with `--min-trade-weight 0.005`: 64 fills, 47 small skips, `verify` ok over 256 rows | a bed with corporate actions (none here); that a human read the numbers on the page | **run and PASSED 2026-09-22** on `feat/paper-book` (this machine) |
| **Paper book** — manual (`face/README.md`, "The paper-book drill": boot the face with `FACE_PAPER_HOME` and `ALPHA_PAPER_HOME` on one scratch home, open the `paper-drill` channel) | the card: the stepped line, the four figures, the pending line, the `counted:` line; the boot line naming the home; no card for a channel without a book | | **not yet run** |
| **Testnet interop** (Sepolia; PayAI's echo and omniterminal) | a stranger's 402 offered, paid and settled through a facilitator the wallet does not run; a stranger's bytes saved whole; `reconcile` closing the rows | | run from agentpay's CLI 2026-09-21 (`payment/docs/interop/testnet-interop-2026-09-21.json`): PayAI echo **settled in 857 ms** through `0xc669…cb63` via Multicall3 — a signer PayAI's own facilitator advertises, not x402.org's `0xd407…f1bf` — 467 bytes saved; omniterminal offered on both networks and answered **503** after the signature (`rejected`, reserved until reconcile); **from the face: not yet run** |
| **Ask-user** — `ask_user_question` offered, called, answered, cancelled | the seam | that it is a gate (the answer is model-visible); the instruction half (README step 6 — on a thin brief that does not name the tool, Kairos asks before it builds, per `AGENTS.md`), left to the operator and not run | passed 2026-09-03 with a real model, 26 tools offered; re-run 2026-09-08 on `main`, passed (34 tools offered; answered, then Stop → `closed · cancelled`) |

---

## 8. Conventions

- **Offline suites, no keys.** Both suites run with nothing configured; a test that needs the
  network monkeypatches the seam. The real-boot tests are opt-in behind `FACE_SMOKE=1`.
- **An arc is** brainstorm → spec (`docs/superpowers/specs/`) → plan → build with tests → a
  whole-branch review → a post-build amendments block on the spec. The block is what freezes the
  spec; the Status line is left as written. Of the five post-reset specs, chat-light,
  instruments and bots-and-rooms carry the block — the last for plan 1 of its four, the rest of
  it still to build; the skeleton and channels specs have none and still read
  "pending user review" (§10). Three pre-reset specs say the same and are retired, not open.
- **A guard ships with its drill in the same change** (charter Rule 4). A guard that has never
  been pulled is presumed broken.
- **Never edit**: `data/pit/` contents (recapture is the only write), the installed profile
  copies under `$DSH_HOME` (operator territory; the face rewrites `cordis.yml`), anything under
  `bots/` (the operator's voices; Kairos proposes one in conversation and creates none), anything
  under `docs/research/` (frozen inputs).
- **No custom session-event types.** dsh's persistence refuses to reload a log carrying an
  unknown type; a room fact rides a known event with a room `source`.
- **A bot's mask is visibility, not authority.** Write sentences that say so; the session's
  sandbox mode and Gate 2 are the fences, and neither is containment.
- **Channel names do not admit spaces.** They become shell paths Kairos types by hand.
- **Line numbers in prose go stale in days.** Cite files and symbols.
- **Credentials never enter the repo**; `.env*` is gitignored; error bodies never echo child
  stderr.
- **Commit messages with code go through a file** (`git commit -F`): backticks and `$()` in
  `-m` are shell.
- **Descriptive docs.** This file, `CLAUDE.md` and `face/README.md` state what is; when the
  code moves, the doc is fixed, not defended.

---

## 9. Recorded residuals

What actually holds, stated once (charter Rule 3). None is a guarantee; each is a known gap.

- **R1 — Both order gates hold the MCP tool surface, not the account.** The library's
  `place_order` has no flag; a shell turn can read `.env.alpaca` (a gitignored file at the repo
  root, which is the workspace) and import `alpaca_kit.account`. dsh scrubs the keys from the
  shell's *environment*, not from the file. The paper-hostname pin bounds the damage.
- **R2 — Gate 2 is a gate, not containment.** `tools/execute` runs after the guard, is handed
  the execution as mutable, and re-resolves the tool by its current name; Kairos has an
  unrestricted shell. It stops the model's ordinary tool calls.
- **R3 — The loopback surfaces are reachability fences, not authentication.** One un-escalated
  shell turn can `curl` `POST /data/channels/agents` or `/api/workspace.*`: no card, no diff, no
  session event. The sandbox confines file effects; network stays unrestricted. Mitigation is
  visibility (`roster.log`), not prevention.
- **R3a — The approval answer itself is forgeable from the workspace.** `POST /api/respond`
  carries no token and the pending `rpcId` is readable off `/api/events.mux`, so one
  un-escalated shell turn can approve the order it just asked for; the log then holds a genuine
  `approval/asked` + `approval/decided{allowed-once}` pair and the guard admits it correctly.
  The gate asked; the wrong party answered (`face/README.md`, "The shell can answer its own
  card").
- **R4 — The channel roster is a menu, not a fence.** Tool registration is tree-wide (schemas
  visible everywhere, only the call refused); a session in no channel is never roster-checked;
  a shell turn can invoke the CLI directly.
- **R5 — The MCP server's writes bypass the sandbox.** It is a child of the face process, not
  of a session; `data/.screen_cache` was written with no card.
- **R6 — The charter recorded a seat the tree now fills.** *Resolved 2026-09-09.* The charter's
  D11 now names the persona mechanism (plan 4). As of 2026-09-07 the model IS told it is Kairos:
  `composeFace` patches the `system-prompt` row's `persona` from `dsh/profile/persona.md` through
  `readPersona`, which refuses the boot on a template the strict renderer would throw on.
- **R7 — Gate 2 exists only inside the face.** A dsh tree composed without it has Gate 1 alone;
  the profile's `always_ask` block is inert.
- **R8 — Registration is not readiness.** The three snapshot-backed tools register whenever
  `ALPHA_PIT_ROOT` is *set* (seven tools with the bed alone, ten once the APCA keys are present
  too); a wrong path still lists them and fails per call with `SnapshotMissingError`. Two
  different half-configured states both print seven.
- **R9 — The never-edit list is prose, not a fence.** No sandbox deny path and no test protect
  `data/pit/`, the skill packs or `docs/research/`; from a root session Kairos can rewrite any
  of them with no card (§4.1). Detection is `verify_checksums` for a bed (run by hand, §2.4)
  and `git diff` for the rest.
- **R10 — A sandboxed write is refused inside the tool's own content, not as an error.** Measured
  on a real tree (`bot-sandbox-smoke.test.ts`, spike S4): under the `read-only` permission preset a
  `bash` write returns `isError: false` with no `approval/asked` event, and the refusal appears in
  the result text as `[sandbox: file access denied under read-only mode]` followed by an offer to
  retry with escalation. The file does not exist. A caller that reads only `isError` sees a
  success, so any rule about a bot's writes is worded off the CONTENT. The escalation the content
  offers is real: a retry with `sandbox_permissions` raises an approval card, so the operator can
  grant a room member the write the preset refuses, and the grant is logged on that member's own
  session (observed and denied in the room drill's part six). The bot/Kairos asymmetry is
  enforced-with-a-human-exception, not absolute.
- **R11 — A question with no client connected blocks; it never fails.** Measured
  (`askuser-noclient-smoke.test.ts`, spike S7): `userQuestions.ask()` from an agent-owned session
  with no browser attached neither answers nor rejects — it parks until the caller aborts, exactly
  as the approval card does. An agentless (host) ask is the other branch and is rejected up front
  with `UserQuestionError: web user interaction requires an agent-owned session`. In a room the
  abort has an owner: a member's turn holds its deadline open while a gate is pending
  (`gatePending`) and the hard cap (`turnHardCapMs`, 20 minutes) is what finally cancels the turn,
  so an unanswered member question ends the round `timed-out` rather than hanging it.
- **R12 — The transcript labels a bot's reply as Kairos.** *Resolved.* Observed in the manual bots
  drill (2026-09-07): a home session's replies open in the bot's persona, the sidebar buckets the
  session under the bot's name, but the speaker label over each assistant turn is the fixed
  `Kairos` the message renderer in `chat.js` writes into the `who` element, not the session's
  `agentPreset`. Cosmetic today (one voice per session); it becomes a truth problem the moment a
  room shows several voices in one log (plan 3). Fixed 2026-09-07: the label is per SESSION
  (`speakerFor` in `client/speaker.js`, from the summary's `agentPreset`), carried by all four
  naming surfaces alike — the `who` element, the ask card's head, the composer placeholder and the
  status pulse, whose phrases (`PULSE_PHRASE`) no longer carry a name at all (§5.1). It is also
  re-derived from every `session.list` that lands (`refreshSessions`), so neither a mux reconnect
  nor a roster that arrives late can leave a stale name over a live transcript. Per-message
  attribution — several voices in one room log — stays plan 3. Browser-proven 2026-09-08
  (manual bots drill, second run): the bot's name held on all four surfaces across session
  switches, a reload and a face restart with the tab parked on the bot's session. Still,
  `speaker.test.ts` pins only the decision; no automated test pins the four surfaces or the
  reconnect path.
- **R13 — Every cold session lists as `untitled`.** The sidebar row and the topbar take a
  session's title from the `projections` column of `session.list` (`titleOf` in `client/chat.js`),
  and that column is filled by `listProjectionsFor` in `dsh-host-apiproxy`: an attached session
  cuts `sessionProjections.snapshot`, a cold one reads `sessionProjectionCache.cachedSnapshot`.
  dsh-base composes `session-projection` and NOT `dsh-session-projection-cache`, and the face adds
  no such row, so the cold branch finds no service and the column is absent. Measured 2026-09-08
  on a fresh boot: `session.list` returned 24 sessions, none with a projections block, while their
  logs carry provider `session/title` events; `$DSH_HOME/storages/session_projcache.json` holds
  three stale records the face never wrote. A title shows only while its session stays attached
  in the boot that titled it; every restart resets the whole sidebar to `untitled`. Pre-existing,
  not a bots regression. *Resolved 2026-09-08.* The face mounts `dsh-session-projection-cache`
  (overlay row, §4.3); a cold session lists with its cached projections once it has completed a
  turn under the row — sessions cold before it stay `untitled` until they are resumed. Observed
  in the room drill's part eight (2026-09-09): after a restart the cold listing carried the
  room's title and its `room` value.
- **R14 — A room's answers are appended to Kairos's log by the face, not spoken by Kairos's
  driver.** Honest and necessary (plan 2, deviation 2), but it means a room log can gain user-role
  messages while no client watches and while Kairos is idle; the persistence write path records
  them like any event. The `quiet` rule (no open turn) is what keeps a running request intact.
- **R15 — Fine states are presence, not truth.** `thinking` / `writing` / `tool` on the strip come
  from the members' own `assistant/chunk` block starts, held in the client's memory and cleared at
  turn boundaries; a reload loses them; the log never held them.
- **R16 — The membership rule is a header rule.** A session is a member of `P` when its header
  names `P`, has no `origin`, and a bot preset, and `P` runs the host. A fork of a room keeps the
  host preset and a subagent child carries `origin`, so both stay out; a blank session re-linked
  to another preset through `agentPreset.select` (an RPC the face never calls) could masquerade.
- **R17 — `superseded` is a third outcome.** The spec named two; a round the operator's next
  message cut short is neither settled nor capped, and the log says so.
- **R18 — The channel landing page lists a room's member sessions as plain `untitled` rows.**
  Observed in the room drill (2026-09-09): the member sessions are shown and counted, so Rule 5
  holds — nothing is hidden — but the rows carry no voice, while the sidebar's own fold labels
  each member with its bot's name. Polish, not a truth problem; a member's transcript names its
  voice the moment it is opened.
- **R19 — Dispatch is Kairos's judgment, and nothing checks it.** Kairos chooses whom to call and
  in which mode; it can under-call or over-call a voice, and no rule in the engine says otherwise.
  Three things push against it and none removes it: the tool result names who was NOT called, the
  operator's `@` reaches any rostered voice directly, and the round-end text asks for the
  disagreements before the conclusion.
- **R-W1 — A budget card is answerable from the workspace.** R3a applied to Gate 3: a shell turn
  can answer the card it raised over loopback, and can mint a principal session over loopback and
  request from it. The log then holds a genuine pair.
- **R-W2 — The payer key is readable by every shell turn.** `config.json` sits under `$DSH_HOME`,
  which the sandbox protects from WRITES only; a copy of the home under `$TMPDIR` runs the CLI
  with self-approved mandates and no card. Unlike R1 there is no paper-hostname analogue: the
  float the operator keeps in the wallet is the bound, and the `/wallet` outflow alert (the
  balance fell by more than the ledger settled since the last look) is the detection (charter
  D16).
- **R-W3 — Attribution is exact for tool calls and absent for the CLI.** A payment through
  `wallet_pay` carries the channel, session and `callId` the face READ off the session; a shell
  turn running `agentpay pay` directly records whatever `--context` it chose, or nothing, and
  lands in `unattributed_usd`.
- **R-W4 — The hosted facilitator fails most concurrent settlements** (3 of 5, measured in
  `payment/`'s README). The face does not queue: several child tasks paying at once will see
  refusals recorded honestly as `rejected` and released by reconcile.
- **R-W5 — The budget card's positive path has Gate 2's test gap.** `budget-gate` proves ask,
  deny and the guard's refusal; the grant → guard → body path is the `wallet-approve-smoke` test
  being written, and the manual drill covers it until then.
- **R-W6 — Gate 3 is a gate, not containment** (R2 applied): a `tools/execute` wrapper can
  rename or mutate a call after the guard, and the card describes what the body will create only
  absent such a wrapper.
- **R-W7 — The wallet tools are an HTTP client inside the face.** The charter disabled
  `tool-web`'s fetch on purpose; what keeps `wallet_offer`/`wallet_pay` from being that fetch tool
  is the mandate-host pre-flight, the private-range refusal (lifted on the local chain only) and
  the no-redirect rule (§3.6) — rules in the face and in agentpay, not a network boundary.
- **R-W8 — The face process writes bought bytes outside the sandbox.** R5's class (D10, the MCP
  server's writes): on `wallet_pay {save_to}` the face writes the payee's body under
  `strategies/<name>/vendor/` — a directory the channel session's own shell could write anyway, so
  nothing is widened; bounded by agentpay's `resolveSavePath` to `<channel>/vendor` (no absolute
  path, no `..`, no symlink escape, no overwrite unless asked), refused for a session in no
  channel, the path Kairos's argument and the root read off the session header (charter D17). Not
  held for a `tools/execute` wrapper that renames the call (R-W6's class).
- **R-P1 — The intent rule reads what it likes.** `signal.py` runs in the engine's process and is
  handed the guarded source, but nothing stops it from calling `make_source()` raw or opening a
  bed's parquet — P3's class, the same as `backtest.py`. A lookahead through the guard is on the
  ledger as `signal_error`; a read around it is review's to catch.
- **R-P2 — The paper home is readable, and the chain is tamper-evidence, not authorship.** Every
  shell turn can read a book (that is the point); the placement holds only while the sandbox
  denies writes outside the workspace, and the face has no write route to the home. `verify`
  proves the ledger consistent with itself and with `book.json`; it does not prove who wrote a
  row.
- **R-P3 — Fills are a model.** Next open, no slippage, no partial fills, no market impact,
  integer targets, longs only, one fee parameter; a book forward-tests a rule, not execution.
- **R-P4 — Corporate actions are partial.** Splits, `delist` and cash dividends (credited on the
  ex-date — the frame has no payable date) are modelled; every other kind is counted as ignored.
  An action Alpaca processes after its ex-date is missed on the day (the live accessor is
  announce-bounded) and never re-applied. A bed with no corp file is unchecked and says so on
  every mark row.
- **R-P5 — Forward days need a bed.** A snapshot-driven rule cannot step on live keys
  (`AlpacaSource.daily_snapshot` raises); the daily capture that would extend a bed is item (2)'s
  territory and is not built. A bars-only rule steps on the live adapter today.
- **R-P6 — `at` and `received_at` are the engine's wall clock.** In a replay they say when the
  engine ran; `day` is the market fact. A walk's reproducibility is the rule's and the bed's;
  the chain is per run.

---

## 10. Forward

In order; each with what "done" is and which charter row it reopens.

1. **Run the manual half of the order-approval drill** in a scratch home (deny path at least).
   Done when the card is seen and the audit pair is in the session log; flips D3.
2. **Track the strategies.** Commit `strategies/市场情绪` (with its `sentiment.py`, backtest
   artifacts and `tests/strategies/`), `storage-chain`, `Bloom-Energy营收预期分析` and the
   channel-name client fold. Done when `git log` is the audit trail it claims to be; this also
   turns ROADMAP item (1) into a built entry.
3. **Carry D11 into the charter.** *Done 2026-09-09* (plan 4 of the bots-and-rooms arc): the
   charter's D11 row names the decision that shipped — `composeFace` sets
   `system-prompt.persona` from `dsh/profile/persona.md`, and a bot's preset shadows it for that
   bot's sessions — so R6 is closed on both sides. R3, R3a and R5 were already answered by the
   2026-09-04 charter revision: §7 rules out loopback authentication and D10 carries the loopback
   fence, the forgeable answer and the MCP server's out-of-sandbox writes as an accepted debt
   with a revisit trigger. What is left of this item belongs to item 1: a real automated test of
   the admit path (R3a's positive twin — a test answerer on `approval/request`, the guard
   admitting, the order dispatching) is the highest-value missing test.
4. **Close the doc debts**: post-build blocks on the skeleton and channels specs (both still
   "pending user review"; the skeleton spec's Gate 2 paragraph describes a mechanism that never
   bound), `dsh/README.md` step 2, step 6 and its "installed state" bullets (the profile comes
   from `npm run setup`, not `dsh web`; Gate 2 is built, in the face; the bash tool does *not*
   inherit the keys; the 2026-08-31 pass was the approval channel), and in `face/README.md` the
   "Gate-2 drill" heading, the dangling "§7.4" charter citation, and the stale line citations.
5. **Daily cadence** via dsh `schedule` — deferred until a strategy is worth running daily;
   reopens D5 (spend metering) the day anything runs unattended.
6. **Paper forward-testing.** The book half is built 2026-09-22 (§2.9, spec
   `2026-09-22-paper-book-design.md`): a per-strategy book the operator's engine keeps outside
   the workspace, the `signal.py` contract, the chained ledger, `verify`, the landing page card,
   the `paper-drill` fixture; the bed drill passed. It is the independent measurement D1 asked
   for before paper forward-testing, for the book's own numbers. Remaining, in order: the
   charter amendments the spec proposes (§5 there — the operator's call); the manual half of the
   drill (the card in a browser); **the Alpaca paper mirror** — the book's target positions
   diffed into orders through Gate 1 and Gate 2, after item 1 (D3), where one card per rebalance
   is a new gate shape; the daily capture for snapshot-driven rules (R-P5) and item 5's cadence,
   which together are what `status: paper` would one day switch on; discretionary intents from a
   session (a `paper_intent` tool); per-strategy cost accounting from the wallet's ledger.
7. **FINRA and float live endpoints**; then a **second data vendor** for pre-2021 history.
8. **Distinct commit identity for Kairos** (D2) on the first confusion.
9. **Rooms** — built 2026-09-08/09 (plans 2–4); the live room drill passed 2026-09-09.
   Remaining from the spec's §11: nothing planned.
10. **A2A voices** — the charter's §7.1 admits an agent reached over A2A as a voice; no spec,
   nothing built; the day anything outside this machine can call in, the last row of the
   charter's §8 revisit table fires ("A second human, or any hosted deployment").
11. **The agent wallet** — built 2026-09-20/21 (Gate 3, `/wallet`, the tools) and extended
   2026-09-21 by the bought-data arc (spec `2026-09-21-bought-data-design.md`): built —
   `wallet_discover` (the public x402 catalogue, filtered to what this wallet can pay),
   `wallet_pay {save_to}` (a bought body under the channel's `vendor/`, sha256 receipt, 1 KB
   preview), agentpay's vendor simulator (`npm run vendor-sim`, Massive-shaped, on the local
   chain) and payee settle lock, the `massive_files` source, capture's corp-actions gate, the
   `bought-data` skill, and the bought-bed path drilled end to end (§7.4). Both manual drills of
   the wallet have now passed; the interop drill from the face has not run. Remaining, in order:
   **(C) real Massive on mainnet** — the first real purchase is a mainnet float, a mainnet key in
   the wallet home (the charter's §8 trigger; D16 and §4 reopen first), the vendor's real URL and
   `eip155:8453` in the skill's budget, nothing else in the path changes; **(B) `upto`** —
   recorded in `payment/docs/upto-design.md`, not built: every US-equities seller found is `exact`,
   and the metered scheme waits for a seller that needs it; **(B) batching and the send queue** —
   pays are sequential by rule (R-W4); the hosted facilitator's concurrency failure stands;
   **funding and custody** — no funding flow beyond "send test USDC here", no facilitator
   failover, the key a raw EOA readable by every shell turn (R-W2).

---

## Appendix A — Environment variable index

| Variable | Layer | Meaning |
|---|---|---|
| `APCA_API_KEY_ID`, `APCA_API_SECRET_KEY` | alpaca_kit, producer, MCP row | Alpaca paper credentials |
| `APCA_API_BASE_URL` | `account.py` | trading host override; anything but the paper hostname fails `_require_paper` |
| `ALPHA_DATA_SOURCE` | `registry.py` | `alpaca` \| `snapshot` \| `composite` \| `massive_files` \| feed names |
| `ALPHA_PIT_ROOT` | registry, MCP, producer, template scripts | the bed; CWD-relative |
| `ALPHA_DATA_FEED` | `alpaca.py` | bars feed, default `iex` |
| `ALPHA_DATA_COMPOSITE`, `ALPHA_DATA_COMPOSITE_BASE` | `registry.py` | composite routing |
| `ALPHA_MASSIVE_ROOT` | `registry.py` (`massive_files`) | the bought-files root, `strategies/<name>/vendor/massive`; required by that source; CWD-relative |
| `ALPHA_PAPER_HOME` | `paper/home.py`, `scripts/paper_book.py` | where paper books live; default `$DSH_HOME/face/paper`, then `~/.dsh/face/paper` |
| `FACE_PAPER_HOME` | face `channels.ts` | where the landing page reads paper books from; default `$DSH_HOME/face/paper` |
| `ALPHA_UNIVERSE_SCREEN` | `universe.py` | `gainer` \| `trend_template` |
| `ALPHA_EDGAR_USER_AGENT`, `ALPHA_FINRA_USER_AGENT`, `ALPHA_FLOAT_USER_AGENT` | feeds | outbound UA strings |
| `ALPACA_KIT_ENABLE_ORDERS` | MCP child (operator's row only) | Gate 1 |
| `DEEPSEEK_API_KEY` | dsh credential seam | the LLM |
| `DSH_HOME` | dsh, face | harness home |
| `DSH_PERMISSION_MODE` | dsh | sandbox preset; `danger-full-access` ⇒ approval policy `never` |
| `DSH_TELEMETRY_DISABLED` | face boot | any non-empty value disables telemetry |
| `FACE_PORT`, `FACE_PROFILE`, `FACE_PYTHON` | face | port, profile name, producer interpreter |
| `FACE_AGENTPAY_HOME` | face `wallet.ts` | the wallet home, default `$DSH_HOME/face/agentpay`; the shell's `AGENTPAY_*` are never read by the face |
| `FACE_AGENTPAY_BAZAAR_URL` | face `wallet.ts` | the x402 catalogue `wallet_discover` queries; default agentpay's (the CDP Bazaar) |
| `FACE_SMOKE` | face tests | enables the real boots |
| `FASTMCP_LOG_LEVEL` | MCP row | `WARNING` silences FastMCP's INFO noise; never edit `server.py` for it |
