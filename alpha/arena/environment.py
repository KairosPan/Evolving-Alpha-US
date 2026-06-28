"""The E-face execution seam. One Protocol, swappable backends:
  - InProcessEnv  : test/offline default; refuses to execute (deterministic).
  - LocalEnv      : host subprocess, workspace-scoped + hardline blocklist + network deny (Task 3).
  - SandboxedEnv  : DEFERRED (kernel sandbox; commercial). See modification-ladder spec §5-§6.
"""
from __future__ import annotations
from typing import Protocol, runtime_checkable
from alpha.arena.contract import ExecResult


@runtime_checkable
class ToolEnvironment(Protocol):
    def run(self, argv: list[str], *, timeout: float = 30.0, net: bool = False) -> ExecResult: ...


class InProcessEnv:
    """The safe default: no external process. Execution tools degrade to a clear refusal so the
    offline suite never needs a real shell/sandbox."""
    def run(self, argv: list[str], *, timeout: float = 30.0, net: bool = False) -> ExecResult:
        return ExecResult(ok=False, stdout="", stderr="execution disabled (InProcessEnv)", exit_code=126)
