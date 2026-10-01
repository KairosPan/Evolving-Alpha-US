# Kairos Workbench — Development Reference

**Status:** living, as-built · **Owner:** the operator · **Last full pass:** 2026-09-09 on
`feat/rooms` @ `ce07925`. **Last reviewed:** 2026-09-30 on the `worktree-dsh-0.2.0-rc.2` branch
(`8f0dedb` and the go-live tooling beside it), for the dsh 0.2.0-rc.2 re-host: every section that
re-host moved (§1, §3.1, §3.6–§3.7, §4–§10, Appendix A) was re-read against the code — 381 pytest
in a clean checkout; 654 face tests, 642 pass + 12 skipped without `FACE_SMOKE`, 654/654 under
`FACE_SMOKE=1`; typecheck clean; `npm run check:fixture` clean. The features built
2026-09-09..15 (bot settings and runtime inspection, structured room discussion, bot journals,
temporary subagents, the market watchlist and its live quotes) are named here by module and
route; their operational depth is `face/README.md`'s, and they have had no full pass here.

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

**Two D-number series.** A bare `D<n>` is a debt of the charter (`Kairos-Design.md` §5). `PLAN
D<n>` is an operator decision of the dsh 0.2.0-rc.2 re-host, numbered as the re-host plan and the
code comments that cite it number them; the plan lived in the build session and is not in the
repository, so §4.8 is where those decisions are recorded now.

**The other documents a developer will meet.**

| Document | What it is |
|---|---|
| `ROADMAP.md` | the five-item forward index from the 2026-08-29 reset plus a built log; §10 below is the ordered detail and cites its items by number — move both together |
| `docs/backtest-rules.md` | the five honest-eval rules, the bed-window table, the warmup facts |
| `docs/superpowers/specs/`, `plans/`, `runbooks/` | only the five specs and eight plans dated 2026-08-29 or later (skeleton, face chat-light, face instruments, channels, bots-and-rooms) describe this system, and none of them the dsh 0.2.0 re-host; the 54 earlier specs, 50 earlier plans and `runbooks/p-b-p-c-activation.md` are the retired product's history, filed unmarked in the same directories. `runbooks/2026-09-30-dsh-0.2.0-rc.2-go-live.md` is current: the operator's procedure for taking the harness home to 0.2.0 (§4.8, §10 item 14) |
| `docs/design/prototypes/` | the face prototypes (`BRIEF.md`, rounds a/b/c and r2–r4) that §5.5 refers to; the R2 instrument grammar and the R4 palette live here |
| `docs/research/` | frozen inputs, never edited: `2026-08-22-deepseek-harness-dsh-survey.md` is the survey the profile template cites, `2026-08-30-dsh-wiring-recon.md` the 0.1.1-era wiring recon; the rows the face composes today, and its MCP tools, are read live from the plugin panel (`/data/plugins.json`, §4.4) |
| `dsh/README.md` | the profile install path, the operator's two profile rows and the default-model row |
| `face/README.md` | run and sign-in, profile and policy layer, AKShare, the instruments and the market watchlist, channels, master rail, bots, rooms, temporary subagents, tests, upgrade order, the drills |

---

## 1. The system in one page

