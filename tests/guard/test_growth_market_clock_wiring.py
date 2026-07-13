"""P2 — growth market-clock, wired pack-conditionally through the L4 guard.

Pins the deliverable-2 contract: a growth-pack run reads the three-state MARKET clock end-to-end
(GuardedPolicy -> screen_decision -> GrowthMarketClock -> frontside/risk_gate veto), while the momo
path stays BYTE-IDENTICAL (GCycle, `vocabulary` defaulted/"momo"). The three-state truth table itself
is unit-tested in tests/regime/test_growth_clock.py; here we prove the vocabulary-conditional selection
and the accumulating history thread reach the veto.
"""
from __future__ import annotations

from datetime import date, datetime

from alpha.data.source import FakeSource
from alpha.eval.decision import Candidate, DecisionPackage
from alpha.guard.screen import GuardedPolicy, screen_decision
from alpha.harness.regime import CANONICAL_PHASES
from alpha.state.market import MarketState
from alpha.universe.universe import CandidateUniverse

CUR = date(2026, 6, 30)


def _state(g: int, l: int, *, day: date = CUR) -> MarketState:
    return MarketState(date=day, gainer_count=g, gap_up_count=0, loser_count=l,
                       failed_breakout_count=0, max_runner_tier=1, echelon=[],
                       breadth_raw=float(g - l), as_of=datetime(day.year, day.month, day.day, 16, 0))


def _pkg(*symbols: str) -> DecisionPackage:
    return DecisionPackage(date=CUR, candidates=[Candidate(symbol=s) for s in symbols])


def _source() -> FakeSource:
    return FakeSource(calendar=[date(2026, 6, d) for d in range(1, 31)], bars={}, snapshots={})


_UPTREND = [_state(g, l) for g, l in [(6, 4), (7, 3)] * 5]        # healthy uptrend backdrop
_CORRECTION = [_state(1, 9) for _ in range(10)]                   # deep breadth weakness


# ── screen_decision: vocabulary picks the reader; the read carries a growth token ────────────────────

def test_growth_vocabulary_reads_the_growth_market_clock():
    """vocabulary='growth' -> the regime phase is a growth MARKET token, not a momo canonical phase."""
    out = screen_decision(_pkg("AAA"), source=_source(), state=_state(7, 3),
                          history=_UPTREND, vocabulary="growth")
    assert out.regime is not None
    assert out.regime.phase == "market:confirmed_uptrend"
    assert out.regime.frontside is True
    assert [c.symbol for c in out.candidates] == ["AAA"]          # confirmed uptrend -> new buy allowed


def test_growth_correction_vetoes_new_entries():
    """A deep-correction backdrop reads correction (risk-off floor) -> the new entry is dropped with a
    growth-token veto reason (现金是仓位)."""
    out = screen_decision(_pkg("AAA"), source=_source(), state=_state(1, 9),
                          history=_CORRECTION, vocabulary="growth")
    assert out.regime.phase == "market:correction"
    assert out.candidates == []
    assert any("AAA" in r for r in out.key_risks)


def test_growth_warmup_blocks_before_history_accrues():
    """No threaded history -> the growth clock is warm-up (under_pressure, NOT frontside) -> new entries
    are blocked until the backdrop can be assessed (the conservative default that keeps trap days out)."""
    out = screen_decision(_pkg("AAA"), source=_source(), state=_state(9, 1), vocabulary="growth")
    assert out.regime.phase == "market:under_pressure"
    assert out.regime.frontside is False
    assert out.candidates == []


# ── momo path is byte-identical: default vocabulary reads GCycle (canonical phase) ───────────────────

def test_momo_default_reads_gcycle_unchanged():
    """Default vocabulary (momo) reads GCycle: the phase is a canonical momo phase, NOT a market token."""
    st = _state(8, 2)
    default = screen_decision(_pkg("AAA"), source=_source(), state=st)
    explicit = screen_decision(_pkg("AAA"), source=_source(), state=st, vocabulary="momo")
    assert default.regime.phase in CANONICAL_PHASES
    assert ":" not in default.regime.phase
    # explicit "momo" and the default are the same read (byte-identical selection)
    assert (default.regime.phase, default.regime.frontside, default.regime.risk_gate) == \
           (explicit.regime.phase, explicit.regime.frontside, explicit.regime.risk_gate)


def test_momo_ignores_growth_history_shape():
    """Under momo the growth clock never runs — the same uptrend history reads GCycle, unchanged by the
    P2 growth branch (the momo regime read does not depend on the threaded market history)."""
    st = _state(8, 2)
    no_hist = screen_decision(_pkg("AAA"), source=_source(), state=st, vocabulary="momo")
    with_hist = screen_decision(_pkg("AAA"), source=_source(), state=st, history=_UPTREND,
                                vocabulary="momo")
    assert no_hist.regime.phase == with_hist.regime.phase in CANONICAL_PHASES


# ── GuardedPolicy(track_history=True): the accumulator reaches the growth read across days ───────────

class _Stub:
    def decide(self, state, universe):
        return _pkg("AAA")


def test_guarded_policy_accumulates_history_into_growth_read():
    """A growth GuardedPolicy accumulates the strictly-prior MarketStates it decides on, so the growth
    clock warms up then confirms: the FINAL day (after a full uptrend backdrop has accrued) reads
    confirmed_uptrend and lets the new entry through, while the early warm-up days blocked it."""
    gp = GuardedPolicy(_Stub(), _source(), vocabulary="growth", track_history=True)
    uni = CandidateUniverse.from_stocks([])
    outs = [gp.decide(s, uni) for s in _UPTREND]                  # feed the uptrend backdrop day by day
    final = gp.decide(_state(7, 3), uni)                          # a healthy up day after the backdrop
    assert outs[0].regime.phase == "market:under_pressure"       # day 1: warm-up, blocked
    assert outs[0].candidates == []
    assert final.regime.phase == "market:confirmed_uptrend"      # backdrop accrued -> confirmed
    assert [c.symbol for c in final.candidates] == ["AAA"]


def test_track_history_default_off_is_byte_identical():
    """Default track_history=False + no state_history -> momo GCycle, no accumulation: the regime read is
    a canonical momo phase (never a growth market token), matching a bare screen_decision on the same day."""
    st = _state(8, 2)
    gp = GuardedPolicy(_Stub(), _source())
    out = gp.decide(st, CandidateUniverse.from_stocks([]))
    bare = screen_decision(_pkg("AAA"), source=_source(), state=st)
    assert out.regime.phase in CANONICAL_PHASES
    assert (out.regime.phase, out.regime.frontside, out.regime.risk_gate) == \
           (bare.regime.phase, bare.regime.frontside, bare.regime.risk_gate)
    assert [c.symbol for c in out.candidates] == [c.symbol for c in bare.candidates]
