# alpha/converse/tools.py
from __future__ import annotations
from alpha.agent.agent import LLMAgentPolicy
from alpha.state.market import MarketState
from alpha.universe.universe import CandidateUniverse
from alpha.eval.decision import DecisionPackage


def make_decide_tool(harness, agent_llm):
    """Expose the EXISTING deterministic decider as a tool (decision a: one decide, two callers).
    Returns the typed DecisionPackage unchanged — not free text."""
    def decide(state: MarketState, universe: CandidateUniverse) -> DecisionPackage:
        return LLMAgentPolicy(harness, agent_llm).decide(state, universe)
    schema = {"name": "decide",
              "description": "Run the deterministic decider; returns a typed DecisionPackage.",
              "parameters": {"type": "object", "properties": {}, "required": []}}
    return schema, decide
