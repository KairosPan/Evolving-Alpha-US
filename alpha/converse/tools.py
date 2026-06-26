# alpha/converse/tools.py
from __future__ import annotations
import copy as _copy
from datetime import date as _Date, datetime as _DateTime
from alpha.agent.agent import LLMAgentPolicy
from alpha.state.market import MarketState
from alpha.universe.universe import CandidateUniverse
from alpha.eval.decision import DecisionPackage
from alpha.data.firewall import AsOfGuard
from alpha.data.source import GuardedSource
from alpha.universe.universe import build_universe
from alpha.state.builder import build_market_state

from alpha.harness.metatools import MetaTools
from alpha.harness.edit_log import EditLog, EditProvenance
from alpha.refine.apply import try_apply_op
from alpha.refine.ops import RefineOp, PASS_TOOLS
from alpha.meta.models import new_edit_id


def make_gated_write_tool(harness, *, min_retire_samples: int = 5, min_promote_samples: int = 3):
    """A tool whose ONLY path to mutate H is try_apply_op (the one write-waist). Restricted to the
    M-pass whitelist for this face; the gate enforces rationale / evidence floors / red-lines."""
    def propose_memory_edit(tool: str, args: dict, rationale: str) -> dict:
        op = RefineOp(tool=tool, args=args, rationale=rationale)
        rec, reason = try_apply_op(MetaTools(harness, EditLog()), harness, op,
                                   allowed=PASS_TOOLS["M"],
                                   min_retire_samples=min_retire_samples,
                                   min_promote_samples=min_promote_samples,
                                   provenance=EditProvenance(path="teaching", proposer="hermes"))
        return {"status": "applied"} if rec is not None else {"status": "rejected", "reason": reason}
    schema = {"name": "propose_memory_edit",
              "description": "Propose a memory edit; applied only if it clears the gate.",
              "parameters": {"type": "object",
                             "properties": {"tool": {"type": "string"}, "args": {"type": "object"},
                                            "rationale": {"type": "string"}},
                             "required": ["tool", "args", "rationale"]}}
    return schema, propose_memory_edit


def make_propose_edit_tool(harness, *, min_retire_samples: int = 5, min_promote_samples: int = 3):
    """Preview/approve variant of the write tool: DRY-RUN the op on a deepcopy via the gate, STAGE the
    result for the user's approval. Never mutates the live harness (no live write during conversation)."""
    def propose_memory_edit(tool: str, args: dict, rationale: str) -> dict:
        op = RefineOp(tool=tool, args=args, rationale=rationale)
        scratch = _copy.deepcopy(harness)
        rec, reason = try_apply_op(MetaTools(scratch, EditLog()), scratch, op,
                                   allowed=PASS_TOOLS["M"],
                                   min_retire_samples=min_retire_samples,
                                   min_promote_samples=min_promote_samples,
                                   provenance=EditProvenance(path="teaching", proposer="hermes"))
        return {"staged": True, "edit_id": new_edit_id(), "tool": tool,
                "op": {"tool": tool, "args": dict(args), "rationale": rationale},
                "summary": rec.summary if rec is not None else "",
                "valid": rec is not None, "reason": reason,
                "preview": rec.model_dump() if rec is not None else {}}
    schema = {"name": "propose_memory_edit",
              "description": "Propose a memory edit for the user's approval (staged, not applied).",
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
