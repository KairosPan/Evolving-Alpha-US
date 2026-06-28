# Activity Space P-A — Arena Skeleton Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Stand up the receiving agent's inner-loop activity space (the NOW/Local phase) — a new `alpha/arena/` package giving the conversational agent a tiered, membrane-guarded tool catalog with a `ToolEnvironment` execution seam — and close the two live-face build gaps + thread PIT-gated recall into the conversational prompt.

**Architecture:** `alpha/arena/` sits *above* `converse` (depends downward on `converse`/`refine`/`agent`/`harness`; nothing lower imports it). One enforcement point — `ActivityPolicy.dispatch(name, args)` — fail-closes on any untiered tool (the no-bypass guarantee) and blocks autonomous T4; T2 execution confinement lives in `LocalEnv`, T3 brain-edits in the existing gate (`try_apply_op`). `run_conversation` gains one optional backward-compatible `dispatch` callable so `arena` injects its policy without `converse` importing `arena`. Data rungs only (R1/R2): no agent-authored-code-with-an-H-handle tool exists.

**Tech Stack:** Python 3.13, pydantic v2 (frozen value objects), stdlib `subprocess`/`shlex`/`pathlib`, pytest. Fully offline (`InProcessEnv` is the test backend; `LocalEnv` tests run harmless commands in a temp workspace with network forced off).

## Global Constraints

- **All English** — code, comments, docs (CLAUDE.md §7).
- **Layer spine one-directional** (CLAUDE.md §2): `alpha/arena/` may import `converse`/`refine`/`agent`/`harness`/`memory`; **none of those may import `alpha/arena/`**. Do not introduce an import cycle.
- **One write-waist** (CLAUDE.md §5.2): the only path that mutates `H` is `alpha/refine/apply.py::try_apply_op`. Arena tools NEVER touch `h.skills`/`h.memory`/`h.doctrine` directly.
- **Single choke-point invariant** (spec §4): every tool dispatch flows through `ActivityPolicy.dispatch`; an untiered tool is **fail-closed** (not callable). A test asserts this.
- **Data rungs only (R1/R2)** in this phase (modification-ladder spec §8): no shell/code tool may import the harness or write the brain dir; brain files live OUTSIDE the workspace and are path-guarded out.
- **PIT firewall** (CLAUDE.md §5.1): recall masks `learned_asof <= asof`; never weaken it.
- **Frozen pydantic v2** for value objects.
- Run the suite with `python -m pytest tests -q` (NOT `pytest -q .` — the vendored `reference/cn/tests/conftest.py` collides on the `tests.conftest` module name). Keep the existing 704 tests green.

**Spec:** `docs/superpowers/specs/2026-06-27-activity-space-arena-design.md` (P-A) + `docs/superpowers/specs/2026-06-27-modification-ladder-and-body-axis-design.md` (§8 NOW).

---

## File Structure

- `alpha/arena/__init__.py` — package marker (empty).
- `alpha/arena/contract.py` — `CapabilityTier` (IntEnum), `ExecResult` (frozen), `Feedback` (frozen). The O/A/E/F value objects.
- `alpha/arena/environment.py` — `ToolEnvironment` Protocol, `InProcessEnv`, `LocalEnv`, the hardline command blocklist.
- `alpha/arena/policy.py` — `ActivityPolicy` (the single dispatch choke point + per-tier enforcement).
- `alpha/arena/tools.py` — computer-use tool factories (file-read/file-write/shell) bound to a `ToolEnvironment`, each carrying its tier.
- `alpha/arena/builder.py` — `build_arena(...)` → `(ToolRegistry, ActivityPolicy)`: registers decide(T0)/workspace tools(T1)/exec tools(T2)/brain-edit(T3) and records tiers.
- `alpha/converse/loop.py` — MODIFY: `run_conversation` gains optional `dispatch` callable (backward compatible).
- `alpha/converse/tools.py` — MODIFY: brain-edit tool accepts a `conflict_queue` + real provenance (build gap 1).
- `alpha/converse/session.py` — MODIFY: enforce `StagedEdit.status` on apply (build gap 2).
- `alpha/converse/agent.py` — MODIFY: `build_system_prompt` threads PIT-gated recalled lessons (build gap 3 / O-face).
- Tests mirror under `tests/arena/` and `tests/converse/`.

Build order: Task 1→7 stand up the arena package and wire it; Task 8→10 close the build gaps + recall. Tasks 8–10 are independent of 1–7 and may be done in either order, but all are part of the P-A done-criteria.

---

### Task 1: Contract value objects (`CapabilityTier`, `ExecResult`, `Feedback`)

**Files:**
- Create: `alpha/arena/__init__.py`
- Create: `alpha/arena/contract.py`
- Test: `tests/arena/__init__.py`, `tests/arena/test_contract.py`

**Interfaces:**
- Produces: `CapabilityTier` IntEnum with members `T0_OBSERVE=0, T1_WORKSPACE_WRITE=1, T2_EXECUTE=2, T3_BRAIN_EDIT=3, T4_CONFIRM=4`; `ExecResult(ok: bool, stdout: str, stderr: str, exit_code: int)` frozen; `Feedback(kind: str, detail: str)` frozen.

- [ ] **Step 1: Create the package markers**

Create `alpha/arena/__init__.py` (empty file) and `tests/arena/__init__.py` (empty file).

- [ ] **Step 2: Write the failing test**

