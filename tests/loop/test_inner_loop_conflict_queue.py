# tests/loop/test_inner_loop_conflict_queue.py
from datetime import date
import pandas as pd
from alpha.harness.loader import load_seeds
from alpha.harness.manager import HarnessManager
from alpha.harness.snapshot import SnapshotStore
from alpha.data.source import FakeSource
from alpha.llm.client import MockLLMClient
from alpha.loop.inner_loop import InnerLoop
from pathlib import Path
import tempfile

SEEDS = Path(__file__).resolve().parents[2] / "seeds"

def _src():
    cal = [date(2026, 6, 10)]
    snaps = {cal[0]: pd.DataFrame({"symbol": ["RUN"], "name": ["RUN"], "open": [1.0], "high": [1.0],
                                   "low": [1.0], "close": [1.0], "volume": [1], "prev_close": [1.0]})}
    bars = {"RUN": pd.DataFrame({"date": cal, "open": [1.0], "high": [1.0], "low": [1.0], "close": [1.0], "volume": [1]})}
    return FakeSource(calendar=cal, bars=bars, snapshots=snaps)

def _loop(conflict_queue):
    mgr = HarnessManager(load_seeds(SEEDS), SnapshotStore(tempfile.mkdtemp()))
    return InnerLoop(mgr, _src(), date(2026, 6, 10), date(2026, 6, 10),
                     MockLLMClient("{}"), MockLLMClient("{}"), conflict_queue=conflict_queue)

def test_conflict_queue_reaches_the_refiner():
    sentinel = object()
    loop = _loop(sentinel)
    assert loop._refiner._conflict_queue is sentinel

def test_conflict_queue_defaults_none():
    loop = _loop(None)
    assert loop._refiner._conflict_queue is None
