"""Growth stock-stage clock — the THIRD of the growth doctrine's three clocks (§1.3 `个股时钟·stage`).

The market clock (`alpha/regime/growth_clock.py::GrowthMarketClock`, P2) bands the market's breadth into
three states; the theme clock (`alpha/regime/theme_clock.py::GrowthThemeClock`) places each sector group
on the §1.2 lifecycle. The doctrine fractals the cycle into three scales (§0 序章): this is the STOCK
scale — a PER-SYMBOL lifecycle placement, read from that symbol's own `StockSnapshot` history + today:

  base     -- 机构建仓的形态学证据（数周计）: sideways/quiet, NOT yet in a confirmed advance. Pre-cycle.
  advance  -- Stage 2 uptrend: close above a RISING trailing SMA + market confirmation (rs_percentile
              strong). THE ONLY stage the doctrine allows going long (§1.3: 只在 advance 做多).
  top      -- distribution language: 放量滞涨 + distribution-day evidence. NOT "分歧转一致再上一波" — the
              A-share daily-relay top read does NOT migrate (轮回锚 → A-14).
  decline  -- below/through the trailing SMA, RS deteriorating.

Plus a distinct **non-stage flag** `climax_run` (§1.3): end-stage acceleration far above the trailing SMA
(large positive distance-from-SMA + accelerating). Climax is REDUCE language, never ADD language — it is
surfaced as a flag on the reading, not as a buy stage. A parabolic stock stays `stock:advance` (still the
only-long stage, structurally) with `climax_run=True` (reduce into strength), distinct from `stock:top`
(distribution confirmed).

The tokens are Option-B scale-typed (`stock:base` …), the sibling of P2's `market:confirmed_uptrend` and
the theme clock's `theme:emerging`. This is a READ (an s_t-side label), never written back into H (SSOT),
exactly like GCycle / GrowthMarketClock / GrowthThemeClock.

Honest proxy (limits STATED, not assumed — the growth-clock index-volume-proxy discipline). `StockSnapshot`
has NO moving-average field and NO multi-week base data, so every structural signal is DERIVED, trailing-
only, from the close-history sequence:
  - trailing SMA = the SMA_WINDOW-day mean of trailing closes (indices ≤ today → PIT-safe). We proxy the
    manuscript's full 50/150/200-day trend template (§4.1) with the SINGLE 50-day line (§4.7's designated
    "关键均线") — requiring 200 closes would abstain on most stocks. Stated, not hidden.
  - "rising SMA" = SMA today > SMA SMA_SLOPE_LOOKBACK days ago; "above SMA" = close > SMA.
  - distribution/stall day = elevated rvol (≥ RVOL_ELEVATED) with pct_change ≤ STALL_PCT (down or flat on
    volume = 放量滞涨). `volume` is the only volume primitive and `rvol` may be THIN/None — then the leg is
    simply not satisfied, so a `top` is NEVER fabricated from missing volume (degrade gracefully).
  - base vs advance leans on consecutive_up_days + rs_percentile + the SMA structure; absent
    consecutive_up_days the clock conservatively HOLDS base (never a fabricated advance).

Cross-day, not memoryless. P1/P2's HIGH bug was a per-day classifier that FLICKERS, so the stage is a
deterministic state machine replayed FORWARD over the symbol's priced history + today — a PURE function of
(history, today) with no hidden mutable state (recomputable; same inputs → same read), exactly like
`_run_machine` / `_run_theme_machine`. The lifecycle is a forward progression, which gives hysteresis
structurally; regressive/terminal transitions (`→ top`, `→ decline`) are guarded by a confirmation count
so an isolated weak day cannot un-confirm an advance (the DD_UNDER_PRESSURE / EXHAUSTION_CONFIRM analog);
the `base → advance` promotion needs a real multi-factor breakout signature, not a single up day. Warm-up
is explicit ABSTAIN (a None read, absent — never a fabricated stage, §0.2 禁止补格). All thresholds are
「文献值待verdict校准」 named constants; the Refiner-calibration metatool path is deferred (same posture as
both sibling clocks).

Also here: the §1.4 `event_reread` DETECTOR (`detect_stock_reread_events`) — the pure trigger-set detector
for the forced-high-scale-reread channel. It builds the detector only; the cadence-orchestration wiring
(there is no live three-clock orchestrator yet) is DEFERRED, exactly as the theme clock deferred its
`clock_cadence` action wiring.

Two scales live here (do not mix): `close`/`pct_change`/`rvol`/`gap_pct` are per-stock price/volume; the
`rs_percentile` field is a cross-sectional PERCENTILE in [0,100].
"""
from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from alpha.universe.stock import StockSnapshot

