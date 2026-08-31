# CLAUDE.md

Descriptive, not prescriptive — the tree is current, this file gets updated; it is the only
CLAUDE.md, and depth lives in docstrings, `docs/`, and `AGENTS.md`.

## What this is
A market-strategy-account research workbench, reset 2026-08-29 from the retired Sonia-Kairos
self-evolving-H product. MARKET + ACCOUNT are `alpaca_kit` — one package, two faces: importable
library and MCP server. STRATEGY is `strategies/`, the agent's arena; its runtime is DeepSeek
Harness (dsh), configured from the repo-side template + skill packs in `dsh/`. Spec:
`docs/superpowers/specs/2026-08-29-market-strategy-account-skeleton-design.md`.

## Map
| Where | What |
|---|---|
| `Kairos-Design.md` | the charter — intent and principles (five principles, the write map, debts, revisit triggers); on intent it outranks the spec, on mechanism the spec and code win |
| `alpaca_kit/{source,firewall}.py` | MarketDataSource Protocol + FakeSource; the AsOfGuard/GuardedSource lookahead firewall (surfaces pinned by name in `tests/test_us0_firewall_surfaces.py`) |
| `alpaca_kit/{alpaca,registry,composite,account}.py` | Alpaca REST + corp-action normalization · source selection · per-capability routing · the paper-pinned trading host |
| `alpaca_kit/{pit,feeds,features}/` + `{replay,universe,integrity}.py` | PIT store/capture/CHECKSUMS · EDGAR + FINRA/float feeds · trend_template/gainer screens + breadth · backtest day iterator · daily screen · canonical hasher |
| `alpaca_kit/mcp/` | the read-only MCP tool surface; order tools live in `account.py` and register only under `ALPACA_KIT_ENABLE_ORDERS=1` |
| `strategies/` · `data/pit/` · `scripts/` | one directory per strategy (`_template` is the copy source) · offline PIT beds, gitignored · capture_window/capture_broad/smoke_alpaca |
| `dsh/` | the harness config the operator installs: `profile/cordis.yml` template + `skills/mechanics` (neutral: backtest rules, alpaca-kit guide) and `skills/style-kairos` (operator style: doctrine/signals/lessons, generated from the retired seeds_v2 packs by `scripts/convert_seeds.py`) |
| `face/` | the operator's chat face: a Node 22 process hosting dsh in-process from profile `face` (bundles dsh-base only), serving chat-light + the read-only `/market` and `/account` instruments (fed by `scripts/face_data.py`) at 127.0.0.1:3090; the Gate-2 approval surface — run, instrument and drill instructions in `face/README.md` |

## Commands
```bash
pip install -e ".[dev]"     # extras: [live] adds alpaca-py + market calendars
python -m pytest            # full suite, offline, no keys (-q is already the default addopts)
python -m alpaca_kit.mcp    # the MCP server, stdio
cd face && npm run setup    # one-time, after npm install: writes $DSH_HOME/profiles/face
cd face && npm start        # the chat face, http://127.0.0.1:3090 (see face/README.md)
```

## Gotchas
- Corp actions key on **`announce_date := process_date`** — Alpaca has no true announce field.
- **`ALPHA_DATA_FEED` defaults to `iex`** — SIP 403s on free/paper keys.
- Prices are stored **RAW/unadjusted**; `make_source()` returns a RAW source by contract, so
  wrapping it in `GuardedSource` + `AsOfGuard` is the caller's job.
- Backtests run **only through `alpaca_kit.replay.replay_days`**, bounded to a bed's usable window
  (2yr 2024-06-03..2026-07-09, broad 2025-11-17..2026-03-27) — outside it a snapshot read raises
  `SnapshotMissingError`, but bar and corp-action reads just return empty, so bounding is on you.
  Neither bed carries **warmup**: bars start AT the window start, so the whole window replays but
  long-indicator readings mature late — on 2yr the 200DMA from 2025-03-20 and 52-week metrics from
  2025-06-04 (trend_template names only from 2025-06-05); broad (90d) never gets there.
  The five honest-eval rules: `docs/backtest-rules.md`.
