from datetime import date, datetime
import pandas as pd
from alpha.harness.doctrine import Doctrine
from alpha.harness.skill import Skill
from alpha.harness.registry import SkillRegistry, MemoryStore
from alpha.harness.state import HarnessState
from alpha.memory.episodes import Episode
from alpha.memory.store import EpisodeStore
from alpha.agent.agent import LLMAgentPolicy
from alpha.state.builder import build_market_state
from alpha.universe.universe import build_universe
from alpha.data.source import FakeSource


class _CaptureLLM:
    """Records the system prompt it was asked to complete; returns a minimal valid decision."""
    def __init__(self): self.system = ""
    def complete(self, system, user):
        self.system = system
        return '{"regime_read": "trend frontside", "candidates": [{"symbol": "RUN", "pattern": "gap_and_go"}]}'


def _h():
    return HarnessState(doctrine=Doctrine(),
                        skills=SkillRegistry.from_skills([Skill(skill_id="gap_and_go", name="Gap and Go",
                                                               type="pattern", status="active")]),
                        memory=MemoryStore.from_lessons([]))


def _src():
    cal = [date(2026, 6, 10)]
    snaps = {cal[0]: pd.DataFrame({"symbol": ["RUN"], "name": ["RUN"], "open": [1.0], "high": [1.0],
                                   "low": [1.0], "close": [1.0], "volume": [1], "prev_close": [1.0]})}
    bars = {"RUN": pd.DataFrame({"date": cal, "open": [1.0], "high": [1.0], "low": [1.0], "close": [1.0], "volume": [1]})}
    return FakeSource(calendar=cal, bars=bars, snapshots=snaps)


def test_decide_threads_episode_store_and_asof():
    s = EpisodeStore.in_memory()
    s.add(Episode(episode_id="e1", symbol="RUN", skill_id="gap_and_go", phase="trend frontside",
                  entry_date=date(2026, 6, 1), exit_date=date(2026, 6, 5), outcome="continued", advantage=2.0,
                  reflection_text="ran into close"))
    day = date(2026, 6, 10)
    src = _src(); universe = build_universe(src, day)
    state = build_market_state(universe, day, as_of=datetime(2026, 6, 10, 16, 0))
    llm = _CaptureLLM()
    LLMAgentPolicy(_h(), llm, injection="full", episode_store=s).decide(state, universe)
    assert "RECALLED EPISODES" in llm.system and "RUN/gap_and_go" in llm.system   # store + as_of were threaded


def test_decide_without_store_has_no_episode_block():
    day = date(2026, 6, 10)
    src = _src(); universe = build_universe(src, day)
    state = build_market_state(universe, day, as_of=datetime(2026, 6, 10, 16, 0))
    llm = _CaptureLLM()
    LLMAgentPolicy(_h(), llm, injection="full").decide(state, universe)        # no episode_store
    assert "RECALLED EPISODES" not in llm.system
