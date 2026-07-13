"""Growth stock-stage clock — truth table + hysteresis + warm-up/abstain + event_reread + boundaries.

Tests for `alpha/regime/stock_clock.py` — the THIRD growth clock (§1.3 `个股时钟·stage`). The clock reads
one symbol's §1.3 lifecycle (`base → advance → top → decline`, plus the `climax_run` reduce-flag) from
that symbol's own `StockSnapshot` history + today, as a state machine replayed forward over the priced
series (P1/P2's no-flicker lesson, one scale further down than the market/theme clocks). All structural
signals are DERIVED trailing-only from the close/rvol series (there is no MA field on `StockSnapshot`), so
the tapes here are built directly from close paths and the derived SMA is tested for PIT-safety.
"""
from __future__ import annotations

from alpha.regime.stock_clock import (
    BREAKOUT_MIN_RUN, CLIMAX_DIST, DECLINE_CONFIRM, EARNINGS_GAP, LAGGARD_BATCH,
    LEADER_BREAKDOWN_RVOL, MIN_HISTORY, REREAD_BREADTH_COLLAPSE, REREAD_EARNINGS_GAP_REVERSAL,
    REREAD_LAGGARD_BATCH, REREAD_LEADER_BREAKDOWN, RS_STRONG, RVOL_ELEVATED, SMA_WINDOW, TOP_CONFIRM,
    StockStageClock, StockStageReading, _run_stock_machine, _features, _sma, classify_stock_stage,
    detect_stock_reread_events,
)
from alpha.universe.stock import StockSnapshot


# ── builders ─────────────────────────────────────────────────────────────────────────────────────────

def _snap(close: float | None, *, symbol: str = "AAA", pct: float | None = None,
          prev: float | None = None, rvol: float | None = None, cud: int | None = None,
          rs: float | None = None, gap: float | None = None) -> StockSnapshot:
    return StockSnapshot(symbol=symbol, name=symbol, status="trend_template", close=close, prev_close=prev,
                         pct_change=pct, rvol=rvol, consecutive_up_days=cud, rs_percentile=rs, gap_pct=gap)


def _col(v, n: int) -> list:
    return list(v) if isinstance(v, (list, tuple)) else [v] * n


def _snaps(closes, *, rvol=None, cud=None, rs=None, symbol: str = "AAA") -> list[StockSnapshot]:
    """A chronological snapshot series from a close path; rvol/cud/rs are scalars (all days) or per-day lists."""
    n = len(closes)
    rv, cu, rr = _col(rvol, n), _col(cud, n), _col(rs, n)
    return [_snap(closes[i], rvol=rv[i], cud=cu[i], rs=rr[i], symbol=symbol) for i in range(n)]


def _classify(closes, **kw) -> StockStageReading | None:
    s = _snaps(closes, **kw)
    return classify_stock_stage(s[:-1], s[-1])


def _ramp(start: float, step: float, n: int) -> list[float]:
    return [start + step * i for i in range(n)]


# canonical close paths (each ≥ MIN_HISTORY priced days so `today` has a determined rising SMA)
RAMP = _ramp(100.0, 1.0, 65)                       # a steady Stage-2 uptrend (close above a rising SMA)
FLAT = [100.0] * 65                                # a quiet sideways base (close == SMA, never above)


# ── truth table: each §1.3 stage on a constructed close/rvol tape ─────────────────────────────────────

def test_base_quiet_sideways_is_the_default_stage():
    """A quiet sideways tape (never above a rising SMA, no breakout signature) reads stock:base — the
    honest default placement (not an abstain: base is a real, informative read)."""
    r = _classify(FLAT, rs=50.0, cud=0)
    assert r is not None and r.stage == "stock:base" and r.climax_run is False


