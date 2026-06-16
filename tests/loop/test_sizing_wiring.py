"""L3 sizing is wired into the live loop and ON by default: a frontside runner's pick carries a size_tier
and the decision carries a portfolio (exposure budget). size=False emits unsized decisions."""
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
    snaps, px, closes = {}, 10.0, []
    for d in cal:
        prev = px; px = px * 1.15; closes.append(px)
        snaps[d] = pd.DataFrame({"symbol": ["RUN"], "name": ["RUN"], "open": [prev], "high": [px],
                                 "low": [prev], "close": [px], "volume": [1], "prev_close": [prev]})
    bars = {"RUN": pd.DataFrame({"date": cal, "open": [10.0] + closes[:-1], "high": closes,
                                 "low": [10.0] + closes[:-1], "close": closes, "volume": [1] * n})}
    return FakeSource(calendar=cal, bars=bars, snapshots=snaps)


def _loop(*, size):
    src = _runner_source(6)
    mgr = HarnessManager(load_seeds(SEEDS), SnapshotStore(tempfile.mkdtemp()))
    cfg = LoopConfig(horizon=2, evidence_min=2, refine_every=1, size=size)
    return InnerLoop(mgr, src, src.trading_calendar()[0], src.trading_calendar()[-1],
                     MockLLMClient('{"candidates": [{"symbol": "RUN", "pattern": "gap_and_go"}]}'),
                     MockLLMClient('{"ops": []}'), config=cfg).run()


def test_size_defaults_on():
    assert LoopConfig().size is True


def test_live_decisions_carry_size_tier_and_portfolio():
    lr = _loop(size=True)
    sized = [c for s in lr.trajectory.steps for c in s.decision.candidates if c.size_tier is not None]
    assert sized                                                    # at least one kept pick is sized
    assert all(c.size_tier in {"flat", "probe", "core", "heavy"} for c in sized)
    assert any(s.decision.portfolio is not None for s in lr.trajectory.steps)


def test_size_off_emits_unsized_decisions():
    lr = _loop(size=False)
    assert all(c.size_tier is None for s in lr.trajectory.steps for c in s.decision.candidates)
    assert all(s.decision.portfolio is None for s in lr.trajectory.steps)
