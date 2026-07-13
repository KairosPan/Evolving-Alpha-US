"""P1 panic-state L4 veto — the momentum-crash guard.

Unit-level coverage for `alpha/guard/panic.py::detect_panic_state` and its wiring through
`CandidateContext` / `veto` / `screen_decision` / `GuardedPolicy`. The end-to-end trap-day battery
lives in `test_trap_day_battery.py`; this file pins the detector truth table + the additive,
default-None thread that keeps every existing caller byte-identical.
"""
from __future__ import annotations

from datetime import date, datetime

from alpha.data.source import FakeSource
from alpha.eval.decision import Candidate, DecisionPackage
from alpha.guard.panic import (
    BEAR_SHARE_MAX, DEEP_BEAR_SHARE_MAX, PANIC_LATCH_MIN_DAYS, PANIC_MIN_HISTORY, REBOUND_SHARE_MIN,
    VOL_SHARE_STD_MIN, detect_panic_state,
)
from alpha.guard.screen import GuardedPolicy, screen_decision
from alpha.guard.veto import CandidateContext, veto
from alpha.regime.classifier import GCycle
from alpha.state.market import MarketState
from alpha.universe.universe import CandidateUniverse

CUR = date(2026, 6, 12)


def _state(g: int, l: int, *, day: date = CUR, fb: int = 0, ft: float | None = None,
           sn: float | None = None) -> MarketState:
    return MarketState(date=day, gainer_count=g, gap_up_count=0, loser_count=l,
                       failed_breakout_count=fb, max_runner_tier=1, echelon=[],
                       breadth_raw=float(g - l), sentiment_norm=sn, follow_through_rate=ft,
                       as_of=datetime(day.year, day.month, day.day, 16, 0))


# a bear + high-volatility context (mean gainer-share 0.30, high dispersion) preceding the rebound
_PANIC_CTX = [_state(g, l) for g, l in
              [(2, 8), (7, 3), (1, 9), (6, 4), (2, 8), (1, 9), (5, 5), (2, 8), (3, 7), (1, 9)]]
# a healthy uptrend context (mean share 0.65, low dispersion) — NOT a bear market
_UPTREND_CTX = [_state(g, l) for g, l in [(6, 4), (7, 3)] * 5]
# a WATERFALL: a uniform crash (gainer-share 0.10 every day) — dispersion is ~0 exactly when the bear is
# most severe, so it slips the high-vol proxy; the `deep_bear` OR-leg is what catches it.
_WATERFALL_CTX = [_state(1, 9) for _ in range(10)]


def _ctx(shares: list[float]) -> list[MarketState]:
    """Build a prior-day context from gainer-share fractions. Denominator 1000 gives precise trailing
    means for the boundary probes; a share < 0.5 is a down-breadth day, > 0.5 an up day."""
    return [_state(round(s * 1000), 1000 - round(s * 1000)) for s in shares]


def _today(share: float) -> MarketState:
    g = round(share * 1000)
    return _state(g, 1000 - g)


def test_sharp_rebound_after_bear_and_vol_is_panic():
    """The momentum-crash window: bear backdrop + high vol + a sharp broad rebound -> panic."""
    assert detect_panic_state(_PANIC_CTX, _state(8, 2)) is True


def test_same_rebound_after_healthy_uptrend_is_not_panic():
    """Targeted, not 'block all frontside': the identical sharp rebound with no bear backdrop is safe."""
    assert detect_panic_state(_UPTREND_CTX, _state(8, 2)) is False


def test_weak_bounce_is_not_a_sharp_rebound():
    """A weak bounce (share 0.3 < REBOUND_SHARE_MIN) is not the 急反弹 the ban targets."""
    assert REBOUND_SHARE_MIN > 0.3
    assert detect_panic_state(_PANIC_CTX, _state(3, 7)) is False


def test_low_vol_grind_down_is_not_panic():
    """Bear but calm (zero dispersion) fails the high-volatility proxy."""
    grind = [_state(4, 6) for _ in range(10)]
    assert detect_panic_state(grind, _state(8, 2)) is False


def test_insufficient_history_returns_false():
    """Honest limit: too few prior days to assess a bear backdrop -> no veto (needs evidence)."""
    assert detect_panic_state(_PANIC_CTX[:PANIC_MIN_HISTORY - 1], _state(8, 2)) is False


