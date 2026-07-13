# Stock-stage clock — the third of the three growth clocks (§1.3)

> Spec. 2026-07-13. Owner: KairosPan. Executes the manuscript §1.3 (`个股时钟·stage`) as a PURE LEAF
> module, mirroring P2's `GrowthMarketClock` (market, §1.1) and the theme clock (`GrowthThemeClock`,
> §1.2) — same hysteresis / forward-state-machine / honest-proxy / explicit-abstain discipline, one
> scale further down. Also builds the §1.4 `event_reread` DETECTOR (the forced-high-scale-reread
> trigger set). Leaf-only: no state-consume wiring, no cadence orchestration (both deferred, exactly
> as the theme clock deferred its `clock_cadence` action wiring).

## 1. Goal & framing

The growth doctrine's §1 fractals the single momo day-level sentiment cycle into **three clocks, one per
scale** (§0 序章): market (§1.1, shipped P2), theme (§1.2, shipped), **stock (§1.3, this spec)**. Each
clock is a READ — an `s_t`-side label, never written back into `H` (SSOT), exactly like `GCycle` /
`GrowthMarketClock` / `GrowthThemeClock`. This is the STOCK scale: a per-symbol lifecycle placement.

**Vocabulary** — Option-B scale-typed tokens (the `market:x` / `theme:x` precedent):
`stock:base` / `stock:advance` / `stock:top` / `stock:decline`. Plus one **non-stage flag**
`climax_run` (§1.3: 减仓语言，不是加仓语言).

> **`stock_stage`**（道）：只在 advance（Stage 2）做多。base 是机构建仓的形态学证据（数周计）；
> top 的语言是放量滞涨与 distribution day，不是"分歧转一致再上一波"——日级接力读法勿迁移
> （轮回锚 → A-14）；climax run（远离均线的末段加速）是减仓语言，不是加仓语言。

### 1.1 The four stages + the climax flag

| §1.3 stage | Manuscript prose | Raw-input signature (derived from `StockSnapshot` history+today) |
|---|---|---|
| `base` | 机构建仓的形态学证据（数周计）：sideways/quiet, NOT yet in a confirmed advance. Pre-cycle. | the default machine state; no confirmed breakout signature yet |
| `advance` | Stage 2 uptrend — **the only stage the doctrine allows going long** | close **above a rising** trailing SMA + **market confirmation** (`rs_percentile` strong) + a real up-run (`consecutive_up_days`) |
| `top` | 放量滞涨与 distribution day (distribution language) | a cluster of **distribution/stall days** (elevated `rvol` with no price progress) since the advance anchor — NOT "分歧转一致再上一波" (A-14: the A-share daily-relay top read does NOT migrate) |
| `decline` | below/through the trailing SMA, RS deteriorating | a **sustained** close below the trailing SMA while RS is no longer strong |

**`climax_run` (a flag, NOT a stage).** End-stage acceleration far above the trailing SMA (large positive
distance-from-SMA + accelerating). This is **REDUCE language, never ADD language** — surfaced as
`StockStageReading.climax_run: bool`, not as a buy stage. A parabolic stock stays `stock:advance` (still
the only-long stage, structurally) with `climax_run=True` (reduce into strength) — distinct from
`stock:top` (distribution confirmed).

### 1.2 Honest proxies (limits STATED, not assumed — the growth-clock index-volume-proxy discipline)

`StockSnapshot` carries **no moving-average field and no multi-week base data**. Every structural signal
is DERIVED, trailing-only, from the close-history sequence. Each proxy and its limit:

