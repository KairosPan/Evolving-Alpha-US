# P5b — Theme/sector breadth feed (design)

> Owner: KairosPan · drafted 2026-07-13 (arc-p5b) · status: BUILT (feed + signals; consumer clock deferred)

## Why

DEVELOPMENT-PLAN §1 P5 bullet: *"Per-narrative-line regime read (per-line `GCycle` vs today's global
one) — blocked on a theme/sector breadth feed landing here."* This is the **data prerequisite** for the
growth doctrine's §1.2 **赛道时钟 · lifecycle** (`emerging → institutional → public_laggard → exhaustion`),
the second of the three clocks. The market clock (§1.1) shipped in P2 as the consumer of P0.4's
market-wide breadth family. This spec builds the **feed + per-group signals** for the theme clock,
exactly as P0.4 built the market-breadth family that P2 later consumed. **The theme-CLOCK itself is a
separate later step** — we expose the raw inputs; we do not classify lifecycle states.

## Scope boundary (what this is NOT)

- NOT the theme clock — no lifecycle-state classification, no `GCycle`-per-line, no regime read.
- NOT narrative clustering (the "other half" the plan names) — grouping here is a **static sector map**,
  a deliberately coarse bootstrap standing in for real GICS/IBD industry groups.
- NOT a new data source — every signal is computable from **existing daily bars** + the sector map,
  the same trailing-only way as P0.4's `market_breadth`.

## 1. Sector-map bootstrap + swap seam — `alpha/data/sector_map.py`

A theme/sector membership mapping `symbol → group`. Since no GICS/IBD-group feed exists offline, we ship
a small **static bootstrap table** (`BOOTSTRAP_SECTORS`), documented as a placeholder for a real feed.

**Swap seam** (the data-layer twin of `make_source` / `make_client`):

```python
class SectorMap(Protocol):
    def sector_of(self, symbol: str) -> str: ...   # group key; UNMAPPED ("unmapped") for unknown
    def sectors(self) -> frozenset[str]: ...        # the known group keys (excludes UNMAPPED)

class StaticSectorMap:                              # bootstrap impl over a {symbol: group} dict
    ...

def make_sector_map(name: str | None = None) -> SectorMap:
    # name precedence: explicit arg > ALPHA_SECTOR_MAP env > "bootstrap"
```

A real feed later (GICS via a vendor, or IBD-197 groups) implements the same Protocol and registers one
line in `_SECTOR_MAPS` — a **whole-map swap**, mirroring `make_source`. Callers depend on the `SectorMap`
Protocol, never on the concrete table (dependency injection, like `build_market_state(breadth=…)`).

- Case-insensitive symbol lookup (uppercased). Unknown symbol → `UNMAPPED = "unmapped"` (explicit
  bucket, never a silent drop). The bootstrap groups: `semiconductors, software, internet, hardware,
  biotech, pharma, energy, financials, consumer, industrials, healthcare, communication`.

## 2. Per-group breadth signals — `alpha/features/theme_breadth.py`

Per-group analogs of P0.4's market breadth, computed by **partitioning the cross-section by
`sector_of`** and running the *existing, PIT-tested* `alpha.features.breadth.market_breadth` on each
group's bar subset (maximal reuse — same trailing-only, same undetermined semantics):

- `pct_above_200dma` — fraction of the group above its own 200-day SMA (as-of-latest≤day).
- `net_new_highs` — group 52-week new highs minus new lows (as-of-latest≤day).
- `advances` / `declines` — group advance/decline ON `day` (day-labeled; stale members excluded).
- `rs_mean` / `rs_median` — the group's mean/median **cross-sectional** RS percentile. RS is ranked
  over the **whole universe** (`alpha.features.trend_template.rs_raw_score` → `rs_percentiles`), then
  aggregated per group — a group's RS is its members' standing *relative to the entire tape*, not
  within-group. Same RAW-price split caveat as `trend_template` (documented, inherited).

## 3. Theme-lifecycle raw inputs (§1.2) — additive, NOT classified

The signals a future theme-clock will difference/threshold to place a group on
`emerging → institutional → public_laggard → exhaustion`. Exposed as additive computed fields; **the
clock does the classifying.**

- `rs_dispersion` — within-group leader-vs-laggard RS gap = `leader_rs_mean − laggard_rs_mean`
  (members split at their RS median: bottom-half = laggards, top-half = leaders; odd middle dropped).
  **Wide** = leaders dominate, laggards lag (emerging/institutional). **Compressing** = laggards
  catching up — the doctrine's `laggard_timer` (§3.4 / A-08): *"跟风股与后排补涨批量启动 = 赛道时钟拨向
  public_laggard 的证据"* — the late-stage / `public_laggard` tell.
