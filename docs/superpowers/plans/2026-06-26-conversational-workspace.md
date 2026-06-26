# Conversational Workspace §4 — Project = {Conversation + Git Workspace + H-Version} Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add the §4 PROJECT/WORKSPACE layer on top of the Phase-1A/1B conversational face: a **project** binds (a) a resumable conversation, (b) a per-project **git-backed workspace** for artifacts, and (c) a per-turn **H-version provenance ref** into `SnapshotStore`. ONE shared evolving brain (not forked); the version authority stays `SnapshotStore` ints (the same authority §5's `parent_checkpoint_version` reads). A pinned project is read-only.

**Architecture:** Purely additive — new files under `alpha/converse/` (`project.py`, `store.py`, `workspace.py`, `session.py`); the existing `converse()`, `run_conversation`, `build_converse_registry`/`build_system_prompt`, the day-agent, `SnapshotStore`, and `try_apply_op` are reused unchanged (the one tiny edit is an additive `read_only=False` kwarg on `build_converse_registry`). Conversation/project persistence is **JSON** (mirror `alpha/meta/store.py::SessionStore`, NOT SQLite — SQLite is reserved for the vendored Hermes `state.db`); artifacts are committed into a **git** workspace via subprocess (no new dep). Per-turn `h_version = SnapshotStore.latest()` (or `project.h_pin`).

**Tech Stack:** Python ≥3.11, pydantic v2, stdlib `subprocess` (git CLI), pytest. Reuses `alpha.converse.agent.{build_converse_registry, build_system_prompt}`, `alpha.converse.loop.{run_conversation, ConversationResult}`, `alpha.llm.chat.ChatMessage`, `alpha.harness.snapshot.SnapshotStore` (`.latest()`, `.load(v)`), `alpha.eval.decision.DecisionPackage`, `alpha.meta.models.{new_session_id, now_iso}`.

## Global Constraints

- **Python `>=3.11`**, pydantic v2. Deterministic tests: `MockLLMClient` + `FakeSource` (offline); git workspace tests run under `tmp_path` with isolated `HOME` + git author env so they never touch the real repo.
- **Additive:** new files + one additive `read_only=False` kwarg on `build_converse_registry`. The existing suite (currently **611 passed**) must stay green; `converse()` and its tests unchanged (a NEW `converse_project()` is the persisted entry).
- **JSON persistence:** `ProjectStore` mirrors `SessionStore` exactly (`_atomic_write` + `_path` `.resolve()`+`is_relative_to` traversal guard, `model_validate_json`, newest-first tolerant `list()`). NO SQLite here.
- **Version authority = `SnapshotStore` ints** (the same authority as §5). `ProjectTurn.h_version = project.h_pin if pinned else snapshots.latest()` (None if no `SnapshotStore` wired). One shared brain — NO per-project fork; isolation is the git workspace.
- **Pinned project = read-only:** when `project.h_pin` is set, the gated write tool (`propose_memory_edit`) is NOT registered (decide/read only).
- **Persisted `tool_calls` must be JSON-safe:** a `DecisionPackage` tool result is serialized (`model_dump()`) before being stored on a `ProjectTurn`; the raw object is what gets committed to the workspace.
- **Git via subprocess CLI** (no GitPython). English; follow existing patterns.

## File Structure

- Create: `alpha/converse/project.py` (`Project`, `ProjectTurn`, `new_project`, `new_turn`), `alpha/converse/store.py` (`ProjectStore`), `alpha/converse/workspace.py` (`Workspace`), `alpha/converse/session.py` (`converse_project`).
- Modify: `alpha/converse/agent.py` (additive `read_only=False` on `build_converse_registry`).
- Tests: `tests/converse/test_project_models.py`, `test_project_store.py`, `test_workspace.py`, `test_converse_project.py`, `test_project_isolation.py`.

---

### Task 1: `Project` + `ProjectTurn` models

**Files:**
- Create: `alpha/converse/project.py`
- Test: `tests/converse/test_project_models.py`

**Interfaces:**
- Produces: `ProjectTurn(turn_id, user_text, final_text="", tool_calls=[], h_version=None, created_at="")`; `Project(project_id, created_at="", title="", h_pin=None, messages: list[ChatMessage]=[], turns: list[ProjectTurn]=[])`; `new_project(title="") -> Project`; `new_turn(user_text) -> ProjectTurn`. Consumed by Tasks 2, 4.

