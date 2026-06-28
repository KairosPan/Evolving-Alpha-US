"""Assemble the activity space for a turn: a tiered tool catalog + the single-choke-point policy.
Data rungs only (R1/R2): decide/read are T0, workspace-write T1, shell T2, brain-edit T3. There is
NO live-order tool and NO code-exec-with-an-H-handle tool (modification-ladder spec §8)."""
from __future__ import annotations
from pathlib import Path
from alpha.arena.contract import CapabilityTier
from alpha.arena.environment import InProcessEnv, ToolEnvironment
from alpha.arena.policy import ActivityPolicy
from alpha.arena.tools import make_read_file_tool, make_write_file_tool, make_shell_tool
from alpha.converse.registry import ToolRegistry
from alpha.converse.tools import make_decide_for_date_tool, make_gated_write_tool


def build_arena(harness, agent_llm, source, *, workspace: Path,
                env: ToolEnvironment | None = None,
                confirm=None) -> tuple[ToolRegistry, ActivityPolicy]:
    env = env if env is not None else InProcessEnv()
    reg = ToolRegistry()
    tiers: dict[str, CapabilityTier] = {}

    decide_schema, decide_fn = make_decide_for_date_tool(harness, agent_llm, source)
    reg.register("decide", decide_schema, decide_fn)
    tiers["decide"] = CapabilityTier.T0_OBSERVE

    rs, rfn, rtier = make_read_file_tool(workspace)
    reg.register("read_file", rs, rfn)
    tiers["read_file"] = rtier

    ws, wfn, wtier = make_write_file_tool(workspace)
    reg.register("write_file", ws, wfn)
    tiers["write_file"] = wtier

    ss, sfn, stier = make_shell_tool(env)
    reg.register("shell", ss, sfn)
    tiers["shell"] = stier

    bw_schema, bw_fn = make_gated_write_tool(harness)
    reg.register("propose_memory_edit", bw_schema, bw_fn)
    tiers["propose_memory_edit"] = CapabilityTier.T3_BRAIN_EDIT

    return reg, ActivityPolicy(reg, tiers, confirm=confirm)