```python
# tests/arena/test_contract.py
from alpha.arena.contract import CapabilityTier, ExecResult, Feedback


def test_capability_tiers_ordered():
    assert CapabilityTier.T0_OBSERVE < CapabilityTier.T3_BRAIN_EDIT < CapabilityTier.T4_CONFIRM
    assert {t.name for t in CapabilityTier} == {
        "T0_OBSERVE", "T1_WORKSPACE_WRITE", "T2_EXECUTE", "T3_BRAIN_EDIT", "T4_CONFIRM"}


def test_exec_result_is_frozen():
    import pytest
    r = ExecResult(ok=True, stdout="hi", stderr="", exit_code=0)
    assert r.ok and r.stdout == "hi"
    with pytest.raises(Exception):     # frozen models reject post-construction mutation
        r.ok = False


def test_feedback_round_trips():
    f = Feedback(kind="gate", detail="applied")
    assert f.kind == "gate" and f.detail == "applied"
```

- [ ] **Step 3: Run test to verify it fails**

Run: `python -m pytest tests/arena/test_contract.py -q`
Expected: FAIL with `ModuleNotFoundError: alpha.arena.contract`.

- [ ] **Step 4: Write minimal implementation**

```python
# alpha/arena/contract.py
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
```

- [ ] **Step 5: Run test to verify it passes**

Run: `python -m pytest tests/arena/test_contract.py -q`
Expected: PASS (3 tests).

- [ ] **Step 6: Commit**

```bash
git add alpha/arena/__init__.py alpha/arena/contract.py tests/arena/__init__.py tests/arena/test_contract.py
git commit -m "feat(arena): ActivitySpace contract value objects (CapabilityTier/ExecResult/Feedback)"
```

---

### Task 2: `ToolEnvironment` Protocol + `InProcessEnv`

**Files:**
- Create: `alpha/arena/environment.py`
- Test: `tests/arena/test_environment_inprocess.py`

**Interfaces:**
- Consumes: `ExecResult` (Task 1).
- Produces: `ToolEnvironment` Protocol with `run(self, argv: list[str], *, timeout: float = 30.0, net: bool = False) -> ExecResult`; `InProcessEnv()` — a deterministic no-subprocess backend that refuses to execute (returns `ExecResult(ok=False, ...)`), used as the safe default in tests.

- [ ] **Step 1: Write the failing test**

```python
# tests/arena/test_environment_inprocess.py
from alpha.arena.contract import ExecResult
from alpha.arena.environment import InProcessEnv, ToolEnvironment


def test_inprocess_is_a_tool_environment():
    env = InProcessEnv()
    assert isinstance(env, ToolEnvironment)


def test_inprocess_refuses_to_execute():
    env = InProcessEnv()
    r = env.run(["echo", "hi"])
    assert isinstance(r, ExecResult)
    assert r.ok is False
    assert "disabled" in r.stderr.lower()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/arena/test_environment_inprocess.py -q`
Expected: FAIL with `ImportError: cannot import name 'InProcessEnv'`.

- [ ] **Step 3: Write minimal implementation**

```python
# alpha/arena/environment.py
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
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/arena/test_environment_inprocess.py -q`
Expected: PASS (2 tests).

- [ ] **Step 5: Commit**

```bash
git add alpha/arena/environment.py tests/arena/test_environment_inprocess.py
git commit -m "feat(arena): ToolEnvironment seam + InProcessEnv (offline default)"
```

---

### Task 3: `LocalEnv` — host subprocess, workspace-scoped, blocklist, network-deny

**Files:**
- Modify: `alpha/arena/environment.py`
- Test: `tests/arena/test_environment_local.py`

**Interfaces:**
- Consumes: `ExecResult` (Task 1), `ToolEnvironment` (Task 2).
- Produces: `LocalEnv(workspace: Path)` with the same `run(argv, *, timeout, net)` signature; `is_blocked(argv) -> str | None` (returns a reason if the hardline blocklist trips); the env runs with `cwd=workspace`, refuses argv whose resolved path operands escape `workspace`, and (when `net=False`, the default) does not widen network — the blocklist + cwd are the Local-phase confinement (NOT a kernel boundary; documented as provisional).

- [ ] **Step 1: Write the failing test**

```python
# tests/arena/test_environment_local.py
from pathlib import Path
from alpha.arena.environment import LocalEnv


def test_local_runs_harmless_command(tmp_path: Path):
    env = LocalEnv(workspace=tmp_path)
    r = env.run(["python", "-c", "print('hello')"])
    assert r.ok and "hello" in r.stdout and r.exit_code == 0


def test_local_blocks_hardline_command(tmp_path: Path):
    env = LocalEnv(workspace=tmp_path)
    r = env.run(["rm", "-rf", "/"])
    assert r.ok is False
    assert "blocked" in r.stderr.lower()


def test_local_blocks_path_escape_above_workspace(tmp_path: Path):
    env = LocalEnv(workspace=tmp_path)
    # an absolute path operand outside the workspace is refused before exec
    r = env.run(["cat", "/etc/passwd"])
    assert r.ok is False
    assert "outside workspace" in r.stderr.lower()


def test_local_blocks_relative_parent_traversal(tmp_path: Path):
    env = LocalEnv(workspace=tmp_path)
    # a RELATIVE ../.. escape must also be refused (not just absolute paths)
    assert env.is_blocked(["cat", "../../etc/passwd"]) is not None
    r = env.run(["cat", "../../etc/passwd"])
    assert r.ok is False and "outside workspace" in r.stderr.lower()


def test_local_allows_path_inside_workspace(tmp_path: Path):
    # the allow-branch: an absolute path INSIDE the workspace must NOT be blocked
    # (guards against an inverted relative_to check that would refuse all path operands)
    (tmp_path / "notes.txt").write_text("inside")
    env = LocalEnv(workspace=tmp_path)
    assert env.is_blocked(["cat", str(tmp_path / "notes.txt")]) is None
    r = env.run(["cat", str(tmp_path / "notes.txt")])
    assert r.ok is True and "inside" in r.stdout


def test_local_times_out(tmp_path: Path):
    env = LocalEnv(workspace=tmp_path)
    r = env.run(["python", "-c", "import time; time.sleep(5)"], timeout=0.3)
    assert r.ok is False
    assert "timeout" in r.stderr.lower()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/arena/test_environment_local.py -q`
