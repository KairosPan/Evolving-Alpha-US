# scripts/smoke_deepseek_agent.py
"""手动冒烟:真实 DeepSeek 跑一天选股。
Run: DEEPSEEK_API_KEY=... python scripts/smoke_deepseek_agent.py 20240627
需要:openai 已装、网络、akshare 可拉数、seeds/ 在位。"""
from __future__ import annotations

import sys
from datetime import datetime, time
from pathlib import Path

from youzi.data.source import AkshareSource
from youzi.replay.firewall import AsOfGuard
from youzi.data.source import GuardedSource
from youzi.universe.universe import build_universe
from youzi.features.builder import build_market_state
from youzi.harness.loader import load_seeds
from youzi.llm.client import DeepSeekClient
from youzi.agent.agent import LLMAgentPolicy


def main(ymd: str) -> None:
    day = datetime.strptime(ymd, "%Y%m%d").date()
    src = AkshareSource()
    guard = AsOfGuard(day)
    gs = GuardedSource(src, guard)
    state = build_market_state(day, gs, history=[], as_of=datetime.combine(day, time(15, 0)))
    universe = build_universe(gs, day)
    print(f"[{day}] 涨停候选 {len(universe.by_status('limit_up'))} 只")

    seeds = Path(__file__).resolve().parent.parent / "seeds"
    agent = LLMAgentPolicy(load_seeds(seeds), DeepSeekClient())
    pkg = agent.decide(state, universe)
    print("regime/候选:")
    print("  no_trade:", pkg.no_trade_reason or ("(有候选)" if pkg.candidates else "(空仓,LLM未给原因)"))
    for c in pkg.candidates:
        print(f"  {c.code} {c.name} 模式={c.pattern} 信心={c.confidence} 理由={c.reason}")


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "20240627")