- [ ] **Step 1: Write the failing test**

```python
# tests/converse/test_project_models.py
from alpha.llm.chat import ChatMessage
from alpha.converse.project import Project, ProjectTurn, new_project, new_turn

def test_project_round_trips_with_turns_and_messages():
    p = new_project(title="TSLA squeeze")
    assert p.project_id and p.created_at and p.title == "TSLA squeeze" and p.h_pin is None
    p.messages.append(ChatMessage(role="user", text="hi"))
    t = new_turn("what's your read?"); t.final_text = "RUN looks strong"; t.h_version = 3
    t.tool_calls = [{"tool": "decide", "args": {"date": "2026-06-12"}, "result": {"candidates": []}}]
    p.turns.append(t)
    assert Project.model_validate_json(p.model_dump_json()) == p

def test_new_turn_has_id_and_timestamp():
    t = new_turn("x")
    assert t.turn_id and t.created_at and t.h_version is None and t.final_text == ""
```

- [ ] **Step 2: Run to verify it fails**

Run: `python -m pytest tests/converse/test_project_models.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'alpha.converse.project'`.

- [ ] **Step 3: Implement**

```python
# alpha/converse/project.py
from __future__ import annotations
from pydantic import BaseModel, Field
from alpha.llm.chat import ChatMessage
from alpha.meta.models import new_session_id, now_iso

class ProjectTurn(BaseModel):
    turn_id: str
    user_text: str
    final_text: str = ""
    tool_calls: list[dict] = Field(default_factory=list)   # JSON-safe (DecisionPackage results dumped)
    h_version: int | None = None                           # the SnapshotStore version this turn ran against
    created_at: str = ""

class Project(BaseModel):
    """One persisted conversation/workspace engagement. ONE shared brain — h_pin (optional) only changes
    which H-version this project READS; never a private brain copy."""
    project_id: str
    created_at: str = ""
    title: str = ""
    h_pin: int | None = None
    messages: list[ChatMessage] = Field(default_factory=list)
    turns: list[ProjectTurn] = Field(default_factory=list)

def new_project(title: str = "") -> Project:
    return Project(project_id=new_session_id(), created_at=now_iso(), title=title)

def new_turn(user_text: str) -> ProjectTurn:
    return ProjectTurn(turn_id=new_session_id(), user_text=user_text, created_at=now_iso())
```

- [ ] **Step 4: Run to verify it passes**

Run: `python -m pytest tests/converse/test_project_models.py -v`
Expected: 2 PASS.

- [ ] **Step 5: Commit**

```bash
git add alpha/converse/project.py tests/converse/test_project_models.py
git commit -m "feat(converse): Project + ProjectTurn models"
```

---

### Task 2: `ProjectStore` (atomic JSON, mirror `SessionStore`)

**Files:**
- Create: `alpha/converse/store.py`
- Test: `tests/converse/test_project_store.py`

**Interfaces:**
- Consumes: `Project` (Task 1).
- Produces: `ProjectStore(root)` with `.put(project) -> Path`, `.get(project_id) -> Project | None`, `.list() -> list[Project]` (newest-first, tolerant of garbage files), `.delete(project_id)` (idempotent), `_path` with the `.resolve()`+`is_relative_to` traversal guard. Consumed by Task 4.

- [ ] **Step 1: Write the failing test**

```python
# tests/converse/test_project_store.py
import pytest
from alpha.converse.project import new_project
from alpha.converse.store import ProjectStore

def test_put_get_list_delete(tmp_path):
    s = ProjectStore(tmp_path)
    p = new_project("a"); s.put(p)
    assert s.get(p.project_id) == p
    assert [x.project_id for x in s.list()] == [p.project_id]
    s.delete(p.project_id)
    assert s.get(p.project_id) is None and s.list() == []

def test_path_traversal_guard(tmp_path):
    with pytest.raises(ValueError):
        ProjectStore(tmp_path)._path("../escape")
```

- [ ] **Step 2: Run to verify it fails**

Run: `python -m pytest tests/converse/test_project_store.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'alpha.converse.store'`.

