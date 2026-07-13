# P5b-consumer — Growth theme-lifecycle clock (the second of the three clocks)

> Spec. 2026-07-13. Owner: KairosPan. Executes the P5b spec's deferred **theme-CLOCK consumer step**
> and DEVELOPMENT-PLAN §1 P5's *"per-narrative-line regime read"* first half: the DATA→PHASE step that
> reads P5b's per-group breadth signals and places each sector/theme group on the manuscript's §1.2
> lifecycle (`emerging → institutional → public_laggard → exhaustion`). Mirrors P2's `GrowthMarketClock`
> (the market clock over P0.4 breadth) — same hysteresis / state-machine discipline, one scale down.

## 1. Goal & framing

The growth doctrine's §1 fractals the single momo day-level sentiment cycle into **three clocks, one per
scale** (§0 序章): market (§1.1, shipped P2), theme (§1.2, *this spec*), stock (§1.3, deferred). Each
clock is a READ — an `s_t`-side label, never written back into `H` (SSOT), exactly like `GCycle` /
`GrowthMarketClock`.

P5b built the theme clock's **feed + signals** (`alpha/features/theme_breadth.py::theme_breadth` →
`ThemeBreadthReading`), stopping deliberately at the DATA and naming the consumer as a separate later
step (P5b spec §4 "deferred consumer handoff"), exactly as P0.4 built the market-breadth family that P2
later consumed. This spec is that consumer: a deterministic classifier `GrowthThemeClock` that reads a
per-group breadth **history** and today, and assigns each determined group a lifecycle phase.

**Vocabulary** — Option B scale-typed tokens (the `market:x` / `stock:x` precedent from
`alpha/harness/growth_regime.py` and P2's `market:confirmed_uptrend`):
`theme:emerging` / `theme:institutional` / `theme:public_laggard` / `theme:exhaustion`.

**A "theme" here = a sector group** from P5b's `SectorMap` partition (the coarse static-bootstrap
groups, or a real GICS/IBD feed once swapped in). This is the DATA→PHASE half. The **per-candidate
narrative clustering** half (dynamic theme discovery — the plan's "other half") is a separate deferred
step; §6 records the handoff.

### 1.1 §1.2 read: composition, not sentiment

> `theme_lifecycle`（道）：读的不是群体情绪而是**持仓构成——现在是谁在买**。

The clock reads WHO IS BUYING through P5b's breadth composition signals — never a price/sentiment band.
The four phases map to the raw inputs P5b exposes on each `GroupBreadthReading`:

| §1.2 phase | Manuscript prose | Raw-input signature (P5b fields) |
|---|---|---|
| `emerging` | 产业事实先行，内行与先手资金建仓，龙头浮现 | breadth **rising off a low base** (`breadth_trend` up, `pct_above_200dma` not yet broad) + **leaders leading** (`rs_dispersion` **wide**) + RS improving (`rs_trend` ≥ 0) |
| `institutional` | 机构接力，财报开始兑现，本稿主战场 | **broad participation** (`pct_above_200dma` **high**) + breadth & RS **trending up together** (`breadth_trend` ≥ 0, `rs_trend` up) |
| `public_laggard` | 大众进场、跟风股与后排补涨启动——计时器拨响 | laggards catching up = `rs_dispersion` **COMPRESSING** from its cycle peak while breadth **still high** — the `laggard_timer` (§3.4 / A-08) |
| `exhaustion` | 轮动加速、边缘概念起舞、兑现不再推动股价 | breadth **rolling over** (`breadth_trend` down) + RS **trend down** (`rs_trend` down); A-09 轮动加速=尾声 |

**The `laggard_timer` (§3.4, 反转★).** `rs_dispersion = leader_rs_mean − laggard_rs_mean`. A **wide**
gap = leaders dominate (emerging/institutional); a **compressing** gap = laggards catching up. Because
dispersion is `leader − laggard` and `public_laggard` additionally requires breadth to stay HIGH
(leaders have NOT collapsed), a compression-under-high-breadth necessarily means the **laggards rose** —
i.e. the clock is differencing `laggard_rs_mean` upward exactly as the doctrine asks, expressed through
the more-robust dispersion-from-peak measure. This is a **计时器不是标的** signal: it changes the theme's
phase (and, downstream, appetite), it is not a buy list — the momo "补涨还能吃一口" reflex is a 禁手 here
(A-08: public 期追补涨=momentum-crash 陷阱).

## 2. Key decisions

### 2.1 A forward state machine with hysteresis (P2's lesson, applied one scale down)

**P1/P2's HIGH bug was a memoryless per-day classifier that FLICKERS** (the ABAB day-parity oscillation
`GrowthMarketClock` fixed with an FTD anchor). We do **not** repeat it: the theme clock is a
**deterministic state machine replayed forward** over each group's determined-reading history + today —
a *pure function of (history, today)* with no hidden mutable state (recomputable; same inputs → same
read), exactly like `_run_machine`.

