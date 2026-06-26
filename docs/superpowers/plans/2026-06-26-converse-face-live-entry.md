# Conversational Face — Live Entry (Workbench) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Give evolving-alpha's conversational face a live entry point — an independent `workbench` FastAPI service (`:8820`) you can converse with, that runs a real PIT `decide`, produces git-workspace artifacts, and **stages brain edits for your preview/approval** before they touch the live H — plus an `alpha_web` **Workbench** page over it.

**Architecture:** New `workbench/` service mirrors `sonia/`; it self-holds a `LiveBrainStore` on the shared `ALPHA_LIVE_BRAIN_DIR` (now guarded by a cross-process `fcntl` file lock — no HTTP coupling to Sonia) plus a `ProjectStore` + git `Workspace` + data source. The converse write tool changes from apply-direct to **stage-a-proposal** (`make_propose_edit_tool`); approval re-runs the op through the same gate (`try_apply_op`) under the lock. `alpha_web` gains a thin `WorkbenchClient` + a Workbench page (HTMX, the conflicts-UI empty-200/escape patterns). Reuses §4 (`Project`/`ProjectStore`/`Workspace`) and §5 (provenance).

**Tech Stack:** Python ≥3.11, FastAPI, pydantic v2, stdlib `fcntl` (no new deps), Jinja2 + HTMX, pytest (Starlette `TestClient`). Reuses `alpha/converse/*`, `alpha/meta/store.py::LiveBrainStore`, `alpha/refine/apply.py::try_apply_op`, `alpha/meta/agent.py::preview_op` (dry-run pattern), `sonia/app.py` + `alpha_web/sonia_client.py` (mirror patterns).

## Global Constraints

- **Python `>=3.11`**, FastAPI, pydantic v2. The existing suite (currently **629 passed**) must stay green. Everything is additive — no existing route/method/tool/template changes behavior.
- **Placement:** an independent `workbench` service (`:8820`), NOT folded into Sonia, NOT run inside `alpha_web`.
- **Write semantics = preview & approve.** The converse write tool STAGES a proposal (dry-run validated on a deepcopy, never applied during the turn); the live brain is touched only on `POST /edits/{id}/approve`, through `try_apply_op` (the one gate), under the lock.
- **Cross-process brain writes:** a `fcntl.flock` lock on `<ALPHA_LIVE_BRAIN_DIR>/.brain.lock` guards the read-modify-write critical section; **both** workbench AND Sonia hold it across their apply. Bounded blocking acquire; timeout → explicit `RuntimeError` (never a silent skip). Zero new deps (stdlib `fcntl`; darwin/linux only — Windows is not a target).
- **v1 scope = a single default project** id `"default"`; multi-project UI deferred.
- **Provenance:** every converse-face gated edit carries `EditProvenance(path="teaching", proposer="hermes")` (§5).
- **Security (conflicts-UI lesson):** all rendered fields via Jinja2 `{{ }}` (autoescape ON); NO raw f-string HTML reflecting request/path/Sonia data.
- English; mirror the existing `sonia/app.py`, `alpha_web/sonia_client.py`, `alpha_web/templates/conflicts.html` patterns.

## File Structure

- Modify: `alpha/meta/store.py` (`LiveBrainStore.lock()` + use it in `save`/`snapshot`/`restore` callers); `sonia/app.py` (wrap `apply_message`/`rollback` in `bstore.lock()`).
- Modify: `alpha/converse/project.py` (`StagedEdit`, `Project.staged_edits`); `alpha/converse/tools.py` (`make_propose_edit_tool`); `alpha/converse/agent.py` (`build_converse_registry(..., write_mode)`); `alpha/converse/session.py` (`converse_project(..., write_mode)` + staged materialization); `alpha/converse/workspace.py` (`Workspace.artifacts()`).
- Create: `workbench/__init__.py`, `workbench/app.py`, `workbench/__main__.py`; `alpha_web/workbench_client.py`; `alpha_web/templates/workbench.html`.
- Modify: `alpha_web/app.py` (Workbench nav + routes).
- Tests: `tests/meta/test_brain_lock.py`, `tests/converse/test_staged_edit_model.py`, `tests/converse/test_propose_edit_tool.py`, `tests/converse/test_converse_project_stage.py`, `tests/workbench/test_workbench_service.py`, `tests/workbench/test_workbench_mutation.py`, `tests/web/test_workbench_page.py`.

---

### Task 1: `LiveBrainStore.lock()` cross-process file lock + Sonia uses it

**Files:**
- Modify: `alpha/meta/store.py`
- Modify: `sonia/app.py` (wrap `apply_message` + `rollback_message` brain sections in `bstore.lock()`)
- Test: `tests/meta/test_brain_lock.py`

**Interfaces:**
- Produces: `LiveBrainStore.lock(timeout: float = 10.0)` — a context manager that exclusively `fcntl.flock`s `<root>/.brain.lock` (bounded non-blocking retry; on timeout raises `RuntimeError`). Consumed by Tasks 5/6 (workbench approve/rollback) and Sonia.

- [ ] **Step 1: Write the failing test**

```python
# tests/meta/test_brain_lock.py
import os, threading, time
import pytest
from alpha.meta.store import LiveBrainStore

def test_lock_is_exclusive_and_times_out(tmp_path):
    s = LiveBrainStore(tmp_path)
    held = threading.Event(); release = threading.Event()
    def holder():
        with s.lock():
            held.set(); release.wait(2)
    t = threading.Thread(target=holder); t.start()
    assert held.wait(1)
    with pytest.raises(RuntimeError):           # second acquirer cannot get it within the timeout
        with LiveBrainStore(tmp_path).lock(timeout=0.3):
            pass
    release.set(); t.join()
    with LiveBrainStore(tmp_path).lock(timeout=1):   # acquirable once released
        pass

def test_lock_file_created_under_root(tmp_path):
    with LiveBrainStore(tmp_path).lock():
        assert (tmp_path / ".brain.lock").exists()
```

