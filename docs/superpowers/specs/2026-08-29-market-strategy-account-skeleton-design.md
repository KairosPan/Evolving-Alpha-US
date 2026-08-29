# Market-Strategy-Account Skeleton — Design (Approach A)

**Date:** 2026-08-29 · **Status:** approved in brainstorming, pending user review of this spec ·
**Supersedes:** the Sonia-Kairos self-evolving-H product concept (charter, H=(p,K,M,C,W,A),
write-waist governance, two entities) — retired by operator decision 2026-08-29.

---

## 1. Context and decision history

The operator is resetting this project from the Sonia-Kairos concept to a three-layer product:

- **MARKET** — market data: bars, snapshots, screening, corporate actions, breadth.
- **STRATEGY** — where the LLM agent mainly operates; strategies are first-class objects.
- **ACCOUNT** — Alpaca paper account: positions/orders (read-only at MVP).

The strategy layer's runtime is **DeepSeek Harness (dsh)** — not a bespoke agent stack. A
9-agent salvage survey (2026-08-29) and the frozen dsh survey
(`docs/research/2026-08-22-deepseek-harness-dsh-survey.md`) established that dsh natively
covers everything the old repo built for the agent side (LLM seam, tool loop, approvals, MCP,
sessions, sandbox, compaction, web UI, skills, workflows, subagents). The only old code carried
forward is the **`alpha/data` dependency island** (Alpaca REST + PIT machinery) and the
**Alpaca trading-host path** for the account layer.

Decisions fixed during brainstorming (each confirmed by the operator):

| # | Question | Decision |
|---|---|---|
| 1 | Daily usage shape | **Research workbench MVP**; skeleton reserves slots for daily-run / managed-strategy evolution but does not implement them |
| 2 | Repo placement | **In-place reset** of Evolving-Alpha-US on a reset branch; git history and GitHub repo preserved |
| 3 | What a "strategy" is | **Strategy = directory** (thesis + executable screen + backtests + journal), git-versioned |
| 4 | Account capability | **MVP read-only**; order tools written but not registered by default (double gate, §5) |
| 5 | LLM | **DeepSeek primary** via dsh first-party `llm-deepseek` adapter + existing `DEEPSEEK_API_KEY` |
| 6 | Personal style | seeds_v2 content is the operator's **personal investment style** — shipped as a clearly labeled style pack, separate from neutral mechanics (§7) |
| A | Architecture | **Approach A: one Python package, two faces** (importable lib + MCP server), over a two-package split (premature) or loose scripts (loses PIT discipline) |

Backups completed 2026-08-29 before any reset:
`~/Desktop/self-evolve/alpha-us-backup-20260829/` (PIT beds 51MB diff-verified, keys, state,
decisions), research docs committed (88b6686), `feat/body-six-components` pushed to origin.

## 2. Repo layout

```
Evolving-Alpha-US/                 # reset branch, history preserved
├── alpaca_kit/                    # THE Python package (two faces: lib + MCP server)
│   ├── source.py                  # MarketDataSource Protocol + FakeSource + AsOfGuard/GuardedSource
│   ├── alpaca.py                  # AlpacaSource: _get_json REST seam + corp-actions normalization + bars
│   ├── account.py                 # NEW: trading host /v2/account /v2/positions /v2/orders
│   │                              #   (place_order/cancel_order live here too; see §5 registration gate)
│   ├── registry.py                # make_source + CompositeSource (source_names() governance hook dropped)
│   ├── pit/                       # PITStore + SnapshotSource + capture + CHECKSUMS + calendar
│   ├── feeds/                     # edgar.py (working) + finra/float stubs + typed models
│   ├── features/                  # trend_template 8-criteria screen + gainer screen + breadth family
│   ├── replay.py                  # NEW ~100-line PIT backtest helper (§6)
│   ├── integrity.py               # the one canonical JSON/file hasher (copied verbatim)
│   ├── settings.py                # slim env registry (APCA_*/ALPHA_DATA_FEED/pit root/...)
│   └── mcp/__main__.py            # MCP server entry: python -m alpaca_kit.mcp
├── strategies/                    # agent's main arena (§6)
│   └── _template/
├── dsh/                           # dsh profile template + skills + install README (§7)
├── AGENTS.md                      # workspace map for the dsh context plugin
├── data/pit/                      # PIT beds remounted from backup (gitignored)
├── scripts/                       # capture_window / capture_broad / smoke_alpaca only (imports updated)
├── tests/                         # migrated offline data-layer tests + meta-gates (§8)
├── docs/                          # research/ stays; this spec; backtest-rules.md
└── pyproject.toml                 # deps: pandas/pydantic/pyarrow + mcp SDK; extras: [live] [dev]
```

## 3. Carried vs dropped

