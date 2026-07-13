"""P3 — verdict symmetry + neutrality regression for the corp-actions blind note.

The blind note is derived from the SINGLE source object compare_harnesses threads into every arm's
GuardedPolicy, so both arms see the same availability view (the screen-flag / recall_store symmetry
pattern). The note lands in key_risks, which eval scoring never reads, so it is verdict-neutral.

The fixture is a sustained-frontside tape WITH BARS so entries genuinely survive the guard AND get
scored by the ReturnOracle (an earlier bars-less version was vacuous: entries kept but nothing scored
-> n_candidates==0, so the <1e-9 delta was trivially 0 and could detect neither a key_risks-reading
scorer nor a real asymmetry). Now each arm scores 4 real GAIN entries at a non-zero forward return, so
the symmetry delta has teeth. Pins: (a) the note appears in BOTH arms symmetrically, (b)
compare_harnesses is non-vacuous (each arm scores >0 entries at a real non-zero return) and stays
verdict-symmetric, and (c) a missing-corp run (note fires) and an otherwise-identical present-but-empty
run (no note) produce byte-identical EvalReports — direct proof the scorer never reads key_risks.
"""
from __future__ import annotations

import tempfile
from datetime import date
from pathlib import Path

import pandas as pd

from alpha.agent.agent import LLMAgentPolicy
from alpha.data.source import FakeSource
from alpha.eval.scorer import ReturnScorer
from alpha.eval.trajectory import report_from_trajectory
from alpha.eval.walk_forward import WalkForwardEval
from alpha.guard.screen import CORP_BLIND_NOTE, GuardedPolicy
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


def _source(*, corp_available: bool) -> FakeSource:
    """Sustained-frontside tape (8 shares up +15% / 2 down -15% -> share ~0.8 -> `trend` frontside) with
    GAIN a clean strong gainer (+25%/day, closes green so no halt/SSR veto) entered every day. BARS are
    supplied so the ReturnOracle scores the entries at a real non-zero forward return. `corp_available`
    toggles the ONLY behavioural difference under test: missing corp artifact -> the reverse-split/
    dilution guard runs blind and screen_decision emits the note; present-but-empty -> no note,
    everything else identical."""
    cal = [date(2026, 6, d) for d in range(10, 17)]     # 7 trading days
    prev = {s: 100.0 for s in _SHARE + [_LEADER]}
    bars: dict[str, list[dict]] = {s: [] for s in _SHARE + [_LEADER]}
    snaps: dict[date, list[dict]] = {d: [] for d in cal}
    for day in cal:
        mults = {s: (1.15 if k < 8 else 0.85) for k, s in enumerate(_SHARE)}
        mults[_LEADER] = 1.25                            # GAIN a strong clean gainer -> non-zero mean_score
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
                      corp_actions_available=corp_available)


def _arm(src):
    """One verdict arm wrapped exactly as compare_harnesses._wrap does: L4 guard inner, L3 sizing outer."""
    agent = LLMAgentPolicy(load_seeds(SEEDS), MockLLMClient(_BUY))
    return SizingPolicy(GuardedPolicy(agent, src, vocabulary="momo", track_history=True))


def _return_report(*, corp_available: bool):
    """Score the arm over the fixture with the real forward-return scorer -> EvalReport."""
    src = _source(corp_available=corp_available)
    start, end = src.trading_calendar()[0], src.trading_calendar()[-1]
    traj = WalkForwardEval(src, start, end, horizon=2, scorer=ReturnScorer()).walk(_arm(src))
    return report_from_trajectory(traj, horizon=2)


def test_missing_corp_blind_note_appears_in_both_arms_symmetrically():
    src = _source(corp_available=False)
    start, end = src.trading_calendar()[0], src.trading_calendar()[-1]
    wf = WalkForwardEval(src, start, end, horizon=2)
    traj_a = wf.walk(_arm(src))
    traj_b = wf.walk(_arm(src))
    # the blind note fires (GAIN is entered under a missing corp artifact) ...
    assert any(CORP_BLIND_NOTE in s.decision.key_risks for s in traj_a.steps)
    # ... and both independently-wrapped arms agree day-for-day (symmetric availability view)
    assert [s.date for s in traj_a.steps] == [s.date for s in traj_b.steps]
    for sa, sb in zip(traj_a.steps, traj_b.steps):
        assert (CORP_BLIND_NOTE in sa.decision.key_risks) == (CORP_BLIND_NOTE in sb.decision.key_risks)


def test_missing_corp_keeps_compare_verdict_symmetric_non_vacuously():
    """With a missing corp artifact threaded through every arm, HCH and Hexpert BOTH score entries and
    stay verdict-symmetric. The non-vacuity asserts (each arm scores >0 entries at a real non-zero
    forward return) give the <1e-9 delta teeth — it now reflects real matched scoring, not an empty
    verdict where a key_risks-reading scorer or a real asymmetry would be undetectable."""
    src = _source(corp_available=False)
    start, end = src.trading_calendar()[0], src.trading_calendar()[-1]
    cr = compare_harnesses(
        lambda: load_seeds(SEEDS), src, start, end,
        agent_llm_factory=lambda: MockLLMClient(_BUY),
        refiner_llm_factory=lambda: MockLLMClient('{"ops": []}'),
        store_factory=lambda: SnapshotStore(tempfile.mkdtemp()),
        loop_config=LoopConfig(horizon=2, evidence_min=2, refine_every=1))
    # non-vacuity: both compared arms genuinely scored entries carrying a real non-zero return
    assert cr.arms["HCH"].report.n_candidates > 0
    assert cr.arms["Hexpert"].report.n_candidates > 0
    assert abs(cr.arms["HCH"].report.mean_score) > 1e-6
    # symmetric: identical arms -> zero score AND excess delta (the note did not tilt the verdict)
    assert abs(cr.hch_minus_hexpert_mean_score) < 1e-9
    assert abs(cr.hch_minus_hexpert_mean_excess) < 1e-9


def test_blind_note_does_not_change_the_scored_eval_report():
    """Direct neutrality pin with teeth: a missing-corp run (note fires) vs an otherwise-IDENTICAL
    present-but-empty run (no note). The corp frame is empty either way, so veto behaviour is byte-
    identical and the ONLY trajectory difference is the key_risks note. Identical, non-empty EvalReports
    => eval scoring never reads key_risks (a key_risks-reading scorer would move the missing-run numbers)."""
    blind = _return_report(corp_available=False)     # note present
    clean = _return_report(corp_available=True)      # note absent
    assert blind.n_candidates > 0                    # non-vacuous: entries actually scored
    assert (blind.n_candidates, blind.mean_score, blind.mean_excess, blind.hit_rate, blind.nuke_rate) == \
           (clean.n_candidates, clean.mean_score, clean.mean_excess, clean.hit_rate, clean.nuke_rate)
