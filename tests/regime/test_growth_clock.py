"""P2 growth market-clock — the three-state classifier (GCycle's growth successor).

Unit truth table + hysteresis + warm-up + boundary probes for
`alpha/regime/growth_clock.py::GrowthMarketClock`. The classifier reads the manuscript's three market
states (confirmed_uptrend / under_pressure / correction; §1.1) NATIVELY from breadth/FTD/distribution
facts (never by translating momo phases). Panic is orthogonal (the guard's veto path); this file pins
the three-state read only. The end-to-end pack-conditional guard wiring lives in the guard tests; the
verdict-symmetry regression in tests/loop.
"""
from __future__ import annotations

from datetime import date, datetime

from alpha.regime.growth_clock import (
    CORRECTION_GATE, DD_CORRECTION, DD_SHARE, DD_UNDER_PRESSURE, DD_WINDOW, DEEP_SHARE, FTD_SHARE,
    GrowthMarketClock, MIN_HISTORY, PRESSURE_GATE, UPTREND_GATE, UP_DAY_SHARE, gainer_share,
    market_share,
)
from alpha.guard.veto import RISK_OFF_THRESHOLD
from alpha.state.market import MarketState

CUR = date(2026, 6, 30)


def _state(g: int, l: int, *, day: date = CUR) -> MarketState:
    return MarketState(date=day, gainer_count=g, gap_up_count=0, loser_count=l,
                       failed_breakout_count=0, max_runner_tier=1, echelon=[],
                       breadth_raw=float(g - l), as_of=datetime(day.year, day.month, day.day, 16, 0))


def _ctx(shares: list[float]) -> list[MarketState]:
    """A prior-day context from gainer-share fractions (denominator 1000 for precise means)."""
    return [_state(round(s * 1000), 1000 - round(s * 1000)) for s in shares]


def _today(share: float) -> MarketState:
    g = round(share * 1000)
    return _state(g, 1000 - g)


def _read(history: list[MarketState], today: MarketState):
    return GrowthMarketClock().read(history, today)


# ── shape: frontside/risk_gate mapping expresses §4.3 through the existing RegimeRead surface ────────

def test_confirmed_uptrend_is_frontside_new_buys_allowed():
    """A healthy uptrend backdrop + an up day reads confirmed_uptrend: frontside, risk_gate clear."""
    read = _read(_ctx([0.60, 0.65] * 5), _today(0.70))
    assert read.phase == "market:confirmed_uptrend"
    assert read.frontside is True
    assert read.risk_gate == UPTREND_GATE and read.risk_gate >= RISK_OFF_THRESHOLD


def test_follow_through_day_out_of_a_correction_confirms():
    """A single strong-breadth up day (>= FTD_SHARE) out of a distribution-heavy backdrop confirms the
    uptrend — the manuscript's 'FTD confirms uptrend'. The choppy correction has a DD cluster but the
    follow-through day ANCHORS a fresh distribution count (its DDs are pre-anchor, no longer counted)."""
    corr = _ctx([0.636, 0.125] * 5)                 # 5 distribution days, mean ~0.38
    read = _read(corr, _today(0.80))
    assert read.phase == "market:confirmed_uptrend"
    assert read.frontside is True


def test_distribution_cluster_downgrades_to_under_pressure():
    """>= DD_UNDER_PRESSURE distribution days in the window, with no follow-through day, is under_pressure:
    NOT frontside (禁新建仓) but above the risk-off floor (graded appetite, not cash-is-position)."""
    # confirm first (FTD), then accrue a DD cluster with only weak (< FTD_SHARE) bounces
    seq = [0.70] + [0.35, 0.52] * 5                  # FTD, then 5 DDs interleaved with sub-FTD up days
    read = _read(_ctx(seq), _today(0.52))
    assert read.phase == "market:under_pressure"
    assert read.frontside is False
    assert read.risk_gate == PRESSURE_GATE
    assert read.risk_gate >= RISK_OFF_THRESHOLD      # under_pressure is NOT risk-off (禁新建仓, 加仓减半)