**Carried** (from the salvage survey): the data Protocol + FakeSource + lookahead firewall;
AlpacaSource with its hard-won gotchas (announce_date := process_date — Alpaca has no true
announce field; ALPHA_DATA_FEED default iex — SIP 403s on free/paper keys; RAW/unadjusted
prices by contract); make_source/CompositeSource; the whole PIT capture/replay stack incl.
CHECKSUMS; EDGAR (keyless, working) and FINRA/float stubs with their PIT-key doctrine;
trend_template + gainer screens + breadth family; integrity.py verbatim; the offline test
suite for all of the above plus the firewall meta-gate.

**Dropped**: momo composite features (sentiment/runner/echelon), MarketState/build_market_state
(GCycle-entangled; breadth becomes standalone functions), the three clocks, guard/sizing/eval,
everything in harness/refine/meta/converse/arena, all three services, alpha/llm, alpha/mcp
(dsh has native MCP), alpha/memory. seeds/seeds_v2 **content** survives as dsh skills (§7);
the container dies.

## 4. MCP tool surface (MVP: all read-only)

| Group | Tool | Notes |
|---|---|---|
| market | `daily_bars(symbol, start, end)` | RAW unadjusted daily bars (IEX feed) |
| | `market_snapshot(date?)` | full cross-section for a day (default: latest trading day) |
| | `calendar(start, end)` | trading days |
| | `corp_actions(symbol?, start?, end?)` | announce-date-keyed |
| | `screen(date, kind)` | kind: gainer \| trend_template |
| | `breadth(date)` | %>200DMA, net new highs, A/D |
| | `earnings(symbol)` | EDGAR XBRL facts, keyless |
| account | `account()` / `positions()` / `orders(status?)` | paper account queries |
| reserved | `place_order(...)` / `cancel_order(id)` | code exists in account.py, **not registered by default** |

Cross-cutting rules:

1. **PIT semantics enforced at the tool layer**: every call wraps the RAW source in
   `GuardedSource(AsOfGuard(as_of))`, as_of defaulting to today and explicitly passable.
   Carries the old contract: registry returns RAW; guarding is the caller's job — here the
   tool layer IS that caller, so the agent cannot commit lookahead through tools.
2. **Fail-soft**: missing APCA keys → key-needing tools are simply not registered (offline
   snapshot-replay tools remain); never a boot error. Per-call failures return
   `{"ok": false, "error": "<actionable hint>"}` (401/403 = entitlement, 429 = backoff —
   the _get_json hint system carried verbatim).
3. **Result shape**: DataFrame → `to_dict(orient="records")`, row-capped with an explicit
   truncation note. dsh's spill plugin handles oversized results on its side.

Implementation: the official Python `mcp` SDK (FastMCP), not a hand-rolled JSON-RPC loop.

## 5. Order reservation — the double gate

- **Gate 1 (registration, operator-only)**: order tools register only when
  `ALPACA_KIT_ENABLE_ORDERS=1` is set in the MCP server's process env. That env is set in the
  **dsh profile in harness home (~/.dsh)** — outside the agent's workspace (the repo), so the
  agent structurally cannot flip it.
- **Gate 2 (per-order approval)**: even when enabled, the order tools are marked always-ask
  in the dsh permission preset, so every order call requires human approval via dsh's native
  user-approval flow.

This reproduces the old product's no-order pin + T4 human-confirm slot using only dsh
primitives plus server config — zero bespoke governance code. A capability-absence test pins
Gate 1's default (§8).

## 6. strategies/ conventions

One directory per strategy:

```
strategies/<name>/
├── THESIS.md              # thesis + rules: what market behavior, why it works,
│                          #   entry/exit/stop, explicit falsification conditions
├── screen.py              # executable screen/signal (imports alpaca_kit)
├── backtest.py            # backtest script over data/pit/ beds
├── backtests/             # archived results: YYYY-MM-DD-<label>.json (params+window+metrics)
├── journal.md             # iteration log: what changed, why, outcome
└── status.yaml            # lifecycle: idea | researching | validated | paper | retired
```

`paper` is a reserved lifecycle state (forward-testing; meaningful only after the order gate
opens) — the "workbench first, evolve later" slot.

Conventions:

1. **Backtests go through the PIT channel.** `alpaca_kit.replay` (~100 lines) iterates a
   captured window's trading days and yields a `GuardedSource(AsOfGuard(day))` per day —
   making the lookahead-safe backtest the path of least resistance. The old eval stack is NOT
   revived; this is the data-layer day iterator the calibrate scripts already embodied.
   Honest-eval rules live in `docs/backtest-rules.md` (delisting/halt-to-zero = terminal loss
   −1.0, never dropped; returns are gross, stated; decide day t → enter t+1 open; missing data
   → discard, never fabricate) and are enforced on the agent via a mechanics skill (§7) —
   prose-bound, honestly stated as such.
2. **Git is the audit trail.** The agent commits its own strategy iterations; evolution
   history = `git log strategies/<name>/`. Replaces the old edit-log/snapshot machinery.