# ── thresholds (文献值待verdict校准; no Refiner-calibration path, same posture as the sibling clocks) ────
# trend structure (derived from the close series):
SMA_WINDOW = 50           # trailing SMA window — §4.7's "关键均线" (the 50-day line); proxies the trend template
SMA_SLOPE_LOOKBACK = 10   # "rising SMA" = SMA today > SMA this-many days ago (slope over ~2 weeks)
MIN_HISTORY = SMA_WINDOW + SMA_SLOPE_LOOKBACK  # priced days needed for a DETERMINED rising SMA today (else warm-up)
# market confirmation (RS percentile, cross-sectional [0,100]):
RS_STRONG = 70.0          # rs_percentile ≥ this = market confirmation (§4.1 trend_template: RS 百分位 ≥ 70)
# distribution / volume (per-stock):
RVOL_ELEVATED = 1.5       # rvol ≥ this = elevated (above-average) volume
STALL_PCT = 0.005         # a distribution/stall day = elevated rvol with pct_change ≤ this (down or flat = 放量滞涨)
DD_WINDOW = 25            # distribution-day counting window cap (O'Neil literature: ~25 sessions), since the anchor
# machine confirmation counts (no-flicker guards):
BREAKOUT_MIN_RUN = 2      # consecutive_up_days ≥ this in the breakout signature — a single up day cannot promote
TOP_CONFIRM = 5           # ≥ this many distribution/stall days since the advance anchor downgrades advance → top
DECLINE_CONFIRM = 3       # consecutive closes below the SMA (or reclaimed above, for decline → base) to confirm
# climax (a reduce-language flag, NOT a stage):
CLIMAX_DIST = 0.40        # distance-from-SMA ≥ this = 远离均线 (far above the trailing SMA)
CLIMAX_PCT = 0.08         # accelerating: a single-day thrust of ≥ this while already extended, OR …
CLIMAX_RUN_DAYS = 5       # … a persistent parabolic run of ≥ this many consecutive up days
# §1.4 event_reread detector:
LEADER_BREAKDOWN_RVOL = 2.0  # 持仓龙头放量破位: break on rvol ≥ this (§4.7: 量 ≥ 2× 20 日均量)
LAGGARD_BATCH = 3            # laggard 批量启动: ≥ this many same-theme non-leaders igniting (§4.7: 默认 ≥3 只)
EARNINGS_GAP = 0.10         # 财报后 gap: |gap_pct| ≥ this (§4.7: 缺口 >10%)

_CLASSIFIED_CONF = 0.6    # confidence for a placed read (warm-up already abstains, so every read is full-history)

# internal machine states → exposed Option-B tokens
_BASE, _ADVANCE, _TOP, _DECLINE = "base", "advance", "top", "decline"
_TOKENS = {
    _BASE: "stock:base",
    _ADVANCE: "stock:advance",
    _TOP: "stock:top",
    _DECLINE: "stock:decline",
}

# §1.4 event_reread trigger tokens (the forced-high-scale-reread channel)
REREAD_LEADER_BREAKDOWN = "reread:leader_breakdown"
REREAD_LAGGARD_BATCH = "reread:laggard_batch"
REREAD_BREADTH_COLLAPSE = "reread:breadth_collapse"
REREAD_EARNINGS_GAP_REVERSAL = "reread:earnings_gap_reversal"