def test_empty_history_returns_false():
    assert detect_panic_state([], _state(8, 2)) is False


def test_thresholds_are_named_constants():
    """Thresholds are 文献值待P2校准 named constants, not magic literals."""
    assert 0.0 < BEAR_SHARE_MAX < 0.5
    assert 0.0 < DEEP_BEAR_SHARE_MAX < BEAR_SHARE_MAX   # deep-bear is a stricter subset of the bear band
    assert 0.0 < VOL_SHARE_STD_MIN < 0.5
    assert 0.5 < REBOUND_SHARE_MIN <= 1.0
    assert PANIC_LATCH_MIN_DAYS >= 1


def test_zero_tape_days_do_not_crash():
    """A day with no gainers or losers (empty tape) contributes share 0.0, never a ZeroDivisionError."""
    ctx = [_state(0, 0) for _ in range(6)]
    assert detect_panic_state(ctx, _state(0, 0)) is False


# ── Fix 1: waterfall (uniform crash) — dispersion is minimised exactly when the bear is most severe ──

def test_waterfall_uniform_crash_is_panic():
    """A uniform crash (gainer-share 0.10 every day, population stdev ~0) slips the high-vol proxy, but
    `deep_bear` (trailing mean <= DEEP_BEAR_SHARE_MAX) is the OR-leg that catches it. A sharp rebound out
    of that waterfall is still a momentum-crash window."""
    assert detect_panic_state(_WATERFALL_CTX, _state(8, 2)) is True
    # the vol-dispersion leg alone would MISS it (all days identical -> pstdev 0):
    assert VOL_SHARE_STD_MIN > 0.0


# ── Fix 2: the latch — the ban persists across the choppy continuation days of a bear rally ──────────

def test_latch_holds_through_bear_rally_continuation():
    """A 0.545-share continuation the day after a trigger is BELOW REBOUND_SHARE_MIN, so it is not itself
    a fresh trigger — but the §4.3 ban spans the crash window, so the latch keeps it vetoed (the
    Daniel-Moskowitz losing-trade case: buying the day after the panic-rebound trigger)."""
    trigger_then = list(_PANIC_CTX) + [_state(8, 2)]      # ... bear backdrop, then a panic-rebound trigger
    assert detect_panic_state(trigger_then, _today(0.545)) is True

    # a trigger day (share 0.545 < 0.60) with NO prior trigger and no bear-context rebound stays unvetoed
    assert detect_panic_state(_UPTREND_CTX, _today(0.545)) is False


def test_latch_releases_after_sustained_recovery_with_bear_cleared():
    """A sustained genuine recovery beyond the latch window, after the bear backdrop has cleared, RELEASES
    the veto (the latch is not a permanent ban). Recovery days at share 0.55 (< REBOUND_SHARE_MIN) never
    re-arm the latch, so the only trigger is the original one; well past PANIC_LATCH_MIN_DAYS with the
    bear cleared, the state releases."""
    bear = [_state(1, 9) for _ in range(5)]
    recovery = _ctx([0.55] * 14)                          # 14 days > PANIC_LATCH_MIN_DAYS, bear cleared
    released = bear + [_state(8, 2)] + recovery
    assert detect_panic_state(released, _today(0.55)) is False


# ── Fix 3: an ordinary choppy correction + follow-through day must NOT be vetoed ─────────────────────

def test_ordinary_correction_followthrough_is_not_panic():
    """The nearest-legitimate shape: an ordinary choppy 8–12% correction (trailing mean well above
    deep-bear, down-fraction below BEAR_DOWN_DAY_FRAC) followed by a legitimate follow-through day is NOT
    a momentum crash. The depth/severity separation (mean above BEAR_SHARE_MAX, < 0.60 down days) keeps
    the bear proxy False so the FTD survives, while the waterfall and interspersed-crash probes still
    fire."""
    correction = _ctx([0.636, 0.125] * 5)                 # mean ~0.38 (> BEAR_SHARE_MAX), down-frac 0.5, choppy
    assert detect_panic_state(correction, _state(8, 2)) is False
    # the separation is depth, not shape: the SAME follow-through out of a deeper bear IS panic
    assert detect_panic_state(_PANIC_CTX, _state(8, 2)) is True