- [ ] **Step 2: Run to verify it fails**

Run: `python -m pytest tests/meta/test_brain_lock.py -v`
Expected: FAIL — `AttributeError: 'LiveBrainStore' object has no attribute 'lock'`.

- [ ] **Step 3: Implement** — in `alpha/meta/store.py` add the import + method:

```python
import contextlib
import fcntl
import time
```
```python
    @contextlib.contextmanager
    def lock(self, timeout: float = 10.0):
        """Cross-process exclusive lock over the brain's read-modify-write critical section.
        Bounded non-blocking retry; on timeout raise (never silently skip a write)."""
        self._root.mkdir(parents=True, exist_ok=True)
        lock_path = self._root / ".brain.lock"
        fd = os.open(str(lock_path), os.O_CREAT | os.O_RDWR, 0o600)
        deadline = time.monotonic() + timeout
        try:
            while True:
                try:
                    fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                    break
                except BlockingIOError:
                    if time.monotonic() >= deadline:
                        raise RuntimeError(f"brain lock busy after {timeout}s: {lock_path}")
                    time.sleep(0.05)
            yield
        finally:
            try:
                fcntl.flock(fd, fcntl.LOCK_UN)
            finally:
                os.close(fd)
```

Then make Sonia hold it across its brain mutation. In `sonia/app.py`, inside `apply_message` (the `with _MUTATION_LOCK:` block, around the `h, log = bstore.load() … bstore.save(h, log)` section) and `rollback_message`, wrap the brain read-modify-write in `with bstore.lock():`. Example for `apply_message`:
```python
            bstore = _brain_store()
            with bstore.lock():
                h, log = bstore.load()
                if not bstore.is_live():
                    bstore.save(h, log)
                msg.snapshot_before = bstore.snapshot(f"{sid}-{mid}")
                applied, _rows = MetaAgent(MetaTools(h, log), MockLLMClient("{}")).apply(accepted)
                bstore.save(h, log)
```
and in `rollback_message` wrap the `_brain_store().restore(...)` in `with _brain_store().lock():` (or bind `bstore` first). This is additive (the lock is uncontended when Sonia runs alone).

- [ ] **Step 4: Run to verify it passes + Sonia tests green**