- [ ] **Step 3: Implement** — read `alpha/meta/store.py::SessionStore` FIRST, then mirror it for `Project` (inline `_atomic_write` to avoid importing meta private names; copy the `_path` guard verbatim; `list()` newest-first by `project_id`, tolerant of non-json/garbage files; `delete` = `unlink(missing_ok=True)`). The `alpha/meta/conflict_store.py::ConflictQueue` (from §5) is the same pattern recently applied — you may use it as a second reference.

- [ ] **Step 4: Run to verify it passes**

Run: `python -m pytest tests/converse/test_project_store.py -v`
Expected: 2 PASS.

- [ ] **Step 5: Commit**

```bash
git add alpha/converse/store.py tests/converse/test_project_store.py
git commit -m "feat(converse): ProjectStore (atomic by-id JSON, mirrors SessionStore)"
```

---

### Task 3: `Workspace` (per-project git-backed artifact dir)

**Files:**
- Create: `alpha/converse/workspace.py`
- Test: `tests/converse/test_workspace.py`

**Interfaces:**
- Consumes: `alpha.eval.decision.DecisionPackage`.
- Produces: `Workspace(root)` with `.init()` (idempotent `git init -q` + local user.name/email; no-op if `.git` exists), `.commit_artifact(relpath, data: str, message) -> str` (write file under root with a traversal guard, `git add` + `git commit -q`, return `git rev-parse HEAD`), `.put_decision(pkg: DecisionPackage) -> str` (write `<pkg.date>.json` via `pkg.model_dump_json()` then commit — the §4.2 "DecisionPackage as a recognized typed artifact" path). Consumed by Task 4.

- [ ] **Step 1: Write the failing test**

```python
# tests/converse/test_workspace.py
import subprocess
from datetime import date
from alpha.eval.decision import DecisionPackage
from alpha.converse.workspace import Workspace

def _git(args, cwd):
    return subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True).stdout.strip()

def test_init_and_commit_artifact(tmp_path):
    ws = Workspace(tmp_path); ws.init()
    assert (tmp_path / ".git").exists()
    ws.init()                                              # idempotent: second init is a no-op
    sha = ws.commit_artifact("note.md", "hello", "add note")
    assert sha and "note.md" in _git(["ls-files"], tmp_path)

def test_put_decision_writes_and_commits_typed_artifact(tmp_path):
    ws = Workspace(tmp_path); ws.init()
    pkg = DecisionPackage(date=date(2026, 6, 12), regime_read="trend frontside")
    ws.put_decision(pkg)
    written = (tmp_path / "2026-06-12.json").read_text()
    assert DecisionPackage.model_validate_json(written) == pkg
    assert "2026-06-12.json" in _git(["ls-files"], tmp_path)

def test_traversal_guard(tmp_path):
    import pytest
    ws = Workspace(tmp_path); ws.init()
    with pytest.raises(ValueError):
        ws.commit_artifact("../escape.txt", "x", "m")
```

> **Implementer note:** run the git subprocesses with `check=True`, `cwd=root`, and an env that isolates author identity so tests are deterministic and never read the user's global git config — pass `env={**os.environ, "GIT_AUTHOR_NAME": "spike", "GIT_AUTHOR_EMAIL": "spike@local", "GIT_COMMITTER_NAME": "spike", "GIT_COMMITTER_EMAIL": "spike@local", "HOME": str(root)}` (and set `user.name`/`user.email` locally in `init()`). Confirm `DecisionPackage`'s required fields by reading `alpha/eval/decision.py` (the test builds a minimal one — `date` + `regime_read`; adjust if more are required, do not change the model).

- [ ] **Step 2: Run to verify it fails**

Run: `python -m pytest tests/converse/test_workspace.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'alpha.converse.workspace'`.

- [ ] **Step 3: Implement** `alpha/converse/workspace.py` per the interface above (subprocess git, traversal-guarded writes, isolated env in `init()`/commits).

- [ ] **Step 4: Run to verify it passes**

Run: `python -m pytest tests/converse/test_workspace.py -v`
Expected: 3 PASS.

- [ ] **Step 5: Commit**

```bash
git add alpha/converse/workspace.py tests/converse/test_workspace.py
git commit -m "feat(converse): git-backed per-project Workspace + put_decision"
```

---

### Task 4: `converse_project` — persisted, provenance-stamped turn

**Files:**
- Create: `alpha/converse/session.py`
- Modify: `alpha/converse/agent.py` (additive `read_only=False` on `build_converse_registry`)
- Test: `tests/converse/test_converse_project.py`