- `laggard_rs_mean` — the group's bottom-half RS level itself (rising across the weekly cadence = the
  laggard timer ringing; the clock differences it).
- `breadth_trend` — `pct_above_200dma(day) − pct_above_200dma(day − trend_lookback)`; is the group's
  participation broadening or narrowing. Both legs trailing-only (PIT-safe).
- `rs_trend` — `rs_mean(day) − rs_mean(day − trend_lookback)`; is the group gaining/losing relative
  strength vs the whole tape. Both legs re-rank the universe at their own as-of (trailing-only).

`trend_lookback` (default 21 trading days ≈ 1 month, the repo's `SMA200_RISING_LOOKBACK` convention) is
a **calibration surface** (文献值待校准). The earlier as-of is the trading day `trend_lookback` positions
back in the *union of bar dates ≤ day* (a PIT trading-calendar proxy) — never a >day fetch.

### Undetermined semantics (pinned)

A group is **UNDETERMINED** — `determined=False`, **all** signal fields `None` (never a fabricated 0) —
when `member_count < min_members` (default 3; matches the doctrine's "≥3 laggards = a batch" floor and
the general "too few names to read breadth" rule). Layered on top, within a *determined* group each
signal is independently `None` when no member qualifies (no member with ≥200 closes → `pct_above_200dma`
None; no earlier as-of → trends None; <2 ranked members → `rs_dispersion` None). Trailing-only
throughout: a future-dated row is ignored (belt-and-suspenders on the caller's `AsOfGuard`).

## 4. Additive perception exposure + the deferred consumer handoff

The per-day bundle a future regime reader consumes:

```python
class GroupBreadthReading(BaseModel):   # frozen; per group
    group: str; member_count: int; determined: bool
    pct_above_200dma / net_new_highs / advances / declines / rs_mean / rs_median: … | None
    rs_dispersion / laggard_rs_mean / breadth_trend / rs_trend: float | None

class ThemeBreadthReading(BaseModel):   # frozen
    day: Date
    groups: dict[str, GroupBreadthReading]   # keyed by group name (incl. "unmapped")

def theme_breadth(bars_by_symbol, sector_map, day, *, ma_window=200, high_low_window=252,
                  trend_lookback=21, min_members=3) -> ThemeBreadthReading
```

**Handoff to the deferred theme-clock (out of this footprint — REPORTED, not built):** follow the exact
P0.4→P2 pattern. `MarketState` (alpha/state/market.py) gains one additive field
`theme_breadth: ThemeBreadthReading | None = None`, and `build_market_state` (alpha/state/builder.py)
gains a `theme_breadth: ThemeBreadthReading | None = None` param threaded straight through — **default
None ⇒ every current caller's `MarketState` is byte-identical** (the P0.4 breadth-family precedent,
lines 33-38/60-63 of builder.py). The theme clock (a later `alpha/regime` step) reads
`state.theme_breadth.groups[line]` to place each narrative line on the §1.2 lifecycle, on the weekly
cadence (`clock_cadence`, §1.4), with `event_reread` (§4.7) as the intra-cadence override. We build the
DATA + signals; the clock is the separate consumer step, as P2 was for P0.4.

## Firewall / PIT

Prices RAW/unadjusted (split caveat inherited from `trend_template.rs_raw_score`). Every window
trailing-only (date ≤ `day`); the caller assembles each frame via `GuardedSource(AsOfGuard(day))`; this
module never fetches. The earlier-as-of trend leg is chosen from bar dates ≤ day only.

## Tests (TDD)

`tests/data/test_sector_map.py`, `tests/features/test_theme_breadth.py`:
per-group breadth correctness on a synthetic multi-sector tape; RS aggregation (mean/median cross-
sectional percentile); dispersion (wide leaders vs compressed laggards); breadth/RS trend sign; PIT
(a future-dated row ignored); undetermined (tiny/insufficient group → all-None); the sector-map swap
seam (inject a custom map); additive default-None byte-identity (empty map / inert bundle changes
nothing). Offline, keyless, no new deps.

## Deliberately not done

- The theme clock (lifecycle classification) — separate consumer step (REPORTED handoff above).
- Threading `theme_breadth` into `MarketState`/`build_market_state` — out of footprint (alpha/state);
  the exact one-field additive change is specified above for the consumer step.
- A real GICS/IBD feed — the bootstrap table is the placeholder; the swap seam is ready.
- Narrative clustering (dynamic theme discovery) — the plan's "other half"; the static map is the stand-in.
