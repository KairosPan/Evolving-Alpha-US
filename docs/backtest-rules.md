# Backtest Rules (honest-eval, carried from the old product)

Every backtest in strategies/ MUST follow these. They exist because each one was a real
bug class once.

1. **PIT channel only.** Iterate days with `alpaca_kit.replay.replay_days` and use the
   yielded `GuardedSource`. Never open the parquet files directly in a backtest loop.

   **Usable bed windows.** A bed's `trading_calendar()` spans the full captured calendar
   (2016-01-04 onward), but only part of it has snapshots. Always bound the replay:

   | bed | usable window | trading days | 200DMA valid from | 52-week metrics from |
   |---|---|---|---|---|
   | `data/pit/2yr` | 2024-06-03 .. 2026-07-09 | 526 | 2025-03-20 | 2025-06-04 |
   | `data/pit/broad` | 2025-11-17 .. 2026-03-27 | 90 | never | never |

   Stay inside the stated window: the beds do NOT fail uniformly outside it. A snapshot read
   out of window raises `SnapshotMissingError`, but `daily_bars` and `corporate_actions`
   return an EMPTY frame and say nothing, and `replay_days` is a lazy generator that checks
   nothing at all. So an unbounded `replay_days(pit_root=...)` walks ~2,100 pre-window days:
   a snapshot-driven backtest crashes on day one, while a bars-driven one silently
   undercounts — the hazard rules 2 and 5 exist to prevent. Bounding the replay with
   `start=`/`end=` (the template's `BED_START`/`BED_END`) is the only guardrail.

   **Warmup: the beds carry no lookback.** Bars start AT the window start, so a 200- or
   252-day indicator has nothing behind it for the first year of the replay. The full window
   is replayable; long-indicator readings mature from ~2025-06 on `2yr` and never on `broad`.
   Measured on `2yr`: `screen(kind="trend_template")` returns ZERO names for the first 252 of
   526 days — through 2025-06-03 every symbol trips `insufficient_history` (< 252 closes), on
   2025-06-04 the RS leg alone is still uncomputable (its 12-month return needs 253), and the
   first names appear 2025-06-05. `breadth` reports `pct_above_200dma = None` before
   2025-03-20 and `net_new_highs = None` before 2025-06-04 — inside an `ok: true` envelope.
   On `broad` (90 days) all of those are empty/None on EVERY day. It degrades honestly but
   silently, so a trend or breadth study starts at 2025-06-05, not at `BED_START`, and says
   in its result which start it used.

2. **Delisting is a terminal loss.** A symbol that delists or halts to zero during a hold
   scores -1.0. It is NEVER dropped from the sample (survivorship laundering).
3. **Returns are gross.** No fee/slippage model unless the strategy adds one explicitly —
   and then it says so in THESIS.md.
4. **No same-day round trip.** Decide on day t → enter at t+1 open → exit at t+N close
   (N >= 1). Prices are RAW/unadjusted; splits inside a window distort naive returns —
   check corp_actions before trusting a large move.
5. **Missing data is discarded, never fabricated.** A day without a bar is skipped and
   counted, not interpolated.

Results land in `backtests/YYYY-MM-DD-<label>.json` and record: window, parameters,
sample size, hit rate, mean/median return, worst case, and the count of discarded days.