The lifecycle is a **forward progression** (`dormant → emerging → institutional → public_laggard →
exhaustion → dormant`), which delivers hysteresis structurally: each state **persists until the next
transition's condition is met**, so an isolated weak reading cannot re-derive the phase. Two extra
guards mirror the market clock:

- **A cycle-peak dispersion anchor** (the analog of P2's FTD anchor): `peak_dispersion` = the max
  `rs_dispersion` seen since the current cycle began (updated only while `emerging`/`institutional`,
  frozen thereafter, reset on return to `dormant`). `public_laggard` fires only on a real **compression
  from a wide peak** (`disp ≤ peak − DISPERSION_COMPRESS` with `peak ≥ DISPERSION_WIDE`) — so a group
  that never had leaders dominating never "rings the laggard timer".
- **A sustained-run guard on the terminal transition** (the analog of P2's `DEEP_MIN_DAYS`): the
  `→ exhaustion` flip requires the exhaustion signal (`breadth_trend` rolling over AND `rs_trend`
  falling) to hold for `EXHAUSTION_CONFIRM` **consecutive** determined readings. A single weak reading
  (run = 1) does NOT flip `institutional → exhaustion`. **This is the pinned no-flicker property.**

Forward *improving* transitions (`emerging → institutional`) fire immediately (an improvement is
harmless); *regressive/terminal* ones (`→ exhaustion`) are the ones guarded — the same asymmetry as
P2's "isolated weakness does not un-confirm, a single FTD re-confirms".

**Transition table** (all predicates None-guarded — a missing signal never satisfies its leg; the group
reading's own `determined=False` days are dropped from the series like P2 drops 0/0 feed-outage days):

```
DORMANT (abstain / pre-cycle):
    rising & wide_dispersion & not broad          → EMERGING        (rising off a low base, leaders leading)
    broad & rs_up                                 → INSTITUTIONAL   (arrive-late: already broad participation)
    else stay DORMANT

EMERGING:
    broad & not rolling_over & rs_up              → INSTITUTIONAL   (participation broadened)
    low_base & not rising                         → DORMANT         (emergence fizzled — not "exhaustion")
    else stay EMERGING

INSTITUTIONAL:
    exhaustion_run ≥ EXHAUSTION_CONFIRM           → EXHAUSTION      (sustained roll-over + RS down)
    broad & disp≤peak−DISPERSION_COMPRESS
          & peak≥DISPERSION_WIDE                  → PUBLIC_LAGGARD  (laggard_timer: compression, breadth high)
    else stay INSTITUTIONAL

PUBLIC_LAGGARD:
    exhaustion_run ≥ EXHAUSTION_CONFIRM           → EXHAUSTION
    else stay PUBLIC_LAGGARD                       (a late warning holds until the roll-over confirms)

EXHAUSTION:
    low_base                                      → DORMANT         (theme over; ready for a fresh cycle)
    else stay EXHAUSTION
```

Predicates (named constants, all 文献值待verdict校准; note the **two scales** — `pct_above_200dma` /
`breadth_trend` are fractions in [0,1], while `rs_*` are cross-sectional **percentiles in [0,100]**):
`broad = pct_above_200dma ≥ BREADTH_HIGH`; `low_base = pct_above_200dma < BREADTH_LOW_BASE`;
`rising = breadth_trend ≥ BREADTH_RISING`; `rolling_over = breadth_trend ≤ BREADTH_ROLLING_OVER`;
`rs_up = rs_trend ≥ RS_RISING`; `rs_down = rs_trend ≤ RS_FALLING`;
`wide_dispersion = rs_dispersion ≥ DISPERSION_WIDE`; the exhaustion signal = `rolling_over AND rs_down`.

### 2.2 Abstain is explicit — never silently a phase

Three abstention paths, all rendered as **the group being ABSENT from the returned mapping** (never a
fabricated phase — the doctrine's §0.2 禁止补格 discipline):

1. **Undetermined today** — the group is `determined=False` in `today` (P5b: `member_count < min_members`
   or all-None signals). We cannot read a group we cannot see today. (The market clock's "empty 0/0 today
   abstains" analog — but here abstention is per-group and returns nothing rather than carrying a
   market-wide state forward.)
2. **Warm-up** — fewer than `MIN_HISTORY` determined readings for the group across history + today: no
   trajectory to anchor a lifecycle (the market clock's `MIN_HISTORY` warm-up, which there returns a
   conservative `under_pressure`; here we abstain, because there is no "conservative lifecycle phase" —
   a lifecycle is a position in a story, not a risk level).
3. **Dormant** — enough history, but the machine ends in `dormant`: a determined-but-flat group with no
   active theme (breadth not rising, not broad). Labeling it `emerging` would fabricate a story; it
   abstains. `dormant` is an internal machine state, never an exposed token.

So the exposed vocabulary is exactly the four `theme:` tokens; everything else is silence.

### 2.3 The read is per-group and history-symmetric

`GrowthThemeClock.read(history, today)` mirrors `GrowthMarketClock.read(history, today)`: `history` is a
chronological `Sequence[ThemeBreadthReading]` (strictly prior), `today` the current `ThemeBreadthReading`.
For each group present-and-determined in `today`, the clock gathers that group's determined readings from
`history` (dropping undetermined days) + today's reading, replays the machine, and emits the final state.
Returns `dict[str, ThemeLifecycleRead]` keyed by group, containing **only** the placed groups.
`ThemeLifecycleRead(group, phase, confidence)` is a frozen dataclass paralleling `RegimeRead` (a future
§1.4 `clock_cadence` consumer wants structured access; confidence is a fixed `_CLASSIFIED_CONF` 待校准,
since warm-up already abstains so every returned read is "full-history").

Like P2's verdict symmetry, the clock reads the caller-provided history and holds no per-instance state,
so two arms fed the same `ThemeBreadthReading` sequence produce identical reads (symmetric by
construction — the read is a pure function of its arguments).

### 2.4 Additive perception exposure — `MarketState.theme_breadth` (P0.4→P2 precedent)

P5b specified the one-field additive change and left it out of its footprint. This spec makes it:

- `alpha/state/market.py` — `MarketState` gains `theme_breadth: ThemeBreadthReading | None = None`
  (importing the type from `alpha.features.theme_breadth`; no import cycle — `theme_breadth.py` imports
  only `alpha.data.sector_map` + `alpha.features.{breadth,trend_template}`, none of which import
  `alpha.state`/`alpha.regime`, verified).
- `alpha/state/builder.py` — `build_market_state` gains `theme_breadth: ThemeBreadthReading | None = None`
  threaded straight onto the model. **Default None ⇒ every current caller's `MarketState` is
  byte-identical** (`model_dump()` gains one `theme_breadth: None` key both sides — the exact P0.4
  breadth-family pattern, `test_off_is_byte_identical_to_no_breadth`).

The theme clock then reads `state.theme_breadth.groups[group]` to place each group. Threading the feed
**live** (computing `theme_breadth` per day in the loop/walk-forward drivers, on the weekly `clock_cadence`
of §1.4) is a separate activation step, out of this footprint — this spec builds the classifier + the
additive seam and leaves the field default-None (DORMANT/inert: no theme_breadth threaded ⇒ no theme
phases ⇒ byte-identical), exactly as P2 shipped the market clock before P2's own live history threading.

### 2.5 PIT-safety

The clock is a pure forward replay of trailing-only inputs: every `GroupBreadthReading` in `history` was
built by P5b's `theme_breadth()` under the caller's `GuardedSource(AsOfGuard(day))` (windows close ≤ day;
prices RAW/unadjusted, split caveat inherited). The clock's hysteresis reads **prior** state from history,
never a future reading; `history` is strictly prior to `today` by the caller's contract. No lookahead is
introduced. RS/breadth scales are as P5b emits them (percentile 0–100 for `rs_*`, fraction 0–1 for
breadth) — the clock never re-fetches or re-ranks.

## 3. Files

New:
- `alpha/regime/theme_clock.py` — `GrowthThemeClock` + `ThemeLifecycleRead` + the lifecycle thresholds
  (named constants 待校准) + `_run_theme_machine` (the pure forward replay). Imports only
  `alpha.features.theme_breadth` (reading types) — a leaf, upstream of any consumer.
- `tests/regime/test_theme_clock.py` — the four-phase truth table on synthetic per-group tapes;
  hysteresis / no-flicker (isolated weak reading holds institutional); the laggard_timer
  (dispersion-compression → public_laggard); the peak anchor (compression without a wide peak does NOT
  ring); undetermined / warm-up / dormant abstain; purity; boundary probes on every threshold.
- `tests/state/test_theme_breadth_field.py` — `MarketState.theme_breadth` additive default-None +
  byte-identity + threaded-populates (the P0.4 pattern, for the theme bundle).

Changed (all NON-TCB — verified: neither `alpha/regime/*` nor `alpha/state/*` is in `tcb.lock`):
- `alpha/state/market.py` — `theme_breadth: ThemeBreadthReading | None = None` additive field.
- `alpha/state/builder.py` — `build_market_state` gains the `theme_breadth` pass-through param.

## 4. Acceptance

- Full offline suite green (keyless); baseline 1775 held + the new tests.
- **No-flicker pinned**: an institutional group with one isolated weak reading (roll-over + RS down for a
  single reading) stays `theme:institutional`; a sustained run (≥ `EXHAUSTION_CONFIRM`) flips to
  `theme:exhaustion` — the P2 stability lesson, one scale down.
- **Byte-identity**: `build_market_state(..., theme_breadth=None)` == omitting it (`model_dump()` equal);
  momo + growth market paths untouched (this arc adds only an additive field + a leaf module nobody wires
  yet).
- `lint_doctrine` 0, `gen_tcb_lock --check` 0.

## 5. Known limits (待verdict校准)

| Limit | What / why | Candidate fix (deferred) |
|---|---|---|
| **Slow-fade dead band** | A group whose breadth drifts down slowly (no sharp `rolling_over`, no dispersion compression) holds `institutional` — the theme-clock analog of P2's 0.41–0.59 dead band. `exhaustion` needs a *confirmed* roll-over; `public_laggard` needs a real compression. | A mean-breadth-since-peak floor, or a slow-decay timeout — both move the base rate, so verdict-calibration decisions. |
| **Coarse groups** | A "theme" is a static-bootstrap sector (P5b's `BOOTSTRAP_SECTORS`), not a real GICS/IBD group nor a dynamic narrative cluster. Cross-sector themes (AI spanning semis+software+power) are not one group. | The real-feed swap seam (P5b §1) + the narrative-clustering half (§6). |
| **Thresholds are literature values** | Every constant is 文献值待verdict校准 (no Refiner-calibration path — the same posture as `GrowthMarketClock`). | H-params metatool (deferred, as in P2 §5). |

## 6. Out of scope / carried forward (the handoff)

- **Live threading of `theme_breadth`** into `MarketState` in the loop / walk-forward / save_decisions
  drivers (compute the P5b bundle per day, on the §1.4 weekly `clock_cadence`, with §4.7 `event_reread`
  as the intra-cadence override). This spec leaves the field default-None; wiring it is the activation
  step, mirroring P2's own DORMANT→live sequence. Needs the market-tape cross-section (the same feed P2's
  `tape_breadth` reads) partitioned by the sector map.
- **Per-candidate narrative clustering** (the plan's "other half"): dynamic theme discovery from the
  agent's `narrative` sympathy key (already emitted for L3 correlation netting) — grouping candidates
  into themes at decision time, distinct from the static sector partition here. A theme there is a
  cluster of correlated picks; the clock's phase logic (§2.1) can then run per-cluster once a cluster
  exposes the same breadth signals. Separate design.
- **§1.4 `clock_cadence` authority wiring** (high-scale vetoes low-scale: market clock vetoes theme
  vetoes stock; theme phase modulates appetite / the guard). This spec produces the theme label; wiring
  it into the guard/sizing surface (the way P2 mapped the market state to `frontside`/`risk_gate`) is a
  separate step — the theme clock has no `frontside`/`risk_gate` yet, it is a pure `s_t` label.
- **The stock clock** (§1.3 `base → advance → top → decline`) — the third clock; separate.
