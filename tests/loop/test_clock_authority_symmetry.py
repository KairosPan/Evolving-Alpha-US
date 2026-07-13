"""§1.4 three-clock activation — VERDICT symmetry + non-vacuity (the write-path-adjacent invariant).

`clock_authority` rides on `LoopConfig` and is threaded into EVERY arm's GuardedPolicy identically
(compare `_wrap` / InnerLoop `_rebind`), so both arms compose the SAME theme+stock cascade over the SAME
source/window — the screen-flag / recall_store symmetry pattern. Three pins:
  - the stock gate DROPS a base-reading leader in BOTH walk arms day-for-day (symmetric firing), while the
    flag-OFF arm KEEPS it (the gate really bites — non-vacuous);
  - compare_harnesses stays verdict-symmetric (|HCH − Hexpert| < 1e-9) with the flag ON, non-vacuously
    (real scored entries, mean_score ≠ 0);
  - ON == OFF when the gate abstains (a warm-up window) — the flag perturbs nothing it does not gate.
"""
from __future__ import annotations

import tempfile
from datetime import date, timedelta

import pandas as pd

from alpha.agent.agent import LLMAgentPolicy
from alpha.data.source import FakeSource
from alpha.eval.walk_forward import WalkForwardEval
from alpha.guard.screen import GuardedPolicy
from alpha.harness.loader import load_pack
from alpha.harness.snapshot import SnapshotStore
from alpha.llm.client import MockLLMClient
from alpha.loop.compare import compare_harnesses
from alpha.loop.inner_loop import LoopConfig
from alpha.sizing.policy import SizingPolicy

_LEADER = "GAIN"
_SHARE = [f"S{i:02d}" for i in range(1, 6)]        # 5 gainers + 1 loser -> gainer_share ~0.86 (FTD fires)
_LOSER = "LOSE"
_BUY = ('{"regime_read": "confirmed_uptrend", "candidates": '
        '[{"symbol": "GAIN", "pattern": "trend_template", "confidence": 0.8}]}')


def _source(n_days: int) -> FakeSource:
    """A mostly-gainer tape (the growth market clock confirms an uptrend after warm-up) with GAIN a gainer
    every day. Over an n≥60-day window GAIN accrues the 60-bar history the stock clock needs -> it reads
    stock:base (rs_percentile is None under the gainer screen) -> the §1.3 gate vetoes it; in a short
    warm-up window GAIN has <60 prior bars -> the stock gate ABSTAINS -> GAIN passes."""
    cal = [date(2026, 1, 1) + timedelta(days=i) for i in range(n_days)]
    syms = [_LEADER, *_SHARE, _LOSER]
    prev = {s: 100.0 for s in syms}
    bars: dict[str, list[dict]] = {s: [] for s in syms}
    snaps: dict[date, list[dict]] = {d: [] for d in cal}
    for day in cal:
        mults = {_LEADER: 1.15, _LOSER: 0.85, **{s: 1.12 for s in _SHARE}}
        for sym, mult in mults.items():
            o = prev[sym]
            c = o * mult
            hi, lo = max(o, c), min(o, c)
            bars[sym].append({"date": day, "open": o, "high": hi, "low": lo, "close": c, "volume": 1_000})
            snaps[day].append({"symbol": sym, "name": sym, "open": o, "high": hi, "low": lo,
                               "close": c, "volume": 1_000, "prev_close": o})
            prev[sym] = c
    return FakeSource(calendar=cal, bars={s: pd.DataFrame(b) for s, b in bars.items()},
                      snapshots={d: pd.DataFrame(r) for d, r in snaps.items()})


def _arm(src, *, clock: bool):
    agent = LLMAgentPolicy(load_pack("growth"), MockLLMClient(_BUY))
    return SizingPolicy(GuardedPolicy(agent, src, vocabulary="growth", track_history=True,
                                      clock_authority=clock))


def _kept_leader(step) -> bool:
    return _LEADER in [c.symbol for c in step.decision.candidates]


# ── symmetric FIRING day-for-day + non-vacuous (the gate bites vs the OFF arm) ────────────────────────