**Interfaces:**
- Consumes: `ProjectStore` (T2), `Workspace` (T3), `Project`/`new_project`/`new_turn` (T1), `build_converse_registry`/`build_system_prompt` (agent.py), `run_conversation` (loop.py), `SnapshotStore`.
- Produces: `converse_project(project_id, user_text, *, harness, store, snapshots=None, agent_llm, chat_llm, source, workspace=None, max_iters=8) -> Project` — load-or-create the project; resolve the H-version (`h_pin` → `snapshots.load(pin)` read-only, else live `harness` + `snapshots.latest()`); reuse `build_converse_registry(h, agent_llm, source, read_only=<pinned>)` + `build_system_prompt`; append the user message; `run_conversation`; persist a `ProjectTurn` (final_text + JSON-safe tool_calls + h_version) + the extended messages; commit any `DecisionPackage` tool result to `workspace`; `store.put(project)`.

- [ ] **Step 1: Write the failing test**

```python
# tests/converse/test_converse_project.py
from datetime import date
import pandas as pd
from alpha.harness.skill import Skill
from alpha.harness.doctrine import Doctrine
from alpha.harness.registry import SkillRegistry, MemoryStore
from alpha.harness.state import HarnessState
from alpha.data.source import FakeSource
from alpha.llm.client import MockLLMClient
from alpha.converse.store import ProjectStore
from alpha.converse.workspace import Workspace
from alpha.converse.session import converse_project

def _h():
    return HarnessState(doctrine=Doctrine(), skills=SkillRegistry.from_skills([
        Skill(skill_id="gap_and_go", name="Gap and Go", type="pattern", family="runner",
              phases=["trend"], status="active")]), memory=MemoryStore.from_lessons([]))

def _fake_source():
    cal = [date(2026, 6, d) for d in range(10, 14)]
    snaps, px, closes = {}, 10.0, []
    for d in cal:
        prev = px; px = px * 1.15; closes.append(px)
        snaps[d] = pd.DataFrame({"symbol": ["RUN"], "name": ["RUN"], "open": [prev], "high": [px],
                                 "low": [prev], "close": [px], "volume": [1], "prev_close": [prev]})
    bars = {"RUN": pd.DataFrame({"date": cal, "open": [10.0] + closes[:-1], "high": closes,
                                 "low": [10.0] + closes[:-1], "close": closes, "volume": [1] * len(cal)})}
    return FakeSource(calendar=cal, bars=bars, snapshots=snaps)

def _agent_llm():
    return MockLLMClient('{"regime_read": "trend frontside", "candidates": '
                         '[{"symbol": "RUN", "pattern": "gap_and_go", "confidence": 0.7}]}')

def test_converse_project_persists_turn_and_commits_decision(tmp_path):
    store = ProjectStore(tmp_path / "projects")
    ws = Workspace(tmp_path / "ws"); ws.init()
    chat = MockLLMClient(['{"tool": "decide", "args": {"date": "2026-06-12"}}', "RUN looks strong."])
    proj = converse_project("p1", "read on RUN for 2026-06-12?", harness=_h(), store=store,
                            agent_llm=_agent_llm(), chat_llm=chat, source=_fake_source(), workspace=ws)
    assert proj.project_id == "p1" and len(proj.turns) == 1
    turn = proj.turns[0]
    assert turn.final_text == "RUN looks strong." and turn.tool_calls[0]["tool"] == "decide"
    assert store.get("p1").turns[0].final_text == "RUN looks strong."          # persisted
    import subprocess
    files = subprocess.run(["git", "ls-files"], cwd=tmp_path / "ws", capture_output=True, text=True).stdout
    assert "2026-06-12.json" in files                                          # decision committed as artifact

def test_resume_appends_a_second_turn(tmp_path):
    store = ProjectStore(tmp_path / "projects")
    chat1 = MockLLMClient(["first answer"])               # no tool call -> immediate final
    converse_project("p1", "hi", harness=_h(), store=store, agent_llm=_agent_llm(),
                     chat_llm=chat1, source=_fake_source())
    chat2 = MockLLMClient(["second answer"])
    proj = converse_project("p1", "again", harness=_h(), store=store, agent_llm=_agent_llm(),
                            chat_llm=chat2, source=_fake_source())
    assert len(proj.turns) == 2 and proj.turns[1].final_text == "second answer"

def test_pinned_project_is_read_only_no_write_tool(tmp_path):
    store = ProjectStore(tmp_path / "projects")
    from alpha.converse.project import new_project
    p = new_project(); p.h_pin = 0
    p.project_id = "pinned"; store.put(p)
    # a pinned project registers no propose_memory_edit; assert the registry has only `decide`
    from alpha.converse.agent import build_converse_registry
    reg = build_converse_registry(_h(), _agent_llm(), _fake_source(), read_only=True)
    assert {s["name"] for s in reg.specs()} == {"decide"}
```