@dataclass(frozen=True)
class StockStageReading:
    """One symbol's stage placement (an s_t-side label; parallels `RegimeRead`/`ThemeLifecycleRead`, not
    written into H). `climax_run` is the §1.3 reduce-language FLAG — a distinct signal, NOT a stage."""
    symbol: str
    stage: str            # one of the four `stock:` tokens
    confidence: float     # [0,1]
    climax_run: bool = False


@dataclass(frozen=True)
class _DayFeat:
    """Per-day derived features (all trailing-only). None-guarded: a missing signal never satisfies a leg."""
    above: bool           # close > trailing SMA (SMA determined)
    below: bool           # close < trailing SMA (SMA determined)
    rising: bool          # SMA today > SMA SMA_SLOPE_LOOKBACK days ago (both determined)
    rs_strong: bool       # rs_percentile ≥ RS_STRONG (market confirmation)
    run: int | None       # consecutive_up_days
    distrib: bool         # a distribution/stall day (elevated rvol, no price progress)
    dist: float | None    # distance from SMA = (close - sma) / sma
    climax: bool          # far above SMA + accelerating (the reduce flag)


# ── SMA / pct helpers (trailing-only → PIT-safe: never read a close at index > i) ─────────────────────

def _sma(closes: Sequence[float], i: int, window: int = SMA_WINDOW) -> float | None:
    """The `window`-day trailing simple moving average ending at index `i` (inclusive). None until there
    are `window` closes. Strictly trailing — uses only `closes[i-window+1 : i+1]` (indices ≤ i), so a
    future close cannot leak into today's SMA (the PIT firewall)."""
    if i < window - 1:
        return None
    return sum(closes[i - window + 1:i + 1]) / window


def _pct(snap: StockSnapshot, closes: Sequence[float], i: int) -> float | None:
    """Today's pct_change, preferring the feed field; falling back to (close - prev_close)/prev_close from
    the trailing close series (never a future close)."""
    if snap.pct_change is not None:
        return snap.pct_change
    if i > 0 and closes[i - 1]:
        return (closes[i] - closes[i - 1]) / closes[i - 1]
    return None


def _features(snaps: Sequence[StockSnapshot]) -> list[_DayFeat]:
    """Derive the per-day feature series (pure; each day reads only trailing closes). `snaps` are the
    priced snapshots (close is not None), chronological."""
    closes = [s.close for s in snaps]
    feats: list[_DayFeat] = []
    for i, s in enumerate(snaps):
        sma = _sma(closes, i)
        sma_back = _sma(closes, i - SMA_SLOPE_LOOKBACK) if i - SMA_SLOPE_LOOKBACK >= 0 else None
        rising = sma is not None and sma_back is not None and sma > sma_back
        above = sma is not None and s.close > sma
        below = sma is not None and s.close < sma
        dist = (s.close - sma) / sma if (sma is not None and sma != 0) else None
        pct = _pct(s, closes, i)
        elevated = s.rvol is not None and s.rvol >= RVOL_ELEVATED
        distrib = elevated and pct is not None and pct <= STALL_PCT   # 放量滞涨: high volume, no price progress
        rs_strong = s.rs_percentile is not None and s.rs_percentile >= RS_STRONG
        run = s.consecutive_up_days
        climax = dist is not None and dist >= CLIMAX_DIST and (
            (pct is not None and pct >= CLIMAX_PCT) or (run is not None and run >= CLIMAX_RUN_DAYS))
        feats.append(_DayFeat(above=above, below=below, rising=rising, rs_strong=rs_strong, run=run,
                              distrib=distrib, dist=dist, climax=climax))
    return feats