def test_deep_breadth_weakness_is_correction_risk_off_floor():
    """A deep, sustained breadth collapse (trailing mean <= DEEP_SHARE) with no follow-through is
    correction: NOT frontside AND risk_gate below the risk-off floor (现金是仓位)."""
    read = _read(_ctx([0.10] * 12), _today(0.20))
    assert read.phase == "market:correction"
    assert read.frontside is False
    assert read.risk_gate == CORRECTION_GATE
    assert read.risk_gate < RISK_OFF_THRESHOLD       # correction trips the risk-off veto branch


# ── warm-up: insufficient history abstains conservatively (not frontside) ────────────────────────────

def test_warmup_insufficient_history_is_under_pressure_not_frontside():
    """Fewer than MIN_HISTORY non-empty prior days -> the backdrop can't be assessed -> conservative
    under_pressure (NOT frontside), regardless of how strong today looks. This is what keeps the P1
    blowoff/backside trap days (empty history) vetoed under the growth read."""
    read = _read(_ctx([0.60] * (MIN_HISTORY - 1)), _today(0.90))   # strong today, too little history
    assert read.frontside is False
    assert read.phase == "market:under_pressure"


def test_empty_history_is_not_frontside():
    read = _read([], _today(0.90))
    assert read.frontside is False


def test_empty_tape_days_excluded_from_history_floor():
    """0/0 empty-tape days (feed outage) don't count toward MIN_HISTORY (not evidence) — a window of
    mostly outages with too few real days stays warm-up (mirrors the panic detector)."""
    ctx = [_state(0, 0) for _ in range(6)] + _ctx([0.60] * (MIN_HISTORY - 1))
    assert _read(ctx, _today(0.90)).frontside is False


# ── hysteresis: cross-day state, not per-day re-derivation ───────────────────────────────────────────

def test_hysteresis_confirmed_persists_through_isolated_down_days():
    """Once confirmed, isolated down days below the cluster threshold do NOT un-confirm — the read is a
    state machine with memory, not a per-day banding of today's share."""
    seq = [0.70] * 6 + [0.30]                         # confirmed, then ONE distribution day
    read = _read(_ctx(seq), _today(0.55))             # a middling day after the dip
    assert read.phase == "market:confirmed_uptrend"   # a single DD is below DD_UNDER_PRESSURE -> stays


def test_same_final_day_reads_differently_by_backdrop():
    """The identical final day reads confirmed after a healthy uptrend but under_pressure after a
    distribution cluster with no follow-through — proving the read is cross-day, not memoryless."""
    healthy = _read(_ctx([0.62, 0.66] * 5), _today(0.50))
    clustered = _read(_ctx([0.70] + [0.35, 0.52] * 5), _today(0.50))
    assert healthy.phase == "market:confirmed_uptrend"
    assert clustered.phase == "market:under_pressure"


# ── confirmation anchor: FTD resets the DD count, so no ABAB oscillation (the HIGH review finding) ────

def _incremental_states(shares: list[float]) -> list[str]:
    """The state read on each day as the driver sees it: today = shares[:k][-1], history = the rest."""
    from alpha.regime.growth_clock import _run_machine
    return [_run_machine(shares[:k]) for k in range(1, len(shares) + 1)]


def _transitions(states: list[str]) -> int:
    return sum(1 for a, b in zip(states, states[1:]) if a != b)


def test_confirmation_anchors_dd_count_no_abab_oscillation():
    """The HIGH bug: after a DD cluster downgrades, a run of IDENTICAL strong up days must confirm and
    STAY confirmed — the fresh FTD anchors a new distribution count, so stale pre-FTD DDs no longer
    un-confirm the next day. Before the fix these four 1.00 days read confirmed/pressure/confirmed/pressure."""
    shares = [0.70] + [0.35, 0.52] * 5 + [1.0, 1.0, 1.0, 1.0]
    states = _incremental_states(shares)
    assert states[-4:] == ["confirmed_uptrend"] * 4
    assert _transitions(states[-5:]) <= 1              # one re-confirmation, not day-parity alternation


