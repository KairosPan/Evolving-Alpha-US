"""P6 integration: purged-CV embargo + regime stratification + Hcredit ablation arm in compare_harnesses
/ multi_window. Verdict symmetry is the load-bearing invariant under test."""
import tempfile
from datetime import date
from pathlib import Path

import pandas as pd

from alpha.data.source import FakeSource
from alpha.eval.stats import StatVerdict
from alpha.harness.loader import load_seeds
from alpha.harness.snapshot import SnapshotStore
from alpha.llm.client import MockLLMClient
from alpha.loop.compare import compare_harnesses, multi_window, MultiWindowReport
from alpha.loop.inner_loop import LoopConfig

SEEDS = Path(__file__).resolve().parents[2] / "seeds"


def _source(n, rate=1.15):
    cal = [date(2026, 6, d) for d in range(1, 1 + n)]
    snaps, px, closes = {}, 10.0, []
    for d in cal:
        prev = px; px = px * rate; closes.append(px)
        snaps[d] = pd.DataFrame({"symbol": ["RUN"], "name": ["RUN"], "open": [prev], "high": [px],
                                 "low": [prev], "close": [px], "volume": [1], "prev_close": [prev]})
    bars = {"RUN": pd.DataFrame({"date": cal, "open": [10.0] + closes[:-1], "high": closes,
                                 "low": [10.0] + closes[:-1], "close": closes, "volume": [1] * n})}
    return FakeSource(calendar=cal, bars=bars, snapshots=snaps)


def _cfg():
    return LoopConfig(horizon=2, evidence_min=2, refine_every=1)


def _af():
    return MockLLMClient('{"candidates": [{"symbol": "RUN", "pattern": "gap_and_go"}]}')


def _compare(src, **kw):
    return compare_harnesses(lambda: load_seeds(SEEDS), src, src.trading_calendar()[0],
                             src.trading_calendar()[-1], agent_llm_factory=_af,
                             refiner_llm_factory=lambda: MockLLMClient('{"ops": []}'),
                             store_factory=lambda: SnapshotStore(tempfile.mkdtemp()), loop_config=_cfg(), **kw)


def test_embargo_zero_is_byte_identical():
    a = _compare(_source(10))
    b = _compare(_source(10), embargo=0)
    assert a.hch_minus_hexpert_mean_excess == b.hch_minus_hexpert_mean_excess
    assert a.arms["HCH"].report.n_candidates == b.arms["HCH"].report.n_candidates
    assert a.stratified is None and a.hch_minus_nocredit_mean_excess is None   # default-off


def test_embargo_drops_trailing_scored_symmetrically_across_arms():
    full = _compare(_source(10))
    emb = _compare(_source(10), embargo=2)
    # both arms drop the same trailing scored decisions -> equal counts, verdict still symmetric
    assert full.arms["HCH"].report.n_candidates == full.arms["Hexpert"].report.n_candidates
    assert emb.arms["HCH"].report.n_candidates == emb.arms["Hexpert"].report.n_candidates
    assert emb.arms["HCH"].report.n_candidates == full.arms["HCH"].report.n_candidates - 2
    assert abs(emb.hch_minus_hexpert_mean_excess) < 1e-9        # identical picks -> still equal
    # the paired stat verdict also shrinks its day count symmetrically
    assert emb.stat_verdict.n_days == full.stat_verdict.n_days - 2


def test_credit_ablation_adds_arm_default_off():
    base = _compare(_source(10))
    assert set(base.arms) == {"HCH", "Hexpert", "Hmin_chase", "Hmin_notrade"}

    ab = _compare(_source(10), credit_ablation=True)
    assert set(ab.arms) == {"HCH", "Hexpert", "Hmin_chase", "Hmin_notrade", "HCH_nocredit"}
    assert ab.hch_minus_nocredit_mean_excess is not None
    # empty-ops refiner -> credit changes no picks -> HCH == HCH_nocredit -> ablation delta 0
    assert abs(ab.hch_minus_nocredit_mean_excess) < 1e-9
    assert ab.arms["HCH_nocredit"].n_refines is not None        # it is a full HCH arm


def test_stratify_populates_per_regime_verdicts():
    cr = _compare(_source(12), stratify=True)
    assert cr.stratified is not None
    assert all(isinstance(v, StatVerdict) for v in cr.stratified.values())
    assert len(cr.stratified) >= 1


def test_multi_window_reserved_and_embargo():
    src = _source(20)
    cal = src.trading_calendar()
    windows = [(cal[0], cal[5]), (cal[7], cal[12]), (cal[14], cal[19])]   # 3 gapped windows
    mw = multi_window(lambda: load_seeds(SEEDS), src, windows, agent_llm_factory=_af,
                      refiner_llm_factory=lambda: MockLLMClient('{"ops": []}'),
                      store_factory=lambda: SnapshotStore(tempfile.mkdtemp()), loop_config=_cfg(),
                      embargo=1, reserved=1)
    assert isinstance(mw, MultiWindowReport)
    assert mw.n_windows == 3 and mw.n_reserved == 1 and mw.embargo == 1
    # existing fields still cover ALL windows (byte-identical semantics)
    assert len(mw.deltas) == 3 and len(mw.verdicts) == 3
    # additive holdout view: iterate over the first 2, reserved over the last 1
    assert len(mw.reserved_deltas) == 1
    assert abs(mw.iterate_mean_delta - sum(mw.deltas[:2]) / 2) < 1e-9
    assert abs(mw.reserved_mean_delta - mw.deltas[2]) < 1e-9


def test_multi_window_reserved_zero_byte_identical():
    src = _source(20)
    cal = src.trading_calendar()
    windows = [(cal[0], cal[5]), (cal[7], cal[12])]
    kw = dict(agent_llm_factory=_af, refiner_llm_factory=lambda: MockLLMClient('{"ops": []}'),
              store_factory=lambda: SnapshotStore(tempfile.mkdtemp()), loop_config=_cfg())
    a = multi_window(lambda: load_seeds(SEEDS), src, windows, **kw)
    b = multi_window(lambda: load_seeds(SEEDS), src, windows, reserved=0, embargo=0, **kw)
    assert a.mean_delta == b.mean_delta and a.deltas == b.deltas
    assert a.n_reserved == 0 and a.iterate_mean_delta == a.mean_delta       # all windows are iterate
