# Live Face → Arena Wiring Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the live conversational face (the workbench → `converse_project`) drive its tool loop through `ActivityPolicy` (the choke point becomes load-bearing) and expose the full computer-use catalog (decide / read_file / write_file / shell), without `converse` ever importing `arena`.

**Architecture:** Dependency injection. `converse_project` (converse layer) gains an optional `registry_factory(h, agent_llm, source, *, read_only, write_mode) -> (ToolRegistry, dispatch|None)`; default `None` = today's `build_converse_registry` path (`dispatch=None`, behavior-preserving). `build_arena` (arena layer) is generalized to build that tuple. The **workbench** (apps layer, may import arena) injects an arena factory that calls `build_arena` with a `LocalEnv` pointed at the project git workspace. The layer spine holds: `converse` → no arena; `arena` → converse; `workbench` → both.

**Tech Stack:** Python 3.13, pydantic v2, pytest. Fully offline.

## Global Constraints

- **All English.**
- **Layer spine:** `alpha/converse/*` must NOT import `alpha/arena/*`. `alpha/arena/*` may import `converse`. `workbench/` may import both. A test asserts no `converse`→`arena` import.
- **One write-waist:** brain mutation only via `try_apply_op`; arena tools never write `H` directly.
- **Single choke-point / fail-closed:** when a dispatch is injected, every tool call goes through it; an untiered tool fail-closes.
- **Live shell = operator-trust posture (accepted):** `LocalEnv` is NOT a kernel boundary; the brain dir lives OUTSIDE the workspace and that placement is asserted, but a shell with an embedded path can still reach the brain — documented, not regex-patched. Real containment = `SandboxedEnv` (deferred).
- **Backward compatibility:** default `registry_factory=None` and the default `build_converse_registry`/`build_arena` params reproduce today's behavior. Existing `tests/converse` + `tests/web` stay green.
- Run tests with `python -m pytest tests -q` (NOT `pytest -q .`).

**Spec:** `docs/superpowers/specs/2026-06-27-live-face-arena-wiring-design.md`.

---

## File Structure
- `alpha/converse/agent.py` — `build_converse_registry` gains `conflict_queue`/`provenance` (Task 1).
- `alpha/arena/builder.py` — `build_arena` generalized (Task 2).
- `alpha/converse/workspace.py` — `root` property (Task 3).
- `alpha/converse/session.py` — `converse_project` gains `registry_factory` + dispatch (Task 4).
- `workbench/app.py` — inject the arena factory + brain-outside-workspace assert (Task 5).
- Verification (Task 6).

---

### Task 1: `build_converse_registry` threads `conflict_queue` + `provenance`

**Files:**
- Modify: `alpha/converse/agent.py` (`build_converse_registry`)
- Test: `tests/converse/test_registry_provenance.py`

**Interfaces:**
- Consumes: `make_gated_write_tool(harness, *, conflict_queue=None, provenance=None)` (exists from build gap 1).
- Produces: `build_converse_registry(harness, agent_llm, source, *, read_only=False, write_mode="apply", conflict_queue=None, provenance=None) -> ToolRegistry`.

- [ ] **Step 1: Write the failing test**

```python
# tests/converse/test_registry_provenance.py
import alpha.converse.agent as agent_mod
from alpha.harness.loader import load_seeds


def test_apply_mode_threads_conflict_queue_and_provenance(monkeypatch):
    captured = {}
    def fake_make_gated(harness, **kw):
        captured.update(kw)
        return {"name": "propose_memory_edit"}, (lambda **a: {"status": "applied"})
    monkeypatch.setattr(agent_mod, "make_gated_write_tool", fake_make_gated)
    h = load_seeds("seeds")
    q, p = object(), object()
    agent_mod.build_converse_registry(h, None, None, write_mode="apply", conflict_queue=q, provenance=p)
    assert captured.get("conflict_queue") is q
    assert captured.get("provenance") is p


def test_apply_mode_defaults_are_none(monkeypatch):
    captured = {}
    def fake_make_gated(harness, **kw):
        captured.update(kw)
        return {"name": "propose_memory_edit"}, (lambda **a: {})
    monkeypatch.setattr(agent_mod, "make_gated_write_tool", fake_make_gated)
    agent_mod.build_converse_registry(load_seeds("seeds"), None, None, write_mode="apply")
    assert captured.get("conflict_queue") is None and captured.get("provenance") is None
```

