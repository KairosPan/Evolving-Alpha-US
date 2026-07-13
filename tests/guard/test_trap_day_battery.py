"""P1 — the adversarial trap-day battery (kairos-mining §2.5; DEVELOPMENT-PLAN §1 P1).

Synthetic trap days — tapes built so that ANY new long = fail — run through the FULL production
decision stack `SizingPolicy(GuardedPolicy(LLMAgentPolicy(H, mock)))` with a scripted MockLLMClient
that AGGRESSIVELY proposes buys every day (the "ten years of muscle memory" adversary). The battery
asserts ZERO new longs survive on every trap day, under BOTH seed packs. These are
regression/promotion preconditions, NOT training signal — they never touch live eval/verdict scoring;
this is the guardrail that lets P2's GCycle recalibration proceed without silently re-opening
chase-risk entries.

Three trap classes (each proves it exercises the intended GCycle read — a mis-constructed fixture is a
bug this battery catches):
  1. blowoff-top  -> distribution (frontside=False), vetoed by the EXISTING backside branch;
  2. backside     -> washout / distribution / flush (frontside=False), existing risk-off/backside branch;
  3. panic-state  -> a sharp rebound the momo GCycle reads as frontside `trend`, which the EXISTING guard
                     does NOT block (the momentum-crash blind spot) — vetoed only by the P1 panic veto.

Fixtures build the `MarketState` directly (like the guard acceptance tests) so the regime read is exact
and asserted per day; the `FakeSource` carries empty snapshots/corp-actions so no per-name flag fires
and the REGIME veto is the sole cause of every drop.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import date, datetime

import pytest

from alpha.agent.agent import LLMAgentPolicy
from alpha.data.source import FakeSource
from alpha.guard.screen import GuardedPolicy
from alpha.harness.loader import load_pack
from alpha.llm.client import MockLLMClient
from alpha.regime.classifier import GCycle
from alpha.sizing.policy import SizingPolicy
from alpha.state.market import MarketState
from alpha.universe.stock import StockSnapshot
from alpha.universe.universe import CandidateUniverse

CUR = date(2026, 6, 30)
LEADS = ("LEADR1", "LEADR2", "LEADR3")

# the aggressive buyer: proposes every leader as a high-conviction long, regardless of the tape.
AGGRESSIVE_BUY = json.dumps({
    "candidates": [{"symbol": s, "pattern": "breakout", "reason": "leader ripping — buy it",
                    "confidence": 0.9, "narrative": "ai-compute"} for s in LEADS],
    "regime_read": "risk-on — chase the leaders", "no_trade_reason": "",
})


def _state(g: int, l: int, *, fb: int = 0, ft: float | None = None, sn: float | None = None,
           day: date = CUR) -> MarketState:
    return MarketState(date=day, gainer_count=g, gap_up_count=0, loser_count=l,
                       failed_breakout_count=fb, max_runner_tier=1, echelon=[],
                       breadth_raw=float(g - l), sentiment_norm=sn, follow_through_rate=ft,
                       as_of=datetime(day.year, day.month, day.day, 16, 0))


def _universe() -> CandidateUniverse:
    return CandidateUniverse.from_stocks(
        [StockSnapshot(symbol=s, name=s, status="gainer", close=115.0, prev_close=100.0,
                       pct_change=15.0) for s in LEADS])


def _source() -> FakeSource:
    # calendar ending at CUR (prev-day SSR lookup resolves); empty snapshots/corp -> no per-name flags.
    return FakeSource(calendar=[date(2026, 6, d) for d in range(1, 31)], bars={}, snapshots={})


# a bear + high-volatility backdrop (mean gainer-share 0.30, high dispersion) preceding a panic rebound
_PANIC_CTX = [_state(g, l) for g, l in
              [(2, 8), (7, 3), (1, 9), (6, 4), (2, 8), (1, 9), (5, 5), (2, 8), (3, 7), (1, 9)]]
# a healthy uptrend backdrop (mean share 0.65, low dispersion) — NOT a bear market
_UPTREND_CTX = [_state(g, l) for g, l in [(6, 4), (7, 3)] * 5]
# a WATERFALL backdrop: a uniform crash (share 0.10 every day, ~zero dispersion). Dispersion is minimised
# exactly when the bear is most severe, so the deep-bear leg — not the vol-dispersion leg — flags it.
_WATERFALL_CTX = [_state(1, 9) for _ in range(10)]
# a DEEP interspersed bear (mean 0.21, high dispersion, few relief bounces) — a third distinct backdrop so
# the panic class does not all share one context shape.
_DEEP_CTX = [_state(g, l) for g, l in
             [(1, 9), (6, 4), (1, 9), (1, 9), (5, 5), (1, 9), (2, 8), (1, 9), (1, 9), (2, 8)]]
# an ordinary choppy 8–12% correction (mean ~0.38 > bear band, down-frac 0.5) — the nearest-legitimate
# shape to a panic backdrop; a follow-through day out of it must NOT be vetoed (Fix: FTD over-block).
_CORRECTION_CTX = [_state(g, l) for g, l in [(7, 4), (1, 7)] * 5]


@dataclass(frozen=True)
class TrapDay:
    trap_id: str
    state: MarketState
    phase: str            # asserted GCycle phase (fixture-integrity)
    frontside: bool       # asserted GCycle frontside (fixture-integrity)
    history: list = field(default_factory=list)   # prior-state backdrop threaded to the guard


# 1. blowoff-top: euphoric reading but internals deteriorating (failed breakouts climbing) -> distribution
BLOWOFF_DAYS = [
    TrapDay("blowoff_climax_high_sentiment", _state(8, 2, fb=5, ft=0.5, sn=0.70), "distribution", False),
    TrapDay("blowoff_breadth_narrowing", _state(10, 3, fb=4, ft=0.1, sn=0.65), "distribution", False),
    TrapDay("blowoff_midband_failed_breakouts", _state(5, 5, fb=3, ft=0.2, sn=0.50), "distribution", False),
]
# 2. backside: every pop sold
BACKSIDE_DAYS = [
    TrapDay("backside_washout_risk_off", _state(1, 9), "washout", False),
    TrapDay("backside_distribution_midband", _state(5, 6, fb=4), "distribution", False),
    TrapDay("backside_flush_elevated_percentile", _state(3, 8, fb=2, ft=0.1, sn=0.65), "flush", False),
]
# 3. panic-state: sharp broad rebounds out of a bear+vol backdrop. The momo GCycle reads `trend`
#    (frontside) — the EXISTING guard passes them; only the P1 panic veto blocks them. Backdrops are
#    diversified across three distinct shapes (interspersed / deep-interspersed / waterfall).
PANIC_DAYS = [
    TrapDay("panic_rebound_broad", _state(7, 3, ft=0.5), "trend", True, list(_PANIC_CTX)),
    TrapDay("panic_rebound_sharp", _state(8, 2, ft=0.5), "trend", True, list(_PANIC_CTX)),
    TrapDay("panic_rebound_violent", _state(9, 1, ft=0.5), "trend", True, list(_DEEP_CTX)),
    TrapDay("panic_rebound_waterfall", _state(8, 2, ft=0.5), "trend", True, list(_WATERFALL_CTX)),
]
ALL_TRAP_DAYS = BLOWOFF_DAYS + BACKSIDE_DAYS + PANIC_DAYS

# a genuine (non-panic) trend day: the SAME sharp rebound after a healthy uptrend -> must NOT be vetoed.
CONTROL_GENUINE_TREND = TrapDay("control_genuine_trend", _state(8, 2, ft=0.5), "trend", True,
                                list(_UPTREND_CTX))
# a second negative control: the SAME follow-through day after an ordinary choppy correction (not a
# crash) -> the depth/severity separation keeps the panic veto off, so the leaders survive.
CONTROL_CHOPPY_CORRECTION = TrapDay("control_choppy_correction", _state(8, 2, ft=0.5), "trend", True,
                                    list(_CORRECTION_CTX))

PACKS = ["momo", "growth"]


def _full_stack(pack: str, history: list):
    """The production decorator stack around an aggressive-buyer mock: L4 guard inner, L3 sizing outer."""
    mock = MockLLMClient(AGGRESSIVE_BUY)
    agent = LLMAgentPolicy(load_pack(pack), mock)
    guarded = GuardedPolicy(agent, _source(), state_history=history)
    return SizingPolicy(guarded), mock


def _vetoed_symbols(pkg) -> set[str]:
    return {s for note in pkg.key_risks for s in LEADS if f"vetoed {s}" in note}


# ── fixture integrity: no vacuous pass ────────────────────────────────────────────────────────────

def test_battery_is_non_empty():
    """Anti-vacuous: the battery FAILS the acceptance gate if zero trap days load."""
    assert len(ALL_TRAP_DAYS) >= 9
    assert len(BLOWOFF_DAYS) >= 3 and len(BACKSIDE_DAYS) >= 3 and len(PANIC_DAYS) >= 3


@pytest.mark.parametrize("trap", ALL_TRAP_DAYS, ids=lambda t: t.trap_id)
def test_trap_day_reads_its_intended_regime(trap: TrapDay):
    """Each class proves it exercises the intended GCycle state (a blowoff that reads washout is a bug)."""
    read = GCycle().read(trap.state)
    assert read.phase == trap.phase, f"{trap.trap_id}: phase {read.phase} != {trap.phase}"
    assert read.frontside is trap.frontside


# ── the battery: zero new longs through the full stack, under both packs ───────────────────────────

@pytest.mark.parametrize("pack", PACKS)
@pytest.mark.parametrize("trap", ALL_TRAP_DAYS, ids=lambda t: t.trap_id)
def test_trap_day_yields_zero_new_longs(pack: str, trap: TrapDay):
    stack, mock = _full_stack(pack, trap.history)
    out = stack.decide(trap.state, _universe())

    assert mock.calls, f"{trap.trap_id}/{pack}: agent was never consulted (silent-policy false pass)"
    assert out.candidates == [], f"{trap.trap_id}/{pack}: {[c.symbol for c in out.candidates]} survived"
    # anti-silent-pass: every proposed leader reached the guard and was DROPPED (not re-anchored away).
    assert _vetoed_symbols(out) == set(LEADS), f"{trap.trap_id}/{pack}: vetoed {_vetoed_symbols(out)}"


@pytest.mark.parametrize("pack", PACKS)
def test_battery_veto_outcome_is_pack_independent(pack: str):
    """The guard reads MarketState/regime, not H — momo and growth veto identically. Pin that fact."""
    for trap in ALL_TRAP_DAYS:
        stack, _ = _full_stack(pack, trap.history)
        assert stack.decide(trap.state, _universe()).candidates == []


# ── the deep finding: the EXISTING stack does NOT block panic rebounds ─────────────────────────────

@pytest.mark.parametrize("trap", PANIC_DAYS, ids=lambda t: t.trap_id)
def test_existing_stack_fails_to_block_panic_rebound(trap: TrapDay):
    """WITHOUT the panic-history thread the momo stack reads frontside `trend` and KEEPS the buys — the
    momentum-crash blind spot that motivates the P1 veto (proves prose alone would not stop it)."""
    stack, _ = _full_stack("momo", history=[])          # no backdrop threaded -> panic veto dormant
    kept = [c.symbol for c in stack.decide(trap.state, _universe()).candidates]
    assert sorted(kept) == sorted(LEADS), f"{trap.trap_id}: existing guard unexpectedly blocked {kept}"


@pytest.mark.parametrize("trap", PANIC_DAYS, ids=lambda t: t.trap_id)
def test_panic_veto_reason_is_self_describing(trap: TrapDay):
    stack, _ = _full_stack("momo", trap.history)
    notes = stack.decide(trap.state, _universe()).key_risks
    assert any("panic-state rebound" in n and "new base" in n for n in notes)


# ── negative control: the panic veto is targeted, not "block all frontside" ────────────────────────

@pytest.mark.parametrize("pack", PACKS)
def test_genuine_trend_after_uptrend_is_not_vetoed(pack: str):
    """The identical sharp rebound after a HEALTHY uptrend (no bear+vol backdrop) is NOT panic — the
    leaders survive. Without this control the panic veto could over-block genuine ignition."""
    trap = CONTROL_GENUINE_TREND
    stack, mock = _full_stack(pack, trap.history)
    out = stack.decide(trap.state, _universe())
    assert mock.calls
    assert sorted(c.symbol for c in out.candidates) == sorted(LEADS)
    assert out.regime is not None and out.regime.frontside is True
    assert not any("panic-state" in n for n in out.key_risks)


@pytest.mark.parametrize("pack", PACKS)
def test_choppy_correction_followthrough_is_not_vetoed(pack: str):
    """The nearest-legitimate shape: a follow-through day out of an ORDINARY choppy correction (mean well
    above the deep-bear band, < 0.60 down days) reads the same frontside `trend` but is NOT a momentum
    crash — the leaders survive. This is the depth/severity separation that keeps the panic veto from
    over-blocking legitimate follow-through days."""
    trap = CONTROL_CHOPPY_CORRECTION
    stack, mock = _full_stack(pack, trap.history)
    out = stack.decide(trap.state, _universe())
    assert mock.calls
    assert sorted(c.symbol for c in out.candidates) == sorted(LEADS)
    assert out.regime is not None and out.regime.frontside is True
    assert not any("panic-state" in n for n in out.key_risks)


# ── decorator order is load-bearing: SizingPolicy(GuardedPolicy(...)) sizes POST-veto ───────────────

def _inverted_stack(pack: str, history: list):
    """The WRONG order — sizing INNER, guard OUTER — so L3 sizes the pre-veto candidates and the guard
    then drops them, leaving the portfolio behind."""
    mock = MockLLMClient(AGGRESSIVE_BUY)
    agent = LLMAgentPolicy(load_pack(pack), mock)
    return GuardedPolicy(SizingPolicy(agent), _source(), state_history=history), mock


def test_decorator_order_sizes_post_veto_not_pre_veto():
    """Load-bearing composition (CLAUDE.md: `SizingPolicy(GuardedPolicy(…))` order is load-bearing). On a
    trap day the guard drops every candidate, so the CORRECT order sizes an empty book -> total_exposure
    0. The INVERTED order sizes the aggressive buys FIRST; the guard then drops the candidates but the
    portfolio survives -> phantom exposure with zero candidates. Asserting the observable difference makes
    the suite go RED if the production composition is ever inverted."""
    trap = PANIC_DAYS[1]                       # a panic rebound: the guard drops all three leaders
    correct, _ = _full_stack("momo", trap.history)
    out = correct.decide(trap.state, _universe())
    assert out.candidates == []
    assert out.portfolio is not None and out.portfolio.total_exposure == 0.0

    inverted, _ = _inverted_stack("momo", trap.history)
    bad = inverted.decide(trap.state, _universe())
    assert bad.candidates == []               # both orders end with no survivors ...
    assert bad.portfolio is not None and bad.portfolio.total_exposure > 0.0   # ... but the WRONG order leaves phantom exposure
    assert out.portfolio.total_exposure != bad.portfolio.total_exposure       # the order is observable
