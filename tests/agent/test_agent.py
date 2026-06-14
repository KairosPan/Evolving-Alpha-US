from datetime import date, datetime
from alpha.harness.skill import Skill
from alpha.harness.doctrine import Doctrine
from alpha.harness.registry import SkillRegistry, MemoryStore
from alpha.harness.state import HarnessState
from alpha.state.market import MarketState
from alpha.universe.stock import StockSnapshot
from alpha.universe.universe import CandidateUniverse
from alpha.llm.client import MockLLMClient
from alpha.agent.agent import LLMAgentPolicy


def _h():
    skills = SkillRegistry.from_skills([
        Skill(skill_id="gap_and_go", name="Gap and Go", type="pattern", family="runner",
              phases=["trend"], status="active"),
    ])
    return HarnessState(doctrine=Doctrine(), skills=skills, memory=MemoryStore.from_lessons([]))


def _state():
    return MarketState(date=date(2026, 6, 12), gainer_count=1, gap_up_count=0, loser_count=0,
                       failed_breakout_count=0, max_runner_tier=1, echelon=[], breadth_raw=1.0,
                       sentiment_norm=0.6, as_of=datetime(2026, 6, 12, 16, 0))


def _uni():
    return CandidateUniverse.from_stocks([StockSnapshot(symbol="RUN", name="Runner", status="gainer")])


def test_agent_decides_and_reanchors():
    llm = MockLLMClient('{"regime_read": "trend frontside", "candidates": '
                        '[{"symbol": "RUN", "pattern": "gap_and_go", "confidence": 0.7}]}')
    agent = LLMAgentPolicy(_h(), llm)
    assert hasattr(agent, "decide") and callable(agent.decide)   # structural DecisionPolicy conformance
    state, uni = _state(), _uni()
    pkg = agent.decide(state, uni)
    assert [c.symbol for c in pkg.candidates] == ["RUN"]
    assert pkg.regime_read == "trend frontside"
    assert pkg.as_of == state.as_of                # agent stamps the inference-path timestamp (§4.1)
    # the agent built a prompt that included the live skill + the candidate
    sys, usr = llm.calls[0]
    assert "gap_and_go" in sys and "RUN" in usr


def test_phase_prior_threads_across_calls():
    # regime_read obeys the multi-token output contract; the agent must EXTRACT the canonical phase
    llm = MockLLMClient(['{"regime_read": "trend frontside", "candidates": []}',
                         '{"regime_read": "", "candidates": []}'])
    agent = LLMAgentPolicy(_h(), llm, injection="retrieval")
    st = _state()
    pkg1 = agent.decide(st, _uni())
    assert agent._phase_prior == "trend"           # extracted from "trend frontside" (NOT None)
    assert pkg1.as_of == st.as_of
    agent.decide(_state(), _uni())                  # second response has empty regime_read
    assert agent._phase_prior is None              # -> prior cleared


def test_malformed_response_is_no_trade():
    agent = LLMAgentPolicy(_h(), MockLLMClient("no json at all"))
    pkg = agent.decide(_state(), _uni())
    assert pkg.candidates == [] and pkg.no_trade_reason