- [ ] **Step 2: Run to verify it fails**

Run: `python -m pytest tests/converse/test_registry_provenance.py -q`
Expected: FAIL — `build_converse_registry() got an unexpected keyword argument 'conflict_queue'`.

- [ ] **Step 3: Modify `build_converse_registry`**

Read the current function first. Change its signature and the apply branch:

```python
def build_converse_registry(harness: HarnessState, agent_llm, source,
                            *, read_only: bool = False, write_mode: str = "apply",
                            conflict_queue=None, provenance=None) -> ToolRegistry:
    reg = ToolRegistry()
    decide_schema, decide_fn = make_decide_for_date_tool(harness, agent_llm, source)
    reg.register("decide", decide_schema, decide_fn)
    mode = "none" if read_only else write_mode
    if mode == "apply":
        write_schema, write_fn = make_gated_write_tool(
            harness, conflict_queue=conflict_queue, provenance=provenance)
        reg.register("propose_memory_edit", write_schema, write_fn)
    elif mode == "stage":
        write_schema, write_fn = make_propose_edit_tool(harness)
        reg.register("propose_memory_edit", write_schema, write_fn)
    return reg
```

(The `stage` branch is unchanged — `make_propose_edit_tool` dry-runs; conflict detection there happens at workbench-approve time.)

- [ ] **Step 4: Run to verify it passes**

Run: `python -m pytest tests/converse/test_registry_provenance.py tests/converse -q`
Expected: PASS (2 new + existing converse green).

- [ ] **Step 5: Commit**

```bash
git add alpha/converse/agent.py tests/converse/test_registry_provenance.py
git commit -m "feat(converse): build_converse_registry threads conflict_queue + provenance (apply mode)"
```

---

### Task 2: `build_arena` generalized (optional workspace, modes, tiers, reuse)

**Files:**
- Modify: `alpha/arena/builder.py` (`build_arena`)
- Test: `tests/arena/test_builder.py` (extend)

**Interfaces:**
- Consumes: `build_converse_registry(...)` (Task 1), `make_read_file_tool`/`make_write_file_tool`/`make_shell_tool` (→ `(schema, fn, tier)`), `InProcessEnv`, `ActivityPolicy`, `CapabilityTier`.
- Produces: `build_arena(harness, agent_llm, source, *, workspace=None, env=None, write_mode="apply", read_only=False, conflict_queue=None, provenance=None, confirm=None) -> (ToolRegistry, ActivityPolicy)`.

- [ ] **Step 1: Write the failing test (append to `tests/arena/test_builder.py`)**

```python
def test_build_arena_no_workspace_is_decide_plus_brain_edit(tmp_path):
    from alpha.arena.contract import CapabilityTier
    h = load_seeds("seeds")
    reg, pol = build_arena(h, _LLM(), source=None)              # workspace=None
    assert set(pol.tiers) == {"decide", "propose_memory_edit"}
    assert pol.tiers["decide"] == CapabilityTier.T0_OBSERVE
    assert pol.tiers["propose_memory_edit"] == CapabilityTier.T3_BRAIN_EDIT


def test_build_arena_with_workspace_adds_computer_use(tmp_path):
    from alpha.arena.contract import CapabilityTier
    reg, pol = build_arena(load_seeds("seeds"), _LLM(), source=None, workspace=tmp_path)
    assert pol.tiers["read_file"] == CapabilityTier.T0_OBSERVE
    assert pol.tiers["write_file"] == CapabilityTier.T1_WORKSPACE_WRITE
    assert pol.tiers["shell"] == CapabilityTier.T2_EXECUTE


def test_build_arena_read_only_is_read_and_decide_only(tmp_path):
    reg, pol = build_arena(load_seeds("seeds"), _LLM(), source=None,
                           workspace=tmp_path, read_only=True)
    assert set(pol.tiers) == {"decide", "read_file"}            # no brain-edit/write/shell


def test_build_arena_write_mode_none_drops_brain_edit(tmp_path):
    reg, pol = build_arena(load_seeds("seeds"), _LLM(), source=None, write_mode="none")
    assert "propose_memory_edit" not in pol.tiers
```

