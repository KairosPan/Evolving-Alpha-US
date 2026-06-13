# tests/test_agent.py
from datetime import date, datetime
from pathlib import Path
from youzi.harness.loader import load_seeds
from youzi.schemas.market import MarketState
from youzi.universe.stock import StockSnapshot
from youzi.universe.universe import CandidateUniverse
from youzi.llm.client import MockLLMClient
from youzi.agent.agent import LLMAgentPolicy

SEEDS = Path(__file__).resolve().parent.parent / "seeds"


def _state():
    return MarketState(date=date(2024, 6, 27), max_board_height=7, limit_up_count=2,
                       blowup_count=0, blowup_rate=0.0, limit_down_count=0, echelon=[],
                       money_effect_raw=2.0, sentiment_raw=12.0, sentiment_norm=None,
                       as_of=datetime(2024, 6, 27, 15, 0))


def _uni():
    return CandidateUniverse.from_stocks([
        StockSnapshot(code="000001", name="甲", status="limit_up", boards=7),
        StockSnapshot(code="300002", name="乙", status="limit_up", boards=2)])


def test_agent_decides_via_llm_and_parses():
    llm = MockLLMClient('{"regime_read":"主升","candidates":'
                        '[{"code":"000001","pattern":"highest_board","reason":"龙头","confidence":0.7}],'
                        '"no_trade_reason":""}')
    agent = LLMAgentPolicy(load_seeds(SEEDS), llm)
    pkg = agent.decide(_state(), _uni())
    assert {c.code for c in pkg.candidates} == {"000001"}
    # LLM 确实收到了渲染好的系统/用户提示
    sys, user = llm.calls[0]
    assert "纪律红线" in sys and "000001" in user


def test_agent_is_a_decision_policy():
    # 结构上满足 WalkForwardEval 期望的 DecisionPolicy(有 decide(state, universe))
    agent = LLMAgentPolicy(load_seeds(SEEDS), MockLLMClient('{"candidates":[]}'))
    pkg = agent.decide(_state(), _uni())
    assert pkg.candidates == []
