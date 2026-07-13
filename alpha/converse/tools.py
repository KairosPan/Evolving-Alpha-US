# alpha/converse/tools.py
from __future__ import annotations
from datetime import date as _Date, datetime as _DateTime
from alpha.agent.agent import LLMAgentPolicy
from alpha.state.market import MarketState
from alpha.universe.universe import CandidateUniverse
from alpha.eval.decision import DecisionPackage
from alpha.data.firewall import AsOfGuard
from alpha.data.source import GuardedSource
from alpha.universe.universe import build_universe
from alpha.state.builder import build_market_state

# The worker face has NO H-mutation tool. make_gated_write_tool (live landing) was retired
# 2026-07-09 (charter: no code path lets the worker's own edit reach the live brain without a human
# step); make_propose_edit_tool (STAGING for user approval) was retired by A7 2026-07-13 (charter
# First Founding Principle: "Kairos does not propose at all" — only a Sonia proposal or the User's
# direct edit may send to the gate). The worker keeps compute-use only (decide/read/write/shell);
# H evolves over worker TRACES via the Sonia-side proposer (alpha/refine/reflect.py → /proposals).


def make_decide_tool(harness, agent_llm):
    """Expose the EXISTING deterministic decider as a tool (decision a: one decide, two callers).
    Returns the typed DecisionPackage unchanged — not free text."""
    def decide(state: MarketState, universe: CandidateUniverse) -> DecisionPackage:
        return LLMAgentPolicy(harness, agent_llm).decide(state, universe)
    schema = {"name": "decide",
              "description": "Run the deterministic decider; returns a typed DecisionPackage.",
              "parameters": {"type": "object", "properties": {}, "required": []}}
    return schema, decide


def make_decide_for_date_tool(harness, agent_llm, source):
    """Date-driven decide tool: build the PIT-guarded universe + state for an ISO date, then delegate
    to the Phase-1A decider. Mirrors scripts/save_decisions.py's single-day perception chain. A single
    ad-hoc decide passes no history/prev_gainers (empty defaults -> follow_through/sentiment_norm None)."""
    _schema, raw_decide = make_decide_tool(harness, agent_llm)        # reuse the low-level (state, universe) decider
    def decide(date: str):
        day = _Date.fromisoformat(date)
        guarded = GuardedSource(source, AsOfGuard(day))
        universe = build_universe(guarded, day)
        state = build_market_state(universe, day,
                                   as_of=_DateTime(day.year, day.month, day.day, 16, 0))
        return raw_decide(state=state, universe=universe)
    schema = {"name": "decide",
              "description": "Decide for a trading date (PIT-guarded). args: {\"date\": \"YYYY-MM-DD\"}.",
              "parameters": {"type": "object",
                             "properties": {"date": {"type": "string", "description": "ISO trading date"}},
                             "required": ["date"]}}
    return schema, decide
