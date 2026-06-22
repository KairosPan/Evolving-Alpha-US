"""Produce + persist real daily DecisionPackages from a captured PIT window into a DecisionStore, so
the web console can browse them by date (`ALPHA_WEB_DECISIONS_DIR`) instead of a single one-off file.

This mirrors the InnerLoop perception path exactly — build_universe -> build_market_state (with the
follow-through / sentiment history threaded forward) -> SizingPolicy(GuardedPolicy(LLMAgentPolicy)) —
but only the *act* half: it decides and persists, no scoring or refinement.

  # 1. capture a PIT window (market data only):
  python scripts/capture_window.py 2026-01-02 2026-01-31 snap AAPL MSFT NVDA TSLA AMD

  # 2. produce + persist a package per trading day (needs the agent LLM key):
  export ALPHA_AGENT_PROVIDER=openai_compat ALPHA_AGENT_MODEL=deepseek-chat   # + DEEPSEEK_API_KEY
  python scripts/save_decisions.py snap 2026-01-02 2026-01-31 decisions

  # 3. browse them in the console:
  ALPHA_WEB_DECISIONS_DIR=decisions python -m alpha_web
"""
from __future__ import annotations

import argparse
from datetime import date as Date, datetime as DateTime
from pathlib import Path

from alpha.agent.agent import LLMAgentPolicy
from alpha.data.calendar import trading_days_between
from alpha.data.firewall import AsOfGuard
from alpha.data.pit_store import PITStore
from alpha.data.snapshot_source import SnapshotSource
from alpha.data.source import GuardedSource
from alpha.eval.decision import DecisionPackage
from alpha.eval.decision_store import DecisionStore
from alpha.guard.screen import GuardedPolicy
from alpha.harness.loader import load_seeds
from alpha.llm.config import make_client
from alpha.sizing.policy import SizingPolicy
from alpha.state.builder import build_market_state
from alpha.universe.universe import build_universe

SEEDS_DIR = Path(__file__).resolve().parents[1] / "seeds"


def produce_decisions(source, start: Date, end: Date, *, seeds_dir: Path = SEEDS_DIR,
                      agent_llm_factory=None, screen: bool = True, size: bool = True):
    """Yield one DecisionPackage per trading day in [start, end] (act-only). `screen`/`size` mirror
    LoopConfig: GuardedPolicy is the L4 veto, SizingPolicy the L3 sizing — both default ON. The
    perception history (sentiment_raw / prior gainers) is threaded forward exactly like InnerLoop so
    the regime read sees frontside on genuine uptrends. Tests inject a MockLLM via agent_llm_factory."""
    agent_llm_factory = agent_llm_factory or (lambda: make_client("agent"))
    h = load_seeds(seeds_dir)
    policy = LLMAgentPolicy(h, agent_llm_factory())
    if screen:
        policy = GuardedPolicy(policy, source)          # L4 veto (inner)
    if size:
        policy = SizingPolicy(policy)                   # L3 sizing (outer; sizes post-veto survivors)

    history: list[float] = []                           # prior-day sentiment_raw
    prev_gainers: frozenset[str] = frozenset()
    for cursor in trading_days_between(source.trading_calendar(), start, end):
        guarded = GuardedSource(source, AsOfGuard(cursor))
        universe = build_universe(guarded, cursor)
        state = build_market_state(universe, cursor,
                                   as_of=DateTime(cursor.year, cursor.month, cursor.day, 16, 0),
                                   history=history, prev_gainers=prev_gainers)
        history.append(state.sentiment_raw)
        prev_gainers = frozenset(s.symbol for s in universe.by_status("gainer"))
        yield policy.decide(state, universe)


def save_decisions(source, start: Date, end: Date, store: DecisionStore, **kw) -> int:
    """Produce + persist; returns the number of daily packages written."""
    n = 0
    for pkg in produce_decisions(source, start, end, **kw):
        store.put(pkg)
        n += 1
    return n


def main() -> None:
    ap = argparse.ArgumentParser(description="Produce + persist daily DecisionPackages for the console.")
    ap.add_argument("pit_root", help="PIT store root built by scripts/capture_window.py")
    ap.add_argument("start", type=Date.fromisoformat)
    ap.add_argument("end", type=Date.fromisoformat)
    ap.add_argument("out_dir", help="DecisionStore directory (point ALPHA_WEB_DECISIONS_DIR here)")
    ap.add_argument("--no-screen", action="store_true", help="skip the L4 guard veto")
    ap.add_argument("--no-size", action="store_true", help="emit unsized decisions (skip L3 sizing)")
    args = ap.parse_args()

    source = SnapshotSource(PITStore(Path(args.pit_root)))
    store = DecisionStore(args.out_dir)
    n = save_decisions(source, args.start, args.end, store,
                       screen=not args.no_screen, size=not args.no_size)
    print(f"saved {n} daily decisions {args.start}..{args.end} -> {args.out_dir}")


if __name__ == "__main__":
    main()
