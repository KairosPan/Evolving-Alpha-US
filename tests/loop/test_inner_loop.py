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
from alpha.loop.inner_loop import InnerLoop, LoopConfig, LoopReport


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


def _loop(src, cfg):
    import tempfile
    mgr = HarnessManager(_h(), SnapshotStore(tempfile.mkdtemp()))
    return InnerLoop(mgr, src, src.trading_calendar()[0], src.trading_calendar()[-1],
                     agent_llm=MockLLMClient("{}"), refiner_llm=MockLLMClient('{"ops": []}'),
                     config=cfg, scorer=ReturnScorer(), agent_factory=lambda h: _PickRun()), mgr


def test_skeleton_runs_and_credits_cumulatively():
    src = _source(6)
    loop, mgr = _loop(src, LoopConfig(horizon=2, enable_refine=False))
    report = loop.run()
    assert isinstance(report, LoopReport)
    assert len(report.trajectory.steps) == 6                  # one step per day
    # horizon=2 over 6 days -> decisions 0..3 scored (4 scored steps); RUN attributed to gap_and_go
    assert len(report.trajectory.scored_steps()) == 4
    assert mgr.harness.skills.get("gap_and_go").stats.n == 4  # online credit ran once per scored step
    assert report.refine_events == [] and report.breaker_events == []   # disabled / not tripped