def test_stable_after_ftd_out_of_dd_cluster_both_variants():
    """Reviewer probe (a): [0.70]*6 + [0.38,0.52]*n + [0.65]*8 — the eight 0.65 follow-through days are
    STABLE (confirm once, then no alternation), for both the 5-DD (under_pressure) and 8-DD (correction)
    preceding clusters."""
    for dd in (5, 8):
        shares = [0.70] * 6 + [0.38, 0.52] * dd + [0.65] * 8
        tail = _incremental_states(shares)[-8:]
        assert tail == ["confirmed_uptrend"] * 8, f"{dd}-DD variant not stable: {tail}"


def test_day_after_ftd_with_residual_dds_stays_confirmed():
    """Reviewer probe (b): the day AFTER a follow-through day stays confirmed even though pre-FTD DDs are
    still inside the 25-day window — they are before the anchor, so they no longer count (the old suite
    only read ON the FTD day, hiding the bug)."""
    shares = [0.70] + [0.35, 0.52] * 5 + [0.65, 0.52]     # confirm, 5-DD cluster, FTD, then a mild day
    states = _incremental_states(shares)
    assert states[-2] == "confirmed_uptrend"              # the FTD day
    assert states[-1] == "confirmed_uptrend"              # the day AFTER — residual DDs do NOT un-confirm


def test_deep_downgrade_needs_more_than_a_single_day():
    """The deep-breadth leg is guarded by DEEP_MIN_DAYS so a single weak day after a confirmation can't
    flip confirmed->correction (which would re-introduce oscillation); a sustained deep run still does."""
    from alpha.regime.growth_clock import DEEP_MIN_DAYS
    one_weak = [0.70] * 6 + [0.10]                        # confirm, then ONE deep day -> no twitch
    assert _incremental_states(one_weak)[-1] == "confirmed_uptrend"
    assert DEEP_MIN_DAYS >= 2
    sustained = [0.70] * 6 + [0.10] * (DEEP_MIN_DAYS + 2)  # confirm, then a sustained waterfall
    assert _incremental_states(sustained)[-1] == "correction"


# ── empty (0/0) today abstains — no synthetic 0.0 max-bearish distribution day (review finding #2) ────

def test_empty_today_does_not_act_as_synthetic_distribution_day():
    """4 post-confirmation DDs (< DD_UNDER_PRESSURE) then an EMPTY (0/0) today. Baking empty in as share
    0.0 would be a synthetic 5th distribution day -> under_pressure; abstaining carries the confirmed read
    forward. A feed-outage day is no evidence (matches the panic detector + the docstring)."""
    history = _ctx([0.70] + [0.35, 0.52] * 4)             # confirm + 4 DDs -> still confirmed
    assert _read(history, _state(0, 0)).phase == "market:confirmed_uptrend"


def test_consecutive_reads_ignore_an_intervening_empty_day():
    """An empty day, once it becomes history, must not change a later read (filtered, not a 0.0 DD) — a
    datum day t treats as never-existing cannot move day t+1's read."""
    base = _ctx([0.62, 0.66] * 5)
    a = _read(list(base), _today(0.50))
    b = _read(list(base) + [_state(0, 0)], _today(0.50))
    assert a.phase == b.phase


# ── purity: same (history, today) always yields the same read (no hidden state) ──────────────────────

def test_read_is_pure_function_of_inputs():
    clock = GrowthMarketClock()
    hist, today = _ctx([0.62, 0.66] * 5), _today(0.50)
    a = clock.read(hist, today)
    b = clock.read(hist, today)
    assert (a.phase, a.frontside, a.risk_gate) == (b.phase, b.frontside, b.risk_gate)


# ── boundary probes: each threshold pinned so mutating it trips a test ────────────────────────────────

def test_ftd_share_boundary():
    """FTD confirms at/above FTD_SHARE, not just below (out of a downgraded state)."""
    corr = _ctx([0.35] * 12)                          # a distribution/correction backdrop
    assert _read(corr, _today(FTD_SHARE)).frontside is True
    assert _read(corr, _today(FTD_SHARE - 0.01)).frontside is False


def test_dd_under_pressure_count_boundary():
    """DD_UNDER_PRESSURE distribution days downgrade a confirmed uptrend; one fewer does not."""
    # confirm, then exactly DD_UNDER_PRESSURE DDs (each followed by a sub-FTD up day so no re-confirm)
    at = [0.70] + [0.35, 0.52] * DD_UNDER_PRESSURE
    below = [0.70] + [0.35, 0.52] * (DD_UNDER_PRESSURE - 1)
    assert _read(_ctx(at), _today(0.52)).phase == "market:under_pressure"
    assert _read(_ctx(below), _today(0.52)).phase == "market:confirmed_uptrend"