def _run_stock_machine(feats: Sequence[_DayFeat]) -> tuple[str, bool]:
    """Replay the four-stage machine forward over the chronological per-day features (history + today) and
    return `(final_state, climax_of_today)`. Pure: depends only on `feats`.

    Start at `base` (the quiet default). A real breakout signature (above a RISING SMA + market confirmation
    + a `consecutive_up_days ≥ BREAKOUT_MIN_RUN` up-run) promotes base → advance and anchors a fresh
    distribution count — a single up day cannot promote (run would be 1, and a lone up day cannot lift a
    stock above a *rising* 50-day SMA). Regressive/terminal transitions are GUARDED (no-flicker): advance →
    top needs `TOP_CONFIRM` distribution/stall days SINCE the anchor (window-capped at DD_WINDOW, so stale
    pre-anchor DDs never bleed in — P2's ABAB fix); advance/top → decline needs a SUSTAINED break
    (`below_run ≥ DECLINE_CONFIRM` consecutive closes below the SMA) while RS is no longer strong (an elite
    leader gets the benefit of the doubt — 龙头不倒题材不死). A shakeout resolved up re-breaks-out to advance;
    a decline that reclaims the SMA for `DECLINE_CONFIRM` closes goes to base (re-accumulation — never
    straight back to advance, so no base is skipped)."""
    state = _BASE
    anchor = -1           # index where advance was last (re)confirmed
    below_run = 0         # consecutive closes below the SMA (→ decline)
    above_run = 0         # consecutive closes at/above the SMA (decline → base)
    for i, f in enumerate(feats):
        breakout = f.above and f.rising and f.rs_strong and f.run is not None and f.run >= BREAKOUT_MIN_RUN
        if f.below:
            below_run, above_run = below_run + 1, 0
        elif f.above:
            above_run, below_run = above_run + 1, 0
        else:                                           # SMA undetermined: no structural evidence either way
            below_run = above_run = 0
        dd_lo = max(anchor + 1, i - DD_WINDOW + 1)      # distribution days SINCE the anchor, window-capped
        dd_count = sum(1 for j in range(dd_lo, i + 1) if feats[j].distrib)

        if state == _BASE:
            if breakout:
                state, anchor = _ADVANCE, i
        elif state == _ADVANCE:
            if below_run >= DECLINE_CONFIRM and not f.rs_strong:
                state = _DECLINE                        # sustained structural break (fast breakdown)
            elif dd_count >= TOP_CONFIRM:
                state = _TOP                            # distribution mounted (放量滞涨) — hysteresis: a lone DD holds advance
        elif state == _TOP:
            if below_run >= DECLINE_CONFIRM and not f.rs_strong:
                state = _DECLINE                        # the top resolves down
            elif breakout:
                state, anchor = _ADVANCE, i             # shakeout resolved up: a fresh breakout re-confirms
        elif state == _DECLINE:
            if above_run >= DECLINE_CONFIRM:
                state = _BASE                           # reclaimed the SMA — re-accumulation (a fresh breakout still required)
    return state, feats[-1].climax if feats else False


def classify_stock_stage(history: Sequence[StockSnapshot],
                         today: StockSnapshot) -> StockStageReading | None:
    """Classify one symbol's §1.3 stage as of `today`, given its strictly-prior chronological `history`.
    Priced snapshots only (no-close days dropped, like P2 drops 0/0 feed-outage days). Returns a frozen
    `StockStageReading`, or ABSTAINS (None) when the symbol cannot be read — never a fabricated stage
    (§0.2 禁止补格):

      - no `close` today ⇒ None (cannot see the stock today);
      - fewer than MIN_HISTORY priced days ⇒ None (warm-up: a *rising* trailing SMA is not yet determinable,
        so base cannot be told from early-advance). Unlike the market clock's conservative-`under_pressure`
        warm-up, there is no "conservative stock stage" — `base` is a real read, not a risk level, so we
        abstain (the theme-clock posture).

    Post-warm-up the machine always returns one of the four real stages (`base` = the honest quiet default).
    Pure function of (history, today)."""
    if today.close is None:
        return None
    priced = [s for s in history if s.close is not None]
    series = [*priced, today]
    if len(series) < MIN_HISTORY:
        return None
    state, climax = _run_stock_machine(_features(series))
    return StockStageReading(symbol=today.symbol, stage=_TOKENS[state],
                             confidence=_CLASSIFIED_CONF, climax_run=climax)