# ── Fix 5: empty-tape (0/0) days are insufficient evidence, not bearish evidence ─────────────────────

def test_empty_tape_days_excluded_below_floor_returns_false():
    """A window that is mostly a feed outage (0/0 days) with fewer than PANIC_MIN_HISTORY real days can
    NOT be assessed -> False (warm-up posture), even though a naive 'empty = maximally bearish' reading
    would have fired."""
    ctx = [_state(0, 0) for _ in range(6)] + [_state(1, 9) for _ in range(4)]   # only 4 non-empty < floor 5
    assert detect_panic_state(ctx, _state(8, 2)) is False


def test_empty_tape_days_excluded_above_floor_still_fires():
    """Interleaved outages do not dilute the bear read: with >= PANIC_MIN_HISTORY real bear days the empty
    days are simply skipped and the detector fires normally."""
    ctx = [_state(0, 0) for _ in range(3)] + [_state(1, 9) for _ in range(6)]   # 6 non-empty deep-bear days
    assert detect_panic_state(ctx, _state(8, 2)) is True


# ── Fix 7: boundary probes — every proxy leg pinned both directions (mutating any leg trips a test) ──

def test_bear_mean_boundary():
    """BEAR_SHARE_MAX (mean leg): isolated with down-frac 0.5 (< BEAR_DOWN_DAY_FRAC) and high dispersion,
    so the ONLY bear evidence is the trailing mean. Fires at/below the threshold, not just above."""
    assert detect_panic_state(_ctx([0.548, 0.150] * 5), _today(0.80)) is True    # mean 0.349 <= 0.35
    assert detect_panic_state(_ctx([0.552, 0.150] * 5), _today(0.80)) is False   # mean 0.351 >  0.35


def test_down_frac_boundary():
    """BEAR_DOWN_DAY_FRAC (alt bear leg): isolated with mean > BEAR_SHARE_MAX so bear rests only on the
    down-day fraction. Fires at 6/10 down days, not at 5/10."""
    fire = _ctx([0.10, 0.10, 0.30, 0.30, 0.30, 0.30, 0.59, 0.59, 0.59, 0.59])    # 6 down, mean ~0.38
    no = _ctx([0.10, 0.10, 0.30, 0.30, 0.30, 0.59, 0.59, 0.59, 0.59, 0.59])      # 5 down, mean ~0.41
    assert detect_panic_state(fire, _today(0.80)) is True
    assert detect_panic_state(no, _today(0.80)) is False


def test_deep_bear_boundary():
    """DEEP_BEAR_SHARE_MAX (vol OR-leg): isolated with zero dispersion (uniform context, high-vol False),
    so the ONLY volatility evidence is the deep-bear mean. Fires at/below 0.25, not just above."""
    assert detect_panic_state(_ctx([0.25] * 10), _today(0.80)) is True    # mean 0.25 <= 0.25
    assert detect_panic_state(_ctx([0.26] * 10), _today(0.80)) is False   # mean 0.26 >  0.25 (and pstdev 0)


def test_vol_stdev_boundary():
    """VOL_SHARE_STD_MIN (vol OR-leg): isolated with mean > DEEP_BEAR_SHARE_MAX so deep-bear is off and
    the ONLY volatility evidence is dispersion. Fires at pstdev 0.15, not just below."""
    assert detect_panic_state(_ctx([0.45, 0.15] * 5), _today(0.80)) is True    # pstdev 0.15
    assert detect_panic_state(_ctx([0.44, 0.16] * 5), _today(0.80)) is False   # pstdev 0.14


def test_rebound_share_boundary():
    """REBOUND_SHARE_MIN: today's gainer-share must be at/above the threshold. Fires at 0.60, not 0.59."""
    assert detect_panic_state(_ctx([0.20] * 10), _today(0.60)) is True
    assert detect_panic_state(_ctx([0.20] * 10), _today(0.59)) is False