Expected: FAIL with `ImportError: cannot import name 'LocalEnv'`.

- [ ] **Step 3: Write minimal implementation (append to `environment.py`)**

```python
# --- append to alpha/arena/environment.py ---
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
            # Treat a token as a path operand if it is absolute, home-relative, or contains a
            # separator / parent ref — then resolve it AGAINST the workspace and refuse escapes
            # (catches both /etc/passwd AND ../../etc/passwd). Accident-prevention only: a path
            # embedded inside a -c string is NOT parsed — that is SandboxedEnv's job, not this
            # provisional, non-kernel guard.
            looks_like_path = (tok.startswith("/") or tok.startswith("~")
                               or "/" in tok or tok == "..")
            if not looks_like_path:
                continue
            base = Path(tok).expanduser()
            resolved = base if base.is_absolute() else (self.workspace / base)
            try:
                resolved.resolve().relative_to(self.workspace)
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
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/arena/test_environment_local.py -q`
Expected: PASS (4 tests).

- [ ] **Step 5: Commit**

```bash
git add alpha/arena/environment.py tests/arena/test_environment_local.py
git commit -m "feat(arena): LocalEnv — workspace-scoped subprocess + hardline blocklist + path-guard"
```

---

### Task 4: `ActivityPolicy` — the single dispatch choke point

**Files:**
- Create: `alpha/arena/policy.py`
- Test: `tests/arena/test_policy.py`

**Interfaces:**
- Consumes: `CapabilityTier` (Task 1), `ToolRegistry` from `alpha/converse/registry.py`.
- Produces: `ActivityPolicy(registry, tiers: dict[str, CapabilityTier], *, confirm=None)`; `.dispatch(name: str, args: dict) -> Any` — fail-closes (returns `{"error": ...}`) on any name with no tier; blocks autonomous T4 unless `confirm(name, args)` returns True; otherwise calls `registry.call(name, **args)`. `confirm` defaults to `None` (≡ always-deny T4 in the autonomous loop).

- [ ] **Step 1: Write the failing test**

```python
# tests/arena/test_policy.py
from alpha.arena.contract import CapabilityTier
from alpha.arena.policy import ActivityPolicy
from alpha.converse.registry import ToolRegistry


def _registry():
    reg = ToolRegistry()
    reg.register("look", {"name": "look"}, lambda: {"saw": "ok"})
    reg.register("send", {"name": "send"}, lambda to: {"sent": to})
    return reg


def test_untiered_tool_is_fail_closed():
    reg = _registry()
    pol = ActivityPolicy(reg, tiers={"look": CapabilityTier.T0_OBSERVE})   # "send" has NO tier
    assert pol.dispatch("look", {}) == {"saw": "ok"}
    out = pol.dispatch("send", {"to": "x"})
    assert "error" in out and "tier" in out["error"].lower()


def test_t4_blocked_without_confirmation():
    reg = ToolRegistry()
    ran: list[str] = []
    reg.register("send", {"name": "send"}, lambda to: (ran.append(to), {"sent": to})[1])
    pol = ActivityPolicy(reg, tiers={"send": CapabilityTier.T4_CONFIRM})
    out = pol.dispatch("send", {"to": "x"})
    assert out.get("needs_confirmation") is True
    assert ran == []   # the fn must NOT have run without confirmation


def test_t4_runs_when_confirmed():
    reg = _registry()
    pol = ActivityPolicy(reg, tiers={"send": CapabilityTier.T4_CONFIRM},
                         confirm=lambda name, args: True)
    assert pol.dispatch("send", {"to": "x"}) == {"sent": "x"}
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/arena/test_policy.py -q`
Expected: FAIL with `ModuleNotFoundError: alpha.arena.policy`.

- [ ] **Step 3: Write minimal implementation**

```python
# alpha/arena/policy.py
"""The single dispatch choke point (spec §4). EVERY tool call flows through ActivityPolicy.dispatch:
an untiered tool is fail-closed (not callable), and a T4 tool never runs autonomously. T2 execution
confinement lives in LocalEnv; T3 brain-edits in the gate (try_apply_op) inside the tool itself —
the policy's job is the tier gate + the no-bypass guarantee."""
from __future__ import annotations
from typing import Any, Callable
from alpha.arena.contract import CapabilityTier
from alpha.converse.registry import ToolRegistry


class ActivityPolicy:
    def __init__(self, registry: ToolRegistry, tiers: dict[str, CapabilityTier],
                 *, confirm: Callable[[str, dict], bool] | None = None):
        self.registry = registry
        self.tiers = dict(tiers)
        self._confirm = confirm

    def dispatch(self, name: str, args: dict) -> Any:
        if name not in self.tiers:
            return {"error": f"tool not permitted (no tier registered): {name}"}
        tier = self.tiers[name]
        if tier == CapabilityTier.T4_CONFIRM:
            ok = bool(self._confirm(name, args)) if self._confirm is not None else False
            if not ok:
                return {"error": f"tool '{name}' requires human confirmation", "needs_confirmation": True}
        return self.registry.call(name, **(args or {}))
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/arena/test_policy.py -q`
Expected: PASS (3 tests).

- [ ] **Step 5: Commit**

```bash
git add alpha/arena/policy.py tests/arena/test_policy.py
git commit -m "feat(arena): ActivityPolicy single choke-point (fail-closed tiers + autonomous-T4 block)"
```

---

### Task 5: Computer-use tools (file-read / file-write / shell) bound to a `ToolEnvironment`

**Files:**
- Create: `alpha/arena/tools.py`
- Test: `tests/arena/test_tools.py`