def test_advance_above_a_rising_sma_with_rs_confirmation():
    """close above a RISING trailing SMA + market confirmation (rs_percentile ≥ RS_STRONG) + an up-run =
    stock:advance, THE ONLY stage the doctrine allows going long (§1.3: 只在 advance 做多)."""
    r = _classify(RAMP, rs=80.0, cud=5)
    assert r is not None and r.stage == "stock:advance"
    assert r.climax_run is False                    # a normal (non-parabolic) advance is not a climax


def test_top_volume_stall_plus_distribution_days():
    """After an advance, TOP_CONFIRM distribution/stall days (elevated rvol, no price progress = 放量滞涨)
    downgrade advance → stock:top — the distribution language of §1.3, not a price band."""
    closes = _ramp(100.0, 1.0, 60) + [159.0] * TOP_CONFIRM
    rvol = [None] * 60 + [RVOL_ELEVATED] * TOP_CONFIRM
    cud = [5] * 60 + [0] * TOP_CONFIRM
    r = _classify(closes, rvol=rvol, cud=cud, rs=80.0)
    assert r is not None and r.stage == "stock:top"


def test_decline_sustained_break_below_the_sma_rs_faded():
    """A SUSTAINED close below the trailing SMA (DECLINE_CONFIRM consecutive days) while RS is no longer
    strong = stock:decline (below/through the SMA, RS deteriorating)."""
    closes = _ramp(100.0, 1.0, 60) + [120.0] * 4
    rs = [80.0] * 60 + [50.0] * 4                    # RS fades below RS_STRONG on the break
    cud = [5] * 60 + [0] * 4
    r = _classify(closes, rs=rs, cud=cud)
    assert r is not None and r.stage == "stock:decline"


# ── the only-long stage is `advance` ─────────────────────────────────────────────────────────────────

def test_only_advance_is_the_long_stage():
    """`stock:advance` is the SOLE stage the doctrine allows going long; the other three stages are
    distinct tokens — pinned so a downstream long-gate can key on exactly `stock:advance`."""
    base = _classify(FLAT, rs=50.0, cud=0)
    advance = _classify(RAMP, rs=80.0, cud=5)
    top = _classify(_ramp(100.0, 1.0, 60) + [159.0] * TOP_CONFIRM,
                    rvol=[None] * 60 + [RVOL_ELEVATED] * TOP_CONFIRM, cud=[5] * 60 + [0] * TOP_CONFIRM, rs=80.0)
    decline = _classify(_ramp(100.0, 1.0, 60) + [120.0] * 4, rs=[80.0] * 60 + [50.0] * 4, cud=[5] * 60 + [0] * 4)
    assert advance.stage == "stock:advance"
    for other in (base, top, decline):
        assert other.stage != "stock:advance"


# ── no-flicker: an isolated weak day does NOT un-confirm a confirmed advance (the P1/P2 lesson) ────────

def test_isolated_distribution_day_holds_advance_no_flicker():
    """A SINGLE distribution day (elevated rvol, flat close) after a confirmed advance must NOT flip it to
    top — advance persists until TOP_CONFIRM distribution days accumulate. The pinned no-flicker property
    (the P1/P2 stability lesson; mirrors GrowthMarketClock's DD_UNDER_PRESSURE / the theme clock's
    EXHAUSTION_CONFIRM)."""
    assert TOP_CONFIRM >= 2                          # the guarantee is only meaningful if > 1
    closes = _ramp(100.0, 1.0, 60) + [159.0]         # exactly ONE stall day
    r = _classify(closes, rvol=[None] * 60 + [RVOL_ELEVATED], cud=[5] * 60 + [0], rs=80.0)
    assert r is not None and r.stage == "stock:advance"


