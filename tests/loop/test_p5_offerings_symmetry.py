"""P5 — verdict symmetry + lift-neutrality for the offerings dilution veto swap.

The dilution flag is read from the SINGLE source object compare_harnesses threads into every arm's
GuardedPolicy, so both arms see the same offering-lifecycle events and DROP the same names day-for-day
(the screen-flag / recall_store symmetry pattern). Two pins: (a) an active overhang drops the leader in
BOTH arms day-for-day; (b) a shelf withdrawn BEFORE the window (proven closed all window long) yields a
byte-identical EvalReport to the no-feed clean baseline — the lifecycle lift reduces exactly to clean —
and compare_harnesses stays verdict-symmetric and non-vacuous over it.
"""
from __future__ import annotations

import tempfile
from datetime import date
from pathlib import Path

import pandas as pd

from alpha.agent.agent import LLMAgentPolicy
from alpha.data.offerings import OfferingEvent
from alpha.data.source import FakeSource
from alpha.eval.scorer import ReturnScorer
from alpha.eval.trajectory import report_from_trajectory
from alpha.eval.walk_forward import WalkForwardEval
from alpha.guard.screen import GuardedPolicy
from alpha.harness.loader import load_seeds
from alpha.harness.snapshot import SnapshotStore
from alpha.llm.client import MockLLMClient
from alpha.loop.compare import compare_harnesses
from alpha.loop.inner_loop import LoopConfig
from alpha.sizing.policy import SizingPolicy

SEEDS = Path(__file__).resolve().parents[2] / "seeds"

_SHARE = [f"S{i:02d}" for i in range(1, 11)]
_LEADER = "GAIN"
_BUY = ('{"regime_read": "trend", "candidates": '
        '[{"symbol": "GAIN", "pattern": "gap_and_go", "confidence": 0.8}]}')

# a shelf withdrawn BEFORE the window opens -> "closed" on every window day -> veto lifted all window.
_WITHDRAWN_PRE = [OfferingEvent(symbol=_LEADER, offering_id="S3-1", event="announce", kind="shelf",
                                process_date=date(2026, 6, 1)),
                  OfferingEvent(symbol=_LEADER, offering_id="S3-1", event="withdrawn", kind="shelf",
                                process_date=date(2026, 6, 5))]
# an announce with no close -> "active" every window day -> veto fires all window.
_ACTIVE = [OfferingEvent(symbol=_LEADER, offering_id="S3-1", event="announce", kind="shelf",
                         process_date=date(2026, 6, 1))]


def _source(*, offering_events=None) -> FakeSource:
    cal = [date(2026, 6, d) for d in range(10, 17)]     # 7 trading days
    prev = {s: 100.0 for s in _SHARE + [_LEADER]}
    bars: dict[str, list[dict]] = {s: [] for s in _SHARE + [_LEADER]}
    snaps: dict[date, list[dict]] = {d: [] for d in cal}
    for day in cal:
        mults = {s: (1.15 if k < 8 else 0.85) for k, s in enumerate(_SHARE)}
        mults[_LEADER] = 1.25
        for sym, mult in mults.items():
            o = prev[sym]
            c = o * mult
            hi, lo = max(o, c), min(o, c)
            bars[sym].append({"date": day, "open": o, "high": hi, "low": lo, "close": c, "volume": 1})
            snaps[day].append({"symbol": sym, "name": sym, "open": o, "high": hi, "low": lo,
                               "close": c, "volume": 1, "prev_close": o})
            prev[sym] = c
    return FakeSource(calendar=cal, bars={s: pd.DataFrame(b) for s, b in bars.items()},
                      snapshots={d: pd.DataFrame(r) for d, r in snaps.items()},
                      corp_actions_available=True, offering_events=offering_events)


def _arm(src):
    agent = LLMAgentPolicy(load_seeds(SEEDS), MockLLMClient(_BUY))
    return SizingPolicy(GuardedPolicy(agent, src, vocabulary="momo", track_history=True))


def _return_report(*, offering_events):
    src = _source(offering_events=offering_events)
    start, end = src.trading_calendar()[0], src.trading_calendar()[-1]
    traj = WalkForwardEval(src, start, end, horizon=2, scorer=ReturnScorer()).walk(_arm(src))
    return report_from_trajectory(traj, horizon=2)


def test_active_overhang_drops_the_leader_in_both_arms_symmetrically():
    src = _source(offering_events=_ACTIVE)
    start, end = src.trading_calendar()[0], src.trading_calendar()[-1]
    wf = WalkForwardEval(src, start, end, horizon=2)
    traj_a, traj_b = wf.walk(_arm(src)), wf.walk(_arm(src))

    def kept_leader(step):
        return _LEADER in [c.symbol for c in step.decision.candidates]

    assert not any(kept_leader(s) for s in traj_a.steps)         # active overhang -> dropped every day
    assert [s.date for s in traj_a.steps] == [s.date for s in traj_b.steps]
    for sa, sb in zip(traj_a.steps, traj_b.steps):
        assert kept_leader(sa) == kept_leader(sb)                # both arms drop it identically


def test_withdrawn_before_window_reduces_to_the_clean_baseline_eval():
    lifted = _return_report(offering_events=_WITHDRAWN_PRE)       # proven-closed all window -> kept
    clean = _return_report(offering_events=None)                  # no feed -> has_dilution_filing (clean)
    assert lifted.n_candidates > 0                                # non-vacuous: the leader is scored
    assert (lifted.n_candidates, lifted.mean_score, lifted.mean_excess, lifted.hit_rate, lifted.nuke_rate) == \
           (clean.n_candidates, clean.mean_score, clean.mean_excess, clean.hit_rate, clean.nuke_rate)


def test_offerings_swap_keeps_compare_verdict_symmetric_non_vacuously():
    src = _source(offering_events=_WITHDRAWN_PRE)
    start, end = src.trading_calendar()[0], src.trading_calendar()[-1]
    cr = compare_harnesses(
        lambda: load_seeds(SEEDS), src, start, end,
        agent_llm_factory=lambda: MockLLMClient(_BUY),
        refiner_llm_factory=lambda: MockLLMClient('{"ops": []}'),
        store_factory=lambda: SnapshotStore(tempfile.mkdtemp()),
        loop_config=LoopConfig(horizon=2, evidence_min=2, refine_every=1))
    assert cr.arms["HCH"].report.n_candidates > 0
    assert cr.arms["Hexpert"].report.n_candidates > 0
    assert abs(cr.arms["HCH"].report.mean_score) > 1e-6
    assert abs(cr.hch_minus_hexpert_mean_score) < 1e-9
    assert abs(cr.hch_minus_hexpert_mean_excess) < 1e-9
