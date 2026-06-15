"""US-2c acceptance: the InnerLoop self-evolves the SEEDED harness end-to-end on a MockLLM agent +
MockLLM refiner — online credit mutates H, a checkpointed refine edits H (audited), the firewall holds,
and a healthy advantage series does not trip the breaker. This is the loop US-2d will compare arm-vs-arm."""
import tempfile
from pathlib import Path
from datetime import date
import pandas as pd
from alpha.data.source import FakeSource
from alpha.harness.loader import load_seeds
from alpha.harness.snapshot import SnapshotStore
from alpha.harness.manager import HarnessManager
from alpha.llm.client import MockLLMClient
from alpha.eval.scorer import ReturnScorer
from alpha.loop.inner_loop import InnerLoop, LoopConfig

SEEDS = Path(__file__).resolve().parents[2] / "seeds"


def _source(n=8):
    cal = [date(2026, 6, d) for d in range(1, 1 + n)]
    snaps, px = {}, 10.0
    closes = []
    for d in cal:
        prev = px; px = px * 1.15; closes.append(px)        # +15%/day: RUN screens in (>10%) and keeps gaining
        snaps[d] = pd.DataFrame({"symbol": ["RUN"], "name": ["RUN"], "open": [prev], "high": [px],
                                 "low": [prev], "close": [px], "volume": [1], "prev_close": [prev]})
    bars = {"RUN": pd.DataFrame({"date": cal, "open": [10.0] + closes[:-1], "high": closes,
                                 "low": [10.0] + closes[:-1], "close": closes, "volume": [1] * n})}
    # +15% < the EXOGENOUS 20% gainer gate, so the decision-day pool is empty -> day_baseline None ->
    # advantage == raw forward return (positive), comfortably above floor_abs -> the breaker never trips.
    return FakeSource(calendar=cal, bars=bars, snapshots=snaps)


def test_inner_loop_self_evolves_seeded_harness_end_to_end():
    mgr = HarnessManager(load_seeds(SEEDS), SnapshotStore(tempfile.mkdtemp()))
    src = _source(8)
    loop = InnerLoop(
        mgr, src, src.trading_calendar()[0], src.trading_calendar()[-1],
        agent_llm=MockLLMClient('{"regime_read": "trend", "candidates": '
                                '[{"symbol": "RUN", "pattern": "gap_and_go", "confidence": 0.7}]}'),
        refiner_llm=MockLLMClient('{"ops": [{"tool": "rewrite_doctrine", "args": {"section": "trend_play", '
                                  '"new_guidance": "ride the lead runner; trim into blowoffs (refined)"}, '
                                  '"rationale": "evidence"}]}'),
        config=LoopConfig(horizon=2, evidence_min=2, refine_every=1), scorer=ReturnScorer())
    report = loop.run()
    # the loop walked every day and scored the matured decisions
    assert len(report.trajectory.steps) == 8 and report.trajectory.scored_steps()
    # online credit populated the seed skill's stats
    assert mgr.harness.skills.get("gap_and_go").stats.n >= 1
    # at least one checkpointed refine fired and edited H (audited in the EditLog)
    assert report.refine_events and report.refine_events[0].checkpoint_version is not None
    assert report.n_edits >= 1 and "refined" in mgr.harness.doctrine.get("trend_play").guidance
    # a healthy advantage series does not trip the breaker (no LookaheadError raised => firewall held)
    assert report.frozen_from is None and report.breaker_events == []
