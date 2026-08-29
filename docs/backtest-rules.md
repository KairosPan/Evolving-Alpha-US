# Backtest Rules (honest-eval, carried from the old product)

Every backtest in strategies/ MUST follow these. They exist because each one was a real
bug class once.

1. **PIT channel only.** Iterate days with `alpaca_kit.replay.replay_days` and use the
   yielded `GuardedSource`. Never open the parquet files directly in a backtest loop.

   **Usable bed windows.** A bed's `trading_calendar()` spans the full captured calendar
   (2016-01-04 onward), but only part of it has snapshots. Always bound the replay:

   | bed | usable window | trading days |
   |---|---|---|
   | `data/pit/2yr` | 2024-06-03 .. 2026-07-09 | 526 |
   | `data/pit/broad` | 2025-11-17 .. 2026-03-27 | 90 |

   Dates outside a bed's window raise `SnapshotMissingError` by design — fail-loud, never
   silent. An unbounded `replay_days(pit_root=...)` therefore walks 2016 first and crashes;
   pass `start=`/`end=` (the template's `BED_START`/`BED_END`).

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
