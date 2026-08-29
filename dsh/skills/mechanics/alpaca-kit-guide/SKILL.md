# alpaca-kit guide (neutral mechanics)

- Interactive queries: use the MCP tools (daily_bars, market_snapshot, screen, breadth,
  earnings, account, positions, orders). Backtests: import alpaca_kit directly and loop
  alpaca_kit.replay.replay_days — never hammer MCP in a loop.
- Which tools exist is decided at server boot from the environment, and a tool that is not
  registered is simply absent (not an error you can retry):
  - `earnings` always — EDGAR is keyless.
  - `daily_bars`, `calendar`, `corp_actions` — APCA keys OR an offline bed (`ALPHA_PIT_ROOT`).
  - `market_snapshot`, `screen`, `breadth` — **`ALPHA_PIT_ROOT` only**. All three read a
    daily cross-section, which exists only on a captured bed: keys alone do NOT give them.
  - `account`, `positions`, `orders` — APCA keys.
  - `place_order`, `cancel_order` — keys AND the operator-only `ALPACA_KIT_ENABLE_ORDERS=1`,
    set outside this workspace. If they are absent, that is the design, not a fault.
- `orders` returns the 50 most recent OPEN orders by default (Alpaca's own default) — pass
  status=closed or status=all when you need the rest.
- Prices are RAW/unadjusted everywhere. A split inside a trailing window fabricates fake
  RS leaders — check corp_actions before trusting a big move.
- Corporate actions are keyed on announce_date := Alpaca process_date (no true announce
  field exists; this is the lookahead-safe key — it lags reality, never leads).
- Bars feed is IEX on free/paper keys (SIP returns 403). History reaches ~2021 only.
- Offline bed: ALPHA_PIT_ROOT=data/pit/2yr (526 days, 2024-06→2026-07, ~800 symbols). No
  warmup: bars start at the window start, so `screen(kind="trend_template")` returns zero names
  before 2025-06-05 and `breadth` returns `pct_above_200dma`/`net_new_highs` as None before
  2025-03-20/2025-06-04 — inside ok=true. The 90-day broad bed never satisfies either.
- Tools are fail-soft: {"ok": false, "error": ...} means fix the call or the env, not retry loops.
  `corp_actions` reports ok=false when the artifact is missing rather than an empty clean
  result — "could not check" is never the same answer as "nothing pending".
- EDGAR earnings are keyed on the FILING date, never the period end.
