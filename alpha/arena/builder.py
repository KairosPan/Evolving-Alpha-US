"""Assemble the activity space for a turn: a tiered tool catalog + the single-choke-point policy.
Reuses build_converse_registry for decide + the brain-edit tool (one source of write-mode logic),
then adds the computer-use tools when a workspace is given. Data rungs only (R1/R2)."""
from __future__ import annotations
from pathlib import Path
from alpha.arena.contract import CapabilityTier
from alpha.arena.environment import InProcessEnv, ToolEnvironment
from alpha.arena.policy import ActivityPolicy
from alpha.arena.tools import make_read_file_tool, make_write_file_tool, make_shell_tool
from alpha.converse.agent import build_converse_registry


def build_arena(harness, agent_llm, source, *, workspace: Path | None = None,
                env: ToolEnvironment | None = None, write_mode: str = "apply",
                read_only: bool = False, conflict_queue=None, provenance=None,
                confirm=None) -> tuple["ToolRegistry", ActivityPolicy]:
    reg = build_converse_registry(harness, agent_llm, source, read_only=read_only,
                                  write_mode=write_mode, conflict_queue=conflict_queue,
                                  provenance=provenance)
    tiers: dict[str, CapabilityTier] = {"decide": CapabilityTier.T0_OBSERVE}
    if not read_only and write_mode in {"apply", "stage"}:
        tiers["propose_memory_edit"] = CapabilityTier.T3_BRAIN_EDIT
    if workspace is not None:
        rs, rfn, rtier = make_read_file_tool(workspace)
        reg.register("read_file", rs, rfn); tiers["read_file"] = rtier
        if not read_only:
            ws, wfn, wtier = make_write_file_tool(workspace)
            reg.register("write_file", ws, wfn); tiers["write_file"] = wtier
            ss, sfn, stier = make_shell_tool(env if env is not None else InProcessEnv())
            reg.register("shell", ss, sfn); tiers["shell"] = stier
    # LIVE-WIRING NOTE: callers MUST drive the loop via run_conversation(dispatch=policy.dispatch).
    # Passing the bare registry to run_conversation skips the tier/membrane enforcement (the choke point).
    return reg, ActivityPolicy(reg, tiers, confirm=confirm)
