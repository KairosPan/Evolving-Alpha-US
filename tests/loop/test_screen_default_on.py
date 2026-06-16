"""screen now defaults ON (the richer builder makes GCycle read frontside, so the guard no longer over-fires).
A frontside runner is KEPT; compare_harnesses wraps the non-HCH arms symmetrically."""
import tempfile
from datetime import date
from pathlib import Path
import pandas as pd
from alpha.data.source import FakeSource
from alpha.harness.loader import load_seeds
from alpha.harness.manager import HarnessManager
from alpha.harness.snapshot import SnapshotStore
from alpha.llm.client import MockLLMClient
from alpha.loop.inner_loop import InnerLoop, LoopConfig

SEEDS = Path(__file__).resolve().parents[2] / "seeds"


def _runner_source(n=6):
    cal = [date(2026, 6, d) for d in range(1, 1 + n)]
    snaps, px = {}, 10.0
    closes = []
    for d in cal:
        prev = px; px = px * 1.15; closes.append(px)
        snaps[d] = pd.DataFrame({"symbol": ["RUN"], "name": ["RUN"], "open": [prev], "high": [px],
                                 "low": [prev], "close": [px], "volume": [1], "prev_close": [prev]})
    bars = {"RUN": pd.DataFrame({"date": cal, "open": [10.0] + closes[:-1], "high": closes,
                                 "low": [10.0] + closes[:-1], "close": closes, "volume": [1] * n})}
    return FakeSource(calendar=cal, bars=bars, snapshots=snaps)


def test_screen_defaults_on():
    assert LoopConfig().screen is True


def test_screen_on_keeps_frontside_runner():
    # default LoopConfig (screen=True). The richer builder -> follow_through=1.0 -> GCycle frontside ->
    # the regime veto does NOT fire, and RUN trips no data veto -> RUN is entered (not dropped).
    src = _runner_source(6)
    mgr = HarnessManager(load_seeds(SEEDS), SnapshotStore(tempfile.mkdtemp()))
    loop = InnerLoop(mgr, src, src.trading_calendar()[0], src.trading_calendar()[-1],
                     MockLLMClient('{"candidates": [{"symbol": "RUN", "pattern": "gap_and_go"}]}'),
                     MockLLMClient('{"ops": []}'),
                     config=LoopConfig(horizon=2, evidence_min=2, refine_every=1))   # screen defaults True
    lr = loop.run()
    assert any(s.entries for s in lr.trajectory.steps)          # frontside runner kept despite screen on