**Interfaces:**
- Consumes: `CapabilityTier` (Task 1), `ToolEnvironment` (Task 2/3).
- Produces: `make_read_file_tool(workspace)`, `make_write_file_tool(workspace)`, `make_shell_tool(env)`. Each returns `(schema: dict, fn: Callable, tier: CapabilityTier)`. File tools are workspace-path-guarded; read=T0, write=T1, shell=T2.

- [ ] **Step 1: Write the failing test**

```python
# tests/arena/test_tools.py
from pathlib import Path
from alpha.arena.contract import CapabilityTier
from alpha.arena.environment import InProcessEnv, LocalEnv
from alpha.arena.tools import make_read_file_tool, make_write_file_tool, make_shell_tool


def test_write_then_read_within_workspace(tmp_path: Path):
    _ws, wfn, wtier = make_write_file_tool(tmp_path)
    _rs, rfn, rtier = make_read_file_tool(tmp_path)
    assert wtier == CapabilityTier.T1_WORKSPACE_WRITE and rtier == CapabilityTier.T0_OBSERVE
    assert wfn(path="note.txt", content="hi")["ok"] is True
    assert rfn(path="note.txt")["content"] == "hi"


def test_file_tools_refuse_escape(tmp_path: Path):
    _s, wfn, _t = make_write_file_tool(tmp_path)
    out = wfn(path="../escape.txt", content="x")
    assert out["ok"] is False and "outside workspace" in out["error"].lower()


def test_shell_tool_tier_and_inprocess_refusal():
    schema, fn, tier = make_shell_tool(InProcessEnv())
    assert tier == CapabilityTier.T2_EXECUTE and schema["name"] == "shell"
    out = fn(argv=["echo", "hi"])
    assert out["ok"] is False   # InProcessEnv refuses


def test_shell_tool_runs_under_localenv(tmp_path: Path):
    _s, fn, _t = make_shell_tool(LocalEnv(workspace=tmp_path))
    out = fn(argv=["python", "-c", "print('x')"])
    assert out["ok"] is True and "x" in out["stdout"]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/arena/test_tools.py -q`
Expected: FAIL with `ModuleNotFoundError: alpha.arena.tools`.

- [ ] **Step 3: Write minimal implementation**

```python
# alpha/arena/tools.py
"""Computer-use tool factories. Each returns (schema, fn, tier). File tools are path-guarded to the
workspace; shell routes through the ToolEnvironment seam. NONE of these can import the harness or
reach the brain dir — data rungs only (modification-ladder spec §8)."""
from __future__ import annotations
from pathlib import Path
from alpha.arena.contract import CapabilityTier
from alpha.arena.environment import ToolEnvironment


def _within(workspace: Path, rel: str) -> Path | None:
    root = Path(workspace).resolve()
    p = (root / rel).resolve() if not Path(rel).is_absolute() else Path(rel).resolve()
    try:
        p.relative_to(root)
    except ValueError:
        return None
    return p


def make_read_file_tool(workspace: Path):
    def read_file(path: str) -> dict:
        p = _within(workspace, path)
        if p is None:
            return {"ok": False, "error": f"path outside workspace: {path}"}
        if not p.exists():
            return {"ok": False, "error": f"not found: {path}"}
        return {"ok": True, "content": p.read_text()}
    schema = {"name": "read_file", "description": "Read a file inside the project workspace.",
              "parameters": {"type": "object", "properties": {"path": {"type": "string"}},
                             "required": ["path"]}}
    return schema, read_file, CapabilityTier.T0_OBSERVE


def make_write_file_tool(workspace: Path):
    def write_file(path: str, content: str) -> dict:
        p = _within(workspace, path)
        if p is None:
            return {"ok": False, "error": f"path outside workspace: {path}"}
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content)
        return {"ok": True, "path": path}
    schema = {"name": "write_file", "description": "Write a file inside the project workspace.",
              "parameters": {"type": "object",
                             "properties": {"path": {"type": "string"}, "content": {"type": "string"}},
                             "required": ["path", "content"]}}
    return schema, write_file, CapabilityTier.T1_WORKSPACE_WRITE


def make_shell_tool(env: ToolEnvironment):
    def shell(argv: list[str]) -> dict:
        r = env.run(list(argv))
        return {"ok": r.ok, "stdout": r.stdout, "stderr": r.stderr, "exit_code": r.exit_code}
    schema = {"name": "shell", "description": "Run a command in the execution environment (confined).",
              "parameters": {"type": "object",
                             "properties": {"argv": {"type": "array", "items": {"type": "string"}}},
                             "required": ["argv"]}}
    return schema, shell, CapabilityTier.T2_EXECUTE
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/arena/test_tools.py -q`
Expected: PASS (4 tests).

- [ ] **Step 5: Commit**

```bash
git add alpha/arena/tools.py tests/arena/test_tools.py
git commit -m "feat(arena): computer-use tools (read/write/shell) over the ToolEnvironment seam"
```

---

### Task 6: `run_conversation` gains an optional `dispatch` callable (backward compatible)

**Files:**
- Modify: `alpha/converse/loop.py:36-56`
- Test: `tests/converse/test_loop_dispatch.py`

**Interfaces:**
- Produces: `run_conversation(registry, chat, system, messages, *, max_iters=8, dispatch=None)`. When `dispatch is None`, behavior is byte-identical to today (`registry.call(name, **args)`); when provided, the loop calls `dispatch(name, args)` instead. This is the seam by which `arena` injects `ActivityPolicy.dispatch` WITHOUT `converse` importing `arena`.

- [ ] **Step 1: Write the failing test**