def test_isolated_dip_below_sma_holds_advance_no_flicker():
    """A single (sub-DECLINE_CONFIRM) dip below the SMA does NOT flip a confirmed advance to decline — an
    isolated weak day cannot un-confirm the advance (the sustained-break guard, the DEEP_MIN_DAYS analog)."""
    assert DECLINE_CONFIRM >= 2
    closes = _ramp(100.0, 1.0, 60) + [120.0] * (DECLINE_CONFIRM - 1)   # one short of a sustained break
    rs = [80.0] * 60 + [50.0] * (DECLINE_CONFIRM - 1)
    r = _classify(closes, rs=rs, cud=[5] * 60 + [0] * (DECLINE_CONFIRM - 1))
    assert r is not None and r.stage == "stock:advance"


def test_elite_leader_holds_through_a_dip_below_sma():
    """A still-elite leader (rs stays ≥ RS_STRONG) that dips below the SMA for DECLINE_CONFIRM days does
    NOT flip to decline — the leader benefit-of-the-doubt guard (龙头不倒题材不死)."""
    closes = _ramp(100.0, 1.0, 60) + [120.0] * 4
    r = _classify(closes, rs=80.0, cud=[5] * 60 + [0] * 4)   # RS stays strong throughout the dip
    assert r is not None and r.stage == "stock:advance"


# ── base → advance needs a REAL breakout, not a single up day ─────────────────────────────────────────

def test_base_to_advance_needs_a_real_breakout_not_one_up_day():
    """A single up day (consecutive_up_days = 1) out of a base does NOT promote to advance, even with a
    strong RS and a close above the SMA — the breakout signature needs consecutive_up_days ≥
    BREAKOUT_MIN_RUN. A multi-day up-run DOES promote."""
    one_up = _classify([100.0] * 64 + [110.0], rs=80.0, cud=[0] * 64 + [1])
    real = _classify([100.0] * 60 + [102.0, 104.0, 106.0, 108.0, 110.0],
                     rs=80.0, cud=[0] * 60 + [1, 2, 3, 4, 5])
    assert one_up is not None and one_up.stage == "stock:base"       # a lone up day cannot promote
    assert real is not None and real.stage == "stock:advance"         # a real up-run breakout does


# ── top is distribution, NOT the A-share daily-relay "分歧转一致再上一波" read (轮回锚 A-14) ──────────────

def test_top_is_not_a_daily_relay_read_up_on_volume_is_accumulation():
    """Strong UP days on elevated volume (what an A-share daily-relay read would call '一致，再上一波') are
    ACCUMULATION here (pct_change > STALL_PCT ⇒ not a distribution day), so the stock stays stock:advance,
    never stock:top. The daily-relay top read does NOT migrate (§1.3 / A-14).

    DECISIVE (not vacuous): the tape ENDS on the last up-on-volume leg — exactly TOP_CONFIRM of them — so
    the read of `today` turns on whether those legs are labelled accumulation or distribution. Under the
    correct pct-gated `distrib` (line 164 `pct <= STALL_PCT`) they are accumulation → stays advance; drop
    that gate (the A-14 leak: count every elevated-volume day as distribution) and TOP_CONFIRM distribution
    days flip advance → stock:top. The terminal is deliberately NOT a fresh breakout (no extra up-leg after
    it), so the `top → advance` shakeout branch cannot mask the leak — mutation-verified."""
    up_legs = [162.0 + 4.0 * i for i in range(TOP_CONFIRM)]          # exactly TOP_CONFIRM strong up-legs...
    closes = _ramp(100.0, 1.0, 60) + up_legs                        # ...and the tape ENDS on the last one
    rvol = [None] * 60 + [RVOL_ELEVATED] * TOP_CONFIRM              # every up-leg on high volume
    r = _classify(closes, rvol=rvol, cud=5, rs=80.0)
    assert r is not None and r.stage == "stock:advance"            # accumulation, NOT stock:top


# ── climax_run: a REDUCE flag, far above the SMA + accelerating — never a buy stage ───────────────────