class StockStageClock:
    """Read-only per-symbol stock-stage classifier (the market/theme clock's stock-scale sibling).
    Deterministic, oracle-auditable. `read()` returns a `StockStageReading` (or None); it writes nothing
    into H (SSOT), exactly like GCycle / GrowthMarketClock / GrowthThemeClock."""

    def read(self, history: Sequence[StockSnapshot],
             today: StockSnapshot) -> StockStageReading | None:
        """Classify one symbol as of `today` given its strictly-prior `history`. Delegates to
        `classify_stock_stage` (the callable core, mirroring `GrowthThemeClock.read` → `theme_lifecycle`)."""
        return classify_stock_stage(history, today)


# ── §1.4 event_reread detector — the forced-high-scale-reread trigger set (pure; detector only) ────────

def detect_stock_reread_events(
    history: Sequence[StockSnapshot],
    today: StockSnapshot,
    *,
    is_leader: bool = False,
    laggard_ignitions: int = 0,
    breadth_collapse: bool = False,
    earnings_event: bool = False,
) -> frozenset[str]:
    """Return the set of §1.4 forced-high-scale-reread triggers PRESENT for this stock/context today (a
    `frozenset` of `reread:*` tokens; empty when none — silent otherwise). Pure given the signals. These
    events force the HIGH-scale clock to re-read regardless of cadence (§1.4: 覆盖任何节拍表); the reread
    conclusion is still the high-scale clock's own call. Cadence-orchestration wiring is DEFERRED.

    Signals not carried by `StockSnapshot` are taken as explicit args (documented at each trigger):
      is_leader          — a DESIGNATED portfolio leader (no "am I a leader" field exists);
      laggard_ignitions  — a COUNT of same-theme non-leaders igniting today (one snapshot cannot see the batch);
      breadth_collapse   — a market/theme breadth read (not a per-stock field);
      earnings_event     — whether today is a post-earnings session (no earnings-date field — the P5a feed).
    """
    events: set[str] = set()

    # (1) 持仓龙头放量破位 (§3.3 / §4.7): a designated leader breaks the key trailing SMA on elevated volume.
    #     Degrades to no-fire when history is thinner than SMA_WINDOW (SMA undeterminable — never fabricated).
    if is_leader and today.close is not None:
        closes = [s.close for s in history if s.close is not None]
        prev_close = closes[-1] if closes else None
        closes = [*closes, today.close]
        i = len(closes) - 1
        sma_today = _sma(closes, i)
        sma_prev = _sma(closes, i - 1)                  # yesterday's trailing SMA (the "was above the line" check)
        if (sma_today is not None and sma_prev is not None and prev_close is not None
                and prev_close >= sma_prev and today.close < sma_today
                and today.rvol is not None and today.rvol >= LEADER_BREAKDOWN_RVOL):
            events.add(REREAD_LEADER_BREAKDOWN)

    # (2) laggard 批量启动 (§3.4 / §4.7): ≥ LAGGARD_BATCH same-theme non-leaders igniting — a TIMER, not a target.
    if laggard_ignitions >= LAGGARD_BATCH:
        events.add(REREAD_LAGGARD_BATCH)

    # (3) breadth 崩塌 (§4.7): a market/theme breadth read, taken as an arg.
    if breadth_collapse:
        events.add(REREAD_BREADTH_COLLAPSE)

    # (4) 财报后 gap 不回补方向反转 (§4.7): a post-earnings gap ≥ EARNINGS_GAP that REVERSED direction
    #     (gapped up, closed down — or the mirror). The "反论点方向 / against-thesis" refinement needs a
    #     thesis-direction arg (deferred to the consumer that holds the thesis).
    if (earnings_event and today.gap_pct is not None and today.pct_change is not None
            and abs(today.gap_pct) >= EARNINGS_GAP
            and ((today.gap_pct > 0 and today.pct_change < 0)
                 or (today.gap_pct < 0 and today.pct_change > 0))):
        events.add(REREAD_EARNINGS_GAP_REVERSAL)

    return frozenset(events)