| Signal | Honest proxy | Limit (待verdict校准) |
|---|---|---|
| trailing SMA | `SMA_WINDOW`-day mean of trailing closes (indices ≤ today) | The manuscript's full trend template (§4.1) wants 50 **and** 150 **and** 200-day structure. We proxy with the SINGLE `SMA_WINDOW`=50-day line (§4.7's designated "关键均线") because (a) it is the rule's key line and (b) requiring 200 closes would abstain on most stocks. |
| rising SMA | SMA today > SMA `SMA_SLOPE_LOOKBACK` days ago | slope over ~2 weeks; a shorter/longer slope window moves the base rate |
| above SMA | close > trailing SMA | — |
| distribution / stall day | elevated `rvol` (≥ `RVOL_ELEVATED`) with pct_change ≤ `STALL_PCT` (down or flat on volume = 放量滞涨) | `volume` is the only volume primitive; `rvol` may be **thin/None** — then the leg is simply not satisfied (never fabricated) |
| base vs advance | leans on `consecutive_up_days` + `rs_percentile` + the SMA structure (per the task) | absent `consecutive_up_days` the clock conservatively **holds base** (graceful degradation, never a fabricated advance) |
| climax | distance-from-SMA ≥ `CLIMAX_DIST` **and** accelerating (a sharp thrust `pct_change ≥ CLIMAX_PCT`, or a long `consecutive_up_days ≥ CLIMAX_RUN_DAYS`) | acceleration is proxied by a single-day thrust or a persistent up-run; a true tick-level parabola detector is deferred |

**Graceful degradation, never fabrication.** Thin HISTORY (< `MIN_HISTORY` priced days, or no close
today) ⇒ the clock ABSTAINS (returns `None`, the group being absent — §0.2 禁止补格). Thin VOLUME (`rvol`
None) ⇒ the distribution leg cannot be satisfied, so a `top` is **never fabricated** from missing volume —
the stage read from price/SMA/RS still stands.

### 1.3 §1.4 `event_reread` detector

> **`event_reread`**（道）：指定事件（持仓龙头放量破位、laggard 批量启动、breadth 崩塌、
> 财报后 gap 不回补方向反转）**强制触发高尺度时钟即时重读**，覆盖任何节拍表。

`detect_stock_reread_events(...)` is a **pure detector** — given the signals, it returns the set of
triggers PRESENT (a `frozenset[str]` of `reread:*` tokens). It builds the DETECTOR only; the
cadence-orchestration wiring (there is no live three-clock orchestrator yet) is DEFERRED, exactly as the
theme clock deferred its `clock_cadence` action wiring. Where a trigger needs a signal `StockSnapshot`
does not carry, it is taken as an explicit function argument and documented:

| Trigger (§1.4 / §4.7) | Detection | Signal taken as an arg (not in `StockSnapshot`) |
|---|---|---|
| `reread:leader_breakdown` (§3.3, 持仓龙头放量破位) | a fresh break of the key trailing SMA on elevated volume: prior close ≥ prior SMA, today close < today SMA, `rvol ≥ LEADER_BREAKDOWN_RVOL` | `is_leader: bool` — a **designated** portfolio leader (no "am I a leader" field exists); degrades to no-fire when history < `SMA_WINDOW` |
| `reread:laggard_batch` (§3.4, laggard 批量启动) | `laggard_ignitions ≥ LAGGARD_BATCH` — a TIMER not a target (`laggard_timer`) | `laggard_ignitions: int` — a **count** of same-theme non-leaders igniting today (one snapshot cannot see the batch) |
| `reread:breadth_collapse` (breadth 崩塌) | `breadth_collapse` true | `breadth_collapse: bool` — a market/theme breadth read (not a per-stock field) |
| `reread:earnings_gap_reversal` (财报后 gap 不回补方向反转) | post-earnings gap ≥ `EARNINGS_GAP` that **reversed direction** (gapped up, closed down — or the mirror): `sign(gap_pct) ≠ sign(pct_change)` | `earnings_event: bool` — whether today is a post-earnings session (no earnings-date field; that is the P5a feed, not wired here). The "反论点方向 / against-thesis" refinement needs a thesis-direction arg — deferred to the consumer that holds the thesis. |

## 2. Key decisions

### 2.1 A forward state machine with hysteresis (P1/P2's lesson, one scale further down)

**P1/P2's HIGH bug was a memoryless per-day classifier that FLICKERS.** We do not repeat it: the stock
clock is a **deterministic state machine replayed forward** over the symbol's priced history + today — a
*pure function of (history, today)* with no hidden mutable state (recomputable; same inputs → same read),
exactly like `_run_machine` / `_run_theme_machine`.