def test_climax_run_flag_fires_far_above_sma_and_is_not_a_stage():
    """A parabolic blow-off (close far above the trailing SMA + a sharp thrust) sets climax_run=True while
    the STAGE stays stock:advance — climax is REDUCE language, a flag on the reading, NOT its own buy
    stage (§1.3: climax run 是减仓语言，不是加仓语言)."""
    closes = [100.0] * 55 + [120.0, 145.0, 175.0, 210.0, 255.0]
    r = _classify(closes, rs=80.0, cud=[0] * 55 + [1, 2, 3, 4, 5])
    assert r is not None
    assert r.stage == "stock:advance"                # still the only-long stage, structurally
    assert r.climax_run is True                      # but the reduce flag is raised
    # and the distance-from-SMA really is far above the line (the flag is not spurious)
    feats = _features(_snaps(closes, rs=80.0, cud=[0] * 55 + [1, 2, 3, 4, 5]))
    assert feats[-1].dist is not None and feats[-1].dist >= CLIMAX_DIST


# ── graceful degradation: thin volume never FABRICATES a top; thin history ABSTAINS ───────────────────

def test_thin_volume_never_fabricates_a_top():
    """A stalling price with NO volume signal (rvol None) cannot be called top — the distribution leg is
    unsatisfiable, so the stage stays stock:advance. Missing volume degrades gracefully; it never
    fabricates a distribution top (§0.2 禁止补格)."""
    closes = _ramp(100.0, 1.0, 60) + [159.0] * 6     # a long stall, but …
    r = _classify(closes, rvol=None, cud=[5] * 60 + [0] * 6, rs=80.0)   # … no rvol → no distribution day
    assert r is not None and r.stage == "stock:advance"


def test_warmup_too_few_priced_days_abstains():
    """Fewer than MIN_HISTORY priced days ⇒ a rising trailing SMA is not determinable ⇒ ABSTAIN (None,
    absent) — never a fabricated stage. Abstention, not a conservative default."""
    assert classify_stock_stage([], _snap(100.0, rs=80.0, cud=5)) is None      # nothing to stand on
    short = _snaps(_ramp(100.0, 1.0, MIN_HISTORY - 1), rs=80.0, cud=5)          # one short of warm-up
    assert classify_stock_stage(short[:-1], short[-1]) is None


def test_no_close_today_abstains():
    """A symbol with no `close` today cannot be read ⇒ None (absent), never a fabricated stage."""
    hist = _snaps(RAMP, rs=80.0, cud=5)
    assert classify_stock_stage(hist, _snap(None, rs=80.0, cud=5)) is None


def test_no_close_history_days_are_dropped_from_the_series():
    """History snapshots with no `close` are dropped (like P2 drops 0/0 feed-outage days): a series that
    is long enough AFTER dropping them still classifies; one that is too short abstains."""
    priced = _snaps(RAMP, rs=80.0, cud=5)
    with_gaps = priced[:30] + [_snap(None), _snap(None)] + priced[30:]          # two blind days inserted
    r = classify_stock_stage(with_gaps[:-1], with_gaps[-1])
    assert r is not None and r.stage == "stock:advance"                          # the blind days didn't break it


# ── further forward transitions (top → decline, decline → base) ──────────────────────────────────────

def test_top_then_resolves_down_to_decline():
    """From a distribution top, a sustained break below the SMA (RS faded) resolves down to stock:decline —
    the forward progression base → advance → top → decline."""
    closes = _ramp(100.0, 1.0, 60) + [159.0] * TOP_CONFIRM + [120.0] * DECLINE_CONFIRM
    rvol = [None] * 60 + [RVOL_ELEVATED] * TOP_CONFIRM + [RVOL_ELEVATED] * DECLINE_CONFIRM
    rs = [80.0] * (60 + TOP_CONFIRM) + [50.0] * DECLINE_CONFIRM
    cud = [5] * 60 + [0] * (TOP_CONFIRM + DECLINE_CONFIRM)
    r = _classify(closes, rvol=rvol, rs=rs, cud=cud)
    assert r is not None and r.stage == "stock:decline"


