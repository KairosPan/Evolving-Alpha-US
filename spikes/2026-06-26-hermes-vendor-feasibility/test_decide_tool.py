# spikes/2026-06-26-hermes-vendor-feasibility/test_decide_tool.py
from datetime import date, datetime
from alpha.harness.skill import Skill
from alpha.harness.doctrine import Doctrine
from alpha.harness.registry import SkillRegistry, MemoryStore
from alpha.harness.state import HarnessState
from alpha.state.market import MarketState
from alpha.universe.stock import StockSnapshot
from alpha.universe.universe import CandidateUniverse
from alpha.llm.client import MockLLMClient
from alpha.eval.decision import DecisionPackage
from spike_loop import Registry
from decide_tool import make_decide_tool

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

def test_decide_tool_returns_typed_package_through_registry():
    agent_llm = MockLLMClient('{"regime_read": "trend frontside", "candidates": '
                              '[{"symbol": "RUN", "pattern": "gap_and_go", "confidence": 0.7}]}')
    schema, decide = make_decide_tool(_h(), agent_llm)
    reg = Registry()
    reg.register("decide", schema, decide)
    pkg = reg.call("decide", state=_state(), universe=_uni())
    assert isinstance(pkg, DecisionPackage)
    assert [c.symbol for c in pkg.candidates] == ["RUN"]
    assert pkg.regime_read == "trend frontside"
