# spikes/2026-06-26-hermes-vendor-feasibility/decide_tool.py
"""Expose the EXISTING deterministic decider as a registry tool. The whole point of decision (a):
one implementation of `decide`, two callers (the offline InnerLoop and this conversational tool).
The tool returns the strongly-typed DecisionPackage unchanged — NOT free text (decision b)."""
from __future__ import annotations
from alpha.agent.agent import LLMAgentPolicy
from alpha.state.market import MarketState
from alpha.universe.universe import CandidateUniverse
from alpha.eval.decision import DecisionPackage

def make_decide_tool(harness, agent_llm):
    def decide(state: MarketState, universe: CandidateUniverse) -> DecisionPackage:
        return LLMAgentPolicy(harness, agent_llm).decide(state, universe)
    schema = {
        "name": "decide",
        "description": "Run the deterministic decider; returns a typed DecisionPackage.",
        "parameters": {"type": "object", "properties": {}, "required": []},
    }
    return schema, decide