def test_decline_reclaims_the_sma_to_base_never_straight_to_advance():
    """A decline that reclaims the SMA for DECLINE_CONFIRM closes returns to stock:base (re-accumulation) —
    NOT straight to advance. A fresh breakout is still required, so no base is skipped."""
    closes = _ramp(100.0, 1.0, 60) + [120.0] * 4 + [145.0] * DECLINE_CONFIRM
    rs = [80.0] * 60 + [50.0] * 4 + [80.0] * DECLINE_CONFIRM
    cud = [5] * 60 + [0] * 4 + [5] * DECLINE_CONFIRM
    r = _classify(closes, rs=rs, cud=cud)
    assert r is not None and r.stage == "stock:base"


# ── cross-history: the SAME final snapshot reads differently by its history ───────────────────────────

def test_same_final_snapshot_reads_differently_by_history():
    """The identical last snapshot reads advance after a healthy uptrend but base after a flat backdrop —
    proving the read is cross-history (a forward replay), not a memoryless per-day band."""
    tail = _snap(159.0, rs=80.0, cud=5)
    up_hist = _snaps(_ramp(100.0, 1.0, 60), rs=80.0, cud=5)      # a real prior uptrend
    flat_hist = _snaps([159.0] * 60, rs=80.0, cud=0)             # a flat backdrop at the same level
    assert classify_stock_stage(up_hist, tail).stage == "stock:advance"
    assert classify_stock_stage(flat_hist, tail).stage == "stock:base"


# ── purity / determinism: same (history, today) → identical read (no hidden state) ────────────────────

def test_read_is_pure_function_of_inputs():
    s = _snaps(RAMP, rs=80.0, cud=5)
    a = classify_stock_stage(s[:-1], s[-1])
    b = classify_stock_stage(s[:-1], s[-1])
    assert a == b


def test_run_stock_machine_is_pure_and_forward():
    """_run_stock_machine replays forward and is pure (exposed for oracle auditing, like the sibling
    machines): base → advance over a rising, RS-confirmed tape."""
    feats = _features(_snaps(RAMP, rs=80.0, cud=5))
    state, _ = _run_stock_machine(feats)
    assert state == "advance"
    assert _run_stock_machine(feats) == _run_stock_machine(feats)


# ── PIT / trailing-only: a future close can never leak into today's SMA ───────────────────────────────

def test_sma_is_trailing_only_no_lookahead():
    """`_sma(closes, i)` uses only closes at indices ≤ i — appending any (wild) future close leaves the SMA
    at i unchanged. The PIT firewall: a future close cannot leak into today's derived SMA."""
    closes = _ramp(100.0, 1.0, 60)
    i = 55
    assert _sma(closes, i) == _sma(closes[:i + 1] + [999999.0, -999999.0], i)
    assert _sma(closes, SMA_WINDOW - 2) is None       # undetermined before a full window
    assert _sma(closes, SMA_WINDOW - 1) is not None    # determined at exactly a full window


def test_features_are_trailing_only_appending_a_future_bar_leaves_earlier_rows_identical():
    """PIT at the PIPELINE level, not just the `_sma` primitive: every `_features` row for day i must
    derive from closes ≤ i, so appending a wild FUTURE bar leaves all earlier rows byte-identical. This
    catches a `_features`-level lookahead (e.g. computing `sma = _sma(closes, i+1)`) that
    test_sma_is_trailing_only_no_lookahead — which guards only the primitive, not its call site — would
    miss. Mutation-verified: under the i+1 leak the last base row reads the appended bar and this fails."""
    base = _snaps(_ramp(100.0, 1.0, 60), rvol=RVOL_ELEVATED, cud=5, rs=80.0)
    extended = base + [_snap(999999.0, rvol=RVOL_ELEVATED, cud=5, rs=80.0)]   # a wild future bar
    assert _features(extended)[: len(base)] == _features(base)                # earlier rows unaffected


