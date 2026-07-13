"""P2 — verdict-symmetry regression for the symmetric market-context history thread.

P1 built the panic veto DORMANT; P2 activates it by ACCUMULATING the strictly-prior daily MarketStates
inside each arm's GuardedPolicy (`track_history=True`). The load-bearing invariant (mirrors the
screen-flag / recall_store symmetry): BOTH verdict arms build the SAME history from the SAME
source/window, so the panic veto (and the growth market clock) fire identically — HCH never gets a
backdrop Hexpert doesn't. This file drives a synthetic momentum-crash tape through the FULL pipeline
(build_universe -> build_market_state -> GuardedPolicy) and pins: (a) panic ACTIVATES in the driver
path (the dormant P1 veto goes live), (b) two independently-wrapped arms are byte-identical, (c) the
untracked control does NOT veto the rebound (proving accumulation is what activates it), and (d)
compare_harnesses stays verdict-symmetric with the thread wired.
"""
from __future__ import annotations

import tempfile
from datetime import date
from pathlib import Path

import pandas as pd

from alpha.agent.agent import LLMAgentPolicy
from alpha.data.source import FakeSource
from alpha.guard.screen import GuardedPolicy
from alpha.harness.loader import load_seeds
from alpha.harness.snapshot import SnapshotStore
from alpha.llm.client import MockLLMClient
from alpha.loop.compare import compare_harnesses
from alpha.loop.inner_loop import LoopConfig
from alpha.sizing.policy import SizingPolicy
from alpha.eval.walk_forward import WalkForwardEval

SEEDS = Path(__file__).resolve().parents[2] / "seeds"

# a bear -> sharp-rebound momentum-crash tape. SHARE symbols S01..S10 drive the market gainer/loser
# breadth; NEWLEADER is FLAT (excluded from the universe) until the rebound day, where it gaps up with
# NO prior-day decline -> it is a clean gainer the panic veto (not SSR) is the sole reason to drop.
_BEAR_DAYS = 7                     # >= PANIC_MIN_HISTORY(5) deep-bear days before the rebound
_REBOUND = _BEAR_DAYS             # day index of the sharp rebound (0-based)
_SHARE = [f"S{i:02d}" for i in range(1, 11)]
_LEADER = "NEWLEADER"
_N_DAYS = _BEAR_DAYS + 3           # a few post-rebound days so the horizon-2 scorer has room


def _dirs_for_day(i: int) -> dict[str, str]:
    """Per-symbol direction on day i: 'up' (+15%), 'down' (-15%), 'flat' (0% -> not in universe)."""
    if i < _BEAR_DAYS:                                     # deep bear: 2 up, 8 down -> share 0.2
        d = {s: ("up" if k < 2 else "down") for k, s in enumerate(_SHARE)}
        d[_LEADER] = "flat"                               # absent from the tape until the rebound
    else:                                                 # rebound + after: 8 up, 2 down -> share ~0.8
        d = {s: ("up" if k < 8 else "down") for k, s in enumerate(_SHARE)}
        d[_LEADER] = "up" if i == _REBOUND else "flat"    # a clean gapper on the rebound day only
    return d


def _panic_source() -> FakeSource:
    cal = [date(2026, 6, d) for d in range(1, 1 + _N_DAYS)]
    prev = {s: 100.0 for s in _SHARE + [_LEADER]}
    rows: dict[date, list[dict]] = {d: [] for d in cal}
    for i, day in enumerate(cal):
        for sym, direction in _dirs_for_day(i).items():
            p = prev[sym]
            close = {"up": p * 1.15, "down": p * 0.85, "flat": p}[direction]
            if direction != "flat":                       # flat names stay out of the cross-section
                rows[day].append({"symbol": sym, "name": sym, "open": p, "high": max(p, close),
                                  "low": min(p, close), "close": close, "volume": 1, "prev_close": p})
            prev[sym] = close
    snaps = {d: pd.DataFrame(rows[d]) for d in cal}
    return FakeSource(calendar=cal, bars={}, snapshots=snaps)