(`_LLM` and `load_seeds` are already imported at the top of `test_builder.py` from the P-A tasks; if `_LLM` is absent, add the trivial stub `class _LLM: \n    def complete(self,*a,**k): return "{}"`.)

- [ ] **Step 2: Run to verify it fails**

Run: `python -m pytest tests/arena/test_builder.py -q`
Expected: FAIL — the no-workspace test fails (current `build_arena` always registers read/write/shell and requires `workspace`).

- [ ] **Step 3: Rewrite `build_arena`**

```python
# alpha/arena/builder.py
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
    if not read_only and write_mode != "none":
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
```

(`ToolRegistry` is the return type of `build_converse_registry`; the forward-ref string in the annotation avoids an extra import. If the existing file imported `ToolRegistry`/`make_decide_for_date_tool`/`make_gated_write_tool` directly, drop the now-unused imports.)

- [ ] **Step 4: Run to verify it passes**

Run: `python -m pytest tests/arena/test_builder.py tests/arena -q`
Expected: PASS (the existing P-A builder tests + the 4 new ones; update any P-A builder test that passed a now-still-valid `workspace=` — `workspace` is still accepted).

- [ ] **Step 5: Commit**

```bash
git add alpha/arena/builder.py tests/arena/test_builder.py
git commit -m "feat(arena): build_arena reuses build_converse_registry; optional workspace; modes + read-only suppression"
```

---

### Task 3: `Workspace.root` public property

**Files:**
- Modify: `alpha/converse/workspace.py`
- Test: `tests/converse/test_workspace_root.py`

**Interfaces:**
- Produces: `Workspace.root -> Path` (the resolved workspace directory, for `LocalEnv`).

- [ ] **Step 1: Write the failing test**

```python
# tests/converse/test_workspace_root.py
from pathlib import Path
from alpha.converse.workspace import Workspace


def test_workspace_root_is_resolved_dir(tmp_path):
    ws = Workspace(tmp_path / "proj")
    assert ws.root == (tmp_path / "proj").resolve()
    assert isinstance(ws.root, Path)
```

- [ ] **Step 2: Run to verify it fails**

Run: `python -m pytest tests/converse/test_workspace_root.py -q`
Expected: FAIL — `AttributeError: 'Workspace' object has no attribute 'root'`.

- [ ] **Step 3: Add the property** (after `__init__`)

```python
    @property
    def root(self) -> Path:
        """The resolved workspace directory (e.g. the LocalEnv cwd for arena tools)."""
        return self._root
```

- [ ] **Step 4: Run to verify it passes**

Run: `python -m pytest tests/converse/test_workspace_root.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add alpha/converse/workspace.py tests/converse/test_workspace_root.py
git commit -m "feat(converse): Workspace.root public property"
```

---

### Task 4: `converse_project` gains `registry_factory` injection + dispatch

**Files:**
- Modify: `alpha/converse/session.py` (`converse_project`)
- Test: `tests/converse/test_session_dispatch.py`

**Interfaces:**
- Consumes: the existing `build_converse_registry`, `build_system_prompt`, `run_conversation(..., dispatch=)`.
- Produces: `converse_project(project_id, user_text, *, harness, store, snapshots=None, agent_llm, chat_llm, source, workspace=None, max_iters=8, write_mode="apply", registry_factory=None) -> Project`. `registry_factory(h, agent_llm, source, *, read_only, write_mode) -> (ToolRegistry, dispatch|None)`. When `None`, uses `build_converse_registry(...)` with `dispatch=None` (unchanged behavior).

