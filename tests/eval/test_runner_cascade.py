"""US-3a cascade locks: once build_universe fills consecutive_up_days, the live walk surfaces
max_runner_tier / echelon / entries.cud, and the failure-signature taxonomy discriminates
chased_blowoff vs weak_laggard_nuke on genuinely-populated runner fields (was generic_nuke)."""
from datetime import date, datetime
from pathlib import Path
import pandas as pd
from alpha.data.source import FakeSource
from alpha.harness.loader import load_seeds
from alpha.llm.client import MockLLMClient
from alpha.agent.agent import LLMAgentPolicy
from alpha.eval.walk_forward import WalkForwardEval
from alpha.universe.universe import build_universe
from alpha.state.builder import build_market_state
from alpha.eval.decision import Candidate, DecisionPackage
from alpha.eval.metrics import ScoredCandidate
from alpha.eval.trajectory import TrajectoryStep, Trajectory
from alpha.refine.signatures import extract_signatures

SEEDS = Path(__file__).resolve().parents[2] / "seeds"


def _runner_source(n=8):
    """Single symbol RUN rising +15%/day -> consecutive_up_days climbs 0,1,2,...,7 over the window."""
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


def _two_runner_source(n=8):
    """RUN rises every day (top tier); LAG is flat then +10% only on the last day (a genuine laggard)."""
    cal = [date(2026, 6, d) for d in range(1, 1 + n)]
    last = cal[-1]
    run = [10.0 * (1.15 ** k) for k in range(1, 1 + n)]      # strictly rising -> cud n-1
    lag = [10.0] * (n - 1) + [11.0]                          # flat then +10% today -> cud 1
    snaps = {last: pd.DataFrame({
        "symbol": ["RUN", "LAG"], "name": ["RUN", "LAG"],
        "open": [run[-2], 10.0], "high": [run[-1], 11.0], "low": [run[-2], 10.0],
        "close": [run[-1], 11.0], "volume": [1, 1], "prev_close": [run[-2], 10.0]})}
    bars = {"RUN": pd.DataFrame({"date": cal, "open": run, "high": run, "low": run, "close": run, "volume": [1] * n}),
            "LAG": pd.DataFrame({"date": cal, "open": lag, "high": lag, "low": lag, "close": lag, "volume": [1] * n})}
    return FakeSource(calendar=cal, bars=bars, snapshots=snaps)


def test_live_walk_surfaces_runner_tier():
    src = _runner_source(8)
    agent = LLMAgentPolicy(load_seeds(SEEDS),
                           MockLLMClient('{"candidates": [{"symbol": "RUN", "pattern": "gap_and_go"}]}'))
    traj = WalkForwardEval(src, src.trading_calendar()[0], src.trading_calendar()[-1], horizon=2).walk(agent)
    tiers = [s.market.max_runner_tier for s in traj.steps]
    assert max(tiers) >= 2                                       # the live state now surfaces a runner tier
    cud = [st.entries["RUN"].consecutive_up_days for st in traj.steps if "RUN" in st.entries]
    assert cud and all(c is not None for c in cud) and max(cud) >= 2   # entries carry real cud (not None)


def test_signatures_discriminate_on_populated_runner_tier():
    src = _two_runner_source(8)
    day = src.trading_calendar()[-1]
    uni = build_universe(src, day)
    state = build_market_state(uni, day, as_of=datetime(day.year, day.month, day.day, 16, 0))
    assert state.max_runner_tier >= 2
    assert uni.get("RUN").consecutive_up_days == state.max_runner_tier   # RUN is the top runner
    assert uni.get("LAG").consecutive_up_days == 1                        # a genuine laggard
    nuke = lambda sym: ScoredCandidate(decision_date=day, symbol=sym, pattern="gap_and_go",
                                       outcome="nuked", score=-0.5, day_baseline=0.0)
    dec = DecisionPackage(date=day, candidates=[Candidate(symbol="RUN", pattern="gap_and_go"),
                                                Candidate(symbol="LAG", pattern="gap_and_go")])
    step = TrajectoryStep(date=day, market=state, decision=dec,
                          entries={"RUN": uni.get("RUN"), "LAG": uni.get("LAG")},
                          outcomes={"RUN": nuke("RUN"), "LAG": nuke("LAG")}, scored=True)
    kinds = {s.symbol: s.kind for s in extract_signatures(Trajectory(steps=[step]), load_seeds(SEEDS))}
    assert kinds == {"RUN": "chased_blowoff", "LAG": "weak_laggard_nuke"}   # both branches locked
