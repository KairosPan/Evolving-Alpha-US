"""Acceptance: wiring L3 sizing into the live loop enriches the DecisionPackage (size_tier + portfolio)
but is VERDICT-NEUTRAL — the per-step advantages are identical with sizing on vs off (scoring is
equal-weighted and never reads size). This is the production posture: a complete decision surface that
does not bias the HCH-vs-Hexpert comparison."""
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


def _src(n=6):
    cal = [date(2026, 6, d) for d in range(1, 1 + n)]
    snaps, px, closes = {}, 10.0, []
    for d in cal:
        prev = px; px = px * 1.15; closes.append(px)
        snaps[d] = pd.DataFrame({"symbol": ["RUN"], "name": ["RUN"], "open": [prev], "high": [px],
                                 "low": [prev], "close": [px], "volume": [1], "prev_close": [prev]})
    bars = {"RUN": pd.DataFrame({"date": cal, "open": [10.0] + closes[:-1], "high": closes,
                                 "low": [10.0] + closes[:-1], "close": closes, "volume": [1] * n})}
    return FakeSource(calendar=cal, bars=bars, snapshots=snaps)


def _run(size):
    # fresh src + mgr + MockLLMClients per call (MockLLMClient is stateful — its response cursor must not
    # carry across the two runs); the ONLY difference between the two runs is the size flag.
    src = _src()
    mgr = HarnessManager(load_seeds(SEEDS), SnapshotStore(tempfile.mkdtemp()))
    cfg = LoopConfig(horizon=2, evidence_min=2, refine_every=1, size=size)
    return InnerLoop(mgr, src, src.trading_calendar()[0], src.trading_calendar()[-1],
                     MockLLMClient('{"candidates": [{"symbol": "RUN", "pattern": "gap_and_go"}]}'),
                     MockLLMClient('{"ops": []}'), config=cfg).run()


def _advantages(lr):
    return [round(c.advantage, 8) for s in lr.trajectory.scored_steps()
            for c in sorted(s.outcomes.values(), key=lambda x: x.symbol)]


def test_l3_sizing_is_verdict_neutral_but_enriches_surface():
    on, off = _run(True), _run(False)
    # surface enriched with sizing on (size_tier + portfolio), absent with sizing off
    assert any(c.size_tier is not None for s in on.trajectory.steps for c in s.decision.candidates)
    assert all(c.size_tier is None for s in off.trajectory.steps for c in s.decision.candidates)
    assert any(s.decision.portfolio is not None for s in on.trajectory.steps)
    assert all(s.decision.portfolio is None for s in off.trajectory.steps)
    # verdict-neutral: the scored advantages are identical on vs off
    assert _advantages(on) == _advantages(off) and _advantages(on)   # non-empty + equal