- [ ] **Step 1: Write the failing test**

```python
# tests/converse/test_session_dispatch.py
from alpha.converse.session import converse_project
from alpha.converse.sqlite_store import SqliteProjectStore
from alpha.harness.loader import load_seeds


class _Chat:
    def __init__(self, replies): self._r = list(replies)
    def chat(self, system, messages): return self._r.pop(0)


def test_converse_project_routes_through_injected_dispatch(tmp_path):
    # a factory whose dispatch fail-closes any tool name (proving the LIVE path uses dispatch)
    seen = {}
    def factory(h, agent_llm, source, *, read_only, write_mode):
        from alpha.converse.registry import ToolRegistry
        reg = ToolRegistry()
        reg.register("decide", {"name": "decide"}, lambda **a: {"unreached": True})
        def dispatch(name, args):
            seen["called"] = (name, args)
            return {"error": "fail-closed (test)"}
        return reg, dispatch
    store = SqliteProjectStore.open(str(tmp_path / "state.db"))
    chat = _Chat(['{"tool": "decide", "args": {"date": "2026-01-05"}}', "done"])
    proj = converse_project("p1", "hi", harness=load_seeds("seeds"), store=store,
                            agent_llm=None, chat_llm=chat, source=None,
                            registry_factory=factory)
    assert seen["called"] == ("decide", {"date": "2026-01-05"})         # dispatch was used
    assert proj.turns[-1].tool_calls[0]["result"] == {"error": "fail-closed (test)"}
    assert proj.turns[-1].final_text == "done"


def test_converse_project_default_factory_unchanged(tmp_path):
    store = SqliteProjectStore.open(str(tmp_path / "s.db"))
    chat = _Chat(["just talking"])                                       # no tool call
    proj = converse_project("p2", "hello", harness=load_seeds("seeds"), store=store,
                            agent_llm=None, chat_llm=chat, source=None)   # no factory
    assert proj.turns[-1].final_text == "just talking"
```

- [ ] **Step 2: Run to verify it fails**

Run: `python -m pytest tests/converse/test_session_dispatch.py -q`
Expected: FAIL — `converse_project() got an unexpected keyword argument 'registry_factory'`.

- [ ] **Step 3: Modify `converse_project`**

Read the current function. Add `registry_factory=None` to the signature, and replace the registry/dispatch construction (the `build_converse_registry(...)` line and the `run_conversation(...)` call):

```python
    # 3. Build registry + dispatch (injected factory keeps converse arena-free).
    if registry_factory is None:
        registry = build_converse_registry(h, agent_llm, source, read_only=read_only,
                                            write_mode=write_mode)
        dispatch = None
    else:
        registry, dispatch = registry_factory(h, agent_llm, source,
                                               read_only=read_only, write_mode=write_mode)
    system = build_system_prompt(h, registry)
    ...
    # 5. Run the conversation loop.
    res = run_conversation(registry, chat_llm, system, project.messages,
                           max_iters=max_iters, dispatch=dispatch)
```

(Leave everything else — project load, message append, turn building, staged-edit materialization, workspace decision commit, persist — unchanged.)

- [ ] **Step 4: Run to verify it passes**

Run: `python -m pytest tests/converse/test_session_dispatch.py tests/converse tests/web -q`
Expected: PASS (2 new + existing converse + web green — default path unchanged).

- [ ] **Step 5: Commit**

```bash
git add alpha/converse/session.py tests/converse/test_session_dispatch.py
git commit -m "feat(converse): converse_project accepts registry_factory injection (arena seam, dispatch)"
```

---

### Task 5: Workbench injects the arena factory + asserts brain-outside-workspace

**Files:**
- Modify: `workbench/app.py`
- Test: `tests/web/test_workbench_arena.py`