```python
# tests/converse/test_loop_dispatch.py
from alpha.converse.loop import run_conversation
from alpha.converse.registry import ToolRegistry


class _Chat:
    def __init__(self, replies): self._r = list(replies)
    def chat(self, system, messages): return self._r.pop(0)


def test_dispatch_callable_intercepts_tool_calls():
    reg = ToolRegistry()
    reg.register("look", {"name": "look"}, lambda: {"raw": "registry"})
    seen = []
    def dispatch(name, args):
        seen.append((name, args))
        return {"via": "policy"}
    chat = _Chat(['{"tool": "look", "args": {}}', "done"])
    res = run_conversation(reg, chat, "sys", [], max_iters=3, dispatch=dispatch)
    assert seen == [("look", {})]
    assert res.tool_calls[0]["result"] == {"via": "policy"}
    assert res.final_text == "done"


def test_default_dispatch_is_registry_call():
    reg = ToolRegistry()
    reg.register("look", {"name": "look"}, lambda: {"raw": "registry"})
    chat = _Chat(['{"tool": "look", "args": {}}', "done"])
    res = run_conversation(reg, chat, "sys", [], max_iters=3)
    assert res.tool_calls[0]["result"] == {"raw": "registry"}
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/converse/test_loop_dispatch.py -q`
Expected: FAIL — `test_dispatch_callable_intercepts_tool_calls` errors (`run_conversation() got an unexpected keyword argument 'dispatch'`).

- [ ] **Step 3: Modify `run_conversation`**

Change the signature and the dispatch line in `alpha/converse/loop.py`:

```python
def run_conversation(registry: ToolRegistry, chat: ChatLLMClient, system: str,
                     messages: list[ChatMessage], *, max_iters: int = 8,
                     dispatch=None) -> ConversationResult:
    """Multi-turn tool-calling loop. Each iter: ask the model; if its reply is a tool call, dispatch
    it and feed the result back; otherwise the reply is the final answer. Bounded by max_iters.

    *dispatch* (name, args) -> result lets a caller (e.g. alpha.arena.ActivityPolicy) intercept every
    tool call at one choke point. Defaults to registry.call(name, **args) — byte-identical to before."""
    if dispatch is None:
        def dispatch(name, args):                 # default: the plain registry call
            return registry.call(name, **(args or {}))
    msgs = list(messages)
    calls: list[dict] = []
    for _ in range(max_iters):
        reply = chat.chat(system, msgs)
        call = _parse_tool_call(reply)
        if call is None:
            return ConversationResult(final_text=reply.strip(), messages=msgs, tool_calls=calls)
        name, args = call["tool"], call.get("args", {}) or {}
        try:
            result = dispatch(name, args)
        except KeyError:
            result = {"error": f"unknown tool: {name}"}
        except Exception as e:                       # a tool raising must not kill the conversation
            result = {"error": f"{type(e).__name__}: {e}"}
        calls.append({"tool": name, "args": args, "result": result})
        msgs.append(ChatMessage(role="assistant", text=reply))
        msgs.append(ChatMessage(role="user", text=f"[tool:{name} result]\n{_result_text(result)}"))
    return ConversationResult(
        final_text=(f"(I reached the {max_iters}-step tool-calling limit without finishing. "
                    "Try narrowing the request or asking again.)"),
        messages=msgs, tool_calls=calls, hit_max_iters=True)
```

- [ ] **Step 4: Run tests to verify pass (new + existing loop tests)**

Run: `python -m pytest tests/converse/test_loop_dispatch.py tests/converse -q`
Expected: PASS (new 2 + all existing converse tests still green).

- [ ] **Step 5: Commit**

```bash
git add alpha/converse/loop.py tests/converse/test_loop_dispatch.py
git commit -m "feat(converse): run_conversation accepts an optional dispatch callable (arena seam)"
```

---

### Task 7: `build_arena` — register tiered tools + wire the policy into a turn

**Files:**
- Create: `alpha/arena/builder.py`
- Test: `tests/arena/test_builder.py`

**Interfaces:**
- Consumes: `ToolRegistry` (converse), `ActivityPolicy` (Task 4), the arena tools (Task 5), `make_decide_for_date_tool`/`make_gated_write_tool` (converse/tools), `run_conversation` (Task 6).
- Produces: `build_arena(harness, agent_llm, source, *, workspace, env=None, confirm=None) -> tuple[ToolRegistry, ActivityPolicy]`. Registers `decide`(T0), `read_file`(T0), `write_file`(T1), `shell`(T2), `propose_memory_edit`(T3); records every tier; the policy fail-closes anything else. `env` defaults to `InProcessEnv()` (offline-safe).

- [ ] **Step 1: Write the failing test**

```python
# tests/arena/test_builder.py
from pathlib import Path
from alpha.arena.builder import build_arena
from alpha.arena.contract import CapabilityTier
from alpha.harness.loader import load_seeds


class _LLM:
    def complete(self, *a, **k): return "{}"


def test_build_arena_registers_tiers(tmp_path: Path):
    h = load_seeds()
    reg, pol = build_arena(h, _LLM(), source=None, workspace=tmp_path)
    assert pol.tiers["decide"] == CapabilityTier.T0_OBSERVE
    assert pol.tiers["read_file"] == CapabilityTier.T0_OBSERVE
    assert pol.tiers["write_file"] == CapabilityTier.T1_WORKSPACE_WRITE
    assert pol.tiers["shell"] == CapabilityTier.T2_EXECUTE
    assert pol.tiers["propose_memory_edit"] == CapabilityTier.T3_BRAIN_EDIT


def test_arena_fail_closes_unknown_tool(tmp_path: Path):
    h = load_seeds()
    _reg, pol = build_arena(h, _LLM(), source=None, workspace=tmp_path)
    out = pol.dispatch("definitely_not_a_tool", {})
    assert "error" in out and "tier" in out["error"].lower()


def test_arena_no_live_order_tool(tmp_path: Path):
    h = load_seeds()
    reg, pol = build_arena(h, _LLM(), source=None, workspace=tmp_path)
    # the hard wall: no order-placement tool exists at any tier
    assert not any("order" in name.lower() for name in pol.tiers)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/arena/test_builder.py -q`
