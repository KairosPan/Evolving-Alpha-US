"""The ActivitySpace contract: the value objects naming the four faces (O/A/E/F).

CapabilityTier is the A-face spine; ExecResult is the E-face environment result; Feedback is the
F-face channel returned to the agent each turn. Kept in the lowest arena module so policy.py,
environment.py and tools.py all import from here."""
from __future__ import annotations
from enum import IntEnum
from pydantic import BaseModel, ConfigDict


class CapabilityTier(IntEnum):
    """How autonomous a tool is. The policy fail-closes on any tool with no tier (see policy.py)."""
    T0_OBSERVE = 0          # read-only / analysis: free, autonomous
    T1_WORKSPACE_WRITE = 1  # write into the project workspace: autonomous, logged
    T2_EXECUTE = 2          # shell / code / network-read: via ToolEnvironment confinement
    T3_BRAIN_EDIT = 3       # propose a RefineOp: only via the gate (try_apply_op)
    T4_CONFIRM = 4          # outward / irreversible: never autonomous (human-confirm)


class ExecResult(BaseModel):
    model_config = ConfigDict(frozen=True)
    ok: bool
    stdout: str = ""
    stderr: str = ""
    exit_code: int = 0


class Feedback(BaseModel):
    model_config = ConfigDict(frozen=True)
    kind: str           # "tool" | "gate" | "confirm" | "verifier"
    detail: str = ""
