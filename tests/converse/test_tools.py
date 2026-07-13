# tests/converse/test_tools.py
from datetime import date, datetime
import pandas as pd
from alpha.harness.skill import Skill
from alpha.harness.doctrine import Doctrine
from alpha.harness.registry import SkillRegistry, MemoryStore
from alpha.harness.state import HarnessState
from alpha.state.market import MarketState
from alpha.universe.stock import StockSnapshot
from alpha.universe.universe import CandidateUniverse
from alpha.llm.client import MockLLMClient
from alpha.eval.decision import DecisionPackage
from alpha.data.source import FakeSource
from alpha.converse.tools import make_decide_tool, make_decide_for_date_tool

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

def _bare_h():
    return HarnessState(doctrine=Doctrine(), skills=SkillRegistry.from_skills([]),
                        memory=MemoryStore.from_lessons([]))


def test_worker_has_no_propose_tool():
    """A7 (charter First Founding Principle: "Kairos does not propose at all"): the worker face's
    H-mutation staging tool was retired — the module no longer exposes it."""
    import alpha.converse.tools as _ct
    assert not hasattr(_ct, "make_propose_edit_tool")


def test_decide_tool_returns_typed_package():
    agent_llm = MockLLMClient('{"regime_read": "trend frontside", "candidates": '
                              '[{"symbol": "RUN", "pattern": "gap_and_go", "confidence": 0.7}]}')
    schema, decide = make_decide_tool(_h(), agent_llm)
    assert schema["name"] == "decide"
    pkg = decide(state=_state(), universe=_uni())
    assert isinstance(pkg, DecisionPackage)
    assert [c.symbol for c in pkg.candidates] == ["RUN"]


def _fake_source():
    cal = [date(2026, 6, d) for d in range(10, 14)]      # 4 trading days
    snaps, px, closes = {}, 10.0, []
    for d in cal:
        prev = px; px = px * 1.15; closes.append(px)      # RUN rises 15%/day -> a gainer (>= gainer_pct 10)
        snaps[d] = pd.DataFrame({"symbol": ["RUN"], "name": ["RUN"], "open": [prev], "high": [px],
                                 "low": [prev], "close": [px], "volume": [1], "prev_close": [prev]})
    bars = {"RUN": pd.DataFrame({"date": cal, "open": [10.0] + closes[:-1], "high": closes,
                                 "low": [10.0] + closes[:-1], "close": closes, "volume": [1] * len(cal)})}
    return FakeSource(calendar=cal, bars=bars, snapshots=snaps)

def _agent_llm():
    return MockLLMClient('{"regime_read": "trend frontside", "candidates": '
                         '[{"symbol": "RUN", "pattern": "gap_and_go", "confidence": 0.7}]}')

def test_decide_for_date_builds_pit_state_and_returns_typed_package():
    schema, decide = make_decide_for_date_tool(_h(), _agent_llm(), _fake_source())
    assert schema["name"] == "decide" and "date" in schema["parameters"]["required"]
    pkg = decide(date="2026-06-12")
    from alpha.eval.decision import DecisionPackage
    assert isinstance(pkg, DecisionPackage)
    assert pkg.date == date(2026, 6, 12)                  # built for the requested date
    assert pkg.as_of == datetime(2026, 6, 12, 16, 0)      # PIT close stamp
    assert [c.symbol for c in pkg.candidates] == ["RUN"]  # RUN surfaced as a gainer and survived