Expected: FAIL with `ModuleNotFoundError: alpha.arena.builder`.

- [ ] **Step 3: Write minimal implementation**

```python
# alpha/arena/builder.py
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
    reg.register("read_file", rs, rfn); tiers["read_file"] = rtier
    ws, wfn, wtier = make_write_file_tool(workspace)
    reg.register("write_file", ws, wfn); tiers["write_file"] = wtier
    ss, sfn, stier = make_shell_tool(env)
    reg.register("shell", ss, sfn); tiers["shell"] = stier

    bw_schema, bw_fn = make_gated_write_tool(harness)
    reg.register("propose_memory_edit", bw_schema, bw_fn)
    tiers["propose_memory_edit"] = CapabilityTier.T3_BRAIN_EDIT

    return reg, ActivityPolicy(reg, tiers, confirm=confirm)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/arena/test_builder.py -q`
Expected: PASS (3 tests).

- [ ] **Step 5: Commit**

```bash
git add alpha/arena/builder.py tests/arena/test_builder.py
git commit -m "feat(arena): build_arena — tiered tool catalog + policy (data rungs, no order tool)"
```

---

### Task 8: Build gap 1 — `conflict_queue` + real provenance on the converse brain-edit tool

**Files:**
- Modify: `alpha/converse/tools.py:21-38` (`make_gated_write_tool`)
- Test: `tests/converse/test_gated_write_conflict.py`

**Interfaces:**
- Consumes: `try_apply_op(..., conflict_queue=...)` (existing gate), `ConflictQueue` (`alpha/meta/conflict_store.py`), `EditProvenance` (existing).
- Produces: `make_gated_write_tool(harness, *, min_retire_samples=5, min_promote_samples=3, conflict_queue=None, provenance=None)`. When `conflict_queue` is passed, a self-study-vs-teaching conflict is **held** (the gate enqueues + returns the `held_for_review` reason) and the tool surfaces `{"status": "held", "reason": ...}`. `provenance` defaults to the current `EditProvenance(path="teaching", proposer="hermes")` (unchanged behavior when omitted).

- [ ] **Step 1: Write the failing test**

```python
# tests/converse/test_gated_write_conflict.py
from alpha.converse.tools import make_gated_write_tool
from alpha.harness.loader import load_seeds


def test_gated_write_accepts_conflict_queue_kw():
    h = load_seeds()
    # must accept the kwargs without error (wiring gap closed)
    schema, fn = make_gated_write_tool(h, conflict_queue=None)
    assert schema["name"] == "propose_memory_edit"


def test_held_result_surfaces_when_conflict_queue_holds(monkeypatch):
    import alpha.converse.tools as t
    h = load_seeds()
    captured = {}

    def fake_try_apply_op(meta, harness, op, **kw):
        captured.update(kw)
        return None, "held_for_review: self-study contests a teaching-owned element"

    monkeypatch.setattr(t, "try_apply_op", fake_try_apply_op)

    class _Q: pass
    schema, fn = make_gated_write_tool(h, conflict_queue=_Q())
    out = fn(tool="process_memory", args={}, rationale="r")
    assert out["status"] == "held"
    assert "held_for_review" in out["reason"]
    assert captured.get("conflict_queue") is not None   # the queue was threaded to the gate
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/converse/test_gated_write_conflict.py -q`
Expected: FAIL — `make_gated_write_tool() got an unexpected keyword argument 'conflict_queue'`.

- [ ] **Step 3: Modify `make_gated_write_tool`**

```python
# alpha/converse/tools.py  (replace make_gated_write_tool, lines ~21-38)
def make_gated_write_tool(harness, *, min_retire_samples: int = 5, min_promote_samples: int = 3,
                          conflict_queue=None, provenance: EditProvenance | None = None):
    """A tool whose ONLY path to mutate H is try_apply_op (the one write-waist). Restricted to the
    M-pass whitelist for this face; the gate enforces rationale / evidence floors / red-lines, and
    (when conflict_queue is provided) HOLDS a self-study-vs-teaching conflict for user review."""
    prov = provenance if provenance is not None else EditProvenance(path="teaching", proposer="hermes")

    def propose_memory_edit(tool: str, args: dict, rationale: str) -> dict:
        op = RefineOp(tool=tool, args=args, rationale=rationale)
        rec, reason = try_apply_op(MetaTools(harness, EditLog()), harness, op,
                                   allowed=PASS_TOOLS["M"],
                                   min_retire_samples=min_retire_samples,
                                   min_promote_samples=min_promote_samples,
                                   provenance=prov, conflict_queue=conflict_queue)
        if rec is not None:
            return {"status": "applied"}
        if reason and reason.startswith("held_for_review"):
            return {"status": "held", "reason": reason}
        return {"status": "rejected", "reason": reason}
    schema = {"name": "propose_memory_edit",
              "description": "Propose a memory edit; applied only if it clears the gate.",
              "parameters": {"type": "object",
                             "properties": {"tool": {"type": "string"}, "args": {"type": "object"},
                                            "rationale": {"type": "string"}},
                             "required": ["tool", "args", "rationale"]}}
    return schema, propose_memory_edit
```

- [ ] **Step 4: Run tests to verify pass**

Run: `python -m pytest tests/converse/test_gated_write_conflict.py tests/converse -q`
Expected: PASS (new 2 + existing converse tests green — the default `conflict_queue=None`/`provenance=None` keeps old behavior).

- [ ] **Step 5: Commit**

