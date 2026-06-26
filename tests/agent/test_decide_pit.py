"""End-to-end PIT-leak regression for decide().

A lesson with learned_asof=2026-06-12 must be ABSENT from the system prompt
when the agent decides at as_of=2026-06-11, and PRESENT at as_of=2026-06-12.
Both injection modes (full, retrieval) are parametrized.
"""
from datetime import date, datetime
import pytest
from alpha.harness.doctrine import Doctrine
from alpha.harness.registry import SkillRegistry, MemoryStore
from alpha.harness.memory import Lesson
from alpha.harness.state import HarnessState
from alpha.state.market import MarketState
from alpha.universe.stock import StockSnapshot
from alpha.universe.universe import CandidateUniverse
from alpha.llm.client import MockLLMClient
from alpha.agent.agent import LLMAgentPolicy


def _h():
    lessons = [Lesson(lesson_id="future", outcome="loss", lesson="FUTURE_LESSON_TEXT",
                      learned_asof=date(2026, 6, 12))]
    return HarnessState(doctrine=Doctrine(), skills=SkillRegistry.from_skills([]),
                        memory=MemoryStore.from_lessons(lessons))


def _state(asof_day: int) -> MarketState:
    return MarketState(date=date(2026, 6, asof_day), gainer_count=1, gap_up_count=0, loser_count=0,
                       failed_breakout_count=0, max_runner_tier=1, echelon=[], breadth_raw=1.0,
                       sentiment_norm=0.6, as_of=datetime(2026, 6, asof_day, 16, 0))


def _uni():
    return CandidateUniverse.from_stocks([StockSnapshot(symbol="RUN", name="Runner", status="gainer")])


@pytest.mark.parametrize("injection", ["full", "retrieval"])
def test_decide_does_not_leak_future_lesson(injection):
    llm = MockLLMClient('{"regime_read": "", "candidates": []}')
    agent = LLMAgentPolicy(_h(), llm, injection=injection)
    agent.decide(_state(11), _uni())                      # as_of = 2026-06-11 (before the lesson's asof)
    system_before, _user = llm.calls[0]
    assert "FUTURE_LESSON_TEXT" not in system_before      # the look-ahead leak is closed


@pytest.mark.parametrize("injection", ["full", "retrieval"])
def test_decide_shows_lesson_on_or_after_asof(injection):
    llm = MockLLMClient('{"regime_read": "", "candidates": []}')
    agent = LLMAgentPolicy(_h(), llm, injection=injection)
    agent.decide(_state(12), _uni())                      # as_of = 2026-06-12 (the lesson's asof)
    system_on, _user = llm.calls[0]
    assert "FUTURE_LESSON_TEXT" in system_on