> **Implementer note:** when `project.h_pin` is set and `snapshots` is provided, load `(h, _) = snapshots.load(project.h_pin)` for the reads; otherwise use the passed `harness`. `h_version = project.h_pin if project.h_pin is not None else (snapshots.latest() if snapshots is not None else None)`. The persisted `ProjectTurn.tool_calls` must be JSON-safe — convert each `result` that is a pydantic model via `.model_dump()` (a `DecisionPackage` result), but pass the RAW object to `workspace.put_decision(...)`. `run_conversation` returns `res.messages` (the extended list) — assign it back to `project.messages`.

- [ ] **Step 2: Run to verify it fails**

Run: `python -m pytest tests/converse/test_converse_project.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'alpha.converse.session'` (and `build_converse_registry` has no `read_only` kwarg).

- [ ] **Step 3: Implement**
- `alpha/converse/agent.py`: add `read_only: bool = False` to `build_converse_registry`; when `read_only`, register only `decide` (skip `propose_memory_edit`). Additive (default False = unchanged).
- `alpha/converse/session.py`: `converse_project(...)` per the interface + the implementer note. JSON-safe `tool_calls` serialization; commit `DecisionPackage` results to `workspace`; persist via `store.put`.

- [ ] **Step 4: Run to verify it passes + full suite green**

Run: `python -m pytest tests/converse/test_converse_project.py -v && python -m pytest -q`
Expected: 3 PASS; full suite green (the `read_only` kwarg defaults False → existing `build_converse_registry` callers + the Phase-1A/1B converse tests unchanged).

- [ ] **Step 5: Commit**

```bash
git add alpha/converse/session.py alpha/converse/agent.py tests/converse/test_converse_project.py
git commit -m "feat(converse): converse_project (persisted, H-version-stamped, commits decisions)"
```

---

### Task 5: Two-project isolation regression (shared brain, separate workspaces)

**Files:**
- Test: `tests/converse/test_project_isolation.py`

**Interfaces:**
- Consumes: everything above. No new production code — this task is a regression proving the §4 isolation invariant.

- [ ] **Step 1: Write the failing test** (it should pass once Tasks 1–4 are in; write it to lock the invariant)