```bash
git add alpha/converse/tools.py tests/converse/test_gated_write_conflict.py
git commit -m "feat(converse): wire conflict_queue + provenance into the gated brain-edit tool (build gap 1)"
```

---

### Task 9: Build gap 2 — enforce `StagedEdit.status` before any apply

**Files:**
- Create: `alpha/converse/approve.py`
- Test: `tests/converse/test_staged_approval.py`

**Interfaces:**
- Consumes: `StagedEdit` (`alpha/converse/project.py`).
- Produces: `assert_approvable(edit: StagedEdit) -> None` — raises `StagedEditNotApproved` unless `edit.status == "approved"` AND `edit.valid is True`; the live-apply path MUST call it before writing. (This makes the currently-vacuous `status` field load-bearing — recon-confirmed it was never checked.)

- [ ] **Step 1: Write the failing test**

```python
# tests/converse/test_staged_approval.py
import pytest
from alpha.converse.approve import assert_approvable, StagedEditNotApproved
from alpha.converse.project import StagedEdit


def _edit(**kw):
    base = dict(edit_id="e1", op={"tool": "process_memory", "args": {}, "rationale": "r"}, valid=True)
    base.update(kw)
    return StagedEdit(**base)


def test_pending_edit_is_not_approvable():
    with pytest.raises(StagedEditNotApproved):
        assert_approvable(_edit(status="pending"))


def test_rejected_edit_is_not_approvable():
    with pytest.raises(StagedEditNotApproved):
        assert_approvable(_edit(status="rejected"))


def test_invalid_edit_is_not_approvable_even_if_approved():
    with pytest.raises(StagedEditNotApproved):
        assert_approvable(_edit(status="approved", valid=False))


def test_approved_and_valid_passes():
    assert_approvable(_edit(status="approved", valid=True))   # no raise
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/converse/test_staged_approval.py -q`
Expected: FAIL with `ModuleNotFoundError: alpha.converse.approve`.

- [ ] **Step 3: Write minimal implementation**

```python
# alpha/converse/approve.py
"""Make StagedEdit.status load-bearing: a staged brain edit may be applied to the live brain ONLY
after the user approves it. Call assert_approvable(edit) at every live-apply site (T4 human-confirm,
modification-ladder spec §4)."""
from __future__ import annotations
from alpha.converse.project import StagedEdit


class StagedEditNotApproved(Exception):
    pass


def assert_approvable(edit: StagedEdit) -> None:
    if not edit.valid:
        raise StagedEditNotApproved(f"edit {edit.edit_id} did not pass the dry-run gate")
    if edit.status != "approved":
        raise StagedEditNotApproved(f"edit {edit.edit_id} is '{edit.status}', not 'approved'")
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/converse/test_staged_approval.py -q`
Expected: PASS (4 tests).

- [ ] **Step 5: Wire the guard into the workbench apply path**

In `workbench/app.py`, locate the approve handler that applies a staged edit through `try_apply_op` under `bstore.lock()`. Immediately before the apply call, set `edit.status = "approved"` then call `assert_approvable(edit)` (import from `alpha.converse.approve`). Run the existing workbench tests:

Run: `python -m pytest tests/web -q`
Expected: PASS (existing workbench/web tests stay green; the guard rejects only never-approved applies).

- [ ] **Step 6: Commit**

```bash
git add alpha/converse/approve.py tests/converse/test_staged_approval.py workbench/app.py
git commit -m "feat(converse): enforce StagedEdit.status before live apply (build gap 2)"
```

---

### Task 10: Thread PIT-gated recall into the conversational system prompt + PIT regression

**Files:**
- Modify: `alpha/converse/agent.py:27-43` (`build_system_prompt`) and `:46-54` (`converse`)
- Test: `tests/converse/test_prompt_recall_pit.py`

**Interfaces:**
- Consumes: `select_for_prompt(memory_store, *, phase_prior=None, asof=None, budget=...)` from `alpha/agent/retrieval.py` (existing PIT-masked selector; masks `asof is None OR learned_asof is None OR learned_asof <= asof`).
- Produces: `build_system_prompt(harness, registry, *, asof=None)` — appends a `RECALLED LESSONS` block built from `select_for_prompt(harness.memory, asof=asof)`; with `asof=None` (the live default) all lessons are visible; with a past `asof`, a lesson learned after `asof` is masked out. `converse(...)` gains an optional `asof` forwarded through.

- [ ] **Step 1: Write the failing test**

```python
# tests/converse/test_prompt_recall_pit.py
from datetime import date
from alpha.converse.agent import build_system_prompt
from alpha.converse.registry import ToolRegistry
from alpha.harness.loader import load_seeds
from alpha.harness.memory import Lesson


def _harness_with_lesson(learned):
    h = load_seeds()
    h.memory.add(Lesson(lesson_id="L_future", text="FUTURE_LESSON_MARKER", learned_asof=learned))
    return h


def test_recalled_lesson_appears_when_unmasked():
    h = _harness_with_lesson(date(2026, 1, 10))
    out = build_system_prompt(h, ToolRegistry(), asof=date(2026, 2, 1))
    assert "FUTURE_LESSON_MARKER" in out


def test_future_lesson_masked_for_past_asof():
    h = _harness_with_lesson(date(2026, 3, 1))
    out = build_system_prompt(h, ToolRegistry(), asof=date(2026, 1, 1))
    assert "FUTURE_LESSON_MARKER" not in out      # learned after asof -> PIT-masked


def test_default_asof_none_keeps_existing_shape():
    h = load_seeds()
    out = build_system_prompt(h, ToolRegistry())   # asof default None
    assert "TOOLS:" in out and "DOCTRINE:" in out
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/converse/test_prompt_recall_pit.py -q`
Expected: FAIL — `build_system_prompt() got an unexpected keyword argument 'asof'` (and the marker assertions fail).