def test_read_only_consumes_history_and_today():
    """The clock is a pure replay of (history, today): `today` is by construction the last element, so no
    caller-supplied future datum exists to leak (the derivation-level trailing property is pinned by
    test_sma_is_trailing_only_no_lookahead + the pipeline-level trailing test above + purity)."""
    s = _snaps(RAMP, rs=80.0, cud=5)
    assert classify_stock_stage(s[:-1], s[-1]).stage == "stock:advance"


# ── the StockStageClock.read adapter (the s_t-side face, like GrowthThemeClock.read) ──────────────────

def test_clock_read_delegates_to_classify_stock_stage():
    s = _snaps(RAMP, rs=80.0, cud=5)
    assert StockStageClock().read(s[:-1], s[-1]) == classify_stock_stage(s[:-1], s[-1])


def test_clock_read_abstains_returns_none():
    short = _snaps(_ramp(100.0, 1.0, MIN_HISTORY - 1), rs=80.0, cud=5)
    assert StockStageClock().read(short[:-1], short[-1]) is None


# ── §1.4 event_reread detector: each trigger fires on its signal and stays silent otherwise ───────────

def _leader_history():
    return _snaps(_ramp(100.0, 1.0, 60), rs=80.0, cud=5)      # ≥ SMA_WINDOW priced days, above a rising SMA


def test_reread_leader_breakdown_fires_on_a_volume_break_of_the_sma():
    """A DESIGNATED leader (is_leader) that was above the key trailing SMA and breaks below it on elevated
    volume fires reread:leader_breakdown (§3.3 持仓龙头放量破位)."""
    hist = _leader_history()
    today = _snap(125.0, rvol=LEADER_BREAKDOWN_RVOL)         # breaks below the SMA on ≥2x volume
    assert REREAD_LEADER_BREAKDOWN in detect_stock_reread_events(hist, today, is_leader=True)


def test_reread_leader_breakdown_silent_when_not_a_leader_or_no_volume_or_no_break():
    """The leader-breakdown trigger is silent for a non-leader, on non-elevated volume, or with no break."""
    hist = _leader_history()
    breakdown = _snap(125.0, rvol=LEADER_BREAKDOWN_RVOL)
    assert detect_stock_reread_events(hist, breakdown, is_leader=False) == frozenset()          # not a leader
    quiet = _snap(125.0, rvol=1.0)                                                                # no 放量
    assert REREAD_LEADER_BREAKDOWN not in detect_stock_reread_events(hist, quiet, is_leader=True)
    holding = _snap(160.0, rvol=LEADER_BREAKDOWN_RVOL)                                            # still above the SMA
    assert REREAD_LEADER_BREAKDOWN not in detect_stock_reread_events(hist, holding, is_leader=True)


def test_reread_leader_breakdown_degrades_gracefully_on_thin_history():
    """With fewer than SMA_WINDOW priced days the key SMA is undeterminable, so the leader-breakdown
    trigger cannot fire (degrades to silence — never fabricated)."""
    thin = _snaps(_ramp(100.0, 1.0, 10), rs=80.0, cud=5)
    assert detect_stock_reread_events(thin, _snap(80.0, rvol=LEADER_BREAKDOWN_RVOL), is_leader=True) == frozenset()


def test_reread_laggard_batch_fires_on_the_count_and_is_a_timer():
    """≥ LAGGARD_BATCH same-theme non-leaders igniting today fires reread:laggard_batch (§3.4 laggard_timer
    — a TIMER, taken as a count arg, not a per-stock field). One short does not fire."""
    hist, today = _leader_history(), _snap(150.0)
    assert REREAD_LAGGARD_BATCH in detect_stock_reread_events(hist, today, laggard_ignitions=LAGGARD_BATCH)
    assert REREAD_LAGGARD_BATCH not in detect_stock_reread_events(hist, today, laggard_ignitions=LAGGARD_BATCH - 1)