The lifecycle is a **forward progression** (`base → advance → top → decline → base`), which delivers
hysteresis structurally. The asymmetry mirrors the siblings: *improving* transitions fire on a confirmed
signature; *regressive/terminal* ones are guarded by a confirmation count so **an isolated weak day cannot
un-confirm an advance**:

- **`base → advance`** needs a **real breakout signature** (above a rising SMA + `rs_strong` +
  `consecutive_up_days ≥ BREAKOUT_MIN_RUN`), NOT a single up day — the multi-factor signature IS the
  confirmation (a single up day gives `consecutive_up_days = 1 < BREAKOUT_MIN_RUN` and cannot lift a stock
  above a *rising* 50-day SMA). This is the analog of P2's "a single FTD re-confirms" — but the signature
  itself structurally rules out a one-day promotion. Entering advance sets the `advance_anchor`.
- **`advance → top`** needs `dd_count ≥ TOP_CONFIRM` distribution/stall days since the anchor (window-
  capped at `DD_WINDOW`) — the analog of P2's `DD_UNDER_PRESSURE` count. An isolated distribution day
  (count < `TOP_CONFIRM`) does NOT flip a confirmed advance. **This is the pinned no-flicker property.**
- **`advance → decline` / `top → decline`** need `below_run ≥ DECLINE_CONFIRM` consecutive closes below
  the SMA while `not rs_strong` — a sustained structural break, not a one-day dip (the `DEEP_MIN_DAYS`
  analog). A still-elite leader (`rs_strong`) gets the benefit of the doubt (龙头不倒题材不死).
- **`top → advance`** on a fresh breakout signature (a shakeout resolved up); **`decline → base`** on
  `above_run ≥ DECLINE_CONFIRM` reclaimed closes (re-accumulation — a reclaim goes to base, never straight
  to advance; a fresh breakout is still required, so no base is skipped).

All thresholds are named module constants tagged 文献值待verdict校准 (no Refiner-calibration path — the
same posture as both sibling clocks).

### 2.2 Abstain is explicit — never silently a stage (§0.2 禁止补格)

Two abstention paths, rendered as the clock returning `None` (the read is ABSENT, never a fabricated
stage):

1. **No close today** — a symbol with no `close` today cannot be read → `None`.
2. **Warm-up** — fewer than `MIN_HISTORY` (= `SMA_WINDOW + SMA_SLOPE_LOOKBACK`) priced days across
   history + today: we cannot determine a *rising* trailing SMA for today, so we cannot tell base from
   early-advance → `None`. (The theme clock's warm-up-abstains posture, NOT the market clock's
   conservative-`under_pressure` posture: there is no "conservative stock stage" — `base` is a real,
   informative read, not a risk level.)

Post-warm-up the machine always returns one of the four real stages (`base` being the honest default for
"quiet / not advancing"); `base` is a placement, not an abstain.

### 2.3 The read is per-symbol, history-symmetric, and PIT-safe

`classify_stock_stage(history, today)` (the callable, like `theme_lifecycle`) and `StockStageClock.read`
(the class face, like `GrowthThemeClock.read` — an `s_t`-side surface) both take a chronological
`Sequence[StockSnapshot]` (strictly prior) + today, filter to priced snapshots (dropping no-close days
like P2 drops 0/0 feed-outage days), replay the machine, and return a frozen
`StockStageReading(symbol, stage, confidence, climax_run)` or `None`.

**PIT-safety.** The SMA at day `i` is `mean(closes[i-SMA_WINDOW+1 : i+1])` — strictly trailing (indices
≤ `i`); the machine only reads day `j ≤ i`. A future close cannot leak into today's SMA (pinned by a
direct `_sma` trailing-only test + purity). `history` is strictly prior to `today` by the caller's
contract; the clock never re-fetches or re-ranks. Confidence is a fixed `_CLASSIFIED_CONF` 待校准 (warm-up
already abstains, so every returned read is full-history).

## 3. Files (pure leaf — NEW files only, no existing file edited)