def test_dd_share_boundary():
    """A day at/below DD_SHARE counts as distribution; just above does not."""
    at = [0.70] + [DD_SHARE, 0.52] * DD_UNDER_PRESSURE
    above = [0.70] + [DD_SHARE + 0.01, 0.52] * DD_UNDER_PRESSURE
    assert _read(_ctx(at), _today(0.52)).phase == "market:under_pressure"
    assert _read(_ctx(above), _today(0.52)).phase == "market:confirmed_uptrend"


def test_deep_share_boundary_forces_correction():
    """A trailing mean at/below DEEP_SHARE reads correction even without a full DD count; just above
    (but still weak) reads the milder under_pressure."""
    assert _read(_ctx([DEEP_SHARE] * 12), _today(0.20)).phase == "market:correction"
    just_above = round(DEEP_SHARE + 0.05, 2)          # weak but not deep; few enough DDs to stay pressure
    read = _read(_ctx([just_above] * 12), _today(just_above))
    assert read.phase in {"market:under_pressure", "market:correction"}
    assert read.frontside is False


def test_thresholds_are_named_constants():
    """Thresholds are 文献值待verdict校准 named constants, not magic literals."""
    assert 0.5 < FTD_SHARE <= 1.0
    assert 0.0 < DD_SHARE < 0.5
    assert 0.0 < DEEP_SHARE <= DD_SHARE
    assert 1 <= DD_UNDER_PRESSURE <= DD_CORRECTION
    assert DD_WINDOW >= DD_CORRECTION
    assert MIN_HISTORY >= 1
    assert CORRECTION_GATE < RISK_OFF_THRESHOLD <= PRESSURE_GATE < UPTREND_GATE
    assert 0.0 < UP_DAY_SHARE < FTD_SHARE


def test_gainer_share_empty_tape_is_zero():
    assert gainer_share(_state(0, 0)) == 0.0
    assert gainer_share(_state(3, 1)) == 0.75


# ── breadth-family refinement: when full advance/decline is threaded, the clock reads it ─────────────

def _ad_state(adv: int, dec: int, *, g: int = 9, l: int = 1) -> MarketState:
    """A state whose gainer tail says one thing (share g/(g+l)) and whose full-cross-section a/d says
    another — so a test can prove which signal the clock reads."""
    return MarketState(date=CUR, gainer_count=g, gap_up_count=0, loser_count=l, failed_breakout_count=0,
                       max_runner_tier=1, echelon=[], breadth_raw=float(g - l), advances=adv, declines=dec,
                       as_of=datetime(CUR.year, CUR.month, CUR.day, 16, 0))


def test_market_share_prefers_advance_decline_when_present():
    """market_share reads the full-cross-section a/d when threaded (a real market-trend signal), NOT the
    ±10%-gainer tail; falls back to gainer_share when a/d is absent (the live-path default)."""
    st = _ad_state(100, 900)                          # gainer tail 0.90, but broad a/d 0.10
    assert gainer_share(st) == 0.9
    assert market_share(st) == 0.1
    assert market_share(_state(9, 1)) == gainer_share(_state(9, 1))   # a/d absent -> gainer_share


def test_clock_reads_advance_decline_backdrop():
    """A backdrop where the gainer tail looks strong every day but the FULL a/d is a broad decline reads
    as weakness (NOT a confirmed uptrend) — the a/d refinement changes the state vs the tail read."""
    ad_decline = [_ad_state(100, 900) for _ in range(12)]            # broad-decline a/d, strong tail
    assert GrowthMarketClock().read(ad_decline, _ad_state(100, 900)).frontside is False
    # the SAME strong gainer tail WITHOUT a/d threaded reads confirmed (proving a/d is what flipped it)
    tail_only = [_state(9, 1) for _ in range(12)]
    assert GrowthMarketClock().read(tail_only, _state(9, 1)).phase == "market:confirmed_uptrend"