def test_stock_gate_drops_base_leader_in_both_arms_symmetrically():
    src = _source(64)                                            # >60 days -> GAIN reads stock:base late
    start, end = src.trading_calendar()[0], src.trading_calendar()[-1]
    wf = WalkForwardEval(src, start, end, horizon=2)
    on_a, on_b = wf.walk(_arm(src, clock=True)), wf.walk(_arm(src, clock=True))
    off = wf.walk(_arm(src, clock=False))

    assert [s.date for s in on_a.steps] == [s.date for s in on_b.steps]
    for sa, sb in zip(on_a.steps, on_b.steps):
        assert _kept_leader(sa) == _kept_leader(sb)             # both clock arms decide identically
    # non-vacuous: the LAST day is a confirmed uptrend (market frontside) yet GAIN is DROPPED by the stock
    # gate under clock=ON while the clock=OFF arm KEEPS it — the §1.3 gate is what bites, not the market.
    last_on, last_off = on_a.steps[-1], off.steps[-1]
    assert last_on.decision.regime is not None and last_on.decision.regime.frontside is True
    assert not _kept_leader(last_on)                            # ON: stock:base -> vetoed
    assert _kept_leader(last_off)                               # OFF: kept (market frontside, no stock gate)


# ── compare_harnesses stays verdict-symmetric + non-vacuous with the flag ON ─────────────────────────

def _compare(src, *, clock: bool):
    start, end = src.trading_calendar()[0], src.trading_calendar()[-1]
    return compare_harnesses(
        lambda: load_pack("growth"), src, start, end,
        agent_llm_factory=lambda: MockLLMClient(_BUY),
        refiner_llm_factory=lambda: MockLLMClient('{"ops": []}'),
        store_factory=lambda: SnapshotStore(tempfile.mkdtemp()),
        loop_config=LoopConfig(horizon=2, evidence_min=2, refine_every=1, clock_authority=clock))


def test_clock_authority_on_keeps_verdict_symmetric_smoke():
    """SMOKE only: with the flag ON both arms stay <1e-9. This is NOT the non-vacuity guard — on this
    synthetic tape every kept GAIN-day scores identically, so the mean is invariant to which arm keeps
    which GAIN-day and a total arm asymmetry would ALSO read <1e-9 (review-confirmed 2026-07-13). The
    real symmetry pin is test_clock_authority_is_threaded_into_every_compare_arm_identically below."""
    cr = _compare(_source(16), clock=True)
    assert cr.arms["HCH"].report.n_candidates > 0
    assert abs(cr.arms["HCH"].report.mean_score) > 1e-6
    assert abs(cr.hch_minus_hexpert_mean_score) < 1e-9
    assert abs(cr.hch_minus_hexpert_mean_excess) < 1e-9


def test_clock_authority_is_threaded_into_every_compare_arm_identically(monkeypatch):
    """THE load-bearing verdict-symmetry pin (CLAUDE.md gotcha): clock_authority must reach EVERY arm's
    GuardedPolicy identically — compare._wrap (Hexpert/Hmin) AND InnerLoop._rebind (HCH). A behavioral
    |HCH−Hexpert|<1e-9 assertion is VACUOUS here (see the smoke above), so pin it STRUCTURALLY: record
    the clock_authority every GuardedPolicy is built with across a full compare run and assert they are
    ALL the requested flag. This FAILS under the exact asymmetry the review caught — HCH's _rebind
    hardcoded clock-off while the wrapped arms stay on (which the behavioral test passed straight through)."""
    import alpha.guard.screen as screen_mod
    seen: list[bool] = []
    orig = screen_mod.GuardedPolicy.__init__

    def _spy(self, *a, **k):
        orig(self, *a, **k)
        seen.append(self._clock_authority)

    monkeypatch.setattr(screen_mod.GuardedPolicy, "__init__", _spy)
    _compare(_source(16), clock=True)
    assert seen, "no GuardedPolicy was constructed — the compare arms are not screened"
    assert all(v is True for v in seen), f"an arm was built clock-OFF while ON was requested: {seen}"
    seen.clear()
    _compare(_source(16), clock=False)
    assert seen and all(v is False for v in seen), f"an arm was built clock-ON while OFF was requested: {seen}"


def test_clock_authority_on_equals_off_when_the_gate_abstains():
    """In a warm-up window the stock gate abstains and no theme_breadth is threaded (theme abstains), so
    the ON cascade adds nothing -> the ComparisonReport is byte-identical to the OFF run."""
    on, off = _compare(_source(16), clock=True), _compare(_source(16), clock=False)
    assert on.arms["HCH"].report.n_candidates == off.arms["HCH"].report.n_candidates > 0
    assert abs(on.hch_minus_hexpert_mean_excess - off.hch_minus_hexpert_mean_excess) < 1e-12
    assert abs(on.arms["HCH"].report.mean_score - off.arms["HCH"].report.mean_score) < 1e-12