_BUY_LEADER = '{"regime_read": "trend", "candidates": [{"symbol": "NEWLEADER", "pattern": "gap_and_go", "confidence": 0.8}]}'


def _arm(src, *, track_history: bool):
    """One verdict arm wrapped exactly as compare_harnesses._wrap does: L4 guard inner, L3 sizing outer."""
    agent = LLMAgentPolicy(load_seeds(SEEDS), MockLLMClient(_BUY_LEADER))
    return SizingPolicy(GuardedPolicy(agent, src, vocabulary="momo", track_history=track_history))


def _leader_step(traj):
    """The rebound-day TrajectoryStep (the day NEWLEADER is a clean gainer)."""
    return next(s for s in traj.steps if s.date == date(2026, 6, 1 + _REBOUND))


def test_panic_activates_in_the_driver_path_and_arms_are_symmetric():
    """Two independently-wrapped arms with the history thread ON drop NEWLEADER on the rebound day via
    the panic veto, and their full trajectories are byte-identical (symmetric backdrop)."""
    src = _panic_source()
    start, end = src.trading_calendar()[0], src.trading_calendar()[-1]
    wf = WalkForwardEval(src, start, end, horizon=2)

    traj_a = wf.walk(_arm(src, track_history=True))
    traj_b = wf.walk(_arm(src, track_history=True))

    # (a) panic ACTIVATED: the rebound day drops NEWLEADER with the self-describing panic reason
    step_a = _leader_step(traj_a)
    assert step_a.decision.candidates == []
    assert any("panic-state" in r for r in step_a.decision.key_risks)

    # (b) symmetric: both arms produced identical per-day candidate sets and regime reads
    assert [s.date for s in traj_a.steps] == [s.date for s in traj_b.steps]
    for sa, sb in zip(traj_a.steps, traj_b.steps):
        assert [c.symbol for c in sa.decision.candidates] == [c.symbol for c in sb.decision.candidates]
        assert (sa.decision.regime.phase, sa.decision.regime.frontside) == \
               (sb.decision.regime.phase, sb.decision.regime.frontside)


def test_untracked_control_does_not_veto_the_rebound():
    """The SAME rebound day, WITHOUT the accumulating history thread, keeps NEWLEADER — proving the
    accumulation (not some other guard) is what activates the panic veto. NEWLEADER was flat the prior
    day, so no SSR fires; the momo GCycle reads the sharp rebound as frontside `trend` and passes it."""
    src = _panic_source()
    start, end = src.trading_calendar()[0], src.trading_calendar()[-1]
    wf = WalkForwardEval(src, start, end, horizon=2)
    step = _leader_step(wf.walk(_arm(src, track_history=False)))
    assert [c.symbol for c in step.decision.candidates] == [_LEADER]
    assert not any("panic-state" in r for r in step.decision.key_risks)


def test_compare_harnesses_stays_verdict_symmetric_with_history_threaded():
    """With the thread wired into every arm, matched agent scripts still give HCH == Hexpert (excess
    delta ~ 0): the history threading is applied symmetrically, so it does not tilt the verdict."""
    src = _panic_source()
    start, end = src.trading_calendar()[0], src.trading_calendar()[-1]
    cr = compare_harnesses(
        lambda: load_seeds(SEEDS), src, start, end,
        agent_llm_factory=lambda: MockLLMClient(_BUY_LEADER),
        refiner_llm_factory=lambda: MockLLMClient('{"ops": []}'),
        store_factory=lambda: SnapshotStore(tempfile.mkdtemp()),
        loop_config=LoopConfig(horizon=2, evidence_min=2, refine_every=1))
    assert cr.hch_beats_hexpert is False
    assert abs(cr.hch_minus_hexpert_mean_excess) < 1e-9        # symmetric guarding -> identical arms