Run: `python -m pytest tests/meta/test_brain_lock.py tests/sonia -q`
Expected: green (the lock is uncontended in Sonia's existing tests).

- [ ] **Step 5: Commit**

```bash
git add alpha/meta/store.py sonia/app.py tests/meta/test_brain_lock.py
git commit -m "feat(brain): LiveBrainStore.lock() cross-process file lock; Sonia holds it on apply/rollback"
```

---

### Task 2: `StagedEdit` model + `Project.staged_edits`

**Files:**
- Modify: `alpha/converse/project.py`
- Test: `tests/converse/test_staged_edit_model.py`

**Interfaces:**
- Produces: `StagedEdit(edit_id: str, op: dict, summary: str = "", valid: bool = False, reason: str | None = None, preview: dict = {}, status: Literal["pending","approved","rejected"] = "pending", snapshot_before: str = "", applied_seq: int | None = None)`; `Project.staged_edits: list[StagedEdit] = []`. Consumed by Tasks 4/6/8.

- [ ] **Step 1: Write the failing test**

```python
# tests/converse/test_staged_edit_model.py
from alpha.converse.project import Project, StagedEdit, new_project

def test_staged_edit_round_trips_on_project():
    p = new_project()
    p.staged_edits.append(StagedEdit(edit_id="e1", op={"tool": "process_memory", "args": {}, "rationale": "r"},
                                     summary="add lesson", valid=True, preview={"op": "create"}))
    assert Project.model_validate_json(p.model_dump_json()) == p
    assert p.staged_edits[0].status == "pending" and p.staged_edits[0].applied_seq is None
```

- [ ] **Step 2: Run to verify it fails**

Run: `python -m pytest tests/converse/test_staged_edit_model.py -v`
Expected: FAIL — `ImportError: cannot import name 'StagedEdit'`.

- [ ] **Step 3: Implement** — in `alpha/converse/project.py`:

```python
from typing import Literal

class StagedEdit(BaseModel):
    """A converse-face brain edit proposed for the user's approval (preview/approve flow)."""
    edit_id: str
    op: dict                                   # {"tool","args","rationale"} — the RefineOp seed
    summary: str = ""
    valid: bool = False                        # passed the dry-run gate
    reason: str | None = None                  # dry-run / apply reject reason
    preview: dict = Field(default_factory=dict)
    status: Literal["pending", "approved", "rejected"] = "pending"
    snapshot_before: str = ""
    applied_seq: int | None = None
```
Add to `Project`:
```python
    staged_edits: list[StagedEdit] = Field(default_factory=list)
```

- [ ] **Step 4: Run to verify it passes**

Run: `python -m pytest tests/converse/test_staged_edit_model.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add alpha/converse/project.py tests/converse/test_staged_edit_model.py
git commit -m "feat(converse): StagedEdit model + Project.staged_edits"
```

---

### Task 3: `make_propose_edit_tool` (stage, don't apply)

**Files:**
- Modify: `alpha/converse/tools.py`
- Test: `tests/converse/test_propose_edit_tool.py`

**Interfaces:**
- Consumes: `try_apply_op`, `EditProvenance`, `PASS_TOOLS`, `alpha.meta.models.new_edit_id`.
- Produces: `make_propose_edit_tool(harness, *, min_retire_samples=5, min_promote_samples=3) -> (schema, fn)` where `fn(tool, args, rationale) -> dict` returns `{"staged": True, "edit_id", "tool", "op": {...}, "summary", "valid": bool, "reason": str|None, "preview": dict}` and NEVER mutates `harness` (dry-run on a `deepcopy`). Consumed by Task 4.

- [ ] **Step 1: Write the failing test**

```python
# tests/converse/test_propose_edit_tool.py
import copy
from alpha.harness.doctrine import Doctrine
from alpha.harness.registry import SkillRegistry, MemoryStore
from alpha.harness.state import HarnessState
from alpha.converse.tools import make_propose_edit_tool

def _h():
    return HarnessState(doctrine=Doctrine(), skills=SkillRegistry.from_skills([]),
                        memory=MemoryStore.from_lessons([]))

def test_propose_stages_without_mutating_live():
    h = _h(); before = copy.deepcopy(h.to_dict())
    schema, fn = make_propose_edit_tool(h)
    out = fn(tool="process_memory", args={"lesson_id": "m1", "phases": ["trend"], "outcome": "win", "lesson": "x"},
             rationale="learned this")
    assert out["staged"] is True and out["valid"] is True and out["edit_id"]
    assert out["op"]["tool"] == "process_memory"
    assert h.to_dict() == before                     # live brain untouched (dry-run only)

def test_propose_invalid_reports_reason():
    h = _h()
    _schema, fn = make_propose_edit_tool(h)
    out = fn(tool="process_memory", args={"lesson_id": "m1", "outcome": "win", "lesson": "x"}, rationale="")
    assert out["staged"] is True and out["valid"] is False and out["reason"]   # missing rationale -> gate reject
```

- [ ] **Step 2: Run to verify it fails**

Run: `python -m pytest tests/converse/test_propose_edit_tool.py -v`
Expected: FAIL — `ImportError: cannot import name 'make_propose_edit_tool'`.

- [ ] **Step 3: Implement** — in `alpha/converse/tools.py` add (alongside `make_gated_write_tool`):

```python
import copy as _copy
from alpha.meta.models import new_edit_id
```
```python
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
```

- [ ] **Step 4: Run to verify it passes**

Run: `python -m pytest tests/converse/test_propose_edit_tool.py -v`
Expected: 2 PASS.

- [ ] **Step 5: Commit**

```bash
git add alpha/converse/tools.py tests/converse/test_propose_edit_tool.py
git commit -m "feat(converse): make_propose_edit_tool (stage a brain edit, dry-run, no live write)"
```

---

### Task 4: `write_mode` threading + staged materialization

**Files:**
- Modify: `alpha/converse/agent.py` (`build_converse_registry(..., write_mode)`)
- Modify: `alpha/converse/session.py` (`converse_project(..., write_mode)` + materialize staged → `project.staged_edits`)
- Test: `tests/converse/test_converse_project_stage.py`

**Interfaces:**
- Consumes: `make_propose_edit_tool` (T3), `StagedEdit` (T2).
- Produces: `build_converse_registry(harness, agent_llm, source, *, read_only=False, write_mode="apply")` — `write_mode ∈ {"apply","stage","none"}`; `read_only=True` forces no write tool (back-compat). `converse_project(..., write_mode="apply")` threads it and, for any `{"staged": True}` tool result, appends a `StagedEdit(status="pending")` to `project.staged_edits`. Consumed by Tasks 5/6.

- [ ] **Step 1: Write the failing test**

```python
# tests/converse/test_converse_project_stage.py
import copy
from datetime import date
import pandas as pd
from alpha.harness.doctrine import Doctrine
from alpha.harness.registry import SkillRegistry, MemoryStore
from alpha.harness.state import HarnessState
from alpha.data.source import FakeSource
from alpha.llm.client import MockLLMClient
from alpha.converse.store import ProjectStore
from alpha.converse.session import converse_project

def _h():
    return HarnessState(doctrine=Doctrine(), skills=SkillRegistry.from_skills([]), memory=MemoryStore.from_lessons([]))

def _src():
    cal = [date(2026, 6, 10)]
    snaps = {cal[0]: pd.DataFrame({"symbol": ["RUN"], "name": ["RUN"], "open": [1.0], "high": [1.0],
                                   "low": [1.0], "close": [1.0], "volume": [1], "prev_close": [1.0]})}
    bars = {"RUN": pd.DataFrame({"date": cal, "open": [1.0], "high": [1.0], "low": [1.0], "close": [1.0], "volume": [1]})}
    return FakeSource(calendar=cal, bars=bars, snapshots=snaps)

def test_stage_mode_stages_proposal_without_live_write(tmp_path):
    h = _h(); before = copy.deepcopy(h.to_dict())
    store = ProjectStore(tmp_path / "projects")
    chat = MockLLMClient([
        '{"tool": "propose_memory_edit", "args": {"tool": "process_memory", "args": '
        '{"lesson_id": "m1", "phases": ["trend"], "outcome": "win", "lesson": "x"}, "rationale": "learned"}}',
        "Proposed an edit for your review.",
    ])
    proj = converse_project("default", "remember this", harness=h, store=store,
                            agent_llm=MockLLMClient("{}"), chat_llm=chat, source=_src(), write_mode="stage")
    assert len(proj.staged_edits) == 1 and proj.staged_edits[0].status == "pending"
    assert proj.staged_edits[0].op["tool"] == "process_memory" and proj.staged_edits[0].valid is True
    assert h.to_dict() == before                                   # live brain untouched
    assert store.get("default").staged_edits[0].edit_id == proj.staged_edits[0].edit_id   # persisted
```

- [ ] **Step 2: Run to verify it fails**

Run: `python -m pytest tests/converse/test_converse_project_stage.py -v`
Expected: FAIL — `converse_project() got an unexpected keyword argument 'write_mode'`.

- [ ] **Step 3: Implement**
- `alpha/converse/agent.py` — change `build_converse_registry`:
```python
from alpha.converse.tools import make_decide_for_date_tool, make_gated_write_tool, make_propose_edit_tool

def build_converse_registry(harness: HarnessState, agent_llm, source,
                            *, read_only: bool = False, write_mode: str = "apply") -> ToolRegistry:
    reg = ToolRegistry()
    decide_schema, decide_fn = make_decide_for_date_tool(harness, agent_llm, source)
    reg.register("decide", decide_schema, decide_fn)
    mode = "none" if read_only else write_mode
    if mode == "apply":
        write_schema, write_fn = make_gated_write_tool(harness)
        reg.register("propose_memory_edit", write_schema, write_fn)
    elif mode == "stage":
        write_schema, write_fn = make_propose_edit_tool(harness)
        reg.register("propose_memory_edit", write_schema, write_fn)
    return reg
```
- `alpha/converse/session.py` — add `write_mode: str = "apply"` to the signature; pass it: `build_converse_registry(h, agent_llm, source, read_only=read_only, write_mode=write_mode)`; import `StagedEdit`; after step 6 (building `turn.tool_calls`), materialize staged results:
```python
    from alpha.converse.project import StagedEdit            # (top-level import preferred)
    for tc in turn.tool_calls:
        r = tc["result"]
        if isinstance(r, dict) and r.get("staged"):
            project.staged_edits.append(StagedEdit(
                edit_id=r["edit_id"], op=r["op"], summary=r.get("summary", ""),
                valid=bool(r.get("valid")), reason=r.get("reason"), preview=r.get("preview", {})))
```
(Place the loop before step 8 `store.put`.)

- [ ] **Step 4: Run to verify it passes + full suite green**

Run: `python -m pytest tests/converse/test_converse_project_stage.py -v && python -m pytest -q`
Expected: PASS; full suite green (default `write_mode="apply"` + `read_only` semantics keep §4 tests unchanged).

- [ ] **Step 5: Commit**

```bash
git add alpha/converse/agent.py alpha/converse/session.py tests/converse/test_converse_project_stage.py
git commit -m "feat(converse): write_mode (apply|stage|none) + stage->Project.staged_edits"
```

---

### Task 5: `workbench` service — skeleton + `/healthz` + `/converse` + `/project`

**Files:**
- Create: `workbench/__init__.py`, `workbench/app.py`, `workbench/__main__.py`
- Modify: `alpha/converse/workspace.py` (add `Workspace.artifacts()`)
- Test: `tests/workbench/test_workbench_service.py`

**Interfaces:**
- Consumes: `converse_project(..., write_mode="stage")` (T4), `LiveBrainStore` (T1), `ProjectStore`/`Workspace` (§4), `make_source`, `make_client`.
- Produces: `workbench.app.create_app() -> FastAPI` with `GET /healthz`, `POST /converse {text}`, `GET /project`; module-level test seam `set_llms(chat=None, agent=None)`. `Workspace.artifacts() -> list[str]` (git ls-files). Consumed by Tasks 6/7/8. `DEFAULT_PROJECT_ID = "default"`.

- [ ] **Step 1: Add `Workspace.artifacts()` first** — in `alpha/converse/workspace.py`:
```python
    def artifacts(self) -> list[str]:
        """Committed artifact paths in this workspace (git ls-files), or [] if not a repo."""
        try:
            out = self._run(["ls-files"])           # reuse the existing subprocess git runner
            return [line for line in out.splitlines() if line.strip()]
        except Exception:
            return []
```
(Read `workspace.py` first to match its `_run`/subprocess helper name + signature; if `_run` returns a CompletedProcess, use `.stdout`.)

- [ ] **Step 2: Write the failing test**

```python
# tests/workbench/test_workbench_service.py
import pytest
pytest.importorskip("fastapi", reason="install: pip install -e '.[web,sonia]'")
from fastapi.testclient import TestClient

def _client(tmp_path, monkeypatch):
    monkeypatch.setenv("ALPHA_LIVE_BRAIN_DIR", str(tmp_path / "brain"))
    monkeypatch.setenv("ALPHA_PROJECTS_DIR", str(tmp_path / "projects"))
    monkeypatch.setenv("ALPHA_WORKSPACE_DIR", str(tmp_path / "ws"))
    from workbench.app import create_app, set_llms
    from alpha.llm.client import MockLLMClient
    set_llms(chat=MockLLMClient([
        '{"tool": "propose_memory_edit", "args": {"tool": "process_memory", "args": '
        '{"lesson_id": "m1", "phases": ["trend"], "outcome": "win", "lesson": "x"}, "rationale": "learned"}}',
        "Staged an edit for your review."]),
        agent=MockLLMClient("{}"))
    return TestClient(create_app())

def test_healthz(tmp_path, monkeypatch):
    assert _client(tmp_path, monkeypatch).get("/healthz").json()["ok"] is True

def test_converse_stages_proposal(tmp_path, monkeypatch):
    c = _client(tmp_path, monkeypatch)
    r = c.post("/converse", json={"text": "remember this"}).json()
    assert r["assistant_text"] == "Staged an edit for your review."
    assert len(r["staged_edits"]) == 1 and r["staged_edits"][0]["status"] == "pending"
    proj = c.get("/project").json()
    assert proj["project_id"] == "default" and len(proj["staged_edits"]) == 1
```

> **Implementer note:** read `sonia/app.py` (the whole file) and mirror its `create_app()` + env-store-helper structure. `set_llms` is a module-level test seam (mirror `alpha_web/app.py::set_sonia_client`): module globals `_CHAT_LLM`/`_AGENT_LLM` default `None`, helper `_chat_llm()`/`_agent_llm()` return the override or `make_client("converse")`/`make_client("agent")`. `/converse` is read+stage only (no live write) → no brain lock needed here.

- [ ] **Step 3: Run to verify it fails**

Run: `python -m pytest tests/workbench/test_workbench_service.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'workbench'`.

- [ ] **Step 4: Implement** — create the package:

`workbench/__init__.py`: empty.

`workbench/app.py` (mirror `sonia/app.py`):
```python
from __future__ import annotations
import os, threading
from fastapi import FastAPI
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from alpha.llm.config import make_client
from alpha.data.registry import make_source
from alpha.meta.store import LiveBrainStore
from alpha.converse.store import ProjectStore
from alpha.converse.workspace import Workspace
from alpha.converse.session import converse_project

DEFAULT_PROJECT_ID = "default"
_MUTATION_LOCK = threading.Lock()
_CHAT_LLM = None
_AGENT_LLM = None

def set_llms(*, chat=None, agent=None) -> None:          # test seam
    global _CHAT_LLM, _AGENT_LLM
    _CHAT_LLM, _AGENT_LLM = chat, agent

def _chat_llm():  return _CHAT_LLM if _CHAT_LLM is not None else make_client("converse")
def _agent_llm(): return _AGENT_LLM if _AGENT_LLM is not None else make_client("agent")
def _brain_store():   return LiveBrainStore(os.environ.get("ALPHA_LIVE_BRAIN_DIR", "./state/brain"))
def _project_store(): return ProjectStore(os.environ.get("ALPHA_PROJECTS_DIR", "./state/projects"))
def _workspace():
    ws = Workspace(os.path.join(os.environ.get("ALPHA_WORKSPACE_DIR", "./state/workspaces"), DEFAULT_PROJECT_ID))
    ws.init()
    return ws

class ConverseIn(BaseModel):
    text: str = ""

def _project_view(proj) -> dict:
    return {"project_id": proj.project_id,
            "messages": [m.model_dump() for m in proj.messages],
            "turns": [t.model_dump() for t in proj.turns],
            "staged_edits": [e.model_dump() for e in proj.staged_edits],
            "artifacts": _workspace().artifacts()}

def create_app() -> FastAPI:
    app = FastAPI(title="Workbench · evolving-alpha conversational face")

    @app.get("/healthz")
    def healthz():
        s = _brain_store()
        return {"ok": True, "brain_live": s.is_live(), "edit_count": s.edit_count()}

    @app.post("/converse")
    def converse_ep(body: ConverseIn):
        with _MUTATION_LOCK:
            h, _log = _brain_store().load()                 # read live brain for context/decide
            try:
                proj = converse_project(DEFAULT_PROJECT_ID, body.text, harness=h, store=_project_store(),
                                        agent_llm=_agent_llm(), chat_llm=_chat_llm(), source=make_source(),
                                        workspace=_workspace(), write_mode="stage")
            except Exception as e:                           # never 500 — keep the user turn
                store = _project_store(); proj = store.get(DEFAULT_PROJECT_ID)
                from alpha.converse.project import new_project, new_turn
                if proj is None:
                    proj = new_project(); proj.project_id = DEFAULT_PROJECT_ID
                t = new_turn(body.text); t.final_text = f"(workbench couldn't respond: {type(e).__name__})"
                proj.turns.append(t); store.put(proj)
            last = proj.turns[-1].final_text if proj.turns else ""
            return {"project_id": proj.project_id, "assistant_text": last,
                    "staged_edits": [e.model_dump() for e in proj.staged_edits if e.status == "pending"],
                    "artifacts": _workspace().artifacts()}

    @app.get("/project")
    def get_project():
        proj = _project_store().get(DEFAULT_PROJECT_ID)
        if proj is None:
            return {"project_id": DEFAULT_PROJECT_ID, "messages": [], "turns": [],
                    "staged_edits": [], "artifacts": []}
        return _project_view(proj)

    return app

app = create_app()
```

`workbench/__main__.py` (copy `sonia/__main__.py`, swap names):
```python
from __future__ import annotations
import os

def main() -> None:
    import uvicorn
    host = os.environ.get("ALPHA_WORKBENCH_HOST", "127.0.0.1")
    port = int(os.environ.get("ALPHA_WORKBENCH_PORT", "8820"))
    uvicorn.run("workbench.app:app", host=host, port=port, reload=False)

if __name__ == "__main__":
    main()
```

- [ ] **Step 5: Run to verify it passes + full suite**

Run: `python -m pytest tests/workbench/test_workbench_service.py -v && python -m pytest -q`
Expected: PASS; full suite green.

- [ ] **Step 6: Commit**

```bash
git add workbench/ alpha/converse/workspace.py tests/workbench/test_workbench_service.py
git commit -m "feat(workbench): service skeleton + /healthz + /converse (stage) + /project; Workspace.artifacts()"
```

---

### Task 6: `workbench` gated mutation — `/edits/{id}/approve|reject` + `/rollback`

**Files:**
- Modify: `workbench/app.py`
- Test: `tests/workbench/test_workbench_mutation.py`

**Interfaces:**
- Consumes: `LiveBrainStore.lock()` (T1), `StagedEdit` (T2), `try_apply_op`, `EditProvenance`, `PASS_TOOLS`, `RefineOp`, `MetaTools`.
- Produces: `POST /edits/{eid}/approve` (apply the staged op through the gate under the lock; mark approved + `applied_seq` + `snapshot_before`), `POST /edits/{eid}/reject` (mark rejected, no brain touch), `POST /rollback` (restore the last `snapshot_before`). 404 on unknown id.

- [ ] **Step 1: Write the failing test**

```python
# tests/workbench/test_workbench_mutation.py
import pytest
pytest.importorskip("fastapi")
from fastapi.testclient import TestClient

def _client(tmp_path, monkeypatch):
    monkeypatch.setenv("ALPHA_LIVE_BRAIN_DIR", str(tmp_path / "brain"))
    monkeypatch.setenv("ALPHA_PROJECTS_DIR", str(tmp_path / "projects"))
    monkeypatch.setenv("ALPHA_WORKSPACE_DIR", str(tmp_path / "ws"))
    from workbench.app import create_app, set_llms
    from alpha.llm.client import MockLLMClient
    set_llms(chat=MockLLMClient([
        '{"tool": "propose_memory_edit", "args": {"tool": "process_memory", "args": '
        '{"lesson_id": "m1", "phases": ["trend"], "outcome": "win", "lesson": "x"}, "rationale": "learned"}}',
        "Staged."]), agent=MockLLMClient("{}"))
    return TestClient(create_app())

def _stage_one(c):
    c.post("/converse", json={"text": "remember"})
    return c.get("/project").json()["staged_edits"][0]["edit_id"]

def test_approve_applies_through_gate(tmp_path, monkeypatch):
    c = _client(tmp_path, monkeypatch)
    eid = _stage_one(c)
    assert c.get("/healthz").json()["edit_count"] == 0
    r = c.post(f"/edits/{eid}/approve")
    assert r.status_code == 200 and r.json()["status"] == "approved"
    assert c.get("/healthz").json()["edit_count"] == 1            # the live brain gained the edit
    assert c.post(f"/edits/{eid}/approve").status_code == 404     # no longer pending

def test_reject_leaves_brain_unchanged(tmp_path, monkeypatch):
    c = _client(tmp_path, monkeypatch)
    eid = _stage_one(c)
    assert c.post(f"/edits/{eid}/reject").json()["status"] == "rejected"
    assert c.get("/healthz").json()["edit_count"] == 0

def test_rollback_after_approve(tmp_path, monkeypatch):
    c = _client(tmp_path, monkeypatch)
    eid = _stage_one(c); c.post(f"/edits/{eid}/approve")
    assert c.get("/healthz").json()["edit_count"] == 1
    assert c.post("/rollback").json()["ok"] is True
    assert c.get("/healthz").json()["edit_count"] == 0            # restored to the pre-approve snapshot
```

- [ ] **Step 2: Run to verify it fails**

Run: `python -m pytest tests/workbench/test_workbench_mutation.py -v`
Expected: FAIL — 404/405 (routes missing).

- [ ] **Step 3: Implement** — add to `workbench/app.py` (inside `create_app`, before `return app`), plus the imports at top:
```python
from alpha.harness.metatools import MetaTools
from alpha.harness.edit_log import EditProvenance
from alpha.refine.apply import try_apply_op, ALL_TOOLS
from alpha.refine.ops import RefineOp, PASS_TOOLS
```
```python
    def _find(proj, eid):
        return next((e for e in proj.staged_edits if e.edit_id == eid and e.status == "pending"), None)

    @app.post("/edits/{eid}/approve")
    def approve_edit(eid: str):
        with _MUTATION_LOCK:
            pstore = _project_store(); proj = pstore.get(DEFAULT_PROJECT_ID)
            se = _find(proj, eid) if proj else None
            if se is None:
                return JSONResponse({"error": "not found"}, status_code=404)
            bstore = _brain_store()
            with bstore.lock():
                h, log = bstore.load()
                if not bstore.is_live():
                    bstore.save(h, log)
                snap = bstore.snapshot(f"approve-{eid}")
                op = RefineOp(tool=se.op["tool"], args=dict(se.op["args"]), rationale=se.op.get("rationale", ""))
                rec, reason = try_apply_op(MetaTools(h, log), h, op, allowed=PASS_TOOLS["M"],
                                           min_retire_samples=5, min_promote_samples=3,
                                           provenance=EditProvenance(path="teaching", proposer="hermes"))
                if rec is not None:
                    bstore.save(h, log)
                    se.status, se.applied_seq, se.snapshot_before, se.reason = "approved", rec.seq, snap, None
                else:
                    se.status, se.reason = "rejected", reason
            pstore.put(proj)
            return {"edit_id": eid, "status": se.status, "reason": se.reason}

    @app.post("/edits/{eid}/reject")
    def reject_edit(eid: str):
        with _MUTATION_LOCK:
            pstore = _project_store(); proj = pstore.get(DEFAULT_PROJECT_ID)
            se = _find(proj, eid) if proj else None
            if se is None:
                return JSONResponse({"error": "not found"}, status_code=404)
            se.status = "rejected"; pstore.put(proj)
            return {"edit_id": eid, "status": "rejected"}

    @app.post("/rollback")
    def rollback():
        with _MUTATION_LOCK:
            pstore = _project_store(); proj = pstore.get(DEFAULT_PROJECT_ID)
            snaps = [e.snapshot_before for e in (proj.staged_edits if proj else []) if e.snapshot_before]
            if not snaps:
                return JSONResponse({"error": "nothing to roll back"}, status_code=404)
            bstore = _brain_store()
            with bstore.lock():
                bstore.restore(snaps[-1])
            return {"ok": True}
```

- [ ] **Step 4: Run to verify it passes + full suite**

Run: `python -m pytest tests/workbench/test_workbench_mutation.py -v && python -m pytest -q`
Expected: PASS; full suite green.

- [ ] **Step 5: Commit**

```bash
git add workbench/app.py tests/workbench/test_workbench_mutation.py
git commit -m "feat(workbench): approve/reject/rollback (gated apply under the brain lock)"
```

---

### Task 7: `WorkbenchClient` (thin httpx, mirror SoniaClient)

**Files:**
- Create: `alpha_web/workbench_client.py`
- Test: `tests/web/test_workbench_page.py` (client half)

**Interfaces:**
- Produces: `WorkbenchClient(base_url=None, *, client=None, timeout=30.0)` with `healthz()`, `converse(text) -> dict`, `get_project() -> dict`, `approve_edit(eid) -> dict`, `reject_edit(eid) -> dict`, `rollback() -> dict`. Base URL from `ALPHA_WORKBENCH_URL` (default `http://127.0.0.1:8820`); test-injectable `client=`. Consumed by Task 8.

- [ ] **Step 1: Write the failing test**

```python
# tests/web/test_workbench_page.py
import pytest
pytest.importorskip("fastapi")
from fastapi.testclient import TestClient
from alpha_web.workbench_client import WorkbenchClient

def _wb_tc(tmp_path, monkeypatch):
    monkeypatch.setenv("ALPHA_LIVE_BRAIN_DIR", str(tmp_path / "brain"))
    monkeypatch.setenv("ALPHA_PROJECTS_DIR", str(tmp_path / "projects"))
    monkeypatch.setenv("ALPHA_WORKSPACE_DIR", str(tmp_path / "ws"))
    from workbench.app import create_app, set_llms
    from alpha.llm.client import MockLLMClient
    set_llms(chat=MockLLMClient([
        '{"tool": "propose_memory_edit", "args": {"tool": "process_memory", "args": '
        '{"lesson_id": "m1", "outcome": "win", "lesson": "x"}, "rationale": "learned"}}', "Staged."]),
        agent=MockLLMClient("{}"))
    return TestClient(create_app())

def test_workbench_client_converse_and_approve(tmp_path, monkeypatch):
    wc = WorkbenchClient(client=_wb_tc(tmp_path, monkeypatch))
    r = wc.converse("remember")
    eid = r["staged_edits"][0]["edit_id"]
    assert wc.approve_edit(eid)["status"] == "approved"
    assert wc.get_project()["project_id"] == "default"
```

- [ ] **Step 2: Run to verify it fails**

Run: `python -m pytest tests/web/test_workbench_page.py::test_workbench_client_converse_and_approve -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'alpha_web.workbench_client'`.

- [ ] **Step 3: Implement** — copy `alpha_web/sonia_client.py` to `alpha_web/workbench_client.py`, rename the class to `WorkbenchClient`, base URL env `ALPHA_WORKBENCH_URL` (default `http://127.0.0.1:8820`), and replace the methods with:
```python
    def healthz(self): return self._request("GET", "/healthz")
    def converse(self, text: str) -> dict: return self._request("POST", "/converse", json={"text": text})
    def get_project(self) -> dict: return self._request("GET", "/project")
    def approve_edit(self, eid: str) -> dict: return self._request("POST", f"/edits/{eid}/approve")
    def reject_edit(self, eid: str) -> dict: return self._request("POST", f"/edits/{eid}/reject")
    def rollback(self) -> dict: return self._request("POST", "/rollback")
```
(Keep the exact `__init__`/`_request` body from `SoniaClient`.)

- [ ] **Step 4: Run to verify it passes**

Run: `python -m pytest tests/web/test_workbench_page.py -k client -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add alpha_web/workbench_client.py tests/web/test_workbench_page.py
git commit -m "feat(web): WorkbenchClient (thin httpx over the workbench service)"
```

---

### Task 8: `alpha_web` Workbench nav + page + HTMX approve/reject

**Files:**
- Modify: `alpha_web/app.py` (Workbench nav entry + routes + a `_workbench()` helper)
- Create: `alpha_web/templates/workbench.html`
- Test: `tests/web/test_workbench_page.py` (page half)

**Interfaces:**
- Consumes: `WorkbenchClient` (T7), the existing `render`/NAV/`set_*_client` machinery.
- Produces: NAV `{"path": "/workbench", "key": "workbench", "label": "Workbench"}`; `GET /workbench` (render the thread + pending proposals + artifacts), `POST /workbench/say` (call `converse`, re-render), `POST /workbench/edits/{eid}/approve|reject` (HTMX empty-200 row-removal), `POST /workbench/rollback`. Workbench-down → banner, never a 500.

- [ ] **Step 1: Read** `alpha_web/app.py` (the `_sonia()`/`set_sonia_client` seam, NAV, `render`, and the conflicts routes `app.py:251-263`) and `alpha_web/templates/conflicts.html`. Mirror them: add a `_workbench()` + `set_workbench_client()` seam exactly like `_sonia()`/`set_sonia_client`.

- [ ] **Step 2: Write the failing test** (append to `tests/web/test_workbench_page.py`)

```python
def _web_client(tmp_path, monkeypatch):
    from alpha_web.app import app, set_workbench_client
    set_workbench_client(WorkbenchClient(client=_wb_tc(tmp_path, monkeypatch)))
    return TestClient(app)

def test_workbench_page_renders(tmp_path, monkeypatch):
    tc = _web_client(tmp_path, monkeypatch)
    tc.post("/workbench/say", data={"text": "remember"})              # stage a proposal
    r = tc.get("/workbench")
    assert r.status_code == 200 and "Workbench" in r.text and "process_memory" in r.text

def test_workbench_approve_empty_200(tmp_path, monkeypatch):
    tc = _web_client(tmp_path, monkeypatch)
    tc.post("/workbench/say", data={"text": "remember"})
    import re
    eid = re.search(r'conflict|edit-([0-9a-f-]+)', tc.get("/workbench").text)   # the proposal row id
    # fetch the edit id via the workbench project directly for robustness:
    from alpha_web.app import _workbench
    pid = _workbench().get_project()["staged_edits"][0]["edit_id"]
    r = tc.post(f"/workbench/edits/{pid}/approve")
    assert r.status_code == 200 and r.text == ""                      # empty-200 row removal
```

> **Implementer note:** the row id scheme is yours — use `id="edit-{{ e.edit_id }}"` on each proposal's single root element and target it with `hx-target="#edit-{{ e.edit_id }}"`, `hx-swap="outerHTML"`, returning `Response(status_code=200, content="")` on success (mirror the conflicts UI `resolve` route exactly, including escaping any reflected value with `html.escape` — but prefer returning empty content with no reflection). Drop the brittle regex; assert via `_workbench().get_project()` as shown.

- [ ] **Step 3: Run to verify it fails**

Run: `python -m pytest tests/web/test_workbench_page.py -k page -v`
Expected: FAIL — `GET /workbench` 404.

- [ ] **Step 4: Implement**
- `alpha_web/app.py`: add the `_workbench()`/`set_workbench_client()` seam (mirror `_sonia`/`set_sonia_client`), the NAV entry (after `/conflicts`), and the routes:
  - `GET /workbench` → `try: data = _workbench().get_project()` then `render(request, "workbench.html", {"active": "workbench", "project": data, "wb_down": False})`; `except Exception` → render with `wb_down=True` + empty project (never 500).
  - `POST /workbench/say` (form `text`) → `_workbench().converse(text)`; redirect/re-render `GET /workbench` (return the rendered page, or a 200 with `HX-Redirect: /workbench` if the form posts via htmx — mirror the cockpit's message-send pattern).
  - `POST /workbench/edits/{eid}/approve` and `/reject` → call the client; return `Response(status_code=200, content="")` (empty-200 row removal). On error → an inline banner fragment with `html.escape(eid)` (the conflicts-UI XSS guard).
  - `POST /workbench/rollback` → `_workbench().rollback()`; return empty-200 or re-render.
- `alpha_web/templates/workbench.html`: `{% extends "base.html" %}` — a chat thread (`project.turns`: `t.user_text` / `t.final_text`), a **say** form (`POST /workbench/say`), an **artifacts** panel (`project.artifacts`), and a **pending proposals** panel: for each `e in project.staged_edits` where `e.status == "pending"`, a single root `id="edit-{{ e.edit_id }}"` showing `e.op.tool` + `e.op.rationale` + (if `e.valid`) the preview, with **Approve**/**Reject** buttons (`hx-post`, `hx-target="#edit-{{ e.edit_id }}"`, `hx-swap="outerHTML"`). All via Jinja2 `{{ }}`. A `wb_down` banner.

- [ ] **Step 5: Run to verify it passes + full suite**

Run: `python -m pytest tests/web/test_workbench_page.py -v && python -m pytest -q`
Expected: PASS; full suite green.

- [ ] **Step 6: Commit**

```bash
git add alpha_web/app.py alpha_web/templates/workbench.html tests/web/test_workbench_page.py
git commit -m "feat(web): Workbench nav + page (converse + approve/reject proposals, HTMX)"
```

---

## Self-Review

**Spec coverage:**
- Independent `workbench` service (:8820) → Tasks 5/6 (+ `__main__`). ✓
- File-locked `LiveBrainStore`, Sonia holds it too → Task 1. ✓
- Preview/approve: stage tool + materialization + approve-through-gate-under-lock → Tasks 3/4/6. ✓
- Single default project, reuse §4 Project/Store/Workspace + §5 provenance → Tasks 4/5/6. ✓
- `alpha_web` Workbench page + WorkbenchClient, HTMX empty-200, Jinja2-escaped → Tasks 7/8. ✓
- Never-500 conversation, lock timeout→RuntimeError, 404 on unknown ids → Tasks 1/5/6. ✓
- Out of scope (multi-project UI, apply-direct mode, live-order, queue-feeding) → not built. ✓

**Placeholder scan:** every code step shows exact code; mirror-heavy steps (workbench/app.py↔sonia/app.py, WorkbenchClient↔SoniaClient, workbench.html↔conflicts.html) name the exact reference file + the precise contract (empty-200, single-root id, escaping). Task 8's test note replaces a brittle regex with a `_workbench().get_project()` lookup — an explicit instruction, not a placeholder.

**Type consistency:** `LiveBrainStore.lock()` (T1) is used in T6 and Sonia. `StagedEdit`/`Project.staged_edits` (T2) are produced in T4, consumed in T6/T8. `make_propose_edit_tool` (T3) is wired by `build_converse_registry(write_mode="stage")` (T4), driven by the workbench `/converse` (T5). `converse_project(..., write_mode)` (T4) is called by T5. `Workspace.artifacts()` (T5) is read by T5/T8. `set_llms`/`set_workbench_client` seams (T5/T8) are used by the T5–T8 tests. `try_apply_op(allowed=PASS_TOOLS["M"], provenance=teaching/hermes)` is identical in the stage dry-run (T3) and the approve apply (T6).