New:
- `alpha/regime/stock_clock.py` — `StockStageClock` + `classify_stock_stage` + `StockStageReading` +
  `detect_stock_reread_events` + the lifecycle thresholds (named constants 待校准) + `_run_stock_machine`
  / `_features` / `_sma` (the pure forward replay, exposed for oracle auditing). Imports only
  `alpha.universe.stock` (the reading type) — a leaf, upstream of any consumer; no import cycle
  (`alpha.universe.stock` imports only pydantic/typing; nothing in `alpha.regime` imports it yet).
- `tests/regime/test_stock_clock.py` — the four-stage truth table on synthetic close/rvol tapes; the
  only-long-in-advance property; warm-up→abstain (non-fabrication); no-flicker (an isolated weak day does
  NOT flip a confirmed advance); base→advance needs a real breakout not one up day; top = volume-stall +
  distribution NOT a daily-relay read; the `climax_run` flag (far-above-SMA, REDUCE not a buy stage);
  PIT-safety (trailing-only SMA); each `event_reread` trigger fires on its signal and stays silent
  otherwise; graceful abstain on thin volume/history; purity/determinism; boundary probes per threshold.

NO existing file is edited (the state-consume wiring is a DEFERRED follow-up). Verified: neither
`alpha/regime/*` nor any TCB member is touched.

## 4. Acceptance

- Full offline suite green (keyless); baseline 1832 held + the new tests (this arc touches no existing
  file, so 1832 must remain and the new tests add on top).
- Scoped run green: `python -m pytest tests/regime -q`.
- **No-flicker pinned**: a confirmed advance with one isolated distribution day stays `stock:advance`; a
  sustained cluster (≥ `TOP_CONFIRM`) flips to `stock:top` — the P1/P2 stability lesson, one scale down.
- **Only-long-in-advance**: `stock:advance` is the sole stage the doctrine allows going long; pinned so
  the token is stable.
- `python scripts/gen_tcb_lock.py --check` prints `[]` / exit 0 (no TCB member touched).
- Lint-clean on the new files (ruff/style; `from __future__ import annotations`, frozen dataclasses).

## 5. Known limits (待verdict校准)

| Limit | What / why | Candidate fix (deferred) |
|---|---|---|
| **Single-SMA proxy** | One 50-day derived SMA proxies the manuscript's 50/150/200-day trend template. | Thread real multi-SMA structure once a longer close history / MA feed exists. |
| **Slow-fade dead band** | A stock that drifts down slowly (no `DECLINE_CONFIRM`-consecutive break, no distribution cluster) holds `advance` — the P2 dead-band analog. | A mean-distance-since-anchor floor or a slow-decay timeout (both move the base rate → verdict decisions). |
| **`consecutive_up_days`-dependent advance** | Absent the up-run signal, the clock holds base (never fabricates an advance). | A pivot-breakout detector on the close series (needs base-shape geometry). |
| **Thresholds are literature values** | Every constant is 文献值待verdict校准 (no Refiner-calibration path — same posture as both sibling clocks). | H-params metatool (deferred, as in P2 §5). |

## 6. Out of scope / carried forward (the handoff)

- **State-consume wiring** — threading a per-symbol stock stage into the decide path (a `StockSnapshot`
  field, a builder pass-through, or a per-candidate placement in the agent prompt / guard). This spec is
  a pure leaf; the consume step is a separate activation, mirroring how P2 shipped the market clock
  before its live history threading and the theme clock shipped before its `MarketState.theme_breadth`
  threading.
- **§1.4 `clock_cadence` authority wiring** — high-scale vetoes low-scale (market vetoes theme vetoes
  stock); the stock stage modulating appetite/guard/sizing (`breakout_entry.rule`, `derisk_on_breakdown`).
  This spec produces the stage label + the `event_reread` trigger set; wiring them into a live three-clock
  orchestrator (which does not exist yet) is a separate step.
- **The `event_reread` against-thesis refinement** — `reread:earnings_gap_reversal` currently fires on a
  technical direction-reversal; the §4.7 "反论点方向" (against the thesis) refinement needs a
  thesis-direction arg, deferred to the consumer that holds the thesis card.
