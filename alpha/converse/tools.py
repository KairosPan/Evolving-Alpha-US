# alpha/converse/tools.py
from __future__ import annotations
from alpha.agent.agent import LLMAgentPolicy
from alpha.state.market import MarketState
from alpha.universe.universe import CandidateUniverse
from alpha.eval.decision import DecisionPackage


from alpha.harness.metatools import MetaTools
from alpha.harness.edit_log import EditLog
from alpha.refine.apply import try_apply_op
from alpha.refine.ops import RefineOp, PASS_TOOLS


def make_gated_write_tool(harness, *, min_retire_samples: int = 5, min_promote_samples: int = 3):
    """A tool whose ONLY path to mutate H is try_apply_op (the one write-waist). Restricted to the
    M-pass whitelist for this face; the gate enforces rationale / evidence floors / red-lines."""
    def propose_memory_edit(tool: str, args: dict, rationale: str) -> dict:
        op = RefineOp(tool=tool, args=args, rationale=rationale)
        rec, reason = try_apply_op(MetaTools(harness, EditLog()), harness, op,
                                   allowed=PASS_TOOLS["M"],
                                   min_retire_samples=min_retire_samples,
                                   min_promote_samples=min_promote_samples)
        return {"status": "applied"} if rec is not None else {"status": "rejected", "reason": reason}
    schema = {"name": "propose_memory_edit",
              "description": "Propose a memory edit; applied only if it clears the gate.",
              "parameters": {"type": "object",
                             "properties": {"tool": {"type": "string"}, "args": {"type": "object"},
                                            "rationale": {"type": "string"}},
                             "required": ["tool", "args", "rationale"]}}
    return schema, propose_memory_edit


def make_decide_tool(harness, agent_llm):
    """Expose the EXISTING deterministic decider as a tool (decision a: one decide, two callers).
    Returns the typed DecisionPackage unchanged — not free text."""
    def decide(state: MarketState, universe: CandidateUniverse) -> DecisionPackage:
        return LLMAgentPolicy(harness, agent_llm).decide(state, universe)
    schema = {"name": "decide",
              "description": "Run the deterministic decider; returns a typed DecisionPackage.",
              "parameters": {"type": "object", "properties": {}, "required": []}}
    return schema, decide
