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
import json
import os
import tempfile
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
from alpha.harness.snapshot import harness_digest
from alpha.llm.config import make_client
from alpha.memory.store import EpisodeStore
from alpha.redact import collect_secrets, redact
from alpha.settings import Settings
from alpha.sizing.policy import SizingPolicy
from alpha.state.builder import build_market_state
from alpha.universe.universe import build_universe

SEEDS_DIR = Path(__file__).resolve().parents[1] / "seeds"


def produce_decisions(source, start: Date, end: Date, *, seeds_dir: Path = SEEDS_DIR,
                      agent_llm_factory=None, screen: bool = True, size: bool = True,
                      episode_store=None, collect=None):
    """Yield one DecisionPackage per trading day in [start, end] (act-only). `screen`/`size` mirror
    LoopConfig: GuardedPolicy is the L4 veto, SizingPolicy the L3 sizing — both default ON. The
    perception history (sentiment_raw / prior gainers) is threaded forward exactly like InnerLoop so
    the regime read sees frontside on genuine uptrends. Tests inject a MockLLM via agent_llm_factory.
    episode_store: optional read-only brain -> §6 recall (LLMAgentPolicy) + taboo (GuardedPolicy); the
    act path never writes episodes (no scoring/maturity here). Default None -> byte-identical (no §6).
    collect: D3 prompt-audit hook, threaded through the policy stack to build_system_prompt (observe-
    only; default None -> byte-identical). Records arrive per-day during each yield's decide().
    Every yielded package carries D4's h_digest = harness_digest(h) (the fixed H this act-only run
    loaded) — additive, eval/loop never read it."""
    agent_llm_factory = agent_llm_factory or (lambda: make_client("agent"))
    h = load_seeds(seeds_dir)
    h_digest = harness_digest(h)
    policy = LLMAgentPolicy(h, agent_llm_factory(), episode_store=episode_store)   # §6 recall (read-only)
    if screen:
        policy = GuardedPolicy(policy, source, episode_store=episode_store)   # L4 veto (+ §6 taboo)
    if size:
        policy = SizingPolicy(policy)                   # L3 sizing (outer; sizes post-veto survivors)
    decide_kw = {} if collect is None else {"collect": collect}

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
        pkg = policy.decide(state, universe, **decide_kw)
        yield pkg.model_copy(update={"h_digest": h_digest})


def _write_prompt_sidecar(dirpath: Path, day: Date, records: list[dict]) -> Path:
    """Write the D3 prompt-audit sidecar `<dir>/<date>.prompt.json` atomically (DecisionStore.put's
    temp-in-dir + os.replace idiom). `assembled` is lifted out of the kind=='assembled' record; the
    remaining offered/dropped records stay in `records` (the shape scripts/render_prompt.py reads)."""
    assembled = next((r.get("text", "") for r in records if r.get("kind") == "assembled"), "")
    payload = {"date": day.isoformat(),
               "records": [r for r in records if r.get("kind") != "assembled"],
               "assembled": assembled}
    payload = redact(payload, collect_secrets())   # new A1 persistence surface -> same redaction waist

    p = dirpath / f"{day.isoformat()}.prompt.json"
    fd, tmp = tempfile.mkstemp(dir=dirpath, suffix=".prompt.json.tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(payload, f)
        os.replace(tmp, p)
    except BaseException:
        if os.path.exists(tmp):
            os.unlink(tmp)
        raise
    return p


def save_decisions(source, start: Date, end: Date, store: DecisionStore, **kw) -> int:
    """Produce + persist; returns the number of daily packages written. Beside each day's decision
    file it writes the D3 prompt-audit sidecar `<date>.prompt.json` (what the assembled system prompt
    was, plus every skill/lesson/episode offered or dropped and why)."""
    records: list[dict] = []                             # this day's audit records (cleared per day)
    n = 0
    for pkg in produce_decisions(source, start, end, collect=records.append, **kw):
        p = store.put(pkg)
        _write_prompt_sidecar(p.parent, pkg.date, records)
        records.clear()
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
    ap.add_argument("--brain", metavar="PATH", help="read-only EpisodeStore (brain.db) for §6 recall+taboo; "
                    "defaults to $ALPHA_EPISODES_DB if set")
    args = ap.parse_args()

    s = Settings.from_env()
    source = SnapshotSource(PITStore(Path(args.pit_root)))
    store = DecisionStore(args.out_dir)
    brain = args.brain or s.episodes_db
    episode_store = EpisodeStore.open(brain, create_if_missing=False) if brain else None
    n = save_decisions(source, args.start, args.end, store,
                       screen=not args.no_screen, size=not args.no_size, episode_store=episode_store)
    print(f"saved {n} daily decisions {args.start}..{args.end} -> {args.out_dir}")


if __name__ == "__main__":
    main()