> Note for the implementer: confirm the exact `select_for_prompt` signature and the `Lesson` field names by reading `alpha/agent/retrieval.py` and `alpha/harness/memory.py` before writing Step 3. If `MemoryStore` has no `add`, use the store's actual mutator (e.g. construct the harness seed with the lesson). The mask semantics (`learned_asof <= asof`, `None` always-visible) are fixed by the memory PIT-leak fix already in the tree.

- [ ] **Step 3: Modify `build_system_prompt` and `converse`**

```python
# alpha/converse/agent.py  (add import at top)
from alpha.agent.retrieval import select_for_prompt

# replace build_system_prompt
def build_system_prompt(harness: HarnessState, registry: ToolRegistry, *, asof=None) -> str:
    lines = [
        "You are evolving-alpha's conversational face. You share one brain (H) with the deterministic "
        "decider. You may use tools.",
        "",
        "TOOLS:",
    ]
    for s in registry.specs():
        lines.append(f"- {s['name']}: {s.get('description', '')}")
    selected = select_for_prompt(harness.memory, asof=asof)     # PIT-masked (asof=None -> all visible)
    if selected:
        lines += ["", "RECALLED LESSONS:"]
        for lesson in selected:
            lines.append(f"- {lesson.text}")
    lines += [
        "",
        "To CALL a tool, reply with a JSON object: {\"tool\": \"<name>\", \"args\": {...}}.",
        "To FINISH, reply with prose and no such JSON object.",
        "",
        f"DOCTRINE: {harness.doctrine.summary() if hasattr(harness.doctrine, 'summary') else ''}",
    ]
    return "\n".join(lines)
```

Then thread `asof` through `converse` (add `asof=None` param, pass to `build_system_prompt(h, registry, asof=asof)`). Adjust the `select_for_prompt` call to match its real signature/return (it returns a `Selection`; use its `.lessons` / list as the code in `retrieval.py` defines — confirm in Step 2's note).

- [ ] **Step 4: Run tests to verify pass**

Run: `python -m pytest tests/converse/test_prompt_recall_pit.py tests/converse -q`
Expected: PASS (new 3 + existing converse tests green).

- [ ] **Step 5: Commit**

```bash
git add alpha/converse/agent.py tests/converse/test_prompt_recall_pit.py
git commit -m "feat(converse): PIT-gated recall into the conversational prompt + regression (O-face)"
```

---

### Task 11: Full-suite green + arena package smoke

**Files:** none (verification task).

- [ ] **Step 1: Run the full suite**

Run: `python -m pytest tests -q`
Expected: PASS — the pre-existing 704 tests plus all new arena/converse tests; zero failures.

- [ ] **Step 2: Confirm no import cycle (arena is a leaf above converse)**

Run: `python -c "import alpha.arena.builder, alpha.arena.policy, alpha.arena.environment, alpha.arena.tools, alpha.arena.contract; print('arena imports clean')"`
Expected: prints `arena imports clean` with no ImportError.

- [ ] **Step 3: Commit any final touch-ups**

```bash
git add -A && git commit -m "test(arena): P-A arena skeleton — full suite green" --allow-empty
```

---

## Self-Review

**1. Spec coverage (activity-space §8 P-A + modification-ladder §8):**
- `alpha/arena/` contract + `ToolEnvironment` seam (`InProcessEnv`/`LocalEnv`) → Tasks 1–3. ✓
- Single dispatch choke point + capability tiers + fail-closed no-bypass → Tasks 4, 6, 7. ✓
- Computer-use tools (file read/write, shell) data-rungs-only, no order tool → Tasks 5, 7. ✓
- Brain files outside workspace + path-guarded → Task 3 (path-guard refuses escapes) + Task 7 (no harness-handle tool); the deployment note (brain dir placement) is an operator/runbook item recorded in the spec, asserted by Task 3's escape test. ✓
- Build gap 1 (conflict_queue + provenance on converse) → Task 8. ✓
- Build gap 2 (StagedEdit.status enforced) → Task 9. ✓
- PIT-gated recall into the conversational prompt + regression → Task 10. ✓
- Offline-testable; existing suite green → Tasks 2/3 (InProcessEnv default, LocalEnv temp workspace), Task 11. ✓
- **Deferred (NOT in this plan, by design):** experience capture (`Episode.kind=task`, P-B), general-task fitness (P-C), kernel `SandboxedEnv` + body axis (commercial). These are correctly out of scope for P-A.

**2. Placeholder scan:** No "TBD"/"add error handling"/"similar to Task N". Task 10 Step 2 carries an explicit implementer note to confirm `select_for_prompt`'s real signature/return shape before coding Step 3 — this is a read-first instruction, not a placeholder (the mask semantics are pinned).

**3. Type consistency:** `CapabilityTier`, `ExecResult`, `ToolEnvironment.run(argv, *, timeout, net)`, `ActivityPolicy(registry, tiers, *, confirm)`, `build_arena(...) -> (ToolRegistry, ActivityPolicy)`, `make_gated_write_tool(..., conflict_queue, provenance)`, `assert_approvable(edit)`, `build_system_prompt(..., *, asof=None)` are used consistently across tasks. The tool factories all return `(schema, fn, tier)`; the converse `make_*` factories return `(schema, fn)` (unchanged) — Task 7 adapts at registration.

## Execution Handoff

Plan complete and saved to `docs/superpowers/plans/2026-06-27-activity-space-pa-arena.md`. Two execution options:

1. **Subagent-Driven (recommended)** — I dispatch a fresh subagent per task, review between tasks, fast iteration.
2. **Inline Execution** — execute tasks in this session via executing-plans, batch execution with checkpoints.

Which approach?
