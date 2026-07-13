"""§1.4 three-clock activation — the source-driven CASCADE wired through the L4 guard + L3 sizing.

Proves the composition end-to-end (the pure matrix is in tests/regime/test_clock_authority.py):
  - flag OFF is byte-identical (momo AND growth), NON-vacuously (flag ON would drop / cap the same pkg);
  - the stock gate is a long-eligibility gate (只在 advance 做多): a base-reading name is vetoed, an
    advance-reading name passes; climax caps the tier but stays eligible;
  - safety-only-tightens at integration: ON veto set ⊇ OFF, ON tier ≤ OFF tier;
  - the theme gate is wired (sector map → GrowthThemeClock): an exhaustion theme vetoes;
  - PIT: a FUTURE bar cannot change a candidate's stock stage read.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta

import pandas as pd

from alpha.data.source import FakeSource
from alpha.eval.decision import Candidate, DecisionPackage
from alpha.features.theme_breadth_types import GroupBreadthReading, ThemeBreadthReading
from alpha.guard.screen import GuardedPolicy, screen_decision
from alpha.regime.clock_authority import clock_tier_cap
from alpha.sizing.policy import SizingPolicy
from alpha.state.market import MarketState
from alpha.universe.stock import StockSnapshot
from alpha.universe.universe import CandidateUniverse

SYM = "NVDA"                                    # BOOTSTRAP_SECTORS: NVDA -> "semiconductors"
CAL = [date(2026, 1, 1) + timedelta(days=i) for i in range(70)]
AS_OF = CAL[-1]


def _state(g: int, lo: int, *, day: date = AS_OF, theme=None) -> MarketState:
    return MarketState(date=day, gainer_count=g, gap_up_count=0, loser_count=lo,
                       failed_breakout_count=0, max_runner_tier=1, echelon=[], breadth_raw=float(g - lo),
                       theme_breadth=theme, as_of=datetime(day.year, day.month, day.day, 16, 0))


# a healthy uptrend backdrop -> growth market clock reads confirmed_uptrend (frontside), so the market
# veto does NOT fire and the stock/theme gates are what decide the candidate.
_UPTREND = [_state(g, lo) for g, lo in [(6, 4), (7, 3)] * 5]


def _bars(*, future: bool = False) -> pd.DataFrame:
    """A rising ramp: close = 100 + i over the calendar (a clean Stage-2 structure). `future=True`
    appends one bar dated AFTER as_of (a lookahead probe — must never change the read)."""
    rows = [{"date": d, "open": 100.0 + i, "high": 101.0 + i, "low": 99.0 + i,
             "close": 100.0 + i, "volume": 1_000} for i, d in enumerate(CAL)]
    if future:
        rows.append({"date": AS_OF + timedelta(days=1), "open": 500.0, "high": 500.0,
                     "low": 500.0, "close": 500.0, "volume": 9_999})
    return pd.DataFrame(rows)


def _source(*, future: bool = False) -> FakeSource:
    return FakeSource(calendar=CAL, bars={SYM: _bars(future=future)}, snapshots={})


def _universe(*, rs: float | None) -> CandidateUniverse:
    """The today snapshot: close continues the ramp; `rs` set (≥70) makes today a fresh breakout ->
    advance, `rs=None` leaves it a non-confirmed base."""
    return CandidateUniverse.from_stocks([
        StockSnapshot(symbol=SYM, name=SYM, status="trend_template", close=169.0, prev_close=168.0,
                      rs_percentile=rs, consecutive_up_days=3, rvol=1.0)])


def _pkg() -> DecisionPackage:
    return DecisionPackage(date=AS_OF, candidates=[Candidate(symbol=SYM, confidence=0.9)])


def _screen(*, clock: bool, rs: float | None = 80.0, vocab: str = "growth",
            theme=None, future: bool = False, state=None) -> DecisionPackage:
    st = state if state is not None else _state(7, 3, theme=theme)
    return screen_decision(_pkg(), source=_source(future=future), state=st, history=_UPTREND,
                           vocabulary=vocab, universe=_universe(rs=rs), clock_authority=clock)


# ── stock gate: only advance is long-eligible (只在 advance 做多) ────────────────────────────────────

def test_stock_advance_passes_the_long_eligibility_gate():
    out = _screen(clock=True, rs=80.0)
    assert [c.symbol for c in out.candidates] == [SYM]                # a fresh breakout -> advance -> kept
    assert out.candidates[0].stock_stage == "stock:advance"           # the read is attached


def test_stock_base_is_vetoed_by_the_gate():
    out = _screen(clock=True, rs=None)                                # no rs confirmation -> stays base
    assert out.candidates == []
    assert any("advance" in r for r in out.key_risks)                 # 只在 advance 做多


def test_documented_limit_no_fresh_breakout_today_reads_base():
    """HONEST-LIMIT pin (see `_bar_stock_history`): history carries no rs_percentile, so advance can only
    anchor on TODAY. A name above a rising SMA with strong RS but NO up-run today (consecutive_up_days<2 ->
    no fresh breakout) reads stock:base and is VETOED — the wired gate is 'fresh breakout today, else base'.
    Stricter, never looser; if a future caller threads historical rs this pin is expected to change."""
    uni = CandidateUniverse.from_stocks([
        StockSnapshot(symbol=SYM, name=SYM, status="trend_template", close=169.0, prev_close=168.0,
                      rs_percentile=90.0, consecutive_up_days=0, rvol=1.0)])   # strong RS, but no up-run
    out = screen_decision(_pkg(), source=_source(), state=_state(7, 3), history=_UPTREND,
                          vocabulary="growth", universe=uni, clock_authority=True)
    assert out.candidates == []                                       # no fresh breakout -> base -> vetoed


# ── flag OFF is byte-identical (NON-vacuous: ON drops the base name) ─────────────────────────────────

def test_flag_off_growth_keeps_the_base_name_byte_identical():
    """A base-reading name that the ON path DROPS is KEPT when the flag is OFF — and the OFF result equals
    the default (no clock_authority kwarg): proof the gate cannot leak when off, and that it really bites."""
    off = _screen(clock=False, rs=None)
    default = screen_decision(_pkg(), source=_source(), state=_state(7, 3), history=_UPTREND,
                              vocabulary="growth", universe=_universe(rs=None))   # no clock kwarg
    on = _screen(clock=True, rs=None)
    assert [c.symbol for c in off.candidates] == [SYM]                # OFF keeps it (market says frontside)
    assert off.model_dump() == default.model_dump()                   # OFF == pre-change default
    assert on.candidates == []                                        # ON drops it (non-vacuous)


def test_flag_off_momo_is_byte_identical():
    """Under momo the cascade never runs even with clock_authority=True (it gates on vocabulary=='growth'):
    ON, OFF, and the no-kwarg default all produce the identical package (the momo path is untouched)."""
    on = _screen(clock=True, rs=None, vocab="momo")
    off = _screen(clock=False, rs=None, vocab="momo")
    default = screen_decision(_pkg(), source=_source(), state=_state(7, 3), history=_UPTREND,
                              vocabulary="momo", universe=_universe(rs=None))   # no clock kwarg
    assert on.model_dump() == off.model_dump() == default.model_dump()


# ── safety-only-tightens at integration: ON veto ⊇ OFF, ON tier ≤ OFF tier ───────────────────────────

def test_on_is_a_veto_superset_of_off():
    on_base = _screen(clock=True, rs=None)
    off_base = _screen(clock=False, rs=None)
    assert set(off_base.key_risks) <= set(on_base.key_risks)          # ON adds reasons, never removes
    assert len(on_base.candidates) <= len(off_base.candidates)        # ON keeps a subset


def test_climax_caps_the_size_tier_but_stays_eligible():
    """A parabolic advance (close far above the SMA + a sharp thrust) stays long-eligible (advance) but
    the attached climax_run caps the L3 tier below what confidence×risk_gate alone would assign."""
    # a blow-off today: close far above the ramp SMA (~144) with a big pct thrust -> climax on advance.
    uni = CandidateUniverse.from_stocks([
        StockSnapshot(symbol=SYM, name=SYM, status="trend_template", close=260.0, prev_close=168.0,
                      rs_percentile=80.0, consecutive_up_days=6, rvol=1.0)])
    src = _source()
    guarded = GuardedPolicy(_StubPolicy(uni), src, vocabulary="growth", state_history=list(_UPTREND),
                            clock_authority=True)
    sized = SizingPolicy(guarded)
    out = sized.decide(_state(7, 3), uni)
    kept = [c for c in out.candidates if c.symbol == SYM]
    assert kept and kept[0].stock_stage == "stock:advance"            # still long-eligible
    assert kept[0].climax_run is True                                 # but flagged reduce
    assert clock_tier_cap(kept[0].stock_stage, kept[0].theme_phase, climax_run=True) == "core"
    assert kept[0].size_tier in ("probe", "core", "flat")             # capped at/below core (not heavy)


class _StubPolicy:
    def __init__(self, uni):
        self._uni = uni

    def decide(self, state, universe, *, collect=None):
        return _pkg()


# ── theme gate is wired: sector map → GrowthThemeClock → veto ────────────────────────────────────────

def _theme(phase_group: str, reading: GroupBreadthReading) -> ThemeBreadthReading:
    return ThemeBreadthReading(day=AS_OF, groups={phase_group: reading})


def _grp(bt, rt, *, breadth=0.6, disp=25.0) -> GroupBreadthReading:
    return GroupBreadthReading(group="semiconductors", member_count=8, determined=True,
                               pct_above_200dma=breadth, breadth_trend=bt, rs_trend=rt,
                               rs_dispersion=disp, laggard_rs_mean=40.0)


def test_theme_exhaustion_vetoes_the_candidate_theme():
    """The candidate's sector (semiconductors) rolls into exhaustion — the theme leg (sector_map ->
    GrowthThemeClock -> compose) vetoes even a clean advance (高尺度否决低尺度)."""
    # institutional for 2 days, then rolling-over + rs-down for EXHAUSTION_CONFIRM days -> exhaustion.
    hist = [_state(7, 3, day=CAL[i], theme=_theme("semiconductors", _grp(0.1, 5.0))) for i in range(3)]
    hist += [_state(7, 3, day=CAL[3], theme=_theme("semiconductors", _grp(-0.1, -5.0)))]
    today = _state(7, 3, theme=_theme("semiconductors", _grp(-0.1, -5.0)))
    out = screen_decision(_pkg(), source=_source(), state=today, history=hist,
                          vocabulary="growth", universe=_universe(rs=80.0), clock_authority=True)
    assert out.candidates == []
    assert any("exhaustion" in r for r in out.key_risks)


# ── PIT: a future bar cannot change the read ─────────────────────────────────────────────────────────

def test_future_bar_cannot_change_the_stock_stage():
    clean = _screen(clock=True, rs=80.0, future=False)
    withfut = _screen(clock=True, rs=80.0, future=True)               # a wild bar dated after as_of
    assert (clean.candidates[0].stock_stage if clean.candidates else None) == \
           (withfut.candidates[0].stock_stage if withfut.candidates else None) == "stock:advance"
