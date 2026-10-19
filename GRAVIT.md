# GRAVIT.md — the workspace, for every agent dsh runs here

Read by Gravit, its role children and the bots alike, as workspace instructions: facts and
rules of this tree, never anyone's identity or persona. When this file and the tree disagree,
the tree is right and this file is wrong.

Three layers. MARKET and ACCOUNT are the `alpaca_kit` package: import it for backtests
(`alpaca_kit.replay.replay_days`), call its MCP tools for interactive reads. STRATEGY is
`strategies/`: one directory per strategy, Gravit's arena.

## Where things are

- `alpaca_kit/` — the data and account library, and the MCP server the `mcp__alpaca-kit__*`
  tools come from. Prices are RAW/unadjusted everywhere. Corporate actions key on
  announce_date := Alpaca's process_date.
- `strategies/<name>/` — `THESIS.md`, `screen.py`, `backtest.py`, `backtests/`, `journal.md`,
  `status.yaml`; `strategies/_template` is the copy source.
- `data/pit/` — the offline point-in-time beds (the table below). `data/` is gitignored.
- `docs/backtest-rules.md` — the five honest-eval rules every backtest follows.
- `roles/` — Gravit's role library; `bots/` — the operator's voices. Both are the operator's.

## Point-in-time reads

Every dated market read goes through `replay_days` (backtests) or the alpaca-kit MCP tools
(interactive). A bare `make_source()` returns a RAW source with no lookahead guard: wrap it in
`GuardedSource` with an `AsOfGuard` for the day, or do not read it. The AKShare tools
(`mcp__akshare__*`) are public A-share queries with NO guard — never backtest evidence.
`akshare_discover` finds a method and its category tool; `stock_zh_a_spot_tx` is the verified
Tencent A-share snapshot method, while Eastmoney and Xueqiu endpoints may fail or require a
login. Check every result's errors, timestamps and `truncated` (the default limit is 500 rows;
a truncated result is not the whole market). Retrieval time is not exchange time.

## The beds — the only usable windows

| bed | usable window | trading days | 200DMA valid from | 52-week metrics from |
|---|---|---|---|---|
| `data/pit/2yr` | 2024-06-03 .. 2026-07-09 | 526 | 2025-03-20 | 2025-06-04 |
| `data/pit/broad` | 2025-11-17 .. 2026-03-27 | 90 | never | never |

Outside a window a snapshot read raises `SnapshotMissingError`, while bar and corp-action reads
return EMPTY frames and say nothing: bound every replay with `start=` and `end=`. The beds carry
no warmup — `screen(kind="trend_template")` returns nothing before 2025-06-05 on `2yr` and ever
on `broad`. Offline work sets `ALPHA_PIT_ROOT=data/pit/2yr` and `ALPHA_DATA_SOURCE=snapshot`,
both resolved against the CWD; a channel session's shell runs in `strategies/<name>/`, so use
the absolute bed path there (`backtest.py` anchors on its own file and is immune).

## A strategy directory

Lifecycle, in `status.yaml`: `idea | researching | validated | paper | retired` (`paper` is
reserved until the order gate opens). Three optional headline keys the channel page renders,
none required: `one_line` (the current conclusion, one sentence), `next` (the next step),
`numbers` (free figures as a mapping of scalar values). Name a strategy as the face names
channels: a letter or digit in any script first, then letters, digits, `-` and `_`, at most 41
code points, no spaces or dots — the name becomes a path typed into shell by hand, and `cd x y` is
zsh's two-argument form, exit 0 in the wrong directory whenever the substituted path exists.
Commit your own iterations between cycles; a cycle commits once, with its verdict. git log is
the audit trail.

## Rooms

A channel whose roster has bots is a room; Gravit organizes it with `dispatch`. Caps per
operator message: 3 rounds, 10 bot messages, 2 peer continuations per round. The operator's
`@<bot>` reaches a voice directly. An `@` naming nobody on the roster reaches Gravit as an
ordinary prompt; no voice answers it, so the answer is Gravit's own.

## Tests

`python -m pytest` at the repo root: offline, no keys. Keep it green.

## Never edit

`data/pit/` contents; `dsh/profile/` and the installed dsh profile copies under the harness
home; anything under `bots/` (a bot may write its own `journal/`) or `roles/` (propose in
conversation — the operator authors them); `docs/research/`.
