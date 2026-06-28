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


# --- LocalEnv: host subprocess, workspace-scoped ---
import re
import subprocess
from pathlib import Path

# Hardline command patterns: unconditionally refused (ported from Hermes tools/approval.py, the
# accident-prevention floor). NOT a security boundary — defense-in-depth for a trusted operator.
_HARDLINE = [
    re.compile(r"\brm\s+(-[a-z]*r[a-z]*\s+|-[a-z]*f[a-z]*\s+).*(/|~)(\s|$)"),
    re.compile(r"\bmkfs\b"),
    re.compile(r"\bdd\b.*\bof=/dev/"),
    re.compile(r":\(\)\s*\{\s*:\s*\|\s*:\s*&\s*\}\s*;\s*:"),   # fork bomb
    re.compile(r"\b(reboot|shutdown|halt|poweroff)\b"),
    re.compile(r">\s*/dev/sd[a-z]"),
]


def _hardline_reason(joined: str) -> str | None:
    for pat in _HARDLINE:
        if pat.search(joined):
            return f"blocked by hardline rule: {pat.pattern}"
    return None


class LocalEnv:
    """Host subprocess execution, scoped to *workspace*. Provisional, operator-trust confinement:
    cwd=workspace + a hardline command blocklist + refusal of absolute path operands that escape the
    workspace + network NOT widened by default. This path-guard is TOCTOU-bypassable and is NOT a
    kernel boundary (see modification-ladder spec §10 risk 1); SandboxedEnv replaces it for untrusted
    surfaces. Brain files MUST live outside *workspace* so even a shell here cannot reach them."""

    def __init__(self, workspace: Path):
        self.workspace = Path(workspace).resolve()

    def is_blocked(self, argv: list[str]) -> str | None:
        joined = " ".join(argv)
        hard = _hardline_reason(joined)
        if hard:
            return hard
        for tok in argv:
            if tok.startswith("/") or tok.startswith("~"):
                p = Path(tok).expanduser()
                try:
                    p.resolve().relative_to(self.workspace)
                except ValueError:
                    return f"path operand outside workspace: {tok}"
        return None

    def run(self, argv: list[str], *, timeout: float = 30.0, net: bool = False) -> ExecResult:
        reason = self.is_blocked(argv)
        if reason is not None:
            return ExecResult(ok=False, stderr=reason, exit_code=126)
        try:
            proc = subprocess.run(
                argv, cwd=str(self.workspace), capture_output=True, text=True, timeout=timeout)
        except subprocess.TimeoutExpired:
            return ExecResult(ok=False, stderr=f"timeout after {timeout}s", exit_code=124)
        except (FileNotFoundError, OSError) as e:
            return ExecResult(ok=False, stderr=f"exec error: {e}", exit_code=127)
        return ExecResult(ok=(proc.returncode == 0), stdout=proc.stdout,
                          stderr=proc.stderr, exit_code=proc.returncode)
