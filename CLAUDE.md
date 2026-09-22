# CLAUDE.md

Descriptive, not prescriptive — present-tense facts about the tree, updated when the tree
moves; the only CLAUDE.md in the repo. Owner: the operator. Last reviewed 2026-09-21. Depth
lives in `DEVELOPMENT.md`, `Kairos-Design.md`, `face/README.md`, docstrings, and `docs/`.
Last reviewed 2026-09-22 (the paper book).

## What this is
A market-strategy-account research workbench for one operator, one principal agent (Kairos) and
operator-authored bots, reset 2026-08-29 from the retired Sonia-Kairos product. MARKET + ACCOUNT
are `alpaca_kit` — one Python package, two faces: importable library and MCP server. STRATEGY is
`strategies/`, the agent's arena, run on DeepSeek Harness (dsh) inside `face/`, the chat face.

## Map
| Where | What |
|---|---|
| `Kairos-Design.md` | the product charter — intent, principles, write map, debts, revisit triggers; outranks everything on intent |
| `DEVELOPMENT.md` | the as-built front/back-end reference — processes, contracts, gates, tests, drills, residuals, forward list; on mechanism the code is the fact and this document follows it |
| `AGENTS.md` | the map written for Kairos: the strategy contract, bed windows, never-edit list (dsh's instruction loader hands Kairos this file *and* `CLAUDE.md`) |
| `ROADMAP.md` | the five-item forward index from the reset plus a built log; `DEVELOPMENT.md` §10 is the ordered detail and cites its items by number |
| `alpaca_kit/{source,firewall}.py` | MarketDataSource Protocol + FakeSource; the AsOfGuard/GuardedSource lookahead firewall (six surfaces pinned by name in `tests/test_us0_firewall_surfaces.py`) |
| `alpaca_kit/{alpaca,registry,composite,account}.py` | Alpaca REST + corp-action normalization · source selection · per-capability routing · the paper-pinned trading host (the order functions live here; Gate 1 is in `mcp/tools.py`) |
| `alpaca_kit/{pit,feeds,features}/` + `{replay,universe,stock,integrity}.py` | PIT store/capture/CHECKSUMS (capture writes `corp_actions.parquet` only when the source can check) · EDGAR (live) + FINRA/float (stubs) + `massive_files` (bought daily-bar files under a strategy's `vendor/`, bars + calendar only) · trend_template/gainer screens + breadth · backtest day iterator · daily screen + its snapshot models · canonical hasher |
| `alpaca_kit/mcp/` | the MCP tool surface, read-only by default; order tools register only under `ALPACA_KIT_ENABLE_ORDERS=1` AND keys; screen/breadth disk cache in `data/.screen_cache`, never inside a bed |
| `alpaca_kit/paper/` | the paper book: one strategy's simulated account, kept by the operator's engine OUTSIDE the workspace at `$DSH_HOME/face/paper/<name>/` (`ALPHA_PAPER_HOME` overrides) so Kairos reads it and cannot write it — `intent.py` (the `signal.py` contract: targets + weights at a day's close, and its by-path loader), `book.py` (`PaperBook`: the intent filled at the NEXT open, marks at the close, splits / `delist` / cash dividends by tape date, a hash-chained `ledger.jsonl`, `verify`), `home.py`; driven by `scripts/paper_book.py open \| walk \| step \| verify \| show`; no order path anywhere in it (a test greps). Spec `docs/superpowers/specs/2026-09-22-paper-book-design.md` |
| `strategies/` · `data/` · `scripts/` | one directory per strategy (`_template` is the copy source — it now ships a `signal.py` that refuses until written; `room-drill` the room drill's fixture channel, `paper-drill` the paper book's: the day's most-traded names equal-weighted) · gitignored PIT beds + caches · capture_window / capture_broad / smoke_alpaca / `face_data.py` (the instruments' producer) / `paper_book.py` (the book's operator command) / convert_seeds |
| `dsh/` | the harness config: `profile/cordis.yml` template (indicative shape, not a validated dsh config) + `skills/mechanics` (rules, tool guide, the `bought-data` skill: how a strategy buys vendor data and beds it) + `skills/style-kairos` (operator style). Install is `cd face && npm run setup`; `dsh/README.md` steps 2 and 6 predate the face and Gate 2 |
| `face/` | kairos-face: Node 22, hosts dsh in-process from profile `face`, serves chat + `/market` + `/account` + `/wallet` at 127.0.0.1:3090; `strategies/*` are rostered channels; `src/orders.ts` is Gate 2, the per-order approval card; `src/budgets.ts` is Gate 3, the budget card, and `src/wallet.ts` registers the nine `wallet_*` tools in-process and names the save root for `wallet_pay {save_to}` (the calling channel's `vendor/`; a session in no channel is refused); the channel landing page shows a paper-book card read from the engine's `summary.json` under `FACE_PAPER_HOME` (default `$DSH_HOME/face/paper`; `readPaperSummary` in `src/channels.ts`) — the face reads, never computes |
| `face/src/akshare.ts` | project-owned AKShare MCP connection for public A-share queries; composed below operator profile/home patches; no PIT guard; install/version and live-query limits in `face/README.md` |
| `bots/` | one directory per bot (`_template` is the copy source, `kairos` the inert default, `drill-bull`/`drill-bear` the room drill's two voices): a dsh agent preset — persona + allow-list mask via `face/plugins/bot.js`; in a room (a channel session with bots rostered) `face/src/room.ts` creates one `read-only` member session per bot and Kairos calls `dispatch` |
| `payment/` | git submodule → [linqizhe07/agentpay](https://github.com/linqizhe07/agentpay), pinned by commit (`git submodule update --init` after checkout, then `(cd payment && npm ci)` after every submodule update — `face/src/wallet.ts` imports it by relative path and needs its `node_modules`): x402 (V2, `exact`/EIP-3009) payments for agents on the official `@x402/*` packages — a budgeted wallet (intent mandates with holders and sub-budgets, policy gate, ledger, reconcile, the wallet lock), payee paywall (with a vendor simulator, `npm run vendor-sim`), self-hostable facilitator, `agentpay` CLI and the host-agnostic tool table (`packages/cli/src/tools.ts`, nine tools: `wallet_discover` reads the public x402 catalogue; `wallet_pay {save_to}` lands a bought body under the channel's `vendor/` with a sha256 receipt) the face consumes; `packages/cli/SKILL.md` is what an agent driving the CLI reads. The face calls it through `face/src/{wallet,wallet-payload,budgets}.ts`; the home is `$DSH_HOME/face/agentpay` (`config.json` with the payer key, `mandates.json`, `ledger.jsonl`, `wallet.lock`, `face-state.json`); the face holds `wallet.lock` while it runs and the CLI's mutating commands refuse a locked home |
| `docs/` | `backtest-rules.md` (the five honest-eval rules) · `superpowers/{specs,plans,runbooks}` (per-feature decision history; everything dated 2026-06/07, and the one runbook, describes the retired product) · `research/` (frozen inputs) · `design/prototypes` (face rounds R1–R4) · `design/kairos-intro.html` (annotated static tour of the four faces and the wallet surfaces as built — the budget card, the pay card, `/wallet`; redrawn for x402 2026-09-21; no requests, sample data) |
| `tests/` · `face/tests/` | offline pytest, no keys · `node --test` via tsx; `FACE_SMOKE=1` adds the real boots (`room-smoke`, `budget-gate`, `wallet-smoke` among them) |

## Commands
```bash
# repo root
pip install -e ".[dev]"     # extras: [live] adds alpaca-py + market calendars
python -m pytest            # offline, no keys (-q is already the default addopts)
python -m alpaca_kit.mcp    # the MCP server, stdio
# face/
npm run setup               # once, after npm install: writes $DSH_HOME/profiles/face, never overwrites
(cd ../payment && npm ci)   # the wallet's substrate; again after every submodule update
npm test && npm run typecheck
npm start                   # http://127.0.0.1:3090 (see face/README.md)
```

## Gotchas
- Corp actions key on **`announce_date := process_date`** — Alpaca has no true announce field.
- **`ALPHA_DATA_FEED` defaults to `iex`** — SIP 403s on free/paper keys.
- Prices are stored **RAW/unadjusted**; `make_source()` returns a RAW source by contract, so
  wrapping it in `GuardedSource` + `AsOfGuard` is the caller's job (`replay_days` and the MCP
  tools do it for you).
- Backtests run **only through `alpaca_kit.replay.replay_days`**, bounded with both `start=` and
  `end=` to a bed's usable window (2yr 2024-06-03..2026-07-09, broad 2025-11-17..2026-03-27) —
  outside it a snapshot read raises `SnapshotMissingError`, but bar and corp-action reads just
  return empty, so bounding is on you. Neither bed carries **warmup**: long indicators mature
  only from mid-2025 on 2yr and never on broad. Exact dates and the five honest-eval rules:
  `docs/backtest-rules.md` (`AGENTS.md` carries the same table).
- **Two order gates, both on the MCP tool surface.** Gate 1 = registration (flag AND keys, in
  `alpaca_kit/mcp/tools.py`); Gate 2 = the face's per-order card (`face/src/orders.ts`), which
  exists only when dsh runs inside the face. Neither is containment — a shell turn can read
  `.env.alpaca` and import `alpaca_kit.account`; the paper-hostname pin bounds it. Never arm
  `ALPACA_KIT_ENABLE_ORDERS` in the real harness home: the automated drill uses `mcp__drill__*`
  stand-ins, the manual half arms Gate 1 in a scratch home only (`face/README.md`).
- **The wallet home is `$DSH_HOME/face/agentpay`; the face is its only writer while it runs
  (`wallet.lock`); a bot never sees a wallet tool.** Gate 3 (`face/src/budgets.ts`) cards only
  `wallet_budget_request`; a payment meets a mandate, not a card. The payer key there is readable
  from any shell turn (charter D16) — keep the float small and testnet, never a mainnet key.
- **A paper book is the engine's, not the strategy's.** `python scripts/paper_book.py walk <name>
  --start … --end …` bounds the replay exactly like a backtest (the bed traps apply) and calls the
  strategy's `signal.py` under the day's guard; a rule that raises, or answers a malformed intent,
  is recorded on the ledger and stops the walk — never read as flat. Books live under
  `$DSH_HOME/face/paper/<name>/` (the face reads `summary.json` from `FACE_PAPER_HOME`, same
  default; point both at one scratch home for a drill); `status: paper` is still a badge and
  schedules nothing; nothing here places an order.
- **`$DSH_HOME/profiles/face/cordis.yml` is rewritten to `[]` on every face boot.** The
  operator's file is `cordis.patch.yml`; the face's overlay rows (webserver, connection, the
  storage chain, tool-ask-user…) compose last and override it silently.
- **`face/client/*` is served with no cache headers** — hard-reload the browser after any client
  edit, or you drill a stale `chat.js`.

Reading order for a new session: `Kairos-Design.md` §1–§2 → the `DEVELOPMENT.md` section you
are touching → `AGENTS.md` for what Kairos itself sees.
