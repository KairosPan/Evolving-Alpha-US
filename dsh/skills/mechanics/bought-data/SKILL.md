---
name: bought-data
description: How to buy vendor data with the wallet into a strategy and turn it into a replayable PIT bed
---

# Bought data (neutral mechanics)

Always applies when a strategy pays for data. Python cannot pay: only `wallet_pay` in a strategy
channel can, and it writes the vendor's bytes under `strategies/<name>/vendor/`. A backtest never
reads those files (backtest-rules rule 1); they go through `capture_window` into a PIT bed and are
replayed like any other bed. Six steps, in order.

1. **Discover.** `wallet_discover({query: "daily bars", max_usd: "0.05"})`. Read `price_usd`
   and `payers_30d`; `resource` is a URL template. The catalogue price (or the vendor's documented
   price — vendor-sim is $0.01 per call) sizes the budget in step 2; step 3 confirms it on the
   concrete URL before any money moves. `discovery_unavailable` means the catalogue is down, not
   the wallet: a URL you already know still works. On the local chain the real catalogue answers
   `ok` with 0 payable resources (nothing on `eip155:31337` is listed) — that is honest, not a
   failure; go on with the vendor's documented price.
2. **ONE budget, sized from the catalogue price.** Budget = tickers × windows × price + headroom;
   `per_call_usd` = that price. `wallet_budget_request({purpose: "<vendor> bars <tickers>
   <from>-<to>", limit_usd, per_call_usd: "<price>", hosts: ["<vendor host>"],
   valid_for_hours: 24})`, then STOP until the card is answered. A denial is a tool error you
   read, not a reason to re-ask wider. The budget comes FIRST: in the face every wallet tool that
   touches a host — `wallet_offer` included — is pre-flighted against a held mandate naming that
   host, and without one it is refused `mandate_required` before signing (drilled 2026-09-21).
3. **Confirm the price.** `wallet_offer` the concrete aggregates URL ONCE (free, no card). The
   quoted `amount_usd` must not exceed the budget's `per_call_usd`; if it does, stop and request
   a new budget sized to the quote — never pay into a price you did not budget for. Pay
   sequentially only (R-W4: the hosted facilitator fails most concurrent settlements — 3 of 5
   measured); never fan the buys out to child tasks.
4. **Buy.** One `wallet_pay` per ticker per window, in sequence:
   `wallet_pay({url: "https://<host>/v2/aggs/ticker/<T>/range/1/day/<from>/<to>?adjusted=false&sort=asc&limit=50000",
   save_to: "massive/<TICKER>/<from>_<to>.json"})`. `adjusted=false` is not optional: the
   vendor's default is adjusted and the reader refuses it. Record `saved.sha256` (the receipt) and
   `tx` per file in `journal.md` (the tool envelope's names: `tx`, `ledger_status`, `amount_usd`). The result carries a 1 KB preview, not the body;
   never read the JSON in a backtest. A refusal (`host_not_allowed`, `mandate_insufficient_budget`,
   …) is not retried; `ledger_status: "unknown"` → `wallet_reconcile` before buying the same file again.
5. **Capture.** `ALPHA_DATA_SOURCE=massive_files ALPHA_MASSIVE_ROOT=strategies/<name>/vendor/massive
   python scripts/capture_window.py <from> <to> data/pit/massive-<from>-<to> <TICKERS>`.
   `data/pit/` is outside your channel's sandbox: hand the command to the operator or take the
   escalation card, never work around it. Then `verify_checksums(root, fail_closed=True)`
   (`alpaca_kit.pit.integrity_check`) on the new bed.
6. **Replay.** `ALPHA_PIT_ROOT=data/pit/massive-<from>-<to>` and `replay_days` bounded to the
   bought window. THESIS.md MUST state: this bed has NO corp actions (`corp_actions` answers
   `artifact missing`, never "clean"; a split inside the window is invisible, rule 4) and its
   calendar = the bought window (union of bar dates: a day no file covers is not a trading day, a
   symbol's missing day is a gap, rule 5). Delisting shows only as bars vanishing (rule 2).

What the reader (`alpaca_kit/feeds/massive_files.py`) refuses, naming the file: `adjusted` not
literally `false` (missing counts), `status` not `"OK"`, body `ticker` ≠ the directory it sits in,
a row missing any of `t/o/h/l/c/v`, and two files giving different OHLCV for one date. `vw`/`n`
are dropped. Fix the file or re-buy; never edit vendor bytes.

Drill targets: the vendor simulator on the local chain, `http://127.0.0.1:4022` (`npm run
vendor-sim` in `payment/`, $0.01 per call, Massive-shaped, no holidays, no corp actions; budget host
`127.0.0.1:4022`), or a Sepolia sim URL when one exists. Real Massive is Base mainnet only — not this
round.

Bought news (`/v2/reference/news?ticker=&limit=`) is interactive evidence with NO PIT guard, like an
AKShare read: cite it in a journal, never as replay/backtest evidence.
