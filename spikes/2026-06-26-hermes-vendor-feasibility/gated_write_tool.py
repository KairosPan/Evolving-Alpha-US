# spikes/2026-06-26-hermes-vendor-feasibility/gated_write_tool.py
"""A registry tool whose ONLY way to mutate H is the existing one-write-waist try_apply_op. Proves
Strategy C's invariant survives the re-base: a Hermes-style tool call cannot bypass the gate. The
restricted whitelist (PASS_TOOLS['M']) is the literal mechanism the spec's fast self-study tier uses;
here it just proves routing + whitelist + reject-reason all work from a tool call."""
from __future__ import annotations
from alpha.harness.metatools import MetaTools
from alpha.harness.edit_log import EditLog
from alpha.refine.apply import try_apply_op
from alpha.refine.ops import RefineOp, PASS_TOOLS

def make_gated_write_tool(harness, *, min_retire_samples: int = 5, min_promote_samples: int = 3):
    def propose_memory_edit(tool: str, args: dict, rationale: str) -> dict:
        op = RefineOp(tool=tool, args=args, rationale=rationale)
        rec, reason = try_apply_op(
            MetaTools(harness, EditLog()), harness, op,
            allowed=PASS_TOOLS["M"],
            min_retire_samples=min_retire_samples,
            min_promote_samples=min_promote_samples,
        )
        return {"status": "applied"} if rec is not None else {"status": "rejected", "reason": reason}
    schema = {
        "name": "propose_memory_edit",
        "description": "Propose a memory edit; applied only if it clears the gate (try_apply_op).",
        "parameters": {"type": "object",
                       "properties": {"tool": {"type": "string"}, "args": {"type": "object"},
                                      "rationale": {"type": "string"}},
                       "required": ["tool", "args", "rationale"]},
    }
    return schema, propose_memory_edit
