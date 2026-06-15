import tempfile
from datetime import date
from pathlib import Path
import pandas as pd
from alpha.data.source import FakeSource
from alpha.harness.loader import load_seeds
from alpha.harness.snapshot import SnapshotStore
from alpha.llm.client import MockLLMClient
from alpha.loop.inner_loop import LoopConfig
from alpha.loop.compare import compare_harnesses, ComparisonReport, daily_advantage

SEEDS = Path(__file__).resolve().parents[2] / "seeds"


def _source(n, rate):
    cal = [date(2026, 6, d) for d in range(1, 1 + n)]
    snaps, px = {}, 10.0
    closes = []
    for d in cal:
        prev = px; px = px * rate; closes.append(px)
        snaps[d] = pd.DataFrame({"symbol": ["RUN"], "name": ["RUN"], "open": [prev], "high": [px],
                                 "low": [prev], "close": [px], "volume": [1], "prev_close": [prev]})
    bars = {"RUN": pd.DataFrame({"date": cal, "open": [10.0] + closes[:-1], "high": closes,
                                 "low": [10.0] + closes[:-1], "close": closes, "volume": [1] * n})}
    return FakeSource(calendar=cal, bars=bars, snapshots=snaps)


class _Counter:
    """Counts calls; returns a fresh object from `make` each time (factory isolation)."""
    def __init__(self, make): self._make = make; self.calls = 0
    def __call__(self): self.calls += 1; return self._make()


def _cfg():
    return LoopConfig(horizon=2, evidence_min=2, refine_every=1)


def test_four_arms_and_factory_isolation():
    src = _source(6, 1.15)                                  # +15%/day: RUN in-universe, advantage > 0
    hf = _Counter(lambda: load_seeds(SEEDS))
    af = _Counter(lambda: MockLLMClient('{"regime_read": "trend", "candidates": '
                                        '[{"symbol": "RUN", "pattern": "gap_and_go", "confidence": 0.7}]}'))
    rf = _Counter(lambda: MockLLMClient('{"ops": []}'))
    sf = _Counter(lambda: SnapshotStore(tempfile.mkdtemp()))
    cr = compare_harnesses(hf, src, src.trading_calendar()[0], src.trading_calendar()[-1],
                           agent_llm_factory=af, refiner_llm_factory=rf, store_factory=sf, loop_config=_cfg())
    assert isinstance(cr, ComparisonReport)
    assert set(cr.arms) == {"HCH", "Hexpert", "Hmin_chase", "Hmin_notrade"}
    assert hf.calls == 2 and af.calls == 2 and rf.calls == 1 and sf.calls == 1   # factory isolation
    # same agent script for HCH & Hexpert + empty-ops refiner -> identical picks -> excess delta ~ 0 -> verdict False
    assert cr.hch_beats_hexpert is False and abs(cr.hch_minus_hexpert_mean_excess) < 1e-9
    assert cr.hch_loop_report is not None and cr.arms["HCH"].n_refines is not None


def test_hch_beats_hexpert_when_excess_higher():
    src = _source(6, 1.15)
    hf = lambda: load_seeds(SEEDS)
    # run-order (shadow=False) is HCH then Hexpert -> seq factory gives HCH a winner, Hexpert no-trade
    seq = iter([MockLLMClient('{"candidates": [{"symbol": "RUN", "pattern": "gap_and_go"}]}'),
                MockLLMClient('{"no_trade_reason": "flat", "candidates": []}')])
    af = lambda: next(seq)
    cr = compare_harnesses(hf, src, src.trading_calendar()[0], src.trading_calendar()[-1],
                           agent_llm_factory=af, refiner_llm_factory=lambda: MockLLMClient('{"ops": []}'),
                           store_factory=lambda: SnapshotStore(tempfile.mkdtemp()), loop_config=_cfg())
    assert cr.hch_minus_hexpert_mean_excess > 0 and cr.hch_beats_hexpert is True


def test_shadow_runs_hexpert_first_and_completes():
    src = _source(8, 1.15)
    hf = lambda: load_seeds(SEEDS)
    af = lambda: MockLLMClient('{"candidates": [{"symbol": "RUN", "pattern": "gap_and_go"}]}')
    cr = compare_harnesses(hf, src, src.trading_calendar()[0], src.trading_calendar()[-1],
                           agent_llm_factory=af, refiner_llm_factory=lambda: MockLLMClient('{"ops": []}'),
                           store_factory=lambda: SnapshotStore(tempfile.mkdtemp()), loop_config=_cfg(),
                           shadow=True)
    assert set(cr.arms) == {"HCH", "Hexpert", "Hmin_chase", "Hmin_notrade"}   # shadow path completes end-to-end


def test_daily_advantage_mirrors_breaker_formula():
    src = _source(6, 1.15)
    from alpha.eval.walk_forward import WalkForwardEval
    from alpha.eval.scorer import ReturnScorer
    from alpha.agent.agent import LLMAgentPolicy
    traj = WalkForwardEval(src, src.trading_calendar()[0], src.trading_calendar()[-1], horizon=2,
                           scorer=ReturnScorer()).walk(
        LLMAgentPolicy(load_seeds(SEEDS),
                       MockLLMClient('{"candidates": [{"symbol": "RUN", "pattern": "gap_and_go"}]}')))
    da = daily_advantage(traj)
    assert da and all(isinstance(k, date) for k in da)        # keyed by decision date, one per scored step


def test_multi_window_aggregates_deltas():
    from alpha.loop.compare import multi_window, MultiWindowReport
    src = _source(10, 1.15)
    cal = src.trading_calendar()
    windows = [(cal[0], cal[4]), (cal[5], cal[9])]              # two non-overlapping windows
    hf = lambda: load_seeds(SEEDS)
    af = lambda: MockLLMClient('{"candidates": [{"symbol": "RUN", "pattern": "gap_and_go"}]}')
    mw = multi_window(hf, src, windows, agent_llm_factory=af,
                      refiner_llm_factory=lambda: MockLLMClient('{"ops": []}'),
                      store_factory=lambda: SnapshotStore(tempfile.mkdtemp()), loop_config=_cfg())
    assert isinstance(mw, MultiWindowReport)
    assert mw.n_windows == 2 and len(mw.deltas) == 2
    assert 0.0 <= mw.win_rate <= 1.0
    assert abs(mw.mean_delta - sum(mw.deltas) / 2) < 1e-9
    assert isinstance(mw.sign_consistent, bool)