One long-lived process (the face) with four kinds of child, one browser tab, and three
external services on five hostnames — plus the market watchlist's quote and search providers
(Alpaca's stream, Coinbase, iFinD, Tencent and Yahoo search) and AKShare's upstreams, which
`face/README.md` lists.

```
 browser (operator) ── http://127.0.0.1:3090/?token=… once, then a 30-day cookie ──────┐
                                                                                       │
 ┌─ kairos-face  (Node 22, `tsx src/main.ts`, cwd = repo root) ────────────────────────┴──┐
 │  hosts DeepSeek Harness (dsh 0.2.0-rc.2) IN-PROCESS from profile `face`                │
 │  ├─ dsh-base bundle: LLM (deepseek), sessions, storage + projection cache, tools       │
 │  │   (§3.6), sandbox, approvals, skills, the `/api` gateway (`typert-gateway`)         │
 │  ├─ face policy layer (§4.3): the 0.1.1 tool roster, egress and telemetry restored     │
 │  ├─ face overlay rows (twelve, §4.3): webserver · connection (sign-in) · api-remotes · │
 │  │   file-upload · workspace · three Remote controllers · directory-picker ·           │
 │  │   ask-user · agent-preset-registry · preset-kairos                                  │
 │  ├─ bots: each `bots/<id>/` declared as a dsh preset after boot (§3.7)                 │
 │  ├─ face routes: `/` (sign-in) `/market` `/account` `/client/*` `/data/*`              │
 │  ├─ Gate 2: armed inside boot's `prepare` (`armOrderGate`) on `tools/pre-execute` +   │
 │  │   `tools.guard`, the moment those services exist; the rules live in `src/orders.ts` │
 │  └─ children:                                                                          │
 │       ├─ MCP servers: alpaca-kit (operator row), akshare-mcp (project row); stdio      │
 │       ├─ `scripts/face_data.py market|account`, `scripts/face_watchlist.py`            │
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

Three homes on disk:

| Home | What lives there | Who writes |
|---|---|---|
| the repo root | code, `strategies/`, `dsh/` (the profile *template* and skill packs), `docs/`; also the session project directory and the sandbox workspace root | operator, coding agents, Kairos (in `strategies/`) |
| `$DSH_HOME` (default `~/.dsh`) | `profiles/face/` (the installed profile; its `cordis.patch.yml` holds the operator's rows — and, once the operator adds it, `agent-default-model`: the provider, model id and reasoning effort Kairos runs with, §3.1, PLAN D2), `sessions/` (per session a 0.1.1 `session.jsonl.zstd` and/or, once 0.2.0 has write-opened it, `session.v4.jsonl.zstd` + `session.lock`), `storages/` (workspace registry; the projection cache, one record per session), `face/` (`archived.json`, `channels.json`, `roster.log`, `agents.json`), `.env`, `.credentials.yaml` (dsh's own key store, mode 0600; since 0.2.0 also the browser-session signing secret), `.anonymous-user-id`; `settings.yaml` is 0.1.1's settings file, which the face no longer reads (PLAN D1) | the operator (the patch file, keys) and the face — including the dsh plugins it hosts (`credentials-local`, `connection`, the session persistence and the storage chain) — for everything else |
| `data/` (gitignored) | `pit/2yr`, `pit/broad` (the PIT beds), `.screen_cache`, `.face_cache` | capture scripts; the two caches |

Credentials: `.env.alpaca` and `.env.deepseek` are gitignored files at the repo root that the
operator `source`s before `npm start`; `$DSH_HOME/.env` is the equivalent placement-safe option
(dsh's layered env load reads `<cwd>/.env` then `$DSH_HOME/.env` at boot, filling only names the
process environment lacks). dsh also keeps its own writable key store,
`$DSH_HOME/.credentials.yaml` (`dsh-credentials-local`, mounted by `dsh-base`): a ref → string
map that holds the literal `DEEPSEEK_API_KEY` once anything stores it there, and that outranks
both `.env` layers (the inherited environment still wins) — so "where are the keys" has three
answers, not two. Since 0.2.0 the same file also holds a `records:` grant,
`client-connection/browser-session`: the secret that signs the browser cookie (§4.4), written by
the first boot on a home and kept across restarts. The MCP child's environment is scrubbed, so
the operator's profile row passes the APCA keys explicitly. Shell turns are scrubbed too: dsh's
subprocess layer drops every variable whose name matches `KEY|PASSWORD|SECRET|TOKEN`
(case-insensitive) and every `DSH_*` name before the spawn's explicit env is merged, so a shell
child does not inherit the keys — but it can read the key files, which is residual R1 in §9 (and,
for the signing secret, R3a).

---

## 2. Backend: `alpaca_kit`

One Python package, two faces: an importable library (backtests import it) and an MCP server
(interactive queries go through it). Distribution `alpaca-kit` 0.1.0, Python ≥ 3.11, deps
pandas / pydantic / pyarrow / mcp; extras `[live]` (alpaca-py, pandas-market-calendars) and `[dev]`
(pytest). 3,678 lines across 36 files — 31 modules plus five empty `__init__.py`.

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
`composite`, `edgar`, `finra`, `edgar_offerings`, `float_feed`.

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
scoped to the symbols, the optional feeds gated on the source's probes, then `write_checksums`
last. `verify_checksums(root, fail_closed=…)` is meant for a script's `main`, never `PITStore`
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
bundling `dsh-base` only, `cordis.patch.yml` with a load-bearing trailing `[]` under a header —
`PATCH_HEADER` in `src/setup.ts` — that names the rows the face owns, `pnpm-workspace.yaml`; the
command refuses an existing directory, so a profile created before 0.2.0 keeps its older header,
which is prose only). The operator mounts the two rows above into `cordis.patch.yml`;
`<profile>/cordis.yml` is face-managed and rewritten to `[]` on every boot (§4.1).
`toolCallTimeoutMs: 300000` on the MCP row is required for cold screens. Both operator rows are
unchanged and valid at 0.2.0-rc.2.

The same file carries Kairos's default model. The face provides no `profileContext` (PLAN D1),
so it reads no `$DSH_HOME/settings.yaml`, and without an `agent-default-model` row Kairos runs
dsh-base's `deepseek-official/deepseek-flash`. Nothing in the running face writes the default
back either: `agentDefaultModel.saveSelection` needs a config editor, which only `profileContext`
brings, so `session/selectModel` — a Remote the face client does not call — would change one
session and save nothing. The row (PLAN D2; `deepseek-v4-pro` and `deepseek-flash` are the
0.2.0 catalog's two DeepSeek models, `deepseek-v4-flash` is gone):

```yaml
- id: agent-default-model
  config: { provider: deepseek-official, model: deepseek-v4-pro, reasoningEffort: max }
```

No module link farm any more: every bare row name resolves through the runtime resolution the
face computes from its own `package.json` at each boot (§4.1). A row naming a package outside
that closure falls through to `$DSH_HOME/profiles/` itself, where a stale 0.1.1
`profiles/node_modules` farm would answer with a 0.1.1 package — harmless for the operator's two
rows, and the reason PLAN D13 deletes the farm once no 0.1.1 tool runs on the home.

AKShare is a project-owned default in `face/src/akshare.ts`: a separate stdio
`mcp-akshare` row, inserted after the bundle and policy layers and before operator profile/home
patches, which can override or disable it. It launches the separately installed
`~/.local/bin/akshare-mcp` (override: `FACE_AKSHARE_MCP_COMMAND`), passes a 500-row
response limit and uses a 120-second tool timeout. Startup failure is logged and
does not stop the host (`failOnStartupError: false`: the row is ACTIVE either way). These vendor
reads have no PIT guard. Since 0.2.0 an MCP server's `instructions` enter the system prompt as a
`mcp:<serverName>` section with no switch — akshare-mcp sets them, so Kairos's prompt and every
bot's carry an `mcp:akshare` section — and instructions over 32 KiB fail the connection; stdio
negotiation starts a probe process before the serving one, so each MCP server is spawned twice
per connect. Installation, source limitations and the live-roster check are in `face/README.md`.

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
on `__file__`), `backtests/` (`YYYY-MM-DD-<label>.json`), `journal.md`, `status.yaml`.
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
| `scripts/face_data.py` | the instruments' producer: `market` (behind the legacy `/data/market.json`, which no page reads since the market watchlist replaced that instrument) walks the bed through the production code path (guarded; a spy test proves every raw read has a matching guard read) and disk-caches under `data/.face_cache` keyed by bed path + producer source + as-of day — the code hash covers **`face_data.py` only**, so an `alpaca_kit` edit or an in-place recapture does not invalidate it (unlike the screen cache); delete `data/.face_cache` after either; `account` = the three read calls + the real `gate_state` (Gate 1 by the same rule as `build_tools`, Gate 2 state and note, paper pin, parsed hostname) | `market` \| `account`; JSON on stdout; exit 0 iff `ok`; read-only by construction (a test greps it for order paths) |
| `scripts/face_watchlist.py` | the market watchlist's US snapshot catalog: the latest captured snapshot and at most 30 trailing closes per symbol, every read guarded at the captured day; no network, no synthetic prices | no arguments; `ALPHA_PIT_ROOT` (default the 2yr bed); JSON on stdout; spawned by `/data/watchlist.json`, which no page reads any more (§4.4) |
| `scripts/smoke_alpaca.py` | manual live probe | `SYM start end`, keys + `[live]` |
| `scripts/convert_seeds.py` | provenance of the style packs | not re-runnable |

### 3.6 What Kairos can call

Everything below is registered tree-wide; only the MCP rows, `agent_<bin>` and `dispatch` are
operator- or face-specific. The host roster is dsh-base's plus the face's policy layer (§4.3),
and on the pinned tree it equals the 0.1.1 face's name for name: 26 tools before any MCP server,
local agent or room (measured 2026-09-30 against a boot of the 0.1.1 composition). dsh-base
0.2.0 alone would differ — `web_fetch` and three MCP resource tools on, `ralph` and
`str_replace_editor` gone — and the policy layer undoes each (PLAN D6, D7, D9). The rows a
running face actually composed, and its MCP and `agent_<bin>` tools, are listed by the plugin
panel (`/data/plugins.json`).

| Tool(s) | Row (`dsh-base` unless noted) | Note |
|---|---|---|
| `bash` (and `pwsh` on Windows) | `tool-bash`, `tool-pwsh` | sandboxed to the calling session's cwd (§4.1); env scrubbed as in §1 |
| `read`, `write`, `edit`, `read_image`, `glob`, `grep` | `tool-fs`, `tool-fs-search` | same sandbox boundary |
| `str_replace_editor` | `tool-str-replace-editor`, inserted by the face's policy layer (PLAN D9) | dsh-base 0.2.0 dropped the row; same sandbox boundary |
| `job_output`, `job_list`, `job_kill` | `tool-jobs` | a job outlives the turn that started it |
| `subagent`, `subagent_fork`, `send_message`, `interrupt_agent`, `list_agents` | `tool-subagent` (continuable), `tool-subagent-fork` (one-shot), `tool-subagent-control`, `tool-subagent-list-agents` (in-process spawn/fork) | a continuable child reaches its parent with `send_message`, delivered as an `agent-message` relay (0.1.1's `report` tool is gone); Gate 2's `tools.guard` is tree-wide, so a gated tool stays gated inside a subagent |
| `ralph` | `tool-ralph`, re-enabled by the policy layer (PLAN D9) | fresh-subagent iteration, up to 64 rounds per call; dsh-base 0.2.0 ships the row disabled |
| `todo_write`, `create_goal` / `get_goal` / `update_goal`, `workflow`, `exit_plan_mode` | `tool-todo`, `tool-goal`, `tool-workflow`, `plan-mode` | |
| `skill` | `tool-skill` + `skill-filesystem` | loads one `SKILL.md` by catalog name; the catalog (name + description) is what the model chooses from |
| `web_search` | `tool-web` (`fetch: false`, PLAN D6) over `web-search-deepseek` | outbound to `https://api.deepseek.com/anthropic/v1` with `DEEPSEEK_API_KEY`; no page fetch |
| `ask_user_question` | `tool-ask-user` (face overlay; the blocking `legacy` mode) | §4.3; the answer is model-visible, so not a gate |
| `mcp__alpaca-kit__*` | the operator's MCP row | §2.7 registration matrix |
| `mcp__akshare__*` | project `mcp-akshare` row | public A-share/other market queries, unguarded; check source errors and truncation |
| `agent_<bin>` | face `agents.ts` | roster-gated per channel (§6.5) |
| `dispatch` | face `room.ts` (`installRoom`) | Kairos's own: refused in any session whose header or `agentPreset` projection names a bot (§6.8) |

Not tools, but in the same prompt: a connected MCP server's `instructions` (the `mcp:akshare`
section, §3.1). The MCP resource tools and their prompt section are off by policy (PLAN D7).

### 3.7 The bot directory contract

`bots/<id>/` = `agent.cordis.yml` (GENERATED by `renderComposition`: two rows — the face-owned
`kairos-bot` plugin, named by the relative path `../../face/plugins/bot.js` and carrying
`persona` + `allow`, and `dsh-skill-filesystem` rooted at `./skills` with
`includeDefaultRoots: false`), `preset.yml` (`name`, `description`, optional `order` — what the
roster shows — and the face-only `model`), `SOUL.md` (the persona SOURCE the face copies into
the composition), `README.md` (the contract, for whoever opens the directory), `skills/` (the
bot's stance pack, `skills/<skill>/SKILL.md` with `name` + `description` frontmatter),
`journal/` (the only directory the bot may write, and its home session's cwd; its
`notes.md` is read into each of the bot's requests, `src/bot-journal.ts`). `bots/_template/` is
the copy source.

dsh 0.2.0 reads none of these files: its preset registry scans no directory. The face turns
each directory into a `PresetDefinition` (`definitionFor` in `src/bot-presets.ts`): `preset.yml`'s
`name`, `description` and `order`, read exactly as 0.1.1's dsh read them (trimmed, a blank value
omitted; an absent or malformed file is empty metadata and the bot still declares), and the
composition's rows REBASED onto the bot directory, because dsh resolves a preset's rows against
the declaring context's base (the profile directory), where 0.1.1 resolved them from the
preset's own. A `./`, `../` or absolute path row becomes an escaped absolute `file:` URL, a
`group: true` row rebases recursively, and a relative `customSkillDirs` entry of the
skill-filesystem row becomes `bots/<id>/…` — a behaviour change: 0.1.1 resolved `./skills`
against the process cwd, `face/`, so no bot ever scanned its own `skills/` (today those hold only
a README). `bots/kairos` is the static `preset-kairos` overlay row (§4.3), built by the same
`definitionFor`, so a missing or non-YAML `bots/kairos/agent.cordis.yml` refuses the compose.
Every other bot is declared by `declareBots` once the tree has settled (§4.1): activation is
eager, and a declaration at row time would mount `plugins/bot.js` before the MCP tools exist. A
composition the face cannot read (missing, unreadable, not YAML) is not declared — the reason,
with the file path, is logged and shown as `broken` on `/data/bots.json` — while a readable
non-list IS declared and the registry lists it broken in its own words.

The face is the only writer, and every write re-declares: a create, a settings save or a soul
save (`src/bots.ts`) rewrites the files, then `redeclare(id)` disposes the bot's declaration and
registers the new one before the route answers, serialized per id. Running conversations keep
the revision they joined; new ones get the saved files. A re-declaration that fails answers 500,
naming what was saved. There is no on-disk generation stamp — a revision is one declaration —
so a hand edit to `SOUL.md`, the composition or `skills/` reaches nothing until the next save
through the face or a restart.

Naming: the face keeps the retired dsh-agent-presets grammar `[a-z0-9][a-z0-9-]*`, bounded to 64
code points (`BOT_ID_RE`), as its own gate — dsh 0.2.0 asks only for a non-blank id; the display
name folds to a proposal through `proposeBotId` (`src/bots.ts`, twinned in `client/botId.js`) and
the field stays editable. `kairos` is refused by name (`RESERVED_IDS`), `_template` by the
grammar, which admits no leading underscore — both through `isBotId`. A soul carrying `{{` is
refused twice, at `rejectSoul` and again at the plugin's `validateBotConfig`: the system prompt
is a strict template with no escape.

State on 2026-09-30: eight directories are tracked. `bots/kairos` is the inert default — an empty
composition (`[]`) every session that names no preset joins, so Kairos's tools stay exactly the
host's — and `bots/_template` is the copy source, never declared and refused as an id.
`bots/drill-bull/` (看多派) and `bots/drill-bear/` (看空派) are the room drill's two voices, kept
as tracked fixtures with their channel `strategies/room-drill`; `news-scout` and the AQR room's
`aqr-data`, `aqr-method` and `aqr-audit` are the operator's own. A created bot is the
operator's to commit; the operator's tree holds untracked ones too.

`preset.yml` may carry one key beyond `name`, `description` and `order`: `model:
<provider>/<model>` (`MODEL_ROUTE_RE`, written by `renderPresetMeta`). It is **face-only**: a
preset definition carries no route, and the face copies only the three display keys into it.
The room engine resolves it per bot, once per room (`selectionFor` in `src/room.ts`), and falls
back to the tree's default route with a logged, model-visible note when the route is not one
`provider/model` pair or the tree does not serve it; a bot's HOME session takes it on its first
request (`src/bot-runtime.ts`).

A bot in a room gets a member session **per room** — one per (room, bot) pair, not one per bot.
Its header is the whole membership rule: `parentSession` = the room session, `agentPreset` = the
bot, `cwd` = the channel directory, and the `read-only` permission preset pinned inside creation
setup — on `setup(agentCtx, agent)`'s own agent, before the session is announced — so it is the
member's first permission fact and no create→set window exists. `src/room.ts` creates it
(`materializeMember`) and resumes it; nothing creates one by hand, and a session that only looks
like one is not a member (§9, R16).

---

## 4. Frontend: the face server (`face/src`)

Some 9,600 lines of TypeScript across 31 files, run directly by `tsx` — no build step, plus one
plain `.js` file outside `src/` (`face/plugins/bot.js`, §3.7 — a bot's composition names it by a
relative path the face rebases to an absolute `file:` URL, and it must import nothing). Pins:
`DSH_PIN = 0.2.0-rc.2` (every `@deepseek-ai/dsh-*` dependency, declared exactly and installed),
`CORDIS_PIN = 4.0.4` (`@deepseek-ai/cordis` rides its own 4.x track; the dsh packages peer it with
a tilde range) and `CORDIS_INCLUDE_PIN = 1.0.9` (the one cordis plugin the face imports itself);
all three are asserted by `tests/version.test.ts`, which also refuses the three package names
0.2.0 retired. `face/README.md` carries the run table, the profile rules, the instruments,
channels, the master rail, bots, the upgrade order, and the drills. Beside the server,
`face/scripts/` holds two operator tools — `check-home.ts`, the go-live dry run that boots the
face on a COPY of a harness home and read-opens every session (it refuses the live home by
device and inode, and a copy without its `DRY-RUN-COPY` marker), and `validate-fixture.mjs`
(`npm run check:fixture`, §6.7) — and, with `face/landing/`, the static product landing page
(`npm run build` → `face/dist/`) and its demo-asset tooling; nothing there runs in the face
process.

### 4.1 Boot sequence (`main.ts` → `boot.ts`)

`boot.ts` mirrors the dsh 0.2.0-rc.2 CLI's `runProfile` (the `@deepseek-ai/dsh` chunk
`lib/profile-boot-BZ2ZjNWi.js`, also published as `@deepseek-ai/dsh/profile-boot` — a reading
aid, not a dependency) with ten divergences, each stated in the file's header: no `--patch`
files; no `profileContext` (PLAN D1 — with it dsh-base's `settings` row would import and rename
the operator's shared `settings.yaml`, and `config-editor`, `plugin-manager` and `dsh-hmr` would
recompose the live tree from files that do not carry the face's layers); no proxy policy (PLAN
D10 — `installProxyFromEnvironment` would reroute the face's own quote and Alpaca fetches too);
no signal handlers, shutdown controller or fail-loud inside `bootFace`; `appReady` committed
last; the face's own `package.json` as the install anchor; a skipped bundle refused; a strict
row audit; and the policy layer.

1. Read `FACE_PORT` (default 3090) and `FACE_PROFILE` (default `face`) with `||`, so an empty
   export means the default rather than a moving port or the profiles root itself. Resolve the
   client directory module-relative.
2. **`process.chdir(<repo root>)`** before boot: `SessionController`, which replaced 0.1.1's
   `ApiProxyService`, takes every session's default project directory from `process.cwd()` and
   offers no config key, and dsh-base's `sandbox-policy.workspaceRoot` is `!!js process.cwd()`.
   The client directory, boot's `INSTALL_ANCHOR` and `data.ts`'s producer paths are
   module-relative; the channel root, the session-delete fence root and the panels' cwd are read
   from `process.cwd()` after this chdir, so they are the repo root only because of it.

   `process.cwd()` is only the *fallback* boundary. `dsh-sandbox-policy` resolves the writable
   root per call from the calling session's `cwd`: a channel session is fenced to
   `strategies/<name>/` (plus platform temp areas), and a write outside it — `alpaca_kit/`,
   another strategy, `docs/` — is denied and escalates to a card; a root session (`+ new` with
   no folder chosen) is fenced to the whole repo, where `data/pit/`, `dsh/skills/` and
   `alpaca_kit/` are all writable with no card (§9, R9).
3. Install SIGINT (exit 130) / SIGTERM (exit 0) handlers and app-boot's own `installFailLoud`,
   before the boot it guards. It covers `unhandledRejection` and `uncaughtException`, skips the
   rejections boot's startup audit already reported, prints one labelled diagnostic, releases
   the room engine, the data routes and the tree under a 2 s bound, and exits 1.
4. `bootFace({profileName, port, deferReady: true})`: dsh's layered env load
   (`$DSH_HOME/.env`, `<cwd>/.env`) → `composeFace`: resolve `$DSH_HOME`, load the profile
   anchored on the face's own `package.json` (a bundle `loadProfile` could not load is now
   skipped, not thrown — the face refuses the compose), **rewrite `<profile>/cordis.yml` to
   `[]`** (the loader's write-back would otherwise bake composed rows in and double every
   bundle insert next boot), stack the patches — bundle layers (`dsh-base`) → the face policy
   layer (§4.3) → project AKShare → the profile's `cordis.patch.yml` → the home's
   `cordis.patch.yml` → a caller's in-memory `extraPatches` (`main.ts` passes none;
   `scripts/check-home.ts` disables a home copy's MCP rows with it) — apply the guarded
   switches (`session-telemetry-otel` disabled when `DSH_TELEMETRY_DISABLED` is non-empty and
   the row is composed; `hmr` disabled whenever composed), patch Kairos's persona into
   `system-prompt` (`personaPrefix` only, §4.3), then push **the face overlay last**. This
   inverts the CLI's layering deliberately: loopback-only binding must survive an operator
   patch, so face rows win silently; the policy layer is the other way round and yields to an
   operator row with the same id.
5. Compute the runtime module resolution (`createRuntimeResolution`, anchored on
   `face/package.json`, pure) and boot. `prepare` provides the launch environment, installs
   `PluginPackages` with that resolution before any row imports — without it a fresh home
   resolves no dsh-base row, and it needs the native `node-addon-require-builtin` — and provides
   the command line (`args: []`) with the face's own `appReady`. Nothing writes
   `$DSH_HOME/profiles/node_modules` any more. A required dsh entry that does not activate
   throws dsh's `StartupError`, whose grouped diagnostic `main.ts` prints before exiting 1.
6. Audit the settled tree, disposing it and throwing on the first failure: **every enabled
   Loader entry ACTIVE** (dsh 0.2's own boot fails only on its required ids and merely warns on
   the rest; the face refuses a partial tree, naming each `id (package): state`); the services
   `approval`, `userQuestions`, `typertGateway` and `permissionPresets` present, each refusal
   naming its consequence; an ACTIVE `@deepseek-ai/dsh-api-remotes` entry — the answerer: a
   tree without it boots clean and passes every other check while every order is denied "no
   approval channel is available" and every question rejects `NO_PROVIDER`; and
   `ask_user_question` in the **live** tool registry (service and tool fail independently — that
   was the 2026-08-31 → 09-02 silent outage).
7. Audit Gate 2 (§4.7) — it was ARMED inside `prepare`, before any row mounted, by
   `armOrderGate`: two `hostCtx.inject` fibers, the guard waiting on `tools` and the prepended
   `tools/pre-execute` listener on `approval`, so both exist the moment their service does and
   re-arm exactly once if that service restarts. That is the tenth divergence, added 2026-09-30
   after a review proved the window it closes: dsh-base's `typert-gateway` activates DURING
   `boot()` and its unary `/api` is not readiness-gated (only the mux upgrade waits on
   `appReady`), so a slow row let `session/create` + `session/prompt` run, and an order tool
   dispatch, seconds before a post-boot registration existed (`order-gate-midboot-smoke` pins
   the closed window). The audit refuses the boot if either fiber is not ACTIVE, then runs
   `auditOrderTools` and logs `order gate armed for …` or refuses. A third
   outcome is silence: `dsh-mcp-client` defaults `failOnStartupError: false`, so an alpaca-kit
   child that cannot start (the row's `command` interpreter cannot `import alpaca_kit`, or the
   bed path is wrong) leaves the row ACTIVE and the tree healthy with no `mcp__alpaca-kit__*`
   tools, no `order gate armed` line and no error from the face — only `mcp-client(alpaca-kit):
   connection failed … no tools were registered` on stdout; reconnect exhaustion unregisters the
   tools for the life of the process. Check the plugin panel's tool list or that stdout line; the
   fix is the row's `command` and a restart.
8. The preset roster: the registry present and its default `kairos`; every other bot declared
   (`declareBots`, §3.7) — a bot that cannot be declared does not fail the boot, its reason is
   kept for `/data/bots.json`; the default listed and not broken; every declared bot listed. Log
   `agent presets: …` (with `N bot(s) not declared, see above` when a declaration failed).
9. `main.ts` mounts the routes (§4.4): `/` behind `ctx.connection.authorizeIndex`, `/market`,
   `/account`, `/client/*`; the `/data` producers, quotes and search; channel routes; session
   routes; bot routes (every save re-declares); the bot runtime; the room engine; and panel
   routes (awaited, because their registration runs `syncAgentTools`, so every connected agent
   that has an exec recipe — `claude`, `codex` — becomes an `agent_<bin>` tool before the face
   reports up; a connected bin without a recipe stays a roster row and gets no tool).
10. `booted.commitReady()`: only now does the gateway register `/api/remote.mux`. A tab still
    holding its 30-day cookie reconnects the moment the upgrade is admitted and must find every
    route mounted. It re-checks that the root is still active and throws otherwise — into
    `installFailLoud`, never a face that would not stream.
11. Print `kairos-face: http://<host>:<port>/?token=… (profile: …)` from the bound service —
    the per-process launch token that mints the browser cookie (§4.4) — then one line
    explaining it, and the room caps.

One `bootFace` per process: given a `dshHome` (as the tests do; `main.ts` passes none) it sets
`process.env.DSH_HOME` permanently, which is why the twelve real-boot tests live in separate
files. Without `deferReady` it commits `appReady` itself as its last step, which is what every
smoke that boots without `main.ts` relies on.

### 4.2 Module table

| File | Responsibility |
|---|---|
| `main.ts` | entry: chdir, signal handlers and `installFailLoud`, boot with `deferReady`, the sign-in route and every route family (the room engine and the bot runtime included), `commitReady`, the tokenized URL |
| `boot.ts` | the mirror of the dsh CLI's `runProfile` (§4.1): `composeFace`, the runtime resolution, the strict row audit, the required-service and answerer checks, `ask_user_question` in the live registry, Gate 2 registration, the preset-roster checks, `declareBots`, `commitReady` |
| `overlay.ts` | the twelve host rows `dsh-base` does not mount (§4.3), `satisfies`-checked against each plugin's own config type; `BOTS_ROOT`, `DEFAULT_PRESET`, `presetRowId` |
| `policy.ts` | the policy layer (§4.3): `POLICY_ID_PATCHES`, `POLICY_INSERTS`, `facePolicyPatches` — each row a PLAN decision; a missing target is reported on stderr, never skipped silently |
| `akshare.ts` | project AKShare MCP defaults, composed below operator profile/home patches |
| `orders.ts` | Gate 2 decision logic, pure: `isOrderTool`, `effectiveApprovalPolicy`, `orderApprovalDecision` (with the `displayReason` twin), `describeOrder`, `hasApprovalGrant`, `isGatedTool`, `orderGuardReason`, `orderGuardReasonForSession` (the guard's one producer; reads `snapshotEvents()`, a distinct denial for an unreadable log), `auditOrderTools`, `OPERATOR_GATED_MARKER` — depends on nothing (structural types only) |
| `setup.ts` | one-shot `$DSH_HOME/profiles/<name>` creation with `PATCH_HEADER`; refuses to overwrite |
| `http.ts` | `HttpError`, `readBody` (4,096 B cap → 413), the fixed `FORBIDDEN` body |
| `static.ts` | `/` behind `IndexAuth` (`ctx.connection.authorizeIndex`), `/market`, `/account`, `/client/*` with a traversal-safe resolver; the `RouteRegistrar` contract |
| `data.ts` | `/data/{market,account,watchlist}.json`: fixed-argv `execFile` of the producers, TTL cache, single-flight, stale-on-error; mounts the search and quote routes; **the trust fence every `/data` route reuses** |
| `watchlist.ts` | joins the watchlist producer's US snapshots with the reference-only search catalog |
| `quotes.ts`, `quote-snapshots.ts`, `quote-streams.ts`, `quote-types.ts` | the market watchlist's live quotes: `/data/quotes` (JSON) and `/data/quotes/stream` (server-sent events), one shared upstream subscription per provider (Alpaca stream and snapshots, Coinbase, iFinD), a bounded latest-value cache; no credential reaches the browser |
| `symbol-search.ts` | `/data/symbols/search`: on-demand instrument search (Tencent, Yahoo), a per-query memory cache, no market directory kept |
| `sessions.ts` | session delete (on disk, cwd-fenced to the repo; the header read from the highest canonical log generation, `pickGenerationLog`) and the reversible archive set with tombstones in `$DSH_HOME/face/archived.json` |
| `roster.ts` | `$DSH_HOME/face/channels.json`, the per-channel agent AND bot rosters: locked, atomic, fail-closed; `roster.log` append, one line kind per roster |
| `channels.ts` | channel = `strategies/<dir>` + workspace-registry identity; reconcile dirs ↔ registry ↔ sessions (durable and live heads, `{header}` snapshots at 0.2); `status.yaml` / `THESIS.md` / `journal.md` / `backtests/` readers; create-from-template; five routes — the overview answers `bots` (this channel's roster) and `allBots` (every preset dsh reports) beside the agent roster, and the listing's `presets` maps each session to its header's `agentPreset` (`presetHintsOf`) |
| `agents.ts` | exec recipes for `claude` and `codex` (fixed argv, prompt on stdin, scrubbed env, `--restricted` / `--sandbox read-only`), the spawn runner, the `agent_<bin>` tool with the roster check on execute, tool sync |
| `bots.ts` | bots = `bots/<id>/` directories: `isBotId`, `renderComposition` (the persona text written into the composition), `createBot`, `updateBotSettings`, `updateSoul`, `listBots` (dsh's roster and the face's declaration failures merged in, `broken`/`listed`); four routes, each save calling `onBotChanged` → `redeclare` |
| `bot-presets.ts` | bots as face-declared presets (§3.7): `definitionFor` (the rebased `PresetDefinition`), `declareBots` (after boot; `redeclare` serialized per id, `errors`, `ids`) |
| `bot-runtime.ts` | a bot HOME session's saved model route on its first request, the journal as a runtime-context snapshot on every request, and `/data/bots/runtime` (a live bot session's mounted persona, model and tools, or its last request's; never resumes one); reads the preset a session RUNS from the `agentPreset` projection (`sessionPresetReader`) |
| `bot-journal.ts` | a bounded, fresh read of one bot's own `journal/notes.md` (12 KiB); never writes |
| `room-rules.ts` | the room's pure rules: `ROOM_CAPS`, `resolveMentions` (by id, by one-token name), `finalTextOf` + `isPass`, `validateDispatch` (names the roster), `dispatchResultText` (names who was not called), `roomLinesOf` + `formatDelta` + `memberPrompt` (the attributed delta and the four standing rules), `roundEndText`, `parseModelRoute`; the `room` message-source vocabulary |
| `room-contract.ts` | the room's optional contracts: the structured `dispatch` brief (`BRIEF_SCHEMA`, bounded) and a member's view block, with the discussion summary; plain prose stays valid |
| `room-projection.ts` | the `room` projection unit: a pure fold of the known events that carry room facts (`dispatch` calls and their `role:'tool'` results, room-sourced messages, turn boundaries) into `{kind, round, members, organizing}`; zod schemas; `stateVersion` (`ROOM_STATE_VERSION` 2) |
| `room.ts` | the engine on the root context: `installRoom` (the `dispatch` tool, the unit, the bus); `RoomEngine` — members created with `ctx.agents.create` (`parentSession`, `agentPreset`, the model ref, `read-only` pinned inside `setup(agentCtx, agent)`) or resumed, and a member whose log dsh 0.2 cannot open is a `failed` turn naming the legacy format, never a crashed round or a silent fresh member; logs read through `eventsOf` (`snapshotEvents()`), failing closed without it; a cold room resumed through `sessionController.resolveAgent`; `driveTurn` with the extending deadline and the hard-cap cancel (`keepInbox`); rounds parallel/serial, peer continuations, the three caps, `settled`/`capped`/`superseded`; answers appended to a quiet room log, the round-end `followup`; `say` (the operator's `@`), `describe`; two routes |
| `persona.ts` | Kairos's deployment persona (`personaPrefix`): `readPersona` validates the strict `{{}}` template and refuses the boot on a bad file |
| `plugins/bot.js` | the `kairos-bot` composition plugin: a scoped `deployment:persona-prefix` section (shadows Kairos's prefix; no suffix) + an allow-list `tools.restrict`, re-expanded after each burst of `tools/change` — coalesced to one timer turn, so a tool that registers after the declaration is admitted when the allow list names it (`expandAllow` resolves `mcp__*__<raw>` against the live tree); dependency-free |
| `panels.ts` | the master rail's feeds: host facts (`/data/host.json`), the local-agent roster (probe, auth, connect, disconnect), memory (skills), plugins (loader rows + tool schemas); builds `PanelDeps` (it requires `skills`, `tools`, `loader`, `workspaceRegistry` and `agents`), whose `channelFor` answers `{workspaceId, name, dir}` — the `dir` is what the room engine gives a member as its `cwd` |
| `version.ts` | the three pins |

The smokes share one client for the host's wire, `tests/remote.ts`: `mountClient(ctx)` mounts
the real `/` (a bare `bootFace` mounts no page), `signIn` trades the launch token for the cookie,
`remote` / `remoteResult` call `POST /api/<ns>/<method>` with it.

### 4.3 The overlay rows and the policy layer

Twelve rows, composed last, winning silently over the operator's patch and the home layer —
`faceOverlay(port, definitionFor(bots, "kairos"))`, in this order:

| Row | Package | Why the face mounts it |
|---|---|---|
| `webserver` | `dsh-host-webserver` | `127.0.0.1:<port>`, `compression: none` — loopback-only is the contract |
| `connection` | `dsh-client-connection` | `trustedHosts: []`: the `/api` Host/Origin fence and, since 0.2.0, the browser sign-in (§4.4); its first activation on a home writes the cookie's signing secret into `$DSH_HOME/.credentials.yaml` |
| `api-remotes` | `dsh-api-remotes` | the gateway's only `$events` source: forwards `approval/request` and `user-questions/request` to every connected browser; without it every approval resolves `unavailable` — boot refuses (§4.1) |
| `file-upload` | `dsh-client-file-upload` | provides `fileUploads`, which the session controller hard-injects |
| `workspace` | `dsh-workspace` | the workspace registry the channels, attach and archive run on (§6.4) |
| `session-controller` | `dsh-api-session-controller` | the `session/*` Remotes and the in-process `sessionController` the room engine resumes cold rooms through |
| `workspace-controller` | `dsh-api-workspace-controller` | the `workspace/*` and `directoryPicker/*` Remotes |
| `settings-controller` | `dsh-api-settings-controller` | `credentials/describe`; its `settings/describe` has no service without `profileContext`, and the client does not call it |
| `directory-picker` | `dsh-host-directory-picker-auto` | the native folder dialog; since 0.2.0 it fails the row when either of its two runtime entries cannot load, hence the four picker packages in `package.json` |
| `tool-ask-user` | `dsh-tool-ask-user` | the model-facing half of `userQuestions`, in no upstream bundle; configless = the blocking `legacy` mode |
| `agent-preset-registry` | `dsh-agent-preset-registry` | `{default: kairos}`. The registry scans no directory and serves only `list`, `read` and `select` Remotes, so 0.1.1's `trust: system` posture — no authoring RPCs over a git-tracked directory — holds with nothing to configure |
| `preset-kairos` | `dsh-agent-preset` | the default preset, static so it exists before the first `session/create`: `bots/kairos` through `definitionFor` — the host composition itself, `plugins: []` |

Gone from the overlay since 0.1.1: `storage`, `storage-json`, `storage-domain` and
`session-projection-cache` — dsh-base mounts all four, so a patch in the profile file now
REACHES them (a same-id insert here would silently replace base's row and swallow that patch);
`api-gateway` (`dsh-host-apiproxy`, deleted upstream: dsh-base's `typert-gateway` serves `/api`
and the three controller rows carry its business methods); `cordis-host-runner` (its consumers
are not mounted); `agent-presets` (deleted: presets are declarations, §3.7). Web-app's
agent-plane disable set is deliberately not followed: Kairos keeps dsh-base's flat host roster.
A patch of the operator's aimed at an overlay row is accepted, overridden, and never reported
(`PATCH_HEADER` says so where the operator looks); a patch matching no row is also silent —
hence the `rows.has(…)` guards around the switches.

**The persona patch** is `composeFace`'s, not an overlay row: it restates `system-prompt`'s
config as the layers below left it and sets `personaPrefix` from `dsh/profile/persona.md`
(section `deployment:persona-prefix`, order 0 — 0.1.1's `persona`, renamed without moving; the
face sets no suffix), so an operator's `includeRuntimeContext`, `includeHarnessIdentity`,
`personaSuffix` or `toolOrder` on that row survives.

**The policy layer** (`src/policy.ts`) composes directly above the bundle layer and BELOW
AKShare, the profile and the home, so an operator row with the same id wins — the opposite of
the overlay, on purpose: these are defaults, not the face's contract. Each row restores a 0.1.1
posture dsh-base 0.2.0 changed, and each is an operator decision (§4.8):

| PLAN | Row(s) | Policy | dsh-base 0.2.0 on its own |
|---|---|---|---|
| D3 telemetry | `session-telemetry-otel` | disabled | `FEEDBACK_ONLY`: a session-log prefix uploaded after `/feedback`, with `.anonymous-user-id` |
| D4 session-log upload | `session-log-deepseek` | disabled | up to 8 MiB of session events on every DeepSeek request |
| D5 package inventory | `plugin-package-inventory-deepseek` | disabled | the active package list on every DeepSeek request |
| D6 `web_fetch` | `tool-web` `{fetch: false, searchTimeoutMs: 60000}`, `web` `{searchProvider: deepseek-official}`, `web-fetch-http` disabled | 0.1.1's values, each config restated whole | `web_fetch` on |
| D7 MCP resource tools | `mcp-resources` | disabled | three model-facing tools and a prompt section |
| D9 `ralph` | `tool-ralph` | `disabled: false`, base config kept | disabled |
| D9 `str_replace_editor` | `tool-str-replace-editor` | inserted, configless (0.1.1's 16,000-character cap is now the default) | row removed |

`facePolicyPatches` guards every id patch on the row being in the bundle composition and
reports a missing target on stderr (`kairos-face: warning: policy D…`); `tests/policy.test.ts`
pins every target against the installed dsh-base. Overriding one is a row in
`profiles/face/cordis.patch.yml`: `- id: session-log-deepseek` / `disabled: false` restores the
upload; `web_fetch` takes `- id: tool-web` / `config: { fetch: true, searchTimeoutMs: 60000 }`
plus re-enabling `web-fetch-http` and restating `web` with `fetchProvider: http`.
`DSH_TELEMETRY_DISABLED` still wins over an operator's telemetry re-enable: its patch composes
after the operator layers. Outside the layer, and undecided (PLAN D18): dsh-base's spill budget
moved from `maxInlineBytes: 50000` to `maxInlineTokens: 12500` (§9, R27).

### 4.4 Route table

All face routes register on dsh's webserver as `exact` or `prefix`; a duplicate `(kind, path)`
throws, and the fallback seat is left empty. dsh's own surface is the `connection` row's
`prefix /api` — the Typert gateway's unary Remotes, `POST /api/<ns>/<method>`, and the gate
answer `POST /api/$events/result` — and the upgrade seat `/api/remote.mux`, which the gateway
registers only once `appReady` commits (§4.1). Both pass Connection's admission: the Host/Origin
fence (403: a loopback `Host`, and a same-origin `Origin` when one is sent), then the signed
browser-session cookie (401). The cookie — `dsh-auth-<hash of the authority>`, `HttpOnly;
SameSite=Strict; Path=/`, 30 days, bound to the exact `host:port`, so `127.0.0.1:3090` and
`localhost:3090` are two sign-ins — is minted in one place: `GET /?token=<launch token>`
through `authorizeIndex`, answered `303 ./` + `Set-Cookie`. The launch token is new on every
start and appears only in the printed URL; the signing secret persists in
`$DSH_HOME/.credentials.yaml`, so a cookie outlives restarts.

**The fence** (`isTrustedDataRequest`, every `/data` route): loopback `Host` (`localhost`,
`127.x.x.x`, `[::1]`; missing or unparsable → refuse) AND `Sec-Fetch-Site ≠ cross-site` AND
(`Origin` absent OR its host equals `Host`). Refusal is the fixed `FORBIDDEN` string, echoing
nothing. `/data` takes no cookie (PLAN D8). POST shells add 405 for other methods, 415 for a
non-JSON content type, 400 for an unparsable body (the sessions and panels shells also 400 a
valid-JSON non-object; the channels shell reads one as `{}` and answers by route: 404 `no such
channel`, or 400 `invalid channel name`), 413 over 4,096 bytes. A request with no `Origin`
passes on `Host` alone — `curl` works, which is residual R3 in §9.

| Route | Module | Does |
|---|---|---|
| `GET /` | `static.ts` | the sign-in and the chat page: `authorizeIndex` first — a valid `?token=` is answered `303 ./` with the cookie, a cookie gets `index.html`, anything else a 401, and on a refusal the face writes nothing itself |
| `/market`, `/account`; `/client/*` | `static.ts` | pages and assets; public (PLAN D8), no cache headers; path containment on the resolved absolute path |
| `GET /data/account.json`, `/data/market.json`, `/data/watchlist.json` | `data.ts` | fence first, then cache, then spawn `$FACE_PYTHON` on the producer from the repo root (account: `face_data.py account`, 30 s, 60 s TTL; market: `face_data.py market`, 600 s, 15 min; watchlist: `face_watchlist.py`, 30 s, 15 min, joined with the reference catalog); single-flight; a later failure re-serves the last good payload flagged `stale:true`; with nothing to fall back on, 503 carrying the producer's own `{ok:false}` when it wrote one, the fixed `producer failed` when it exited 0 with no output, or `producer spawn failed` + the error code (`ENOENT`, `null` for a timeout kill, an exit number) — **never the child's error text**, which carries stderr and possibly keys. Only the account page reads its route; `market.json` and `watchlist.json` remain for compatibility since the market watchlist replaced the market instrument |
| `GET /data/symbols/search?q=&market=` | `symbol-search.ts` | instrument search across the Tencent and Yahoo endpoints, cached per query in memory |
| `GET /data/quotes?ids=`, `/data/quotes/stream?ids=` | `quotes.ts` | the selected ids' live quotes (at most 100), as JSON or as server-sent events; empty selections reach no upstream |
| `GET /data/channels.json` | `channels.ts` | **reconciles on every GET**: registry `create` per directory, `attachSession`, `seedRoster`; returns `{root, channels, ungrouped, archived, presets}` — `presets` maps a session id to its header's `agentPreset`, the client's fallback where a 0.2 list row names none |
| `POST /data/channels/overview` `{workspaceId}` | `channels.ts` | reconcile + `status.yaml`, thesis, the whole journal newest-first (the client folds entries past five), backtests newest-first with the newest dated one parsed as `latest`, file list, roster |
| `POST /data/channels/agents` `{workspaceId, agents[]}` | `channels.ts` | `setRoster` → `channels.json` (409 on a corrupt file), then a dated line to `roster.log` and stdout |
| `POST /data/channels/bots` `{workspaceId, bots[]}` | `channels.ts` | `setBots` → `channels.json` (`bots[]` beside `agents[]`; 400 an id outside the bot grammar or more than `ROOM_CAPS.maxMembers` ids, 404 no such channel, 409 a corrupt file), then a dated `bots` line to `roster.log`. The overview answers `bots` (the roster) and `allBots` (every preset dsh reports, `broken` reasons included) |
| `POST /data/channels` `{name}` | `channels.ts` | `NAME_RE` + NFC; copies `_template` (409 if exists); a reconcile failure after the copy is a warning, not a 500 — the directory exists and a 500 would make the retry 409 |
| `GET /data/sessions-meta.json`; `POST /data/sessions/archive`, `/delete` | `sessions.ts` | the archive set (409 on un-archiving a host-archived id: the face does not un-archive host archives, PLAN D14 — the host can, but a host-archived session runs no model step until restored); delete reads the session header's `cwd` from the first zstd frame of the highest canonical log generation (`session.v4.jsonl.zstd` over a 0.1.1 `session.jsonl.zstd`; `.zstd` wins a tie; the lock and temps never count) and `rm -rf`s **only if it is inside the repo root** (ids are unique across every project under `$DSH_HOME/sessions`); an unreadable header is a 404, never "safe" |
| `GET /data/host.json` | `panels.ts` | `{cwd, home, attachedSessions, version}`: the host facts 0.1.1's `host.describe` gave (dsh 0.2 has no such Remote); `version` is `DSH_PIN` |
| `GET /data/memory.json`, `POST /data/memory/skill` | `panels.ts` | the skill catalog grouped by pack; one skill's content |
| `GET /data/plugins.json` | `panels.ts` | loader rows with their phase (config never serialized) + `mcp__*` / `agent_*` tool schemas |
| `GET /data/agents.json`; `POST /data/agents/connect`, `/disconnect`, `/rescan` | `panels.ts` | probe fifteen known CLIs (`--version` 3 s, auth 10 s, 60 s cache); connect writes `agents.json` and registers `agent_<bin>` live; disconnect disposes it |
| `GET /data/bots.json` | `bots.ts` | every directory under `bots/` in the id grammar, `listBots` merging dsh's roster and the face's declaration failures in: `broken` carries dsh's reason or the face's, `listed:false` marks a directory the roster did not report |
| `POST /data/bots` `{name?, id?, description?, soul?, model?}` | `bots.ts` | `createBot`: id = the one given or `proposeBotId(name)`; copies `_template` and writes `preset.yml`, `SOUL.md` and the rendered composition, then re-declares. 400 an id outside the grammar or reserved, 400 a soul carrying `{{` or empty, 409 the directory exists (never overwritten), 500 `_template` missing. The returned row reads `listed:false` — it is built without the roster, which is re-read on the next GET |
| `POST /data/bots/settings` `{id, name?, description?, model?, soul?, revision?}` | `bots.ts` | `updateBotSettings`: a partial update — every value validated and every file staged before any is replaced, 409 when `revision` is not the saved one — then re-declares |
| `POST /data/bots/soul` `{id, soul}` | `bots.ts` | the older soul route, through the same update. All three POSTs take a 64 KiB body cap, not the shared 4,096 B — a soul is prose — and answer 500 `bots/<id> was saved, but the running face could not re-declare it …` when the re-declaration fails |
| `GET /data/bots/runtime?id=&sessionId=` | `bot-runtime.ts` | an attached bot session's mounted persona, model, tools, skills and journal snapshot (the last request's facts while a turn runs); a cold one is reported unattached, never resumed |
| `POST /data/rooms/say` `{sessionId, text}` | `room.ts` | the operator's `@`: mentions resolved against the roster (by id, by one-token display name); nobody named → `addressed: []` and the client sends an ordinary prompt; else the message is appended to the room as the operator's own (never a prompt), a cold room is resumed through `sessionController.resolveAgent` — the host's own composition, model selection and preset join — and each named member turns. 400 a bad id or empty text, 404 not in a channel or `session/not-found`, 409 a corrupt roster or any other resolve failure, with dsh's code and message and, when the log predates dsh 0.2, the legacy-format note |
| `POST /data/rooms/state` `{sessionId}` | `room.ts` | the roster, the members the engine drove this boot, the caps left; never resumes |

### 4.5 Persistent state the face writes

| Path | Writer | Note |
|---|---|---|
| `$DSH_HOME/profiles/<profile>/cordis.yml` | `composeFace` | rewritten to `[]` every boot; edit `cordis.patch.yml` |
| `$DSH_HOME/profiles/<profile>/{package.json, cordis.patch.yml, pnpm-workspace.yaml}` | `setupFaceProfile` | only when the profile *directory* is absent; an existing directory is left untouched even if one of the three files is missing |
| `$DSH_HOME/.credentials.yaml` | the `connection` row the face mounts | a `client-connection/browser-session` grant — the cookie's signing secret — written by the first boot on a home; the 0.1.1 CLI still reads the file's keys past it |
| `$DSH_HOME/storages/**` | dsh-base's storage rows | workspace registry records (`registry.create`, `attachSession`) |
| `$DSH_HOME/storages/session_projcache/sessions/<id>.json` | dsh-base's projection cache | one checkpoint record per session, written behind the log and throttled by `writeEveryEvents: 200` / `writeIntervalMs: 5000`; what `session/list` reads for a cold session's projections; bootstrapped once from 0.1.1's single `session_projcache.json`, which stays in place |
| `$DSH_HOME/sessions/<slug>/<id>/session.v4.jsonl.zstd`, `session.lock` | dsh's session persistence | published by a session's first WRITE-open under 0.2.0 — a prompt, a command, a fork, a room turn, any resume — beside a 0.1.1 `session.jsonl.zstd`, which stays byte-identical; never rolled back. A read-open migrates in memory and writes nothing, and opening a cold session in the chat pages it without activating it (§5.4) |
| `$DSH_HOME/face/archived.json` | `sessions.ts` | `{archived[], deleted[]}`; plain write |
| `$DSH_HOME/face/channels.json` | `roster.ts` | `{version:1, channels:{<wsId>:{agents[], bots[]}}}`; file lock + atomic write, mode 0600; the one file that needs a cross-process lock because the reconcile writes on GET |
| `$DSH_HOME/face/roster.log` | `roster.ts` | append-only, one dated line per operator roster write |
| `$DSH_HOME/face/agents.json` | `panels.ts` | `{connected:[{bin,label}]}` |
| `$DSH_HOME/sessions/<slug>/<id>/` | `deleteSession` | removed with every generation, the lock and the temps, cwd-fenced |
| `strategies/<name>/` | `createChannel` | copied from `_template`, never overwritten |
| `bots/<id>/` | `createBot`, `updateBotSettings`, `updateSoul` | copied from `_template`; `preset.yml`, `SOUL.md` and the composition's persona row rewritten together, staged then renamed; never overwritten by create |
| `bots/<id>/journal/` | a bot's HOME session | workspace-write, cwd = the journal; the only directory a bot writes (the write to `../SOUL.md` is refused, proven in `room-smoke`) |
| `dsh/profile/persona.md` | the operator | not written by the face — read by `composeFace` into `system-prompt`'s `personaPrefix`, and a malformed template refuses the boot |
| `data/.face_cache` | the producer, not the face | |

Not written any more: `$DSH_HOME/profiles/node_modules`, 0.1.1's module link farm (a stale one
answers only for a row outside the face's closure, §3.1; PLAN D13). Never written by the face:
`$DSH_HOME/settings.yaml` (PLAN D1).

Deleting a session does **not** detach it from its channel: `deleteSession` removes the
persistence directory and tombstones the id but never touches the registry, although in-process
the workspace entity does expose one (`WorkspaceEntity.detachSession`, reachable through
`ctx.workspaceRegistry.list()`; not a registry method, not a Remote, and not declared by the
face's `WorkspaceLike`). Recorded, not fixed.

### 4.6 Environment

| Variable | Read by | Default | Effect |
|---|---|---|---|
| `FACE_PORT` | `main.ts` | `3090` | `"0"` asks the OS; `""` means default |
| `FACE_PROFILE` | `main.ts`, `setup.ts` | `face` | honored by both `setup` and `start` |
| `FACE_PYTHON` | `data.ts` | `python3` | the producers' interpreter; must `import alpaca_kit` |
| `FACE_AKSHARE_MCP_COMMAND` | `akshare.ts` | `~/.local/bin/akshare-mcp` | the AKShare server's executable |
| `FACE_IFIND_POLL_MS`, `IFIND_ACCESS_TOKEN`, `IFIND_REFRESH_TOKEN`, `ALPHA_DATA_FEED` | the quote routes | `30000`, —, —, `iex` | the watchlist's live quotes (`face/README.md`, "Market credentials") |
| `DSH_HOME` | `main.ts`, `boot.ts`, `sessions.ts`, `panels.ts` and dsh itself via `resolveDshHome`; `setup.ts` reads it raw (`?? ~/.dsh`) | `~/.dsh` | written by `bootFace` when a test passes an override; `resolveDshHome` treats an empty or whitespace value as unset and expands `~`, `setup.ts` does neither, so such a value sends `setup` and `start` to different homes |
| `DSH_TELEMETRY_DISABLED` | `boot.ts` | unset | any non-empty value (`0`, `false` included) disables the telemetry row, and its patch composes after the operator layers, so it wins over an operator's re-enable; the policy layer disables the row by default anyway |
| `DSH_PERMISSION_MODE` | dsh, not the face | `workspace-write` | `danger-full-access` sets approval policy `never`: it disarms the sandbox-escalation card but **not** Gate 2, which then denies in its own words |
| `ALPACA_KIT_ENABLE_ORDERS` | the MCP child only | unset | Gate 1; the face cannot read it and consults the tool registry instead |
| `FACE_SMOKE` | tests | unset | `=1` enables the twelve real-boot tests |
| `DEEPSEEK_API_KEY`, `APCA_API_KEY_ID`, `APCA_API_SECRET_KEY` | dsh's credential seam; the producers and the quote routes; the MCP row | — | not auto-loaded from the repo's `.env.*` files |

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
`face/src/orders.ts` is that producer, armed by `boot.ts`'s `armOrderGate` inside boot's
`prepare` — before any row mounts, each half on its own `hostCtx.inject` fiber — in two parts,
because neither alone suffices:

1. A **`tools/pre-execute` listener**, registered `prepend` so it is outermost in the waterfall
   and an inner listener cannot swallow its answer. Non-order tools pass through. For
   `place_order` / `cancel_order` — matched on the **raw name suffix**
   (`name === raw || name.endsWith("__" + raw)`), so an operator renaming the MCP server row
   cannot slip a tool past, while the read-only `orders` listing is never matched — it returns
   `{kind:"ask", reason:"PAPER order - <tool>: side=… qty=… symbol=… …", displayReason:{en: <the
   same line>}}` under policy `ask` (`describeOrder`: `key=value` pairs, values capped at 40
   characters, unknown keys appended). The approval request carries no arguments — only the
   tool name, the call id, `reason` and `displayReason` — and `api-remotes` forwards it to every
   connected browser's `$events` stream as an `approval/request` waterfall keyed by `eventId`.
   The card shows the tool name, the order line and two buttons; an upstream-style panel draws
   `displayReason` instead of `reason`, so both carry the line, and the order details reach the
   human only if they are inside it. Under policy `never` (`danger-full-access`, or a runtime
   preset switch) it returns **`deny`** in its own words rather than `ask`, because dsh would
   otherwise render the false `the user rejected tool …` when nobody was asked. No `approval`
   service or no session → deny. (`PreToolDecision` is stated structurally, widened with 0.2:
   `deny.info`, `cancel`, `ask.displayReason`.)
2. A **`tools.guard`**, deny-only and evaluated on *every* allow, including the allow that
   `allowed-once` becomes. It asks the calling session's **event log** — not "did my listener
   see this call" — for an `approval/asked` carrying this exact `callId` **and this tool's
   name** paired with an `approval/decided` whose outcome is `allowed-once`. A sighting is not a
   grant; only the log is. The log is read through `snapshotEvents()`, and only for a gated tool
   (a snapshot copies the whole log): 0.2.0 removed the `events` getter this guard used to read,
   the read went `undefined` without a word, and every approved order was denied. An UNREADABLE
   log — no `snapshotEvents`, a throw, a non-list — is denied with its own sentence,
   `cannot read this session's log to verify an allowed-once approval (dsh Session API changed:
   …)`, never with the "without a logged allowed-once approval" one; `orderGuardReasonForSession`
   is the one producer of both. The guard reads the tool's *live* description (MCP servers can
   register after boot) and denies any `mcp__*` tool carrying `(operator-gated)` that the gate
   cannot name, with a fix hint.
3. A **boot audit**: if any `mcp__*` tool is marked `(operator-gated)` but not name-matched, the
   face disposes the tree and throws — a gate that covers nothing must not look healthy. Boot
   also refuses a tree with no ACTIVE `api-remotes` entry (§4.1), without which every ask
   resolves `unavailable` and every order is denied at once, with no card anywhere.

Consequences worth knowing: a card with no connected browser **blocks**, it does not deny —
the gateway holds the request and replays it, same `eventId`, to the next `$events` client;
grants are one-shot (`allowed-once`, no allow-always); `cancel_order` is gated identically, so
under policy `never` the risk-reducing action is refused too; and the gate binds only when dsh
runs inside the face — a dsh tree composed without the face has Gate 1 alone. The answer is the
browser's `POST /api/$events/result` under its `$events` clientId (§5.2); the host would accept
any outcome of the approval vocabulary from a client, so keeping the operator to
`allowed-once` / `rejected` is `client/api.js`'s job. **It is a gate, not containment** (§9,
R2), and the log proves a grant was recorded, not who recorded it (§9, R3a). Drill status is in
§7.4: the refusing half and the admitting half are automated on a real tree, the admitting half
through the real `$events` channel too; the human half has not been run.

### 4.8 The re-host's operator decisions

The dsh 0.2.0-rc.2 re-host (2026-09-30) defaulted every decision that changes what Kairos can
do, what leaves the machine, or which operator data survives; each stays the operator's. The
numbers are the re-host plan's, which the code comments cite as `PLAN D<n>`. The go-live runbook
(`docs/superpowers/runbooks/2026-09-30-dsh-0.2.0-rc.2-go-live.md`, §4) walks each one that
needs an answer before the operator's home moves.

| PLAN | Decision | Default in the tree | To choose otherwise |
|---|---|---|---|
| D1 | a `profileContext` (settings forms, a live model save, `dsh-hmr`, `plugin-manager`) | none (§4.1) | a code change: every face layer moves into `profileContext.overlays`, and the first boot imports and renames the shared `settings.yaml` |
| D2 | Kairos's default model | dsh-base's `deepseek-official/deepseek-flash` until the operator adds the `agent-default-model` row (§3.1) | that row in `profiles/face/cordis.patch.yml` |
| D3–D7, D9 | telemetry, session-log upload, package inventory, `web_fetch`, MCP resource tools, `ralph` and `str_replace_editor` | the 0.1.1 posture (§4.3) | one operator row each |
| D8 | the browser cookie on `/data`, `/market`, `/account` | fence-only, as at 0.1.1 | a code change behind `isTrustedDataRequest` (Connection's `requestRejection`) |
| D10 | an HTTP proxy policy | none: the face's own fetches go direct; children still inherit proxy variables | a code change (`installProxyFromEnvironment`), which reroutes every fetch |
| D11 | the ten 0.1.1 room sessions the 0.2 migration refuses | left on disk and reported, never rewritten (§9, R20) | archive them in the face, or rewrite COPIES — never the originals — to a source kind the migration admits |
| D12 | the 0.1.1 global CLI and the 0.1.1 face on the shared home | never again once 0.2.0 has written it: 0.1.1 re-heals its link farm, forks history away from `session.v4`, and on its next workspace write detaches every 0.2-born session from its channel in `workspace.json`; a full restore of the backup is the only rollback | upgrade the CLI (its first run imports `settings.yaml` into its OWN profile) or give 0.1.1 tools their own `DSH_HOME` |
| D13 | `$DSH_HOME/profiles/node_modules` | delete once D12 holds | keep it: a mixed-version hazard for any row outside the face's closure |
| D14 | un-archiving host archives | refused with a 409 naming why (§4.4) | route it to `workspaceRegistry.unarchiveSession` |
| D15 | telemetry opt-in | the policy row off; `DSH_TELEMETRY_DISABLED` still works | `- id: session-telemetry-otel` / `disabled: false` |
| D16 | opening a cold session in the chat | page-only, never activating (§5.4) | follow on open, as the upstream client does — every browsed session then gets a v4 log and a lock |
| D17 | three subagent children with a version-2 descriptor and one log with a sequence gap, unreadable under 0.2 | left on disk and reported, like D11 (§9, R20) | export their transcripts while a 0.1.1 face can still render them, or wait for an upstream migration edge |
| D18 | the spill budget | dsh-base's `maxInlineTokens: 12500` (§9, R27) | one row restating `spill-policy`; about 4,200 tokens restores the old CJK budget and spills ASCII three times earlier |

---

## 5. Frontend: the browser client (`face/client`)

Some 8,900 lines across 25 ES modules served from `/client`, no bundler, no framework. Every string
from the host lands via `textContent`; the only two `innerHTML` writes are constant SVG icon
literals (`navigation.js`, `market.js`).

### 5.1 Pages and files

| File | Role |
|---|---|
| `index.html` | the chat app shell: master rail (strategy / agent / memory / plugin), sidebar (brand, `+ new`, conversation list, panels), main pane (topbar, transcript, detail view, composer). Holds not one byte of host data |
| `market.html`, `account.html` | the two instruments' frames; each built entirely by its script |
| `api.js` | the wire (§5.2): `call(endpoint, args)` — one unary Remote; `openMux({onReady, onEvent, onGate, onGateGone, onDown})` — the one reconnecting `/api/remote.mux` socket, with `stream()` and `answer()`; `randomUuid()` for the prompt's `requestId` |
| `mapper.js` | pure frame → view-model (`bubble`, `card`, `approval`, `question`, `gate-resolved`, `pulse`, `projection`, `room-line`, `subagent-message`, `turn`, `ignore`); shapes pinned to dsh 0.2.0-rc.2 (the gateway's gate frames, the session controller's follow records and projections, v4 session events), and every 0.1.1 shape maps to `ignore`, so a stale host renders nothing rather than something half-right. Four of those views are the room's: a member's answer becomes a `bubble` with `role: "bot"` carrying `bot` and `name`, a round end becomes a `room-line`, a turn boundary becomes a `turn` (for every session, not only the one on screen), and the operator's `@` stays an operator bubble carrying `mention` |
| `summaries.js` | `summaryOf(row, presets)`: restores `agentPreset` on a `session/list` row — the projection value first, `/data/channels.json`'s header hint second, never a guess (0.2's summary no longer carries the field, and the sidebar buckets, the member fold, the speaker and the gate attribution all read it) |
| `chat.js` | the impure half: sessions sidebar, transcript, composer, gates, rail panels, detail pane, strategy picker, channel page glue, the bot settings and inspection pages, the subagent dock; how the session on screen is read (`activeView`, §5.4); and the room: the participants strip (`renderStrip`, refetched by `loadRoomInfo`), a member's gate rendered inline in its room (`gateWho`), members folded under their room row, the members' follows, and the composer's `@` path |
| `member-traces.js` | a room answer's process, read from the member session through `session/projections` + `session/page` — never activating it |
| `subagents.js` | temporary subagents: `composeSubagentCatalog` builds 0.1.1's catalog shape from the parent's `subagentCatalog` projection and the list rows (0.2 has no catalog Remote), and `normalizeSubagentCatalog` and the dock's decisions run on it unchanged |
| `answer-traces.js` | the closed 思考轨迹 disclosure shared by Kairos's and a member's answers |
| `render.js` | pretty renderers for alpaca-kit tool results; returns null unless both tool and payload shape are recognised, so the raw `<pre>` is always kept |
| `markdown.js` | DOM-built markdown for Kairos bubbles (inline emphasis, code, links; headings, nested lists, GFM tables, fences, quotes, rules) |
| `channels.js` | the channel landing page, assembly only — every judgement is made server-side; the **bots in this channel** chips (one per bot dsh reports, `on` when the roster carries it, `broken` with its reason as the title, plus a removable chip for a rostered id no directory answers to) |
| `grouping.js`, `channelName.js`, `botId.js` | sidebar buckets keyed by `workspaceId` (never title) or by `bot:<id>`; the whitespace → dash fold; the display-name → bot-id fold |
| `botSettings.js` | the bot settings page's pure translations: the `provider/model` route grammar, the payload, the model choices from `session/modelCatalog` |
| `room.js` | the pure room rules: `foldMembers` (the membership fold — a bot session parented by a host session, no `origin`), `isMemberSession`, `stripChips` (the strip's chips and their state precedence), `avatarGlyph`, `isMentionText` (the composer anchor), `roundEndLine`, `gateSpeaker` |
| `speaker.js` | the name the transcript writes over a turn: `speakerFor(summary, bots)` reads the session's `agentPreset` — a rostered bot's display name, its id when the roster has none, `Kairos` for the host and for no session. Per session, never per message; an unknown preset falls to the id, never to the host |
| `navigation.js` | the primary navigation rail shared by the chat, market and account pages |
| `market.js`, `market-model.js`, `market-search.js`, `market-quotes.js`, `market-catalog.js` | the market watchlist: selections kept in this browser's `localStorage`, on-demand search (`/data/symbols/search`), live quotes over server-sent events with a polling fallback (`/data/quotes/stream`, `/data/quotes`), a reference catalog of identities (never prices) |
| `account.js`, `account-view.js`, `account-model.js` | the read-only paper account dashboard over `/data/account.json` |
| `chat.css`; `market.css`, `account.css` | one sheet shared by all three pages — every color a `:root` token (radii only about half — four `--r-*` tokens, the rest literal px); light only — plus each instrument's own |

`speakerFor` and `botOf` read the same field, so the label over a turn and the sidebar bucket it
files under can never disagree. `chat.js` holds the answer in one module-level `speaker`, set by
`setSpeaker` before anything renders for a session — `openSession` (before the window is drawn),
`send` (from the `session/create` answer, which still carries `agentPreset`) and `openBotHome`
(armed, before a session exists) — and reset at the three other sites that clear
`pendingAgentPreset`: `newSession`, the strategy picker's row, and a channel page's new round.
`refreshSessions` re-derives it for the active session from every `session/list` that lands
(each row through `summaryOf`), which is what makes the label survive a reconnect and what turns
a bare id into a bot's name once `loadBotIndex` answers; the drawn window fills the preset from
its own snapshot when the list does not name one, and `openSession` leaves the label alone when
it reopens the session already on screen and the list carries no row for it. Four surfaces read
the answer: the `who` element over an assistant bubble (`bubbleNode`), the ask card's head
(`questionNode`) and the status pulse (`pulse`) read `speaker` as they render, and `setSpeaker`
rewrites the composer placeholder, the one naming surface already on screen when the voice
changes.

`bucketFor` orders its buckets archived → bot → channel → ungrouped, so a session whose
`agentPreset` names a bot files under that bot even when its cwd is a channel directory. Not
reachable from the client as built — `openBotHome` is the only caller that sets `agentPreset`,
and it always sets `cwd` to the bot's journal — but the precedence is written down rather than
relied on.

### 5.2 Wire contracts

The client speaks dsh 0.2.0-rc.2's Typert Remote wire through `api.js`; 0.1.1's apiproxy wire
(`POST /api/<dotted.method>`, `POST /api/respond`, the downlink-only `/api/events.mux`) was
deleted upstream, and `call` refuses a dotted name before any fetch. Every `/api` request and the
mux upgrade carry the browser cookie (§4.4) with no code of the page's; a 401 is reported as
"not signed in — open the URL kairos-face printed".

**Unary** — `call(endpoint, args)`: `POST /api/<ns>/<method>` with
`{type:"client-request", rpcId, method:"<ns>/<method>", payload:{args}}` — the method repeats the
path, the payload is exactly `{args}`, and `content-type: application/json` is load-bearing (the
host 415s anything else). The answer is `{type:"server-response", rpcId, result:{ok:true,
value?}}` or `{ok:false, error:{code, message, details}}`; `call` checks the echoed `rpcId`,
resolves the value, and rejects with the host's `code` (`session/not-found`,
`gateway/arguments-invalid`, …) or the HTTP `status`. Every wire parameter
is sent (`{_request:{}}`, `{request:{…}}`): an unknown top-level key is
`gateway/arguments-invalid`. The Remotes the client uses: `session/list`; `session/create`
(`{workspaceId}`, `{cwd}`, or neither — the host then uses its default project directory, the
repo root; never both; `agentPreset` rides beside `cwd` when the prompt opens a bot's home
session); `session/prompt` (`mode:"queue"`, a client-minted `requestId` — a retry with the same id
is admitted once — content parts, client time zone); `commands/execute` (a slash line, which
0.1.1's prompt ran itself; `undefined` — no command claims the line — falls back to a prompt);
`session/cancel`, `session/rename`, `session/fork`; `session/projections` and `session/page`,
the two non-activating reads; `session/modelCatalog` (the agent panel's model, provider and
effort, and the bot settings' model choices); `subagents/prompt` and
`subagents/interruptByParent`; `workspace/rename`; `directoryPicker/pick`;
`credentials/describe` for the three key names. The agent panel's host facts are the face's own
`/data/host.json`. The surface is closed by design: `session/selectModel`, `agentPresets/*` and
`settings/describe` are not called.

**Streams** — one WebSocket, `/api/remote.mux`, carries any number of logical streams keyed by a
client-chosen `streamId`: client frames `open` / `cancel`, host frames `item` / `end` / `error`,
exact keys. Three kinds ride it:
- `$events`, internal to `api.js`, one per socket generation and opened with exactly `{args:{}}`:
  `ready` first (the `clientId` every answer is bound to, and the host's `home`), then `emit`
  (host facts: `api-session/added|removed|status|activity|error`, `agent-preset/selected`),
  `waterfall` (an `approval/request` or a `user-questions/request` waiting on the operator:
  `{event, eventId, agentId, request}` — `agentId` is the session id; `request` carries the tool
  name, call id, `reason` and `displayReason`, or the questions) and `cancel` (that wait is over;
  it carries no outcome). Any other waterfall is handed straight back with `next`. Every pending
  gate is replayed, same `eventId`, right after each `ready`.
- `session/control`: a `baseline` of every attached session's projections, then `projection`
  frames — `tokenUsage`, `contextPressure`, `title`, the `room` unit's whole value,
  `subagentCatalog` and the rest.
- `session/follow`: one session's transcript — a `snapshot` (header, cursor, the tail window of
  records, projections), then gap-free `event` records and, when opened with
  `assistantStream: true`, `assistant-stream` frames whose `block-start` chunks are the pulses
  (0.2.0 logs no `assistant/chunk`). A follow item names no session; the caller re-addresses it.

**Reconnect** — there is no resume cursor. A socket close, a frame outside the stream grammar,
and an `$events` end, error or non-`ready` opening all lose the generation the same way: `onDown`
runs while only the lost socket exists (the chat suspends there every follow a re-open could
promote), a fixed 1.5 s later a new socket re-opens every registered stream under fresh ids
(`$events` first), and `onReady` re-fetches the list. A follow the host itself ends is re-decided
by the page 2 s later — followed if the session is live, paged if not — never blindly re-followed.

**Answering a gate** — `mux.answer(eventId, value)` POSTs `$events/result`
`{clientId, eventId, outcome:{kind:"result", value}}` under the CURRENT generation's clientId: an
approval with the bare `"allowed-once"` or `"rejected"` (the host itself would take any value of
the approval vocabulary, so `api.js` is where `cancelled` and `unavailable` stay host-side), a
question with `{answers:[…]}`, the whole batch. The host answers a settled or undelivered gate
with a silent `ok`, so `api.js` tracks the gates each generation was delivered and refuses:
`not-ready` (no clientId yet), `not-pending` (this connection does not hold the gate),
`gate-gone` (withdrawn while the answer was in flight), `bad-value`. A `cancel` that lands after
this tab's answer resolved means the answer lost a race — the host never cancels the winner — and
is reported too (the last 64 answered ids per generation are remembered). A gate not replayed
within 1 s of a reconnect's `ready` was settled while the page was away and is retired; `chat.js`
backstops at 4 s.

**Approval card flow** — `$events` `waterfall` → `mapFrame` (`approval {id: eventId, sessionId:
agentId, toolName, callId, reason, displayReason}`) → `acceptGate`, routed AROUND the transcript
queue so a pending transcript read can never hide a card; stored across sessions, a card for
another session becomes a `waiting` chip on that sidebar row → the card renders an `approval`
kind label beside the tool name (two spans, no separator glyph; the ids — `eventId · callId` — sit
in a `raw` tooltip), the `displayReason` line (and the audit `reason` too when the two differ),
and exactly two buttons → click disables, `answer`, settle. The card's end states:
`answered · approve|deny` (this tab's answer was taken); `closed` (withdrawn, and nobody here
answered — the `cancel` frame has no outcome); `closed · no longer pending` (this connection does
not hold it: answered elsewhere, withdrawn, or settled while disconnected); `closed · settled
elsewhere` (this answer lost a race and was not applied). A question card settles the same way.
For Gate 2 the line is the whole order description; no drill yet proves the card is readable by
a human (§7.4).

**Room routes** — `/data/rooms/say` is called **before** `session/prompt` whenever the composer's
text carries `(^|\s)@` and the session is in a channel; an answer of `addressed: []` means the text
named nobody on the roster and it goes out as an ordinary prompt instead. `/data/rooms/state` is
called on session open (before the gate replay, so a member's gate is attributed), on a new
session's first prompt, when the channel page's bot roster changes, and when no session is
selected (which hides the strip).

**`/data` routes** — fence only, no cookie. The account page fetches `/data/account.json` on load
and on `refresh` (button disabled in flight) and marks a re-served payload stale; the market page
reads `/data/symbols/search` and `/data/quotes/stream`, with `/data/quotes` as its polling
fallback. Only the sidebar list is re-polled, trailing-edge 1.2 s after its triggers: the
`$events` facts `api-session/added|removed|status|activity` and `agent-preset/selected`, the
followed session's turn frames, a control-stream `title` the list does not show yet,
`subagentCatalog` / `subagent` projection cuts, and every gate settlement (which may render
nothing — another session's gate — but must rebuild the row's `waiting` chip).

### 5.3 Rendering pipeline

Frame → `acceptFrame` (queued while the opening window of the session on screen is loading) →
`mapFrame` → dispatch: pulses to the status line and an ephemeral `◐ thinking…` row;
projections into a per-session store (token usage, context pressure, title, the `room` value),
seeded by the control stream's baseline and a window's snapshot — a `cached` list block is never
seeded (its watermark is not comparable), though the sidebar still reads its title off the row;
a `sessionId:seq` set dedupes. Gates bypass the queue (`onGate` → `acceptGate`, `onGateGone` →
`acceptGateResolved`): their cards are drawn after the window of the session on screen, and
still drawn when that window fails to load. Then `honourSurfaceOp` — a compaction checkpoint's
`startSeq`/`endSeq`, mapped to `{op:"replace", start, end}`, removes every rendered node in that
seq range — then bubble or card.

The opening window — a follow's snapshot or a page — is drawn by one `applySnapshot`: records
re-addressed as `session/event` frames, projections seeded, the preset filled from the snapshot
when the list lacks it, then room info, the subagent catalog and the session's pending gates. A
later window REPLACES the drawn one — a follow re-opened after a reconnect, or a paged session
that came alive — as upstream's journal stream does and as 0.1.1's refetch did, never a second
copy. Pulses and turn boundaries of the room's MEMBER sessions come from one `session/follow`
(`maxMessages: 1`, the assistant stream) per LIVE member of the room on screen
(`agentAvailable`), opened from list refreshes, `api-session/added` and the room projection's
members; a member not followed gets `thinking` from `api-session/status running`. A cold member
is never followed: that would activate it. A `user/message` whose source is `room`/`answer`
renders in the bot's own voice, `room`/`round-end` as a room line, and `room`/`delta` (in a
member's own session) as a `context · room` row; a child's `send_message` (an `agent-message`
relay) renders as its report line, and in a child's transcript a parent's relay renders as
父会话消息 with a way back, not as a report.

Operator text renders verbatim; injected user-role events from a plugin, tool or model become a
collapsed `context · <source>` row; Kairos bubbles get an optional collapsed `think` row and
DOM-built markdown (a bubble with headings, tables or fences widens to `doc`); an interrupted
answer is cut-marked, never shown complete. `tool/call` opens a collapsed card indexed by
`callId`, titled by its `bash` command or else the tool name (host presenters no longer reach the
client); `tool/result` — a `role:'tool'` message — fills the same node: pretty renderer when both
tool and shape are recognised (`market_snapshot` table, `daily_bars` SVG with volume and
crosshair, calendar, breadth tiles and an account key-value grid — one flat-object renderer,
tiles up to eight fields, a grid beyond — generic eight-column tables), raw `<pre>` always
appended, `.danger` on error, spill-elided results salvaged row by row with a `truncated` note.

### 5.4 State

In memory: the active session and how it is read — `activeView`, one of two modes:
- `follow`: a LIVE ordinary session, and every subagent child (a subagent address is never
  promoted), through its `session/follow` with the assistant stream;
- `page`: a COLD ordinary session, through one non-activating `session/projections` +
  `session/page` read — 0.1.1's read-only history window. Following it instead would promote it:
  the Agent resumes, and a resume write-opens the log, publishing `session.v4.jsonl.zstd` and
  taking `session.lock` irreversibly for a session the operator only looked at (PLAN D16).

A paged session becomes a follow when this tab writes to it (a prompt, a command, an `@`), when
`api-session/added` reports it live, or when a list refresh shows `agentAvailable`; a list
refresh never downgrades a live follow; `api-session/removed` stops following and keeps the
window; a socket drop suspends every follow a re-open could promote, and `onReady` re-decides
each from the fresh list. A new session is followed before its first prompt is sent, since a
follow is the only way a transcript reaches the page. Beside it: the members' follows, the
seen/seq/card indexes, the gate map (all sessions) with each generation's deliveries, the
projection store, the channel index, the archived/deleted sets, generation tokens for list /
open / detail. `localStorage` holds exactly one key for the chat page, `face.collapsed-groups`
(bucket keys; legacy title-keyed entries dropped by a UUID regex; every access in try/catch), and
the market page keeps its own, `kairos.market.watchlist.v1`. A reload restores only those — the
transcript comes back from the host on the next open, and the pending gates on the new `$events`
generation. Archive/delete metadata lives host-side so it survives any browser.

### 5.5 Styling

Light only: no `prefers-color-scheme`, no `data-theme`; the media queries are
`prefers-reduced-motion` and a few narrow-width layouts. Two type stacks, `--sans` and
`--mono` — the prototypes' three-voice rule (mono for machine fact, serif for argued prose, sans
for the operator) did not carry into the live sheet, so Kairos prose renders in sans. The R4
palette is overridden lower in the file by the 2026-09-01 neutral-grey + blue-accent block, which
also adds the chart tokens. The market and account pages style themselves in `market.css` and
`account.css` (`body.market-body`, `body.account-body`); the `.inst-*` rules still in `chat.css`,
including the gate strip drawn as a circuit, belong to the retired instrument pages and no page
uses them. Client assets carry **no cache headers**: hard-reload after any client edit, or you
drill a stale `chat.js` (two false drill failures came from exactly that).

---

## 6. Paths end to end

**6.1 A paper order.** Operator arms Gate 1 in the home copy of the MCP row (flag + keys) →
the MCP child registers `place_order` with `(operator-gated)` in its description → the face's
boot audit name-matches it and logs `order gate armed` → Kairos calls it → the prepended
listener returns `ask` naming the order (`reason`, and the same line as `displayReason`) → dsh's
`ApprovalService` logs `approval/asked{callId}` and runs the `approval/request` waterfall →
`api-remotes` forwards it to every connected browser's `$events` stream, keyed by `eventId` (no
browser: it waits, and is replayed to the next one) → the operator answers; the page POSTs
`$events/result` → `approval/decided{outcome}` is logged and every other tab holding the card
gets `cancel` → the guard reads the log through `snapshotEvents()` and admits the call only on a
logged `allowed-once` for that `callId` and tool → `TradingClient.place_order` →
`_require_paper` → `POST /v2/orders` on the paper host. Deny: the model reads `the user rejected
tool "…"` and the card never reached the broker. Under `danger-full-access` the listener denies
outright.

**6.2 A dated market read.** In a backtest: `replay_days` yields `(day, GuardedSource)`; a
read for a later date raises `LookaheadError`. Through MCP: the tool builds
`GuardedSource(source, AsOfGuard(as_of or today))`, and for `screen` the guard check precedes
the cache read so a cached answer can never bypass it. The instrument producers take the same
path, and a spy test proves every raw read has a matching guard read.

**6.3 An instrument read.** Browser → `GET /data/account.json` → fence → memory cache (60 s) →
single-flight spawn of `face_data.py account` (30 s budget: the three read calls and the real
`gate_state`) → JSON → served; a later producer failure re-serves the last good payload as
`stale: true`, which the page marks. The legacy `/data/market.json` — no page reads it since the
market watchlist replaced that instrument — takes the same path with a 600 s budget, a 15-minute
memory cache and the producer's own disk cache under `data/.face_cache` (cold assembly ~284 s
measured; warm under a second), and serves two stamps: `assembled_at` (when the bed walk ran;
every disk-cache hit carries the same value) and `generated_at` (when the producer last ran).

**6.4 A channel listing.** Browser → `GET /data/channels.json` → the repo root first (always
a channel, named `workbench`, `isRoot: true`, listed even when `strategies/` does not exist),
then walk `strategies/*` (directories only, skipping `_template`, dot- and `__`-prefixed) → for
each directory, `registry.create` (create-or-reuse by real path) → attach every session whose
header `cwd` is that directory (persisted ∪ live, live wins) → seed a roster entry if absent
(inside the file lock) → report missing directories rather than deleting channels →
`{channels, ungrouped, archived, presets}`, `presets` naming each session's header preset for
the client's `summaryOf`.

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

**6.6 The loopback fence and the sign-in.** `webserver` binds `127.0.0.1`; `connection` trusts
no extra hosts; every `/data` route and dsh's `/api` refuse a non-loopback `Host`, a cross-site
fetch, or a mismatched `Origin` (403). `/` and `/api` then want the browser cookie (401): `/`
mints it from the printed token, `/api` and the mux upgrade check it. `/data`, `/market`,
`/account` and `/client/*` stay fence-only (PLAN D8). The fence is a reachability policy, not
authentication (§9, R3); the cookie authenticates only as far as its signing secret is out of
reach, and a shell turn can read the file that holds it (§9, R3a).

**6.7 Pins and upgrades.** Bump `DSH_PIN`, `CORDIS_PIN` and `CORDIS_INCLUDE_PIN` together with
`package.json` (every dsh package exact; the cordis peers are tilde ranges, `~4.0.4`); `npm
install` → `npm test` → `npm run typecheck` (it checks the dependencies' `.d.ts` too,
`skipLibCheck: false`) → re-diff `boot.ts` against the CLI's `profile-boot` chunk (at 0.2.0-rc.2
`lib/profile-boot-BZ2ZjNWi.js`, also published as `@deepseek-ai/dsh/profile-boot`) and let
`tests/policy.test.ts` re-pin every policy target against the new dsh-base → re-check the frame
shapes — `client/api.js`, `client/mapper.js` and the hand-kept `tests/fixtures/events.jsonl` —
against the gateway's `stream-protocol`, `api-remotes`' event list, the session controller's
`types` and the user-approval and user-questions request types, in their installed
`lib/types/*.d.ts` (there is no generator; correct the fixture by hand, then `npm run
check:fixture` validates every line it can against the installed dsh's own acceptance code —
the session controller's `assertSessionWireEvent`, the gateway's frame parser and `$events` id
predicates; on 2026-09-30, 23 of 26 lines validated, 0 rejected, and the 3 with no upstream
validator named) → `FACE_SMOKE=1 npm test` — the twelve real boots, `order-gate-smoke` and
`client-mux-smoke` above all, are the contract the structural `*Like` types cannot be → the
drills. `cordis-plugin-include` is pinned; `loader` and `group` arrive as app-boot peers and
`timer` through dsh-base, held by the lockfile alone; `cordis-plugin-hmr` is gone.

**6.8 A room round.** Operator checks two bots into a channel (`POST /data/channels/bots` →
`channels.json` `bots[]`) → asks a question in a channel session → Kairos calls `dispatch` with
a brief (`tool/call`) → the engine refuses a session whose header or `agentPreset` projection
names a bot, validates against the roster, starts the round and returns at once (`tool/result`
naming who was not called) → per bot: find the member session (the room log's record of it,
then the persisted `{header}` snapshots) or create it (`ctx.agents.create`, `parentSession` =
the room, `agentPreset` = the bot; the model ref, the preset join and the `read-only` pin inside
`setup(agentCtx, agent)`; attached to the channel workspace) — a member session dsh 0.2 cannot
open is that member's `failed` turn, named in the round-end text and on the console, and the
round goes on → `followup` the delta prompt (its `messageIds` are the member's cursor, in its
own log) → await that turn's `turn/end` under the extending deadline (a pending gate, read off
the member's log, holds it open) → final text after the last tool result; empty or `(pass)` →
`passed`; an error → `failed` → an answer is appended to the room log while no Kairos turn is
open (else held until its `turn/end`) → peer `@`s queue continuations (≤ 2) → round end: every
held answer flushed, then ONE `followup` naming who answered and who passed → Kairos's synthesis
turn. A cold room the operator `@`s is resumed through `sessionController.resolveAgent`, the
host's own composition. Every step is a known event; the `room` projection folds them; the
client renders each answer in the bot's voice as it lands and the strip from the projection plus
the pulses of each LIVE member's own `session/follow`.

---

## 7. Tests and drills

### 7.1 Commands that work

| Command | From | Needs | Measured 2026-09-30 |
|---|---|---|---|
| `python -m pytest` | repo root | nothing — offline, no keys, no bed | 381 passed in a clean checkout, ~2 s (the operator's tree adds the untracked `tests/strategies/`) |
| `cd face && npm test` | `face/` | nothing — no port, no key | 654 tests, 642 pass, 12 skipped |
| `cd face && npm run typecheck` | `face/` | | clean, the dependencies' `.d.ts` included (`skipLibCheck: false`) |
| `cd face && FACE_SMOKE=1 npm test` | `face/` | boots twelve real trees into `mkdtemp` homes and binds ports; still no LLM or key (four of the smokes also create, and remove, a gitignored `.bots-smoke-*` bots root at the repo root) | the twelve skipped tests; 654/654, ~12 s |
| `cd face && npm run check:fixture` | `face/` | the installed dsh | 26 fixture lines: 23 validated, 0 rejected, 3 with no upstream validator |

### 7.2 The Python suite

381 tests in a clean checkout: `tests/data/` (the data layer — Protocol, guard, Alpaca
normalization, PIT store, snapshot source, registry, composite, EDGAR, FINRA, float, capture and
checksums), `tests/features/`, `tests/kit/` (MCP tools, server, cache, trading host, replay),
`tests/universe/`, and the root files (the instrument producer, the watchlist producer,
integrity, the firewall meta-gate, capture wiring). The operator's tree adds `tests/strategies/`
(12 tests on 2026-09-09, untracked alongside the untracked `strategies/市场情绪/` it loads by file
path; a tree with the tests but not the strategy fails collection there rather than skipping).
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

654 tests in 56 files (642 pass, 12 skipped without `FACE_SMOKE=1`), run by `node --test`
through `tsx`:

- **Composition and boot** — `boot` (the layer order ending with the overlay; the policy layer
  between bundle and AKShare; the storage chain and projection cache composed once, from
  dsh-base, and reachable by an operator patch; the persona patch setting `personaPrefix` and
  keeping the operator's other `system-prompt` keys; a skipped bundle refused; the static
  `preset-kairos` row equal to `definitionFor(bots, "kairos")`, and a missing default composition
  refused), `overlay` (exactly the twelve rows, in order; loopback config; the rows dsh-base owns
  now and the retired ones never inserted), `policy` (every target a row the installed dsh-base
  composes; the composed posture; an operator row overriding a default;
  `DSH_TELEMETRY_DISABLED` winning over an operator re-enable), `setup`, `static` (`/` asks the
  index gate first and writes nothing on a refusal; the instrument pages and `/client` never
  consult it), `version` (the three pins, the retired names), `persona` (cross-checked against
  the installed strict renderer), `check-home` (the go-live dry run's pieces, offline: the
  live-home refusal by device and inode — through a symlink, in another letter case, inside or
  above the home — and the marker; the refusal classes; the multi-frame log reader; the inventory
  diff; the MCP row walk; the `extraPatches` seam composing after the operator's layers and
  before the face's own).
- **Gate 2** — `orders` (pure gate logic: raw and minted names, renamed server caught, read-only
  listing not gated, deny under `never`, one-shot grants for this `callId` and tool only, marker
  only on `mcp__` tools, the `displayReason` twin, the widened decision type, and
  `orderGuardReasonForSession`'s distinct denial for a session whose log cannot be read — the
  0.1.1 `{events}` shape with a real grant among them), `order-gate` (offline: a session without
  `snapshotEvents` denied with that distinct reason).
- **The client's wire and pure halves** — `api` (the unary envelope and its failures, dotted
  names refused before fetch, `randomUuid`; the mux: `$events` first with exactly `{args:{}}`,
  every reconnect re-opening every stream under new ids, a `cancel` after reconnect naming the
  current id, `onDown` running before the next socket exists, gates answered only under the
  generation that holds them, the refusal codes, a late `cancel` reporting a lost race, retirement
  of unreplayed gates, an `$events` failure losing the generation), `mapper` (against
  `tests/fixtures/events.jsonl`, rewritten to the v4 wire and checked against upstream's
  `assertSessionWireEvent`: every 0.1.1 shape maps to `ignore`; the room's views — a member's
  answer as a bot bubble, the round-end line, the operator's `@`, a member's delta, a turn
  boundary for a session not on screen; gate frames by `eventId`; tool titles from the call;
  `agent-message` relays), `summaries`, `member-traces`, `subagents` (including `chat.js`'s
  controllers — the composer's follow before the first prompt, the two view modes, gates across
  reconnects, a failed open still drawing its gates — in a vm harness), `room-client`,
  `answer-traces`, `speaker`, `grouping`, `channelName`, `botId`, `bot-settings-client`, and
  the instrument pages' `market-model`, `market-quotes`, `market-search`, `account-model`.
- **Server modules** — `channels` (the `presets` hints among the rest), `panels`
  (`/data/host.json`), `data`, `http`, `sessions` (`pickGenerationLog`; a v4-only session
  deleted and fenced; a migrated v0 + v4 directory decided by the v4 header; a lock-and-temps
  directory never deletable; the host-archive 409), `roster`, `agents`, `bots`, `bot-presets`
  (the rebasing of every shipped bot onto the real `face/plugins/bot.js` and its own `skills/`;
  `preset.yml` read as 0.1.1 read it; `declareBots` never declaring `_template` or `kairos`;
  `redeclare` disposing before registering, following the disk, serialized; the root's disposal
  taking every declaration with it), `bot-plugin` (the persona-prefix slot, a late tool admitted,
  the mask shrinking and re-admitting, a failed re-expansion contained), `bot-journal`,
  `quotes`, `quote-snapshots`, `quote-streams`, `symbol-search`, and the room suites below.
- **The twelve `FACE_SMOKE` boots**, below.

The room suites are `room-rules` (the caps block verbatim, `AGENTS.md`'s caps sentence pinned to
`ROOM_CAPS`, mention resolution, `isPass`, `finalTextOf`, dispatch validation and its two result
texts, the delta and the member prompt, the round-end text, the model route), `room-contract`,
`room-projection` (each fold in isolation, a refused `dispatch` restoring exactly what it
displaced, an `@` folded into an open round, the schema accepting every state the fold produces,
0.1.1's tool-result wrapper neither settling nor rolling back a dispatch), `room-engine` —
against a fake tree held to the engine's contract (`room-fake.ts`, in dsh 0.2's shapes: a
scriptable agent per member, `setup(agentCtx, agent)`, `snapshotEvents()`, `{header}`
snapshots, `sessionController.resolveAgent`, a manual clock, a root `session/event` bus)
covering member creation with the read-only pin in force at publication and refusal when it does
not take, `Context.agent` never read, resume-not-recreate, a legacy member session as a failed
turn while the other voice answers, a reader-less session failing closed, parallel isolation and
serial accumulation, continuations bounded to one turn per member per round, the three caps,
`settled` / `capped` / `superseded`, the deadline that extends while a member runs or has a gate
open and the hard cap that cancels with `keepInbox`, an `@` queued behind a running turn, the
cold-room resume and its 404/409 mapping, a re-selected session refused `dispatch`, and the two
routes under the fence — and `room-client` (the header fold, the strip and its state
precedence, the glyph, the mention anchor, the round-end line, the gate speaker).

The twelve boots each own a file, because `bootFace` sets `process.env.DSH_HOME` for good, and
each speaks the browser's wire through `tests/remote.ts` (`mountClient`, `signIn`, `remote`):

- `smoke.test.ts` — the sign-in (`/` 401 without the cookie, the token's 303 and `dsh-auth-*`
  cookie, the page with it), `session/list` over the Remote wire, `/api` 401 without the cookie,
  a forged `Host` 403 even WITH a valid cookie (the fence runs first; sent through `node:http`,
  because `fetch` silently drops a forged `Host`), the mux upgrade refused before `commitReady()`
  and then 401 without / 101 with the cookie, `/data` fence-only, the stub producer; the Gate-2
  answer channel end to end — two signed-in `$events` tabs, a real `approval/request` reaching
  both, `$events/result` from one settling `allowed-once`, `cancel` to the other, the grant in
  `snapshotEvents()`; and the live tree itself: zero inactive entries, `str_replace_editor` and
  `ralph` registered, `web_fetch` and the three MCP resource tools not.
- `order-gate.test.ts`'s real-tree case — fires `tools/pre-execute` at `mcp__drill__place_order`
  with a bare session so the real approval service's policy lookup runs: `ask` with a decidable
  reason, `cancel_order` asked, `orders` allowed, an agentless call denied, a renamed server
  still caught, `bash` and `ask_user_question` left alone; then the guard through the registry's
  real `execute` path — a tool marked `(operator-gated)` registered after boot, which the
  listener does not claim, comes back `isError` naming `ORDER_RAW_NAMES` with its body never run,
  and a session without `snapshotEvents` is denied with the distinct reason.
- `order-gate-smoke.test.ts` — Gate 2's positive path: a stand-in answerer on
  `approval/request` → the real `ApprovalService` → the logged `approval/asked` /
  `approval/decided` pair → the guard reading it → the body RAN for `allowed-once` and did not
  for `rejected` (`the user rejected tool "…"`); then, the stand-in removed, the real browser
  channel — two `$events` streams on one cookie-admitted socket, `$events/result`, the body
  running, `cancel` to the other stream.
- `order-gate-midboot-smoke.test.ts` — the window a 2026-09-30 review proved and `armOrderGate`
  closed: a fixture row (`tests/fixtures/midboot-slow-row.js`) holds `boot()` open on a latch
  while a second fixture row registers a marked `mcp__drill__place_order` stand-in as soon as
  `tools` exists; with `bootFace` still pending and unary `/api` already serving
  `session/create`, the order call is HELD with `approval/asked` logged and its body not run, an
  agentless call is denied by the listener, and a marked tool with an unrecognised name is
  denied by the guard alone; after the latch releases, the held card reaches the first `$events`
  tab and `allowed-once` dispatches exactly once; a restart of the real `approval` row re-arms the
  listener exactly once (outermost again); after dispose no `tools/pre-execute` record remains.
- `client-mux-smoke.test.ts` — the page's own `client/api.js` and `client/mapper.js`,
  unmodified, against a booted face: `ready` and `host.home`, the envelope and business codes,
  `api-session/added`, the control baseline, a follow snapshot mapped raw and normalized alike, a
  real approval answered through `answer()`, the gap-free tail, a rejection, a second tab's
  `cancel` and `not-pending`, a Stop that withdraws a gate, a question answered with its batch, a
  gate replayed to a late tab, the non-activating `session/projections` + `session/page` reads,
  and a follow `cancel()`.
- `askuser-noclient-smoke.test.ts` (S7) — an agent-scoped `ask` with no client BLOCKS (it
  parks until the caller aborts); an agentless one rejects `NO_PROVIDER`. Prints one `observed:`
  line.
- `bots-smoke.test.ts` — roster listing with a broken fixture and never `_template`; the
  header's `agentPreset`; mask = allow ∩ tree, and a tool registered after the declaration
  admitted by the re-expansion; the persona shadow; the inert default's tool set equal to the
  host's; the SHIPPED relative plugin path rebased onto the real `face/plugins/bot.js` — its bots
  root is `mkdtemp`'d inside the repository as `.bots-smoke-*`, gitignored and removed in
  `finally` — beside an absolute one; **Gate 2 from a bot session**, both outcomes (a bot whose
  own mask NAMES the `mcp__drill__submit_order` stand-in still meets the tree-wide guard, and
  `mcp__drill__place_order` fired with that bot's agent returns `ask` with the symbol on the
  card, so the refusal cannot be credited to the mask); a `session/create` naming the broken
  preset refused with dsh's own `agent-preset` error.
- `bot-runtime-smoke.test.ts` — a saved bot route reaching the real model request without
  moving the host default (set by the profile's `agent-default-model` row, since nothing saves
  one); a save re-declaring, so an old conversation keeps its soul and a new one gets the saved
  one; the journal as a runtime-context snapshot.
- `bot-sandbox-smoke.test.ts` (S4) — a `read-only` session's write refused inside the tool's
  content, the command having run (§9, R10). Prints one `observed:` line.
- `room-smoke.test.ts` — a stub model route, three bots in a temp channel, one operator prompt
  → Kairos dispatches all three in parallel → alpha answers, beta passes, gamma's model fails →
  the answer is on the room log before the round-end wake, the wake is one turn, Kairos's
  synthesis is in it; every member is parented, preset-joined, `read-only` as its only
  `permission/preset` before its first turn, carries the channel's `AGENTS.md` chain and lacks
  `dispatch`; the `room` value rides the session row and the per-record cache file; an `@` turns
  alpha, whose write into the channel is refused inside the tool content (D12) and never woke
  Kairos; a home session writes its journal and is refused on `../SOUL.md`.
- `room-discussion-smoke.test.ts` — the structured brief and member views, and each bot's
  journal, through the real request and log path; a member's persona is its own soul.
- `subagents-smoke.test.ts` — the native subagent lifecycle through the Remotes the page uses:
  the catalog composed from the parent's `subagentCatalog` projection and `session/list`,
  history as `session/page` on a subagent address, `subagents/prompt` and
  `subagents/interruptByParent`, a continuable child's `send_message` arriving as an
  `agent-message` relay, the slash-namespaced `subagent/*` errors.

The drills use `mcp__drill__*` stand-ins so `ALPACA_KIT_ENABLE_ORDERS` is never armed.

### 7.4 Drills (`face/README.md`)

The live browser drills below ran on dsh 0.1.1-rc.2. At 0.2.0-rc.2 their automated halves pass
(2026-09-30), and a first live pass ran the same day on a face at `8f0dedb` booted against a
SCRATCH `DSH_HOME` with the operator's `mcp-alpaca-kit` row, AKShare and a real model (never the
operator's home): the tokenized sign-in and the 401 without it; a new conversation streaming
its reply without a sidebar click; the approval channel's deny half (card with `displayReason`
and `reason` → `answered · deny` → the command did not run); a restart with the page open — the
old tab reconnected, the cookie survived (the plain URL loaded), the redrawn window carried no
duplicate bubbles, and the session stayed cold (`attachedSessions: 0`, `session.v4.jsonl.zstd`
and `session.lock` mtimes unchanged) until a prompt resumed it (attached 1, the log grew); the
agent panel (`dsh 0.2.0-rc.2`, model, host, keys `set · env`); `/data/plugins.json` listing ten
`mcp__alpaca-kit__*` and fourteen `mcp__akshare__*` tools (both FastMCP servers negotiate with
the 0.2 MCP client); and a room round in `strategies/room-drill` (two bots checked in through
`/data/channels/bots`, one prompt → `dispatch` → both members answered → the strip read
`round 1 · settled`, the discussion card attributed each voice, Kairos's synthesis followed,
and the member sessions carried `drill-bull` / `drill-bear` in `/data/channels.json`'s
`presets`). Every other manual row is still owed a re-run on the new pin, along with the checks
the re-host added (§10, item 14).

| Drill | Proves | Does not prove | Status |
|---|---|---|---|
| **Approval channel** (the README heading still reads "The Gate-2 drill"; its PASSED line calls it the approval-channel drill) — a file write outside the workspace escalates | request → answerer → card → outcome → paired `approval/asked` / `decided`; deny blocks, approve runs once | a producer for an MCP tool call | passed live 2026-08-31; re-run 2026-09-08 on `main`, passed. At 0.2.0 the channel itself — `api-remotes`, `$events`, `$events/result`, a second holder's `cancel` — is automated (`smoke`, `order-gate-smoke`, `client-mux-smoke`); the live browser re-run is owed |
| **Order approval** — automated half | the listener is registered, reaches the live approval service, defaults to `ask`, catches renamed servers, leaves `orders` alone (mutation-proven: removing the registration fails it); the positive path — a grant logged by the real approval service, the guard finding it through `snapshotEvents()`, the order dispatching, a rejection not — and the same answer over the real `$events` channel | that a human can read the card; containment | passes 2026-09-30 (`order-gate`, `order-gate-smoke`) |
| **Order approval** — manual half (arm Gate 1 in a *scratch* home, ask for one paper order, deny, see the audit pair) | the card, end to end | | **not yet run** — the condition before the flag flips in the real home |
| **Client transport** — automated (`client-mux-smoke`) | the page's own `api.js` + `mapper.js` against a real host: gates, replays, withdrawals, follows, the non-activating reads | the DOM: `chat.js`'s rendering and its view modes run only in a vm harness | passes 2026-09-30 |
| **Transport** — manual (`face/README.md`) | the browser half of the wire: the tokenized sign-in and the per-authority cookie; a cold session opened page-only, gaining no `session.v4.jsonl.zstd` or `session.lock` until it is prompted; a reconnect redrawing the window once; a new session's reply streaming without a click; `/compact` answered by `commands/execute`; the agent panel; the subagent dock; rename, fork, the directory picker, a channel rename | the approval card's endings, which are the Gate-2 drill's | **not yet run** on 0.2.0 — a headless load of the page on a scratch home reached `connected` with no console errors |
| **Bots** — automated (`bots-smoke`, `bot-runtime-smoke`, `bot-sandbox-smoke`, `askuser-noclient-smoke`) | roster listing incl. broken; header `agentPreset`; mask = allow ∩ tree, following late tools; persona shadow; inert default; the shipped relative plugin path, rebased; a save re-declaring; Gate 2 refusing an order tool the bot's own mask admits; the S4/S7 observations | that the approval CARD renders (no client) — a bot in a room and a home session's write to `../SOUL.md` were this row's two gaps until `room-smoke` closed both | passes 2026-09-30 |
| **Bots** — manual (`face/README.md`) | create → home → persona → tools named and not named → `{{` refused; the sidebar buckets the home session under the bot; a restart's boot line lists the id; the transcript names the speaker on all four surfaces (second run) | no automated test pins the four naming surfaces or the reconnect path; per-message attribution in a room is the Room rows below | passed 2026-09-07; re-run 2026-09-08 on `main` with the R12 fix in, passed; owed on 0.2.0 |
| **Room** — automated (`room-smoke`, `room-discussion-smoke`) | a real round on a stub model: dispatch → three members (answered / passed / failed) → answers on the log before one wake → synthesis in one turn; members parented, preset-joined, `read-only` first, `AGENTS.md` chain, no `dispatch`; the projection on the row and in the cache; the `@` route with a member's write refused in content; a home refused on `../SOUL.md`; the structured brief and views; the journal | that a human can read the strip; a real model's behaviour on the four standing rules | passes 2026-09-30 |
| **Room** — manual (`face/README.md`, eight parts) | check-in → dispatch line → attributed bubbles and the strip → the fold → `@` → an inline member question with the needs-you mark → a member's write refused → `left` and re-check → a restart keeps states and titles | per-message attribution across a reconnect; convergence of four voices on one model (spec §12, R3); the peer-`@` continuation, which the operator's next `@` superseded before it ran (by design) — that path stands on the engine tests | **Drilled and PASSED 2026-09-09** on the operator's own face (`feat/rooms` @ `31b2e68`, two fresh template bots, DeepSeek as the model); one client finding (F1, the strip missing on a session's first round) fixed the same day and re-verified; owed on 0.2.0, whose 0.1.1 room sessions no longer open (§9, R20) |
| **Ask-user** — `ask_user_question` offered, called, answered, cancelled | the seam | that it is a gate (the answer is model-visible); the instruction half (README step 6 — on a thin brief that does not name the tool, Kairos asks before it builds, per `AGENTS.md`), left to the operator and not run | passed 2026-09-03 with a real model, 26 tools offered; re-run 2026-09-08 on `main`, passed (34 tools offered; answered, then Stop → `closed · cancelled`); owed on 0.2.0 |

Owed besides, from the re-host, never yet run in a browser: the Gate-2 drill's new card endings
— a second tab's `closed`, a lost race's `closed · settled elsewhere`, a stale card's `closed ·
no longer pending`; the approve half of the approval channel and the order-approval manual half;
the room drill's `@`, an inline member question, a member's refused write, and a member trace
that does not activate its member; the bots drill (create, soul edit, re-declare without a
restart); the ask-user drill; rename, fork and the directory picker. The go-live runbook's §7
stages all of them, with the transport drill, on a copy of the operator's home.

---

## 8. Conventions

- **Offline suites, no keys.** Both suites run with nothing configured; a test that needs the
  network monkeypatches the seam. The real-boot tests are opt-in behind `FACE_SMOKE=1`.
- **A real boot speaks the browser's wire.** Each smoke owns one `bootFace` in its own file,
  mounts the real `/` and signs in through it (`tests/remote.ts`: `mountClient`, `signIn`,
  `remote`) before any `/api` call; `client-mux-smoke` drives the page's own `api.js` and
  `mapper.js`. The structural `*Like` types hide most dsh drift from `tsc`, so after every pin
  bump the twelve real boots are the contract.
- **An arc is** brainstorm → spec (`docs/superpowers/specs/`) → plan → build with tests → a
  whole-branch review → a post-build amendments block on the spec. The block is what freezes the
  spec; the Status line is left as written. Of the five post-reset specs, chat-light,
  instruments and bots-and-rooms carry the block — the last for all four of its plans; the
  skeleton and channels specs have none and still read "pending user review" (§10). Three
  pre-reset specs say the same and are retired, not open. The dsh 0.2.0 re-host was built from
  a plan kept outside the repository; its decisions are §4.8.
- **A guard ships with its drill in the same change** (charter Rule 4). A guard that has never
  been pulled is presumed broken.
- **Never edit**: `data/pit/` contents (recapture is the only write), the installed profile
  copies under `$DSH_HOME` (operator territory; the face rewrites `cordis.yml`), anything under
  `bots/` (the operator's voices; Kairos proposes one in conversation and creates none), anything
  under `docs/research/` (frozen inputs).
- **No custom session-event types.** dsh's persistence refuses to reload a log carrying an
  unknown type; a room fact rides a known event with a room `source` — `kind: 'room'`, a native
  v4 message source since 0.2.0 (the 0.1.1 logs that carry it are the ones the 0.2 migration
  refuses, §9 R20).
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
- **R3 — The face's loopback surfaces are reachability fences, not authentication.** One
  un-escalated shell turn can `curl` `POST /data/channels/agents` (or `/data/agents/connect`): no
  card, no diff, no session event — `/data` takes no cookie (PLAN D8). The sandbox confines file
  effects; network stays unrestricted. Mitigation is visibility (`roster.log`), not prevention.
  dsh's own `/api` (`workspace/*` among it) wants the browser cookie since 0.2.0, which puts it
  one step further off, not out of reach (R3a).
- **R3a — The approval answer itself is forgeable from the workspace.** Since 0.2.0 the answer
  is `POST /api/$events/result` under an `$events` clientId, and both want the browser cookie.
  But the cookie is an HMAC over a signing secret stored in `$DSH_HOME/.credentials.yaml`, and
  the sandbox fences file writes, not reads: one un-escalated shell turn can read the secret,
  sign a cookie for `127.0.0.1:3090`, open its own `$events` stream — every pending approval is
  replayed to it — and answer the order it just asked for; the log then holds a genuine
  `approval/asked` + `approval/decided{allowed-once}` pair and the guard admits it correctly.
  The gate asked; the wrong party answered. Read from the code, not executed (0.1.1's version of
  this hole — `/api/respond` with a readable `rpcId` — was `face/README.md`'s "The shell can
  answer its own card").
- **R4 — The channel roster is a menu, not a fence.** Tool registration is tree-wide (schemas
  visible everywhere, only the call refused); a session in no channel is never roster-checked;
  a shell turn can invoke the CLI directly.
- **R5 — The MCP server's writes bypass the sandbox.** It is a child of the face process, not
  of a session; `data/.screen_cache` was written with no card.
- **R6 — The charter recorded a seat the tree now fills.** *Resolved 2026-09-09.* The charter's
  D11 now names the persona mechanism (plan 4). As of 2026-09-07 the model IS told it is Kairos:
  `composeFace` patches the `system-prompt` row's persona — `personaPrefix` since 0.2.0, the
  same order-0 slot 0.1.1 called `persona` — from `dsh/profile/persona.md` through `readPersona`,
  which refuses the boot on a template the strict renderer would throw on.
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
  the result text as `[sandbox: file access denied under read-only mode]`, followed at 0.2.0 by
  `[sandbox: escalation available — retry this exact command once with sandbox_permissions …]`.
  The file does not exist. A caller that reads only `isError` sees a success, so any rule about a
  bot's writes is worded off the CONTENT. The escalation the content offers is real: a retry
  with `sandbox_permissions` raises an approval card, so the operator can grant a room member the
  write the preset refuses, and the grant is logged on that member's own session (observed and
  denied in the room drill's part six). The bot/Kairos asymmetry is
  enforced-with-a-human-exception, not absolute.
- **R11 — A question with no client connected blocks; it never fails.** Measured
  (`askuser-noclient-smoke.test.ts`, spike S7): `userQuestions.ask()` from an agent-owned session
  with no browser attached neither answers nor rejects — `api-remotes` parks it in the gateway
  until the caller aborts, exactly as the approval card does. An agentless (host) ask is the other
  branch and is rejected up front: `NO_PROVIDER` at 0.2.0, since `api-remotes` forwards only a
  scoped ask (0.1.1's apiproxy said `web user interaction requires an agent-owned session`). In a
  room the abort has an owner: a member's turn holds its deadline open while a gate is pending
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
  re-derived from every `session/list` that lands (`refreshSessions`; since 0.2.0 each row's
  `agentPreset` is restored by `summaryOf`), so neither a reconnect nor a roster that arrives late
  can leave a stale name over a live transcript. Per-message attribution — several voices in one
  room log — stays plan 3. Browser-proven 2026-09-08 (manual bots drill, second run): the bot's
  name held on all four surfaces across session switches, a reload and a face restart with the tab
  parked on the bot's session. Still, `speaker.test.ts` and `summaries.test.ts` pin only the
  decision; no automated test pins the four surfaces or the reconnect path.
- **R13 — Every cold session lists as `untitled`.** *Resolved 2026-09-08.* Measured before that on
  a fresh boot: `session.list` returned 24 sessions with no projections block, because dsh-base
  0.1.1 composed `session-projection` without a persisted cache, so a title showed only while its
  session stayed attached; the face closed it with an overlay row of its own. At 0.2.0 dsh-base
  mounts `dsh-session-projection-cache` itself and the face's row is gone: one record per session
  under `storages/session_projcache/sessions/`, bootstrapped from 0.1.1's single
  `session_projcache.json`; a cold session's `session/list` row carries a `cached` projection
  block, from which the sidebar reads the title. A record carried over from 0.1.1
  yields the title alone, so the row's `agentPreset` comes from `/data/channels.json`'s header
  hint until the session runs under 0.2.0 (§5.1, `summaries.js`).
- **R14 — A room's answers are appended to Kairos's log by the face, not spoken by Kairos's
  driver.** Honest and necessary (plan 2, deviation 2), but it means a room log can gain user-role
  messages while no client watches and while Kairos is idle; the persistence write path records
  them like any event. The `quiet` rule (no open turn) is what keeps a running request intact.
- **R15 — Fine states are presence, not truth.** `thinking` / `writing` / `tool` on the strip
  come from the `block-start` frames of each LIVE member's own `session/follow` (a member not
  followed gets only `thinking`, from `api-session/status`), held in the client's memory and
  cleared at turn boundaries; a reload loses them; the log never held them.
- **R16 — The membership rule is a header rule.** A session is a member of `P` when its header
  names `P`, has no `origin`, and a bot preset, and `P` runs the host. A fork of a room keeps the
  host preset and a subagent child carries `origin`, so both stay out; a session re-linked to
  another preset through `agentPresets/select` (a Remote the face never calls) could masquerade
  in the sidebar's fold, though not at `dispatch`, which since 0.2.0 refuses any session whose
  header OR `agentPreset` projection names a bot.
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
- **R20 — Logs the 0.2 migration refuses stay unreadable.** Measured 2026-09-30 by read-opening a
  COPY of the operator's home with the installed 0.2.0 persistence (a read-open writes nothing;
  `face/scripts/check-home.ts` repeats the measurement and classifies each refusal):
  14 of 39 sessions refused, holding 64.8% of all logged events — the ten 0.1.1 room sessions,
  whose `kind: 'room'` user messages the v2→v3 edge does not admit (PLAN D11), three subagent
  children with a version-2 `subagent/descriptor`, and one ordinary session with a sequence gap
  (PLAN D17). Nothing rewrites them. The face reports instead of crashing: a legacy member is
  that member's `failed` turn, naming the legacy format, on every round until the operator
  deletes the member session (archiving does not help: an archived session is still found);
  `/data/rooms/say` on a legacy room answers 409 with dsh's message; an ordinary legacy session
  fails its page read with dsh's error; a child the migration marks `unknown` shows as the dock's
  `unsupported` diagnostic. Detection is by error name or text, so a corrupt v4 log would also
  read "looks like a log written before dsh 0.2" — the message hedges.
- **R21 — Gate 2 and the room engine read `snapshotEvents()`, which upstream deprecates for new
  callers.** It replaced the `events` getter 0.2.0 removed without a word. A later pin may remove
  it too; both then fail closed and say so (the `orders`, `order-gate` and `room-engine` suites
  pin the sentences). The successor upstream names is a grant index fed by `session/event`
  (§10, item 11).
- **R22 — Following can still activate.** A cold session is never followed on purpose (§5.4), but
  liveness is a snapshot: a member, or the session on screen, that goes cold between the list's
  `agentAvailable` and a follow's open is promoted — its log write-opened, `session.v4.jsonl.zstd`
  and `session.lock` published. The reconnect path depends on `api.js` calling `onDown` before
  the next socket re-opens the registered streams (`api.test.ts` pins that order). Stop on a
  paged session answers the host's live-only `session/not-found … (not attached)`.
- **R23 — MCP servers spawn twice and speak into every prompt.** At 0.2.0 stdio negotiation
  starts a probe process before the serving one, doubling alpaca-kit's import cost per connect;
  a server's `instructions` become an unswitchable `mcp:<server>` prompt section that bots see
  too (sections are not masked like tools), and instructions over 32 KiB fail the connection. A
  one-tool FastMCP server on the operator's interpreter (`mcp` 1.28.1) negotiated with the 0.2
  client; the live `mcp__alpaca-kit__*` listing and AKShare's install are drills still owed
  (§7.4).
- **R24 — `agentPresets/read` hands any signed-in client a bot's composition**: its persona text
  and the absolute rebased paths (the face's install path). 0.1.1 had no such Remote; `/api` is
  cookie-gated, which R3a qualifies.
- **R25 — A subagent's `activity` now means mid-turn.** 0.1.1's `running` meant "resident"; at
  0.2.0 the dock reads `running` only while the child is in a turn, so an idle resident child
  reads 未运行 and offers no interrupt.
- **R26 — The redeclare window.** A save disposes a bot's declaration before registering the new
  one (the registry refuses a duplicate id); in between, a `session/create` or a room mount
  naming that bot fails `agent-preset/not-found`. Saves of one bot are serialized; running
  conversations keep the revision they joined.
- **R27 — The spill budget moved (PLAN D18).** dsh-base's `spill-policy` now takes only
  `maxInlineTokens` — 12,500, estimated as UTF-16 length / 4 — where 0.1.1 had `maxInlineBytes:
  50000`. ASCII results spill where they did; CJK-heavy AKShare results stay inline about three
  times longer (about 50,000 characters, some 150 KB), which is context and cost per call. No
  single value reproduces 0.1.1; the policy row is one line once the operator chooses.
- **R28 — The default model is a patch row, and nothing saves it** (PLAN D1, D2). Without
  `profileContext` there is no config editor, so `agentDefaultModel.saveSelection` writes nothing:
  a model selection changes one session only, and the route is the profile's
  `agent-default-model` row or dsh-base's `deepseek-official/deepseek-flash`.

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
   charter's D11 row names the decision that shipped — `composeFace` sets the `system-prompt`
   persona (`personaPrefix` since 0.2.0) from `dsh/profile/persona.md`, and a bot's preset
   shadows it for that bot's sessions — so R6 is closed on both sides. R3, R3a and R5 were
   already answered by the 2026-09-04 charter revision: §7 rules out loopback authentication and
   D10 carries the loopback fence, the forgeable answer and the MCP server's out-of-sandbox
   writes as an accepted debt with a revisit trigger. The admit path's automated test — R3a's
   positive twin, a test answerer on `approval/request`, the guard admitting, the order
   dispatching — landed 2026-09-30 (`order-gate-smoke`, §7.3); what is left belongs to item 1.
4. **Close the doc debts**: post-build blocks on the skeleton and channels specs (both still
   "pending user review"; the skeleton spec's Gate 2 paragraph describes a mechanism that never
   bound), and in `face/README.md` the "Gate-2 drill" heading, the dangling "§7.4" charter
   citation, and the stale line citations. (`dsh/README.md`'s steps 2 and 6 and its installed-state
   bullets were brought to the tree on 2026-09-30.)
5. **Daily cadence** via dsh `schedule` — deferred until a strategy is worth running daily;
   reopens D5 (spend metering) the day anything runs unattended.
6. **Paper forward-testing** behind the gate (`status: paper`) — after 1 and after an
   independent evaluator exists (D1, D7).
7. **FINRA and float live endpoints**; then a **second data vendor** for pre-2021 history.
8. **Distinct commit identity for Kairos** (D2) on the first confusion.
9. **Rooms** — built 2026-09-08/09 (plans 2–4); the live room drill passed 2026-09-09.
   Remaining from the spec's §11: nothing planned.
10. **A2A voices** — the charter's §7.1 admits an agent reached over A2A as a voice; no spec,
   nothing built; the day anything outside this machine can call in, the last row of the
   charter's §8 revisit table fires ("A second human, or any hosted deployment").
11. **A grant index for Gate 2.** Replace the guard's `snapshotEvents()` read — and the room
   engine's — with an index of `approval/asked` / `approval/decided` pairs fed by
   `ctx.on('session/event', …)`, the successor upstream names for the deprecated synchronous
   read. Done when both run on a Session without `snapshotEvents` (R21).
12. **`profileContext`, if ever** (PLAN D1): settings forms, a model save that persists, live
   reload. It means moving every face layer into `profileContext.overlays` and letting the first
   boot import and rename the shared `settings.yaml`. Nothing planned; taking it would close R28.
13. **Take the CLI's `runProfile` instead of mirroring it** (`@deepseek-ai/dsh/profile-boot`),
   the day upstream offers the seams the face's ten divergences need (§4.1) — above all an
   `appReady` the caller commits and no `profileContext`. Until then every pin bump re-diffs
   `boot.ts` by hand.
14. **Take the operator's home to 0.2.0**, by the go-live runbook
   (`docs/superpowers/runbooks/2026-09-30-dsh-0.2.0-rc.2-go-live.md`): stop every 0.1.1 CLI and
   face on it; back it up (a full restore is the only rollback, PLAN D12); dry-run a copy with
   `face/scripts/check-home.ts`, which boots the face on the copy and read-opens every session;
   add the D2 row; decide PLAN D11, D12, D13, D17 and D18; rehearse the drills §7.4 owes on a
   second copy; then boot on the home. Done when those drills pass on the real home.

---

## Appendix A — Environment variable index

| Variable | Layer | Meaning |
|---|---|---|
| `APCA_API_KEY_ID`, `APCA_API_SECRET_KEY` | alpaca_kit, producers, quote routes, MCP row | Alpaca paper credentials |
| `APCA_API_BASE_URL` | `account.py` | trading host override; anything but the paper hostname fails `_require_paper` |
| `ALPHA_DATA_SOURCE` | `registry.py` | `alpaca` \| `snapshot` \| `composite` \| feed names |
| `ALPHA_PIT_ROOT` | registry, MCP, producers, template scripts | the bed; CWD-relative |
| `ALPHA_DATA_FEED` | `alpaca.py`, the quote routes | bars and quotes feed, default `iex` |
| `ALPHA_DATA_COMPOSITE`, `ALPHA_DATA_COMPOSITE_BASE` | `registry.py` | composite routing |
| `ALPHA_UNIVERSE_SCREEN` | `universe.py` | `gainer` \| `trend_template` |
| `ALPHA_EDGAR_USER_AGENT`, `ALPHA_FINRA_USER_AGENT`, `ALPHA_FLOAT_USER_AGENT` | feeds | outbound UA strings |
| `ALPACA_KIT_ENABLE_ORDERS` | MCP child (operator's row only) | Gate 1 |
| `DEEPSEEK_API_KEY` | dsh credential seam | the LLM and `web_search` |
| `DSH_HOME` | dsh, face | harness home |
| `DSH_PERMISSION_MODE` | dsh | sandbox preset; `danger-full-access` ⇒ approval policy `never` |
| `DSH_TELEMETRY_DISABLED` | face boot | any non-empty value disables telemetry; composed after the operator layers, it still wins over an operator's re-enable of the row the policy layer disables |
| `FACE_PORT`, `FACE_PROFILE`, `FACE_PYTHON` | face | port, profile name, producer interpreter |
| `FACE_AKSHARE_MCP_COMMAND` | face (`akshare.ts`) | the AKShare MCP executable, default `~/.local/bin/akshare-mcp` |
| `FACE_IFIND_POLL_MS`, `IFIND_ACCESS_TOKEN`, `IFIND_REFRESH_TOKEN` | face (quote routes) | the A-share quote provider's refresh period and credentials |
| `FACE_SMOKE` | face tests | enables the twelve real boots |
| `FASTMCP_LOG_LEVEL` | MCP row | `WARNING` silences FastMCP's INFO noise; never edit `server.py` for it |
