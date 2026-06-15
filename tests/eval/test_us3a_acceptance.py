"""US-3a acceptance: the runner-tier cascade renders end-to-end on a seeded-harness walk — a live
multi-day runner surfaces a MarketState tier, its universe snapshot carries the tier, and the agent
prompt the policy builds shows a real up_days (not '?'). This is the headline US-3a guarantee:
forward-plumbed runner machinery is now live on the walk path, driven by build_universe."""
from datetime import date
from pathlib import Path
import pandas as pd
from alpha.data.source import FakeSource
from alpha.harness.loader import load_seeds
from alpha.llm.client import MockLLMClient
from alpha.agent.agent import LLMAgentPolicy
from alpha.eval.walk_forward import WalkForwardEval
from alpha.universe.universe import build_universe
from alpha.agent.prompt import build_user_prompt

SEEDS = Path(__file__).resolve().parents[2] / "seeds"


def _runner_source(n=8):
    cal = [date(2026, 6, d) for d in range(1, 1 + n)]
    snaps, px = {}, 10.0
    closes = []
    for d in cal:
        prev = px; px = px * 1.15; closes.append(px)
        snaps[d] = pd.DataFrame({"symbol": ["RUN"], "name": ["RUN"], "open": [prev], "high": [px],
                                 "low": [prev], "close": [px], "volume": [1], "prev_close": [prev]})
    bars = {"RUN": pd.DataFrame({"date": cal, "open": [10.0] + closes[:-1], "high": closes,
                                 "low": [10.0] + closes[:-1], "close": closes, "volume": [1] * n})}
    return FakeSource(calendar=cal, bars=bars, snapshots=snaps)


def test_runner_tier_cascade_renders_end_to_end():
    src = _runner_source(8)
    agent = LLMAgentPolicy(load_seeds(SEEDS),
                           MockLLMClient('{"candidates": [{"symbol": "RUN", "pattern": "gap_and_go"}]}'))
    traj = WalkForwardEval(src, src.trading_calendar()[0], src.trading_calendar()[-1], horizon=2).walk(agent)
    # pick a step where the runner tier has surfaced (>=2 trailing up-days; RUN's cud climbs toward 7)
    hot = [s for s in traj.steps if s.market.max_runner_tier >= 2 and "RUN" in s.entries]
    assert hot, "expected at least one step where the multi-day runner surfaced a tier"
    step = hot[0]
    assert step.entries["RUN"].consecutive_up_days >= 2          # universe snapshot carries the tier
    text = build_user_prompt(step.market, build_universe(src, step.date))
    assert "up_days=?" not in text and f"max_runner_tier={step.market.max_runner_tier}" in text
