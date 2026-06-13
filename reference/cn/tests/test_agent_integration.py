# tests/test_agent_integration.py
from datetime import date
from pathlib import Path
import pandas as pd
from youzi.harness.loader import load_seeds
from youzi.llm.client import MockLLMClient
from youzi.agent.agent import LLMAgentPolicy
from youzi.eval.walk_forward import WalkForwardEval
from tests.conftest import FakeSource

SEEDS = Path(__file__).resolve().parent.parent / "seeds"


def _src():
    """3 天,代码 A 每日涨停(MockLLM 固定选 A → continued)。"""
    d0, d1, d2 = date(2024, 6, 26), date(2024, 6, 27), date(2024, 6, 28)
    frames = {}
    for d, b in [(d0, 2), (d1, 3), (d2, 4)]:
        frames[("zt", d)] = pd.DataFrame({"code": ["A"], "name": ["甲"], "boards": [b]})
        frames[("blowup", d)] = pd.DataFrame()
        frames[("dt", d)] = pd.DataFrame()
    return FakeSource(frames, [d0, d1, d2])


def test_agent_runs_through_eval_harness():
    # MockLLM 固定选 A(候选池里有 A)
    llm = MockLLMClient('{"regime_read":"主升","candidates":'
                        '[{"code":"A","pattern":"highest_board","reason":"龙头","confidence":0.7}],'
                        '"no_trade_reason":""}')
    agent = LLMAgentPolicy(load_seeds(SEEDS), llm)
    rep = WalkForwardEval(_src(), date(2024, 6, 26), date(2024, 6, 28), horizon=1).run(agent)
    # day0 选A→day1 A涨停=continued; day1 选A→day2 A涨停=continued; day2 选A 无次日丢弃
    assert rep.n_decisions == 3 and rep.n_candidates == 2
    assert rep.hit_rate == 1.0 and rep.mean_score == 1.0
    assert "highest_board" in rep.by_pattern
    # 走查每天系统提示都注入了 H 的纪律红线(证明 harness 真的被接上,而非仅单测)
    assert all("纪律红线" in call[0] for call in llm.calls)
    # 防幻觉:即便 agent 每天都返回 "A",A 在每天候选池里才被计入(已验证)


def test_agent_hallucination_yields_no_candidates():
    # MockLLM 选一个不存在的 code → parse 丢弃 → 全程空仓
    llm = MockLLMClient('{"candidates":[{"code":"ZZZ","pattern":"x","confidence":0.9}]}')
    agent = LLMAgentPolicy(load_seeds(SEEDS), llm)
    rep = WalkForwardEval(_src(), date(2024, 6, 26), date(2024, 6, 28), horizon=1).run(agent)
    assert rep.n_candidates == 0          # 幻觉 code 全被丢弃
    assert rep.n_decisions == 3           # 确认 walk 完整跑完(没因空候选短路)