def test_reread_breadth_collapse_fires_on_the_arg():
    """A breadth-collapse read (a market/theme signal, taken as an arg — not a per-stock field) fires
    reread:breadth_collapse; absent it, silent."""
    hist, today = _leader_history(), _snap(150.0)
    assert REREAD_BREADTH_COLLAPSE in detect_stock_reread_events(hist, today, breadth_collapse=True)
    assert REREAD_BREADTH_COLLAPSE not in detect_stock_reread_events(hist, today, breadth_collapse=False)


def test_reread_earnings_gap_reversal_fires_on_a_reversed_gap():
    """A post-earnings gap ≥ EARNINGS_GAP that REVERSED direction (gapped up, closed down — or the mirror)
    fires reread:earnings_gap_reversal (§4.7 财报后 gap 不回补方向反转)."""
    hist = _leader_history()
    up_trap = _snap(150.0, gap=EARNINGS_GAP + 0.02, pct=-0.03)        # gapped up, closed down = bull trap
    down_reversal = _snap(150.0, gap=-(EARNINGS_GAP + 0.02), pct=0.03)  # gapped down, closed up
    assert REREAD_EARNINGS_GAP_REVERSAL in detect_stock_reread_events(hist, up_trap, earnings_event=True)
    assert REREAD_EARNINGS_GAP_REVERSAL in detect_stock_reread_events(hist, down_reversal, earnings_event=True)


def test_reread_earnings_gap_reversal_silent_without_event_or_reversal_or_size():
    """Silent when it is not an earnings session, when the gap held its direction (no reversal), or when
    the gap is below the size floor."""
    hist = _leader_history()
    reversed_gap = _snap(150.0, gap=EARNINGS_GAP + 0.02, pct=-0.03)
    assert detect_stock_reread_events(hist, reversed_gap, earnings_event=False) == frozenset()   # not earnings
    gap_and_go = _snap(150.0, gap=EARNINGS_GAP + 0.02, pct=0.05)                                  # held direction
    assert REREAD_EARNINGS_GAP_REVERSAL not in detect_stock_reread_events(hist, gap_and_go, earnings_event=True)
    small = _snap(150.0, gap=0.03, pct=-0.03)                                                     # below the floor
    assert REREAD_EARNINGS_GAP_REVERSAL not in detect_stock_reread_events(hist, small, earnings_event=True)


def test_reread_detector_silent_when_no_signal_present():
    """No triggers present ⇒ an empty frozenset (silence — the detector never volunteers a reread)."""
    assert detect_stock_reread_events(_leader_history(), _snap(150.0)) == frozenset()


def test_reread_detector_returns_all_present_triggers():
    """Multiple simultaneous signals return all present triggers (a set, order-independent)."""
    hist = _leader_history()
    today = _snap(125.0, rvol=LEADER_BREAKDOWN_RVOL, gap=EARNINGS_GAP + 0.02, pct=-0.03)
    events = detect_stock_reread_events(hist, today, is_leader=True, laggard_ignitions=LAGGARD_BATCH,
                                        breadth_collapse=True, earnings_event=True)
    assert events == frozenset({REREAD_LEADER_BREAKDOWN, REREAD_LAGGARD_BATCH,
                                REREAD_BREADTH_COLLAPSE, REREAD_EARNINGS_GAP_REVERSAL})


# ── boundary probes: each threshold pinned so mutating it trips a test ─────────────────────────────────

def test_rs_strong_boundary_for_advance():
    """The advance breakout needs rs_percentile ≥ RS_STRONG; just below, the same rising tape stays base."""
    at = _classify(RAMP, rs=RS_STRONG, cud=5)
    below = _classify(RAMP, rs=round(RS_STRONG - 1.0, 4), cud=5)
    assert at.stage == "stock:advance"
    assert below.stage == "stock:base"


