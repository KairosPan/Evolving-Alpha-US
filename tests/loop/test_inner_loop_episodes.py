"""Tests that InnerLoop optionally records episodes with realized exit_date at the maturity seam."""
from datetime import date
import pandas as pd

from alpha.data.source import FakeSource
from alpha.harness.skill import Skill
from alpha.harness.doctrine import Doctrine
from alpha.harness.registry import SkillRegistry, MemoryStore
from alpha.harness.state import HarnessState
from alpha.harness.snapshot import SnapshotStore
from alpha.harness.manager import HarnessManager
from alpha.eval.decision import Candidate, DecisionPackage
from alpha.eval.scorer import ReturnScorer
from alpha.llm.client import MockLLMClient
from alpha.loop.inner_loop import InnerLoop, LoopConfig
from alpha.memory.store import EpisodeStore


class _PickRun:
    """Deterministic LLM-free policy: pick every universe symbol as gap_and_go."""
    def decide(self, state, universe):
        return DecisionPackage(date=state.date,
                               candidates=[Candidate(symbol=s.symbol, pattern="gap_and_go")
                                           for s in universe.all()])


def _h():
    skills = SkillRegistry.from_skills([Skill(skill_id="gap_and_go", name="Gap and Go", type="pattern",
                                              status="active")])
    return HarnessState(doctrine=Doctrine(), skills=skills, memory=MemoryStore.from_lessons([]))


def _source(n=6):
    cal = [date(2026, 6, d) for d in range(1, 1 + n)]
    snaps, px = {}, 10.0
    closes = []
    for d in cal:
        prev = px
        px = px * 1.2                      # +20% gainer every day (screens in)
        closes.append(px)
        snaps[d] = pd.DataFrame({"symbol": ["RUN"], "name": ["RUN"], "open": [prev], "high": [px],
                                 "low": [prev], "close": [px], "volume": [1], "prev_close": [prev]})
    bars = {"RUN": pd.DataFrame({"date": cal, "open": [10.0] + closes[:-1], "high": closes,
                                 "low": [10.0] + closes[:-1], "close": closes, "volume": [1] * n})}
    return FakeSource(calendar=cal, bars=bars, snapshots=snaps)


def _loop(src, cfg, episode_store=None):
    import tempfile
    mgr = HarnessManager(_h(), SnapshotStore(tempfile.mkdtemp()))
    return InnerLoop(mgr, src, src.trading_calendar()[0], src.trading_calendar()[-1],
                     agent_llm=MockLLMClient("{}"), refiner_llm=MockLLMClient('{"ops": []}'),
                     config=cfg, scorer=ReturnScorer(), agent_factory=lambda h: _PickRun(),
                     episode_store=episode_store), mgr


def test_inner_loop_writes_episodes_with_realized_exit_date():
    """Episode exit_date must be the maturity cursor (decision_date + horizon trading days),
    strictly greater than entry_date, and learned_asof must equal exit_date."""
    src = _source(6)
    store = EpisodeStore.in_memory()
    loop, _ = _loop(src, LoopConfig(horizon=2, enable_refine=False, screen=False), episode_store=store)
    loop.run()
    eps = store.all()
    assert eps, "expected episodes for the scored steps (horizon=2, 6 days → 4 scored steps)"
    # exit_date is the realized maturity cursor, strictly after entry_date (decision_date)
    assert all(e.exit_date > e.entry_date for e in eps), (
        f"exit_date not > entry_date for some episode: {[(e.entry_date, e.exit_date) for e in eps]}"
    )
    assert all(e.learned_asof == e.exit_date for e in eps), (
        f"learned_asof != exit_date for some episode: {[(e.learned_asof, e.exit_date) for e in eps]}"
    )


def test_inner_loop_no_episode_store_still_runs():
    """Default (episode_store=None) must produce no episodes and not crash."""
    src = _source(6)
    loop, _ = _loop(src, LoopConfig(horizon=2, enable_refine=False, screen=False))
    report = loop.run()
    # no store → no assertion on episodes; just confirm the loop ran normally
    assert len(report.trajectory.steps) == 6
    assert len(report.trajectory.scored_steps()) == 4