```python
# tests/converse/test_project_isolation.py
from datetime import date
import pandas as pd, subprocess
from alpha.harness.skill import Skill
from alpha.harness.doctrine import Doctrine
from alpha.harness.registry import SkillRegistry, MemoryStore
from alpha.harness.state import HarnessState
from alpha.data.source import FakeSource
from alpha.llm.client import MockLLMClient
from alpha.converse.store import ProjectStore
from alpha.converse.workspace import Workspace
from alpha.converse.session import converse_project

def _h():
    return HarnessState(doctrine=Doctrine(), skills=SkillRegistry.from_skills([
        Skill(skill_id="gap_and_go", name="Gap and Go", type="pattern", family="runner",
              phases=["trend"], status="active")]), memory=MemoryStore.from_lessons([]))

def _src():
    cal = [date(2026, 6, d) for d in range(10, 14)]; snaps, px, closes = {}, 10.0, []
    for d in cal:
        prev = px; px = px * 1.15; closes.append(px)
        snaps[d] = pd.DataFrame({"symbol": ["RUN"], "name": ["RUN"], "open": [prev], "high": [px],
                                 "low": [prev], "close": [px], "volume": [1], "prev_close": [prev]})
    bars = {"RUN": pd.DataFrame({"date": cal, "open": [10.0] + closes[:-1], "high": closes,
                                 "low": [10.0] + closes[:-1], "close": closes, "volume": [1] * len(cal)})}
    return FakeSource(calendar=cal, bars=bars, snapshots=snaps)

def _agent():
    return MockLLMClient('{"regime_read": "trend frontside", "candidates": [{"symbol": "RUN", "pattern": "gap_and_go"}]}')

def test_two_projects_share_brain_isolate_workspaces(tmp_path):
    store = ProjectStore(tmp_path / "projects")
    h = _h()                                              # ONE shared brain instance
    wsA = Workspace(tmp_path / "A"); wsA.init()
    wsB = Workspace(tmp_path / "B"); wsB.init()
    converse_project("A", "read for 2026-06-11?", harness=h, store=store, agent_llm=_agent(),
                     chat_llm=MockLLMClient(['{"tool": "decide", "args": {"date": "2026-06-11"}}', "A done"]),
                     source=_src(), workspace=wsA)
    converse_project("B", "read for 2026-06-12?", harness=h, store=store, agent_llm=_agent(),
                     chat_llm=MockLLMClient(['{"tool": "decide", "args": {"date": "2026-06-12"}}', "B done"]),
                     source=_src(), workspace=wsB)
    filesA = subprocess.run(["git", "ls-files"], cwd=tmp_path / "A", capture_output=True, text=True).stdout
    filesB = subprocess.run(["git", "ls-files"], cwd=tmp_path / "B", capture_output=True, text=True).stdout
    assert "2026-06-11.json" in filesA and "2026-06-11.json" not in filesB    # workspaces isolated
    assert "2026-06-12.json" in filesB and "2026-06-12.json" not in filesA
    assert store.get("A").project_id == "A" and store.get("B").project_id == "B"   # two distinct projects
    assert {p.project_id for p in store.list()} == {"A", "B"}                 # one shared store, no fork
```

- [ ] **Step 2: Run to verify it passes (Tasks 1–4 already provide the behavior)**

Run: `python -m pytest tests/converse/test_project_isolation.py -v`
Expected: PASS — the two projects share `h`, write to separate git workspaces, and persist as two distinct `Project` docs.

- [ ] **Step 3: Run the whole suite (no regressions)**

Run: `python -m pytest -q`
Expected: green — all of §4 plus the prior **611** (additive; `converse()`/day-agent/gate untouched).

- [ ] **Step 4: Commit**

```bash
git add tests/converse/test_project_isolation.py
git commit -m "test(converse): two-project isolation (shared brain, separate git workspaces)"
```

---

## Self-Review

**Spec coverage (decisions b, c — §4):**
- project = {resumable conversation + git workspace + H-version provenance} → Tasks 1 (Project/turns) + 2 (store) + 3 (workspace) + 4 (assembled). ✓
- DecisionPackage as a recognized typed git-workspace artifact (§4.2) → Task 3 `put_decision` + Task 4 commit-on-decide. ✓
- ONE shared evolving brain, version authority = `SnapshotStore` ints, per-turn provenance ref, optional pin → Task 4 (`h_version`, `h_pin` load), Task 5 (shared brain, no fork). ✓
- Pinned project = read-only → Task 4 (`read_only` → no write tool). ✓
- JSON (not SQLite) for conversations → Task 2 (mirror SessionStore). ✓
- Additive, 611 stays green → Task 4/5 (`read_only` default False; new `converse_project` beside `converse`). ✓

**Placeholder scan:** Tasks 2 + 3 describe the implementation against the named reference (`SessionStore`, the git subprocess idiom) with the exact interface + tests inlined — Task 1's full code is given; Tasks 2/3 are "mirror this exact existing pattern" instructions, not placeholders. The implementer notes name the files to read and the env to isolate.

**Type consistency:** `Project`/`ProjectTurn`/`new_project`/`new_turn` (Task 1) are used by `ProjectStore` (Task 2) and `converse_project` (Task 4). `Workspace.put_decision(pkg)` (Task 3) is called in Task 4. `build_converse_registry(harness, agent_llm, source, read_only=False)` (Task 4's additive kwarg) is called by `converse_project` and asserted by the pinned test. `run_conversation(...) -> ConversationResult` (`.final_text`/`.messages`/`.tool_calls`) is consumed in Task 4. `SnapshotStore.latest()`/`.load(v)` provide the `h_version`. `new_session_id`/`now_iso` from `alpha.meta.models` are the id/timestamp source (same as SessionStore/ConflictQueue).
