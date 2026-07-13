"""P5b — verdict symmetry + neutrality regression for the earnings T-3 checklist note.

The checklist note is derived from the SINGLE source object compare_harnesses threads into every arm's
GuardedPolicy, so both arms see the same earnings calendar (the screen-flag / recall_store symmetry
pattern). The note lands in key_risks, which eval scoring never reads, so it is verdict-neutral.

The fixture is a sustained-frontside tape WITH BARS so entries genuinely survive the guard AND get
scored by the ReturnOracle — mirrors the P3 corp-blind symmetry file. GAIN carries an upcoming
earnings date so the checklist note fires on the T-3 window days. Pins: (a) the note appears in BOTH
arms day-for-day, (b) compare_harnesses stays verdict-symmetric non-vacuously, and (c) a
feed-present run (note fires) and an otherwise-identical no-feed run (no note) produce byte-identical
EvalReports — direct proof the scorer never reads key_risks.
"""
from __future__ import annotations

import tempfile
from datetime import date
from pathlib import Path

import pandas as pd

from alpha.agent.agent import LLMAgentPolicy
from alpha.data.earnings import EarningsCalendarEntry
from alpha.data.source import FakeSource
from alpha.eval.scorer import ReturnScorer
from alpha.eval.trajectory import report_from_trajectory
from alpha.eval.walk_forward import WalkForwardEval
from alpha.guard.screen import GuardedPolicy, earnings_checklist_note
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


def _source(*, earnings_present: bool) -> FakeSource:
    """Sustained-frontside tape (8 shares +15% / 2 -15% -> share ~0.8 -> `trend` frontside) with GAIN a
    clean strong gainer (+25%/day, closes green -> no halt/SSR veto) entered every day. BARS supplied so
    the ReturnOracle scores the entries at a real non-zero forward return. `earnings_present` toggles the
    ONLY behavioural difference under test: an earnings calendar with GAIN reporting on 2026-06-13 ->
    screen_decision emits the T-3 checklist note on the window days; absent -> no note, else identical."""
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
    earnings_cal = ([EarningsCalendarEntry(symbol=_LEADER, expected_date=date(2026, 6, 13),
                                           known_asof=date(2026, 6, 1))] if earnings_present else None)
    return FakeSource(calendar=cal, bars={s: pd.DataFrame(b) for s, b in bars.items()},
                      snapshots={d: pd.DataFrame(r) for d, r in snaps.items()},
                      corp_actions_available=True, earnings_calendar=earnings_cal)


def _arm(src):
    """One verdict arm wrapped exactly as compare_harnesses._wrap does: L4 guard inner, L3 sizing outer."""
    agent = LLMAgentPolicy(load_seeds(SEEDS), MockLLMClient(_BUY))
    return SizingPolicy(GuardedPolicy(agent, src, vocabulary="momo", track_history=True))


def _return_report(*, earnings_present: bool):
    src = _source(earnings_present=earnings_present)
    start, end = src.trading_calendar()[0], src.trading_calendar()[-1]
    traj = WalkForwardEval(src, start, end, horizon=2, scorer=ReturnScorer()).walk(_arm(src))
    return report_from_trajectory(traj, horizon=2)


def test_earnings_note_appears_in_both_arms_symmetrically():
    src = _source(earnings_present=True)
    start, end = src.trading_calendar()[0], src.trading_calendar()[-1]
    wf = WalkForwardEval(src, start, end, horizon=2)
    traj_a = wf.walk(_arm(src))
    traj_b = wf.walk(_arm(src))

    # the checklist note fires on the T-3 window (GAIN reports 2026-06-13) ...
    def has_note(step):
        return any(earnings_checklist_note("GAIN", d) in step.decision.key_risks for d in range(0, 4))

    assert any(has_note(s) for s in traj_a.steps)
    # ... and both independently-wrapped arms agree day-for-day (symmetric earnings view)
    assert [s.date for s in traj_a.steps] == [s.date for s in traj_b.steps]
    for sa, sb in zip(traj_a.steps, traj_b.steps):
        assert has_note(sa) == has_note(sb)


def test_earnings_note_keeps_compare_verdict_symmetric_non_vacuously():
    src = _source(earnings_present=True)
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


def test_earnings_note_does_not_change_the_scored_eval_report():
    """Direct neutrality pin with teeth: a feed-present run (note fires) vs an otherwise-IDENTICAL
    no-feed run (no note). The candidates kept are identical either way (the note never vetoes), so the
    ONLY trajectory difference is the key_risks note. Identical, non-empty EvalReports => eval scoring
    never reads key_risks."""
    noted = _return_report(earnings_present=True)     # note present
    plain = _return_report(earnings_present=False)    # note absent
    assert noted.n_candidates > 0                     # non-vacuous: entries actually scored
    assert (noted.n_candidates, noted.mean_score, noted.mean_excess, noted.hit_rate, noted.nuke_rate) == \
           (plain.n_candidates, plain.mean_score, plain.mean_excess, plain.hit_rate, plain.nuke_rate)
