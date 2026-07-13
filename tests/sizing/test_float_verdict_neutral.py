"""P5b float-aware sizing — verdict-neutrality through the REAL walk-forward + compare_harnesses paths
(spec 2026-07-13-p5b-float-feed-design.md). Modelled on tests/loop/test_p5b_earnings_symmetry.py.

Two proofs:
  (a) TEETH — over one float-present tape, a float_aware=True arm caps a small-float leader's size_tier
      (non-vacuous: the tiers genuinely differ from the tier-only arm), yet report_from_trajectory yields a
      byte-identical, non-empty EvalReport. Direct proof the scorer never reads size_tier. This is the same
      SizingPolicy(GuardedPolicy(...)) scoring path compare_harnesses walks per arm.
  (b) LITERAL — compare_harnesses over a float-present source equals the float-absent baseline verdict,
      non-vacuously (entries scored at a real non-zero return). Float DATA in the source never perturbs the
      verdict (the scoring path is float-blind end-to-end).
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


def _source(*, float_present: bool) -> FakeSource:
    """Sustained-frontside tape (8 shares +15% / 2 -15%) with GAIN a clean strong gainer (+25%/day, closes
    green) entered every day; BARS supplied so the ReturnOracle scores the entries at a real forward return.
    `float_present` toggles the ONLY behavioural difference: a small `free_float` (3M shares -> 3.0 millions)
    on every snapshot row, which float-aware sizing caps to `probe`. Absent -> no float column, else identical."""
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
            row = {"symbol": sym, "name": sym, "open": o, "high": hi, "low": lo,
                   "close": c, "volume": 1, "prev_close": o}
            if float_present:
                row["free_float"] = 3.0                  # 3.0 millions = 3M shares -> below mid -> probe cap
            snaps[day].append(row)
            prev[sym] = c
    return FakeSource(calendar=cal, bars={s: pd.DataFrame(b) for s, b in bars.items()},
                      snapshots={d: pd.DataFrame(r) for d, r in snaps.items()},
                      corp_actions_available=True)


def _arm(src, *, float_aware: bool):
    """One verdict arm wrapped exactly as compare_harnesses._wrap does: L4 guard inner, L3 sizing outer.
    `float_aware` toggles the float-aware cap on the L3 sizing decorator."""
    agent = LLMAgentPolicy(load_seeds(SEEDS), MockLLMClient(_BUY))
    return SizingPolicy(GuardedPolicy(agent, src, vocabulary="momo", track_history=True),
                        float_aware=float_aware)


def _leader_tiers(traj) -> dict[date, str]:
    out = {}
    for s in traj.steps:
        for c in s.decision.candidates:
            if c.symbol == _LEADER and c.size_tier is not None:
                out[s.date] = c.size_tier
    return out


def test_float_aware_caps_tier_but_eval_report_is_byte_identical():
    src = _source(float_present=True)
    start, end = src.trading_calendar()[0], src.trading_calendar()[-1]

    def _walk(arm):
        return WalkForwardEval(src, start, end, horizon=2, scorer=ReturnScorer()).walk(arm)

    traj_capped = _walk(_arm(src, float_aware=True))
    traj_plain = _walk(_arm(src, float_aware=False))

    tiers_capped, tiers_plain = _leader_tiers(traj_capped), _leader_tiers(traj_plain)
    # non-vacuous: the leader was actually sized on both walks, and float-aware genuinely capped it lower
    assert tiers_capped and tiers_plain
    assert tiers_capped != tiers_plain
    assert all(t == "probe" for t in tiers_capped.values())     # small float -> probe ceiling
    assert any(tiers_plain[d] != "probe" for d in tiers_plain)  # tier-only sized it heavier at least once

    rep_capped = report_from_trajectory(traj_capped, horizon=2)
    rep_plain = report_from_trajectory(traj_plain, horizon=2)
    assert rep_capped.n_candidates > 0                          # non-vacuous: entries genuinely scored
    assert (rep_capped.n_candidates, rep_capped.mean_score, rep_capped.mean_excess,
            rep_capped.hit_rate, rep_capped.nuke_rate) == \
           (rep_plain.n_candidates, rep_plain.mean_score, rep_plain.mean_excess,
            rep_plain.hit_rate, rep_plain.nuke_rate)            # size_tier never enters the score


def _compare(src):
    start, end = src.trading_calendar()[0], src.trading_calendar()[-1]
    return compare_harnesses(
        lambda: load_seeds(SEEDS), src, start, end,
        agent_llm_factory=lambda: MockLLMClient(_BUY),
        refiner_llm_factory=lambda: MockLLMClient('{"ops": []}'),
        store_factory=lambda: SnapshotStore(tempfile.mkdtemp()),
        loop_config=LoopConfig(horizon=2, evidence_min=2, refine_every=1))


def test_compare_harnesses_verdict_unchanged_with_float_present():
    cr_float = _compare(_source(float_present=True))
    cr_none = _compare(_source(float_present=False))
    # non-vacuous: real entries scored at a real non-zero return in the float-present run
    assert cr_float.arms["HCH"].report.n_candidates > 0
    assert abs(cr_float.arms["HCH"].report.mean_score) > 1e-6
    # float DATA in the source does not move the verdict (the scoring path is float-blind end-to-end)
    assert cr_float.hch_minus_hexpert_mean_score == cr_none.hch_minus_hexpert_mean_score
    assert cr_float.hch_minus_hexpert_mean_excess == cr_none.hch_minus_hexpert_mean_excess
    assert cr_float.arms["HCH"].report.mean_score == cr_none.arms["HCH"].report.mean_score