def test_breakout_min_run_boundary_for_advance():
    """The breakout needs consecutive_up_days ≥ BREAKOUT_MIN_RUN; one fewer (on the same tape) stays base."""
    at = _classify(RAMP, rs=80.0, cud=BREAKOUT_MIN_RUN)
    below = _classify(RAMP, rs=80.0, cud=BREAKOUT_MIN_RUN - 1)
    assert at.stage == "stock:advance"
    assert below.stage == "stock:base"


def test_top_confirm_boundary():
    """Exactly TOP_CONFIRM distribution days flip advance → top; one fewer stays advance (no-flicker)."""
    base = _ramp(100.0, 1.0, 60)
    at = _classify(base + [159.0] * TOP_CONFIRM,
                   rvol=[None] * 60 + [RVOL_ELEVATED] * TOP_CONFIRM, cud=[5] * 60 + [0] * TOP_CONFIRM, rs=80.0)
    below = _classify(base + [159.0] * (TOP_CONFIRM - 1),
                      rvol=[None] * 60 + [RVOL_ELEVATED] * (TOP_CONFIRM - 1),
                      cud=[5] * 60 + [0] * (TOP_CONFIRM - 1), rs=80.0)
    assert at.stage == "stock:top"
    assert below.stage == "stock:advance"


def test_decline_confirm_boundary():
    """Exactly DECLINE_CONFIRM consecutive closes below the SMA (RS faded) flip to decline; one fewer holds."""
    base = _ramp(100.0, 1.0, 60)
    at = _classify(base + [120.0] * DECLINE_CONFIRM,
                   rs=[80.0] * 60 + [50.0] * DECLINE_CONFIRM, cud=[5] * 60 + [0] * DECLINE_CONFIRM)
    below = _classify(base + [120.0] * (DECLINE_CONFIRM - 1),
                      rs=[80.0] * 60 + [50.0] * (DECLINE_CONFIRM - 1), cud=[5] * 60 + [0] * (DECLINE_CONFIRM - 1))
    assert at.stage == "stock:decline"
    assert below.stage == "stock:advance"


def test_rvol_elevated_boundary_for_distribution():
    """A stall day counts as distribution only at rvol ≥ RVOL_ELEVATED; just below, the stall is not
    distribution, so TOP_CONFIRM such days do NOT top the stock."""
    base = _ramp(100.0, 1.0, 60)
    at = _classify(base + [159.0] * TOP_CONFIRM,
                   rvol=[None] * 60 + [RVOL_ELEVATED] * TOP_CONFIRM, cud=[5] * 60 + [0] * TOP_CONFIRM, rs=80.0)
    below = _classify(base + [159.0] * TOP_CONFIRM,
                      rvol=[None] * 60 + [round(RVOL_ELEVATED - 0.1, 4)] * TOP_CONFIRM,
                      cud=[5] * 60 + [0] * TOP_CONFIRM, rs=80.0)
    assert at.stage == "stock:top"
    assert below.stage == "stock:advance"             # sub-elevated volume ⇒ no distribution ⇒ no top


def test_thresholds_are_named_constants():
    """Thresholds are 文献值待verdict校准 named constants, not magic literals (sane ordering across scales)."""
    assert 2 <= SMA_WINDOW and 1 <= BREAKOUT_MIN_RUN
    assert 0.0 < RS_STRONG <= 100.0                   # rs_percentile scale [0,100]
    assert RVOL_ELEVATED > 1.0                         # elevated = above average
    assert TOP_CONFIRM >= 2 and DECLINE_CONFIRM >= 2   # the no-flicker guarantees need > 1
    assert 0.0 < EARNINGS_GAP < 1.0 and CLIMAX_DIST > 0.0
    assert MIN_HISTORY >= SMA_WINDOW                    # warm-up covers at least a full SMA window
