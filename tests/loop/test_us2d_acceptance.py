"""US-2d acceptance: the three-way HCH/Hexpert/Hmin compare runs end-to-end on the SEEDED harness with
the SHADOW breaker armed off the Hexpert reference, produces a ComparisonReport (excess delta + verdict
+ all four arms), and a multi_window diagnostic aggregates across windows. Validates the loop's measuring
apparatus; real efficacy needs temp=0 Claude/DeepSeek (MockLLM ignores prompts). NOTE: the spec §9/§10
statistical acceptance gate (CI/MDE/multi-seed/offense-defense) is the required US-2e validation slice."""
import tempfile
from pathlib import Path
from datetime import date
import pandas as pd
from alpha.data.source import FakeSource
from alpha.harness.loader import load_seeds
from alpha.harness.snapshot import SnapshotStore
from alpha.llm.client import MockLLMClient
from alpha.loop.inner_loop import LoopConfig
from alpha.loop.compare import compare_harnesses, multi_window, ComparisonReport

SEEDS = Path(__file__).resolve().parents[2] / "seeds"


def _source(n=10):
    cal = [date(2026, 6, d) for d in range(1, 1 + n)]
    snaps, px = {}, 10.0
    closes = []
    for d in cal:
        prev = px; px = px * 1.15; closes.append(px)         # +15%/day: in-universe, advantage > 0, no breaker trip
        snaps[d] = pd.DataFrame({"symbol": ["RUN"], "name": ["RUN"], "open": [prev], "high": [px],
                                 "low": [prev], "close": [px], "volume": [1], "prev_close": [prev]})
    bars = {"RUN": pd.DataFrame({"date": cal, "open": [10.0] + closes[:-1], "high": closes,
                                 "low": [10.0] + closes[:-1], "close": closes, "volume": [1] * n})}
    return FakeSource(calendar=cal, bars=bars, snapshots=snaps)


def _agent():
    return MockLLMClient('{"regime_read": "trend", "candidates": '
                         '[{"symbol": "RUN", "pattern": "gap_and_go", "confidence": 0.7}]}')


def test_three_way_compare_with_shadow_end_to_end():
    src = _source(10)
    cal = src.trading_calendar()
    cr = compare_harnesses(lambda: load_seeds(SEEDS), src, cal[0], cal[-1],
                           agent_llm_factory=_agent,
                           refiner_llm_factory=lambda: MockLLMClient('{"ops": []}'),
                           store_factory=lambda: SnapshotStore(tempfile.mkdtemp()),
                           loop_config=LoopConfig(horizon=2, evidence_min=2, refine_every=1),
                           shadow=True)
    assert isinstance(cr, ComparisonReport)
    assert set(cr.arms) == {"HCH", "Hexpert", "Hmin_chase", "Hmin_notrade"}
    # every arm produced a real EvalReport over the same window
    assert all(a.report.n_decisions == 10 for a in cr.arms.values())
    assert isinstance(cr.hch_beats_hexpert, bool) and cr.hch_loop_report is not None
    # HCH is the only arm carrying loop telemetry; the shadow breaker did not spuriously trip on a healthy run
    assert cr.arms["HCH"].n_refines is not None and cr.arms["HCH"].frozen_from is None


def test_multi_window_diagnostic_end_to_end():
    src = _source(10)
    cal = src.trading_calendar()
    mw = multi_window(lambda: load_seeds(SEEDS), src, [(cal[0], cal[4]), (cal[5], cal[9])],
                      agent_llm_factory=_agent,
                      refiner_llm_factory=lambda: MockLLMClient('{"ops": []}'),
                      store_factory=lambda: SnapshotStore(tempfile.mkdtemp()),
                      loop_config=LoopConfig(horizon=2, evidence_min=2, refine_every=1))
    assert mw.n_windows == 2 and len(mw.deltas) == 2 and 0.0 <= mw.win_rate <= 1.0