3. **Strategies ≠ knowledge.** strategies/ holds specific tradeable hypotheses; general
   trading knowledge lives in dsh skills. seeds_v2's breakout_entry et al. may seed the first
   strategy directory as material, but the two are distinct kinds.

## 7. dsh configuration

```
dsh/
├── profile/cordis.yml          # template: llm-deepseek · mcp mount of alpaca_kit ·
│                               #   sandbox · permission preset
├── skills/
│   ├── mechanics/              # neutral, always-on
│   │   ├── backtest-rules/     #   the honest-eval rules (references docs/backtest-rules.md)
│   │   └── alpaca-kit-guide/   #   lib/MCP usage + the gotcha corpus (announce:=process_date,
│   │                           #     IEX feed, RAW prices, PIT keys per feed, ...)
│   └── style-kairos/           # the operator's PERSONAL investment style — loaded by default,
│       ├── doctrine/           #   but every skill opens with: "this is the operator's style
│       ├── signals/            #   and preference, not objective market law; when research
│       └── lessons/            #   findings conflict with a style entry, REPORT the conflict,
│                               #   do not silently defer" (39 rules + 6 signals + 21 lessons,
│                               #   rewritten from seeds_v2)
└── README.md                   # install steps: profile → ~/.dsh, where keys live
AGENTS.md                       # repo root: workspace map + strategies/ conventions
```

Boundary arrangements:

1. **Model & credentials**: main loop = dsh first-party `llm-deepseek` + `DEEPSEEK_API_KEY`.
   `APCA_*` keys enter only the **MCP server process env** (referenced by name in the profile's
   mcp config) — the agent's shell never holds broker keys; dsh's env-scrubbing defensive
   pattern compounds this.
2. **The real profile lives in harness home** (~/.dsh); the repo holds a template. Operator
   switches (`ALPACA_KIT_ENABLE_ORDERS`) exist only home-side, out of the agent's reach.
3. **Permission preset**: read-only market/account tools auto-allowed; in-workspace shell
   allowed; (future) order tools always-ask.
4. **Skills are knowledge, AGENTS.md is the map** — no mixing.

**Honest caveat**: dsh is in developer preview ("THERE WILL BE COMPATIBILITY-BREAKING
CHANGES"); the frozen survey dates to 2026-08-22. This spec commits to *placement and
content*; exact profile/skill file formats are pinned against the live dsh docs at
implementation time.

## 8. Testing

- **Migrate**: the old `tests/data/` offline modules (FakeSource + mocked `_get_json`, no keys)
  with imports renamed to alpaca_kit. Target ~150–200 tests at reset, `pytest -q` in seconds.
- **Two meta-gates carried**: (1) the PIT firewall surfaces test — the four lookahead guards
  pinned by (module, name); (2) a capability-absence test: under default config, no tool whose
  name contains "order" exists in the MCP registry.
- **New coverage**: account.py's three queries (mocked `_get_json`); replay helper PIT
  semantics; MCP server registration/fail-soft behavior via the SDK's in-memory client.

## 9. Reset execution order (first implementation batch)

1. `git checkout -b reset/market-strategy-account` (main untouched; the old tree stays
   reachable forever).
2. Clear to skeleton: delete alpha/ (except migration sources), the three services, seeds,
   the rest of old tests.
3. Migrate alpha/data + related → alpaca_kit/, rename imports, migrate tests, go green.
4. Write new code: account.py → mcp/__main__.py → replay.py.
5. Remount data/pit/ from backup; place strategies/_template/, dsh/, AGENTS.md.
6. Pin profile/skill formats against current dsh docs; write skills (mechanics + style-kairos).
7. End-to-end smoke: dsh web up → agent calls screen/daily_bars → create the first strategy
   directory and run a backtest through replay.py.

## 10. Out of scope (deferred, slots reserved)

- Daily-run cadence (dsh schedule/workflow) and managed strategy execution — the "evolve
  later" half of decision #1.
- Enabling paper orders (Gate 1 stays off until the operator flips it).
- FINRA/float live endpoints (stubs carried; PIT mapping already built).
- A second data vendor (CompositeSource seam is ready).
- Any bespoke self-evolution/governance machinery — dsh primitives or nothing.

## 11. Risks

| Risk | Mitigation |
|---|---|
| dsh developer preview breaks formats/APIs | Formats pinned at build time; dsh pinned by version in the profile; survey re-read before build |
| Agent-written backtests dodge the honest rules | replay.py makes the safe path easiest; rules skill + backtests/ archives make violations visible in review; accepted as prose-bound at MVP |
| MCP JSON round-trips too slow for research loops | By design: backtests import the lib directly; MCP is for interactive queries only |
| IEX free-tier data limits (post-2021 only) | Preserved beds (2yr window) cover the near past; longer history is a future vendor decision |