**Interfaces:**
- Consumes: `build_arena` (Task 2), `LocalEnv` (`alpha.arena.environment`), `Workspace.root` (Task 3), `converse_project(..., registry_factory=)` (Task 4).
- Produces: the workbench `/converse` handler passes a `registry_factory` that builds the arena (with `LocalEnv(ws.root)`) so the live conversational face runs the full computer-use catalog through the policy; a startup assertion that the brain dir is not inside the workspace dir.

- [ ] **Step 1: Write the failing test**

```python
# tests/web/test_workbench_arena.py
from pathlib import Path
import pytest


def test_brain_under_workspace_is_rejected(tmp_path, monkeypatch):
    # brain INSIDE the workspace must fail fast (the live shell could reach it)
    ws = tmp_path / "ws"; brain = ws / "brain"
    monkeypatch.setenv("ALPHA_WORKSPACE_DIR", str(ws))
    monkeypatch.setenv("ALPHA_LIVE_BRAIN_DIR", str(brain))
    from workbench.app import _assert_brain_outside_workspace
    with pytest.raises(Exception):
        _assert_brain_outside_workspace()


def test_brain_sibling_of_workspace_is_ok(tmp_path, monkeypatch):
    monkeypatch.setenv("ALPHA_WORKSPACE_DIR", str(tmp_path / "ws"))
    monkeypatch.setenv("ALPHA_LIVE_BRAIN_DIR", str(tmp_path / "brain"))
    from workbench.app import _assert_brain_outside_workspace
    _assert_brain_outside_workspace()   # no raise


def test_arena_factory_registers_shell_t2(tmp_path):
    # the workbench's factory wires the full computer-use catalog through the policy
    from workbench.app import _arena_factory
    from alpha.arena.contract import CapabilityTier
    from alpha.harness.loader import load_seeds
    factory = _arena_factory(tmp_path)                 # tmp_path stands in for ws.root
    reg, dispatch = factory(load_seeds("seeds"), None, None, read_only=False, write_mode="stage")
    # dispatch is the policy's; an untiered tool fail-closes
    out = dispatch("definitely_not_a_tool", {})
    assert "error" in out
```

- [ ] **Step 2: Run to verify it fails**

Run: `python -m pytest tests/web/test_workbench_arena.py -q`
Expected: FAIL — `_assert_brain_outside_workspace` / `_arena_factory` not defined.

- [ ] **Step 3: Add the helpers + wire the handler**

Add near the other workbench helpers in `workbench/app.py`:

```python
from pathlib import Path as _Path
from alpha.arena.builder import build_arena
from alpha.arena.environment import LocalEnv


def _brain_dir() -> str:
    return os.environ.get("ALPHA_LIVE_BRAIN_DIR", "./state/brain")


def _assert_brain_outside_workspace() -> None:
    """Fail fast if the brain dir is inside the workspace — a live shell could then reach it."""
    ws_root = _Path(os.environ.get("ALPHA_WORKSPACE_DIR", "./state/workspaces")).resolve()
    brain = _Path(_brain_dir()).resolve()
    if brain == ws_root or brain.is_relative_to(ws_root):
        raise RuntimeError(
            f"brain dir {brain} is inside workspace {ws_root}; move them apart "
            "(LocalEnv is not a kernel boundary — the brain must sit outside the shell's workspace)")


def _arena_factory(workspace_root):
    """Return a converse_project registry_factory that builds the arena with a LocalEnv pointed
    at *workspace_root* (full computer-use: decide/read/write/shell + the policy choke point)."""
    env = LocalEnv(workspace=workspace_root)
    def factory(h, agent_llm, source, *, read_only, write_mode):
        reg, pol = build_arena(h, agent_llm, source, workspace=workspace_root, env=env,
                               write_mode=write_mode, read_only=read_only)
        return reg, pol.dispatch
    return factory
```

Then in the `/converse` handler, call the assertion once and pass the factory to `converse_project`:

```python
    @app.post("/converse")
    def converse_ep(body: ConverseIn):
        with _MUTATION_LOCK:
            _assert_brain_outside_workspace()
            h, _log = _brain_store().load()
            ws = _workspace()
            try:
                proj = converse_project(DEFAULT_PROJECT_ID, body.text, harness=h, store=_project_store(),
                                        agent_llm=_agent_llm(), chat_llm=_chat_llm(), source=_source(),
                                        workspace=ws, write_mode="stage",
                                        registry_factory=_arena_factory(ws.root))
            except Exception as e:
                ...  # unchanged fallback
```

(Keep the existing fallback `except` block exactly as-is.)

- [ ] **Step 4: Run to verify it passes**

Run: `python -m pytest tests/web/test_workbench_arena.py tests/web -q`
Expected: PASS (3 new + existing workbench/web green).

- [ ] **Step 5: Commit**

```bash
git add workbench/app.py tests/web/test_workbench_arena.py
git commit -m "feat(workbench): wire live face onto arena (full computer-use via LocalEnv) + brain-outside-workspace assert"
```

---

### Task 6: Full-suite green + layer-spine check

**Files:** Test: `tests/arena/test_no_converse_arena_cycle.py`

- [ ] **Step 1: Write the layer-spine guard test**

```python
# tests/arena/test_no_converse_arena_cycle.py
import ast, pathlib


def test_converse_never_imports_arena():
    converse_dir = pathlib.Path("alpha/converse")
    offenders = []
    for py in converse_dir.rglob("*.py"):
        tree = ast.parse(py.read_text())
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and (node.module or "").startswith("alpha.arena"):
                offenders.append(f"{py}: from {node.module}")
            if isinstance(node, ast.Import):
                for n in node.names:
                    if n.name.startswith("alpha.arena"):
                        offenders.append(f"{py}: import {n.name}")
    assert offenders == [], f"converse must not import arena: {offenders}"
```

- [ ] **Step 2: Run it**

Run: `python -m pytest tests/arena/test_no_converse_arena_cycle.py -q`
Expected: PASS (the injection keeps converse arena-free).

- [ ] **Step 3: Full suite**

Run: `python -m pytest tests -q`
Expected: PASS (all prior + the new tests; zero failures).

- [ ] **Step 4: Commit**

```bash
git add tests/arena/test_no_converse_arena_cycle.py
git commit -m "test(arena): assert converse never imports arena (layer spine) + full suite green"
```

---

## Self-Review

**1. Spec coverage:** build_arena reuse + conflict_queue/provenance → Tasks 1,2. Optional workspace + modes + read-only suppression → Task 2. registry_factory injection (converse arena-free) → Task 4. Workspace.root → Task 3. Workbench arena factory + LocalEnv + brain-outside-workspace assert → Task 5. Layer spine + full suite → Task 6. Live shell operator-trust posture → documented in Task 5's assertion message + the spec (no regex). `converse()` injection intentionally OMITTED (YAGNI — the live face is the workbench→converse_project path; add later if a CLI needs it). ✓

**2. Placeholder scan:** No TBD/vague steps; every code step shows complete code. Steps 3 instruct "read the current function first" because they modify existing functions whose surrounding lines must be preserved — that is a read-before-edit instruction, not a placeholder.

**3. Type consistency:** `registry_factory(h, agent_llm, source, *, read_only, write_mode) -> (ToolRegistry, dispatch|None)` is identical in Tasks 4 (consumer) and 5 (producer `_arena_factory`). `build_arena(... workspace=None ...) -> (ToolRegistry, ActivityPolicy)` consistent in Tasks 2 and 5. `Workspace.root -> Path` consistent in Tasks 3 and 5. `build_converse_registry(..., conflict_queue, provenance)` consistent in Tasks 1 and 2.

## Execution Handoff

Plan complete and saved to `docs/superpowers/plans/2026-06-27-live-face-arena-wiring.md`. Two execution options:

1. **Subagent-Driven (recommended)** — fresh subagent per task, review between tasks.
2. **Inline Execution** — execute in this session with checkpoints.

Which approach?