def test_rebound_jump_boundary():
    """REBOUND_JUMP_MIN: today's share minus the trailing mean must be at/above the threshold. With today
    fixed at 0.60, mean 0.40 -> jump 0.20 (fires); mean 0.41 -> jump 0.19 (does not)."""
    fire = _ctx([0.59, 0.59, 0.59, 0.59, 0.10, 0.30, 0.30, 0.30, 0.30, 0.34])   # mean 0.40
    no = _ctx([0.59, 0.59, 0.59, 0.59, 0.10, 0.30, 0.30, 0.30, 0.30, 0.35])     # mean 0.41
    assert detect_panic_state(fire, _today(0.60)) is True
    assert detect_panic_state(no, _today(0.60)) is False


def test_latch_length_boundary():
    """PANIC_LATCH_MIN_DAYS: with the bear backdrop cleared, a trigger exactly PANIC_LATCH_MIN_DAYS old is
    still latched; one day older releases. Recovery days at 0.55 (< REBOUND_SHARE_MIN) never re-arm, so
    the single trigger's age is unambiguous."""
    bear = [_state(1, 9) for _ in range(5)]
    at_boundary = bear + [_state(8, 2)] + _ctx([0.55] * (PANIC_LATCH_MIN_DAYS - 1))    # trigger age == floor
    past_boundary = bear + [_state(8, 2)] + _ctx([0.55] * PANIC_LATCH_MIN_DAYS)        # trigger age == floor+1
    assert detect_panic_state(at_boundary, _today(0.55)) is True
    assert detect_panic_state(past_boundary, _today(0.55)) is False


def test_veto_fires_on_panic_state_flag():
    """CandidateContext.panic_state -> veto with the self-describing wait-for-new-base reason."""
    frontside = GCycle().read(_state(8, 2, ft=0.5))     # trend, frontside=True, risk_gate 0.5
    assert frontside.frontside is True                   # precondition: existing guard would NOT block
    v = veto(CandidateContext(symbol="AAA", regime=frontside, panic_state=True))
    assert v.vetoed is True
    assert any("panic-state" in r and "new base" in r for r in v.reasons)


def test_candidate_context_panic_defaults_false():
    """Additive: panic_state defaults False so every existing CandidateContext is byte-identical."""
    assert CandidateContext(symbol="AAA", regime=GCycle().read(_state(8, 2, ft=0.5))).panic_state is False


def _pkg(*symbols: str) -> DecisionPackage:
    return DecisionPackage(date=CUR, candidates=[Candidate(symbol=s) for s in symbols])


def _empty_source() -> FakeSource:
    # calendar covering the context + rebound day; empty snapshots/corp -> no per-name flags fire
    return FakeSource(calendar=[date(2026, 6, d) for d in range(1, 13)], bars={}, snapshots={})


def test_screen_decision_default_history_none_is_byte_identical():
    """history=None -> detector never runs; a frontside panic-shaped day keeps its candidate."""
    out = screen_decision(_pkg("AAA"), source=_empty_source(), state=_state(8, 2, ft=0.5))
    assert [c.symbol for c in out.candidates] == ["AAA"]


def test_screen_decision_vetoes_with_panic_history_threaded():
    """With the bear+vol context threaded, the same frontside rebound day is dropped by the panic veto."""
    out = screen_decision(_pkg("AAA"), source=_empty_source(), state=_state(8, 2, ft=0.5),
                          history=_PANIC_CTX)
    assert out.candidates == []
    assert any("AAA" in r and "panic-state" in r for r in out.key_risks)


def test_guarded_policy_state_history_threads_to_veto():
    """GuardedPolicy(state_history=...) is the driver-facing thread; it reaches the veto end-to-end."""
    class _Stub:
        def decide(self, state, universe):
            return _pkg("AAA")

    gp = GuardedPolicy(_Stub(), _empty_source(), state_history=_PANIC_CTX)
    out = gp.decide(_state(8, 2, ft=0.5), CandidateUniverse.from_stocks([]))
    assert out.candidates == []
    assert any("panic-state" in r for r in out.key_risks)


def test_guarded_policy_default_state_history_byte_identical():
    class _Stub:
        def decide(self, state, universe):
            return _pkg("AAA")

    out = GuardedPolicy(_Stub(), _empty_source()).decide(
        _state(8, 2, ft=0.5), CandidateUniverse.from_stocks([]))
    assert [c.symbol for c in out.candidates] == ["AAA"]
