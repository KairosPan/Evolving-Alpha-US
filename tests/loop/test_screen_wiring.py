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


def _source(n=6):
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


def _loop(src, *, screen):
    mgr = HarnessManager(load_seeds(SEEDS), SnapshotStore(tempfile.mkdtemp()))
    cfg = LoopConfig(horizon=2, evidence_min=2, refine_every=1, screen=screen)
    return InnerLoop(mgr, src, src.trading_calendar()[0], src.trading_calendar()[-1],
                     MockLLMClient('{"candidates": [{"symbol": "RUN", "pattern": "gap_and_go"}]}'),
                     MockLLMClient('{"ops": []}'), config=cfg)


def test_screen_off_by_default_keeps_entries():
    lr = _loop(_source(6), screen=False).run()
    assert any(s.entries for s in lr.trajectory.steps)             # RUN enters normally (apparatus unchanged)


def test_screen_on_vetoes_backside_entries():
    # the minimal state builder feeds GCycle sentiment_norm=None/ft=0 -> single-gainer reads backside,
    # so the wired veto drops every RUN pick (entries empty) and records reasons. This demonstrates the
    # opt-in wiring; the SSR/reverse-split discrimination is unit-tested in tests/guard/test_screen.py.
    lr = _loop(_source(6), screen=True).run()
    assert all(not s.entries for s in lr.trajectory.steps)         # all vetoed -> no entries
    assert any(s.decision.key_risks for s in lr.trajectory.steps)  # veto reasons surfaced
    assert any(s.decision.regime is not None for s in lr.trajectory.steps)  # structured regime populated
