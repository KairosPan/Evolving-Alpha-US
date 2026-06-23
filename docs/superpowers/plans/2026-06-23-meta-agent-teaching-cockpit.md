# Meta-Agent Teaching Cockpit Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Turn the web console's Evolution surface into an interactive meta-agent cockpit where the human teaches the trading brain from pasted text / URLs, the agent proposes a direction then a concrete edit queue, the human accepts/tweaks/comments, and accepted edits accumulate into a persistent live brain — each round a browsable, rollback-able session.

**Architecture:** Approach A — extend `alpha_web` with mutating POST routes backed by a stateless, per-request `MetaAgent` (`alpha/meta/`). Teaching reuses the Refiner's exact apply path (extracted into a shared `try_apply_op`) and the 9 meta-tools. The evolving brain lives in a new `LiveBrainStore` (seeds stay frozen); rollback is a pre-apply file copy — no `SnapshotStore`/`HarnessManager` in the cockpit.

**Tech Stack:** Python 3.11+, pydantic v2, FastAPI + Jinja2 + HTMX (the `web` extra), stdlib `urllib`/`html.parser` for ingestion, `pytest` + `httpx` `TestClient`, `MockLLMClient` for offline tests, Playwright for the final visual check.

## Global Constraints

- Python `>=3.11`; pydantic `>=2.6`. (`pyproject.toml`)
- **Zero new runtime dependencies.** URL fetch uses stdlib `urllib` + `html.parser` only.
- LLM access only via `alpha.llm.config.make_client` / injected `LLMClient`; tests use `MockLLMClient` (scriptable with a `list[str]` of per-call responses). Temperature via `ALPHA_LLM_TEMPERATURE` (default `0`).
- Every harness mutation goes through `MetaTools` (never touch `h.skills`/`h.memory`/`h.doctrine` directly) so the `EditLog` audit holds.
- The immutable doctrine red-line *text* must stay write-protected via `Doctrine.rewrite` (raises `ImmutableDoctrineError`); teaching must not be able to bypass it.
- New state roots default to `./state/brain` and `./state/sessions`, overridable by `ALPHA_LIVE_BRAIN_DIR` / `ALPHA_SESSIONS_DIR`; `/state/` must be gitignored; tests pin both to `tmp_path`.
- GET routes are side-effect-free (never write the brain). Mutating POST routes (`apply`, `rollback`) serialize on a process-level `threading.Lock`.
- TDD throughout: failing test → run-fail → minimal impl → run-pass → commit. Keep commits small. The existing `tests/refine/test_refiner_*.py` suite must stay green after the `try_apply_op` extraction (behavior identity).
- Spec: `docs/superpowers/specs/2026-06-23-meta-agent-teaching-cockpit-design.md`.

---

## File Structure

```
alpha/meta/__init__.py            # new package
alpha/meta/models.py              # LessonSource, ProposedDirection, ProposedEdit, Session, id helpers
alpha/meta/store.py               # LiveBrainStore, SessionStore
alpha/refine/apply.py             # try_apply_op + _dispatch + ALL_TOOLS (extracted from Refiner)
alpha/meta/prompts.py             # render_brain_summary + 3 prompt builders + parse_directions
alpha/meta/agent.py               # MetaAgent (propose_directions/expand_to_edits/apply/repropose_edit)
alpha/meta/ingest.py             # from_text, fetch_url (injectable fetcher), IngestError
alpha_web/data_access.py          # MODIFY: load_brain prefers LiveBrainStore; + brain_badge()
alpha_web/app.py                  # MODIFY: /deck, cockpit GET/POST routes, nav, mutation lock
alpha_web/templates/cockpit.html  # + partials/{directions,edit_queue,edit_row,apply_result,session_list}.html
alpha_web/static/app.js           # MODIFY: htmx loading-state (disable-on-inflight)
tests/meta/__init__.py + test_models.py, test_store.py, test_apply.py, test_agent.py, test_ingest.py
tests/web/conftest.py             # MODIFY: pin ALPHA_LIVE_BRAIN_DIR/ALPHA_SESSIONS_DIR to tmp_path
tests/web/test_cockpit.py         # new route tests
.gitignore                        # + /state/
```

---

# SLICE 1 — Models + Stores (pure data, offline)

### Task 1: Meta data models

**Files:**
- Create: `alpha/meta/__init__.py` (empty)
- Create: `alpha/meta/models.py`
- Create: `tests/meta/__init__.py` (empty)
- Test: `tests/meta/test_models.py`

**Interfaces:**
- Produces: `LessonSource`, `ProposedDirection`, `ProposedEdit`, `Session` (pydantic models); `new_session_id() -> str`; `new_edit_id() -> str`; `new_direction_id() -> str`.

- [ ] **Step 1: Write the failing test**

```python
# tests/meta/test_models.py
from alpha.meta.models import (
    LessonSource, ProposedDirection, ProposedEdit, Session,
    new_session_id, new_edit_id,
)


def test_lesson_source_roundtrips():
    s = LessonSource(kind="text", title="t", text="body")
    assert LessonSource.model_validate(s.model_dump()) == s
    assert s.url is None


def test_proposed_edit_defaults_and_roundtrip():
    e = ProposedEdit(edit_id="e1", tool="write_skill", args={"skill_id": "x"})
    assert e.status == "proposed" and e.target_id is None and e.applied_seq is None
    assert ProposedEdit.model_validate(e.model_dump()) == e


def test_session_holds_nested_models_and_roundtrips():
    sess = Session(
        session_id="s1",
        sources=[LessonSource(kind="text", text="b")],
        directions=[ProposedDirection(direction_id="d1", title="lean into squeezes")],
        edits=[ProposedEdit(edit_id="e1", tool="patch_skill", args={"skill_id": "x"})],
    )
    assert sess.status == "open"
    again = Session.model_validate(sess.model_dump())
    assert again == sess and again.edits[0].tool == "patch_skill"


def test_id_helpers_are_unique_and_sortable():
    a, b = new_session_id(), new_session_id()
    assert a != b and len(a) > 8
    assert new_edit_id() != new_edit_id()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/meta/test_models.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'alpha.meta'`

- [ ] **Step 3: Write minimal implementation**

```python
# alpha/meta/models.py
from __future__ import annotations

from datetime import datetime, timezone
from typing import Literal
from uuid import uuid4

from pydantic import BaseModel, Field


def new_session_id() -> str:
    return f"{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%f')}-{uuid4().hex[:4]}"


def new_edit_id() -> str:
    return uuid4().hex[:8]


def new_direction_id() -> str:
    return uuid4().hex[:6]


class LessonSource(BaseModel):
    kind: Literal["text", "url"]
    url: str | None = None
    title: str = ""
    text: str
    fetched_at: str = ""


class ProposedDirection(BaseModel):
    direction_id: str
    title: str
    summary: str = ""
    rationale: str = ""
    target_kinds: list[str] = Field(default_factory=list)   # advisory hint: {doctrine,skills,memory}


class ProposedEdit(BaseModel):
    edit_id: str
    tool: str
    target_kind: str = ""
    target_id: str | None = None
    op: str = ""
    summary: str = ""
    payload: dict | None = None
    rationale: str = ""
    args: dict = Field(default_factory=dict)
    status: Literal["proposed", "accepted", "rejected", "applied", "failed"] = "proposed"
    user_comment: str = ""
    apply_reason: str = ""
    applied_seq: int | None = None


class Session(BaseModel):
    session_id: str
    created_at: str = ""
    channel: str = "teach"
    status: Literal["open", "applied", "discarded"] = "open"
    sources: list[LessonSource] = Field(default_factory=list)
    directions: list[ProposedDirection] = Field(default_factory=list)
    chosen_direction_id: str | None = None
    direction_comment: str = ""
    edits: list[ProposedEdit] = Field(default_factory=list)
    applied_seqs: list[int] = Field(default_factory=list)
    snapshot_before: str | None = None
    notes: list[str] = Field(default_factory=list)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/meta/test_models.py -v`
Expected: PASS (4 passed)

- [ ] **Step 5: Commit**

```bash
git add alpha/meta/__init__.py alpha/meta/models.py tests/meta/__init__.py tests/meta/test_models.py
git commit -m "feat(meta): teaching-cockpit data models (LessonSource/Direction/Edit/Session)"
```

---

### Task 2: LiveBrainStore

**Files:**
- Create: `alpha/meta/store.py`
- Test: `tests/meta/test_store.py`

**Interfaces:**
- Consumes: `alpha.harness.state.HarnessState`, `alpha.harness.edit_log.EditLog`, `alpha.harness.loader.load_seeds`.
- Produces: `LiveBrainStore(root, *, seeds_dir=DEFAULT_SEEDS_DIR)` with `load() -> tuple[HarnessState, EditLog]`, `save(harness, log) -> Path`, `is_live() -> bool`, `edit_count() -> int`, `snapshot(session_id) -> str`, `restore(snapshot_path) -> None`. Module const `DEFAULT_SEEDS_DIR: Path`.

- [ ] **Step 1: Write the failing test**

```python
# tests/meta/test_store.py
from alpha.meta.store import LiveBrainStore
from alpha.harness.edit_log import EditLog


def test_load_empty_falls_back_to_seeds_without_writing(tmp_path):
    store = LiveBrainStore(tmp_path)
    assert store.is_live() is False
    h, log = store.load()
    assert len(h.skills.all()) > 0 and len(log) == 0   # seeds loaded
    assert not (tmp_path / "brain.json").exists()       # read never writes
    assert store.edit_count() == 0


def test_save_then_load_roundtrips_and_marks_live(tmp_path):
    store = LiveBrainStore(tmp_path)
    h, log = store.load()
    log.append("promote_skill", "skill", "base_breakout", "promote", "x", rationale="why")
    store.save(h, log)
    assert store.is_live() is True and store.edit_count() == 1
    h2, log2 = store.load()
    assert len(log2) == 1 and log2.records()[0].target_id == "base_breakout"
    assert len(h2.skills.all()) == len(h.skills.all())


def test_snapshot_and_restore(tmp_path):
    store = LiveBrainStore(tmp_path)
    h, log = store.load()
    store.save(h, log)                                  # v0: no edits
    snap = store.snapshot("sess1")
    log.append("promote_skill", "skill", "base_breakout", "promote", "x", rationale="why")
    store.save(h, log)
    assert store.edit_count() == 1
    store.restore(snap)
    assert store.edit_count() == 0                      # rolled back to pre-edit
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/meta/test_store.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'alpha.meta.store'`

- [ ] **Step 3: Write minimal implementation**

```python
# alpha/meta/store.py
from __future__ import annotations

import json
import os
import shutil
import tempfile
from pathlib import Path

from alpha.harness.edit_log import EditLog
from alpha.harness.loader import load_seeds
from alpha.harness.state import HarnessState

DEFAULT_SEEDS_DIR = Path(__file__).resolve().parents[2] / "seeds"


def _atomic_write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=path.parent, suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(text)
        os.replace(tmp, path)
    except BaseException:
        if os.path.exists(tmp):
            os.unlink(tmp)
        raise


class LiveBrainStore:
    """The persistent evolving brain (HarnessState + EditLog) as one JSON. Empty/missing -> seeds
    in-memory (no write on read). Rollback is a pre-apply file copy under history/."""

    def __init__(self, root: str | Path, *, seeds_dir: str | Path = DEFAULT_SEEDS_DIR) -> None:
        self._root = Path(root)
        self._seeds_dir = Path(seeds_dir)
        self._brain = self._root / "brain.json"
        self._history = self._root / "history"

    def is_live(self) -> bool:
        return self._brain.exists()

    def load(self) -> tuple[HarnessState, EditLog]:
        if not self._brain.exists():
            return load_seeds(self._seeds_dir), EditLog()
        data = json.loads(self._brain.read_text(encoding="utf-8"))
        return HarnessState.from_dict(data["harness"]), EditLog.from_dict(data["log"])

    def save(self, harness: HarnessState, log: EditLog) -> Path:
        _atomic_write(self._brain, json.dumps({"harness": harness.to_dict(), "log": log.to_dict()}))
        return self._brain

    def edit_count(self) -> int:
        if not self._brain.exists():
            return 0
        return len(json.loads(self._brain.read_text(encoding="utf-8")).get("log", []))

    def snapshot(self, session_id: str) -> str:
        self._history.mkdir(parents=True, exist_ok=True)
        dest = self._history / f"{session_id}.json"
        shutil.copyfile(self._brain, dest)
        return str(dest)

    def restore(self, snapshot_path: str) -> None:
        _atomic_write(self._brain, Path(snapshot_path).read_text(encoding="utf-8"))
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/meta/test_store.py -v`
Expected: PASS (3 passed)

- [ ] **Step 5: Commit**

```bash
git add alpha/meta/store.py tests/meta/test_store.py
git commit -m "feat(meta): LiveBrainStore (seed-fallback load, atomic save, snapshot/restore)"
```

---

### Task 3: SessionStore

**Files:**
- Modify: `alpha/meta/store.py` (append `SessionStore`)
- Test: `tests/meta/test_store.py` (append)

**Interfaces:**
- Consumes: `alpha.meta.models.Session`.
- Produces: `SessionStore(root)` with `put(session) -> Path`, `get(session_id) -> Session | None`, `list() -> list[Session]` (newest first by `session_id`).

- [ ] **Step 1: Write the failing test**

```python
# tests/meta/test_store.py  (append)
from alpha.meta.store import SessionStore
from alpha.meta.models import Session


def test_session_store_put_get_list_newest_first(tmp_path):
    store = SessionStore(tmp_path)
    store.put(Session(session_id="20260101T000000000000-aaaa"))
    store.put(Session(session_id="20260102T000000000000-bbbb", status="applied"))
    assert store.get("20260102T000000000000-bbbb").status == "applied"
    assert store.get("missing") is None
    ids = [s.session_id for s in store.list()]
    assert ids == ["20260102T000000000000-bbbb", "20260101T000000000000-aaaa"]


def test_session_store_missing_dir_is_empty(tmp_path):
    assert SessionStore(tmp_path / "nope").list() == []
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/meta/test_store.py -k session_store -v`
Expected: FAIL with `ImportError: cannot import name 'SessionStore'`

- [ ] **Step 3: Write minimal implementation**

```python
# alpha/meta/store.py  (append at end; reuse _atomic_write)
from alpha.meta.models import Session


class SessionStore:
    """Flat by-id store of teaching Sessions (atomic write, newest-first listing)."""

    def __init__(self, root: str | Path) -> None:
        self._root = Path(root)

    def _path(self, session_id: str) -> Path:
        return self._root / f"{session_id}.json"

    def put(self, session: Session) -> Path:
        p = self._path(session.session_id)
        _atomic_write(p, session.model_dump_json())
        return p

    def get(self, session_id: str) -> Session | None:
        p = self._path(session_id)
        if not p.exists():
            return None
        return Session.model_validate_json(p.read_text(encoding="utf-8"))

    def list(self) -> list[Session]:
        if not self._root.is_dir():
            return []
        out = [Session.model_validate_json(p.read_text(encoding="utf-8"))
               for p in self._root.glob("*.json")]
        return sorted(out, key=lambda s: s.session_id, reverse=True)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/meta/test_store.py -v`
Expected: PASS (5 passed)

- [ ] **Step 5: Commit**

```bash
git add alpha/meta/store.py tests/meta/test_store.py
git commit -m "feat(meta): SessionStore (atomic by-id, newest-first)"
```

---

# SLICE 2 — Shared apply path (the one existing-code change)

### Task 4: Extract `try_apply_op`; refactor Refiner; keep it green

**Files:**
- Create: `alpha/refine/apply.py`
- Modify: `alpha/refine/refiner.py` (replace `_dispatch`/`_apply_op` bodies with calls into `apply.py`)
- Test: `tests/meta/test_apply.py` (new) — and the EXISTING `tests/refine/test_refiner_*.py` must stay green.

**Interfaces:**
- Consumes: `RefineOp` (`alpha.refine.ops`), `MetaTools`, `HarnessState`, `EditRecord`.
- Produces: `try_apply_op(meta, harness, op, *, allowed, min_retire_samples, min_promote_samples) -> tuple[EditRecord | None, str | None]`; `ALL_TOOLS: frozenset[str]`.

- [ ] **Step 1: Write the failing test (new teaching-path coverage)**

```python
# tests/meta/test_apply.py
import pytest

from alpha.harness.loader import load_seeds
from alpha.harness.metatools import MetaTools
from alpha.harness.edit_log import EditLog
from alpha.refine.apply import try_apply_op, ALL_TOOLS
from alpha.refine.ops import RefineOp

SEEDS = "seeds"


def _tools():
    h = load_seeds(SEEDS)
    return MetaTools(h, EditLog()), h


def test_apply_patch_skill_succeeds():
    meta, h = _tools()
    sid = h.skills.all()[0].skill_id
    op = RefineOp(tool="patch_skill", args={"skill_id": sid, "notes": "taught note"}, rationale="r")
    rec, reason = try_apply_op(meta, h, op, allowed=ALL_TOOLS, min_retire_samples=5, min_promote_samples=3)
    assert reason is None and rec is not None and rec.tool == "patch_skill"
    assert h.skills.get(sid).notes == "taught note"


def test_apply_missing_rationale_rejected():
    meta, h = _tools()
    sid = h.skills.all()[0].skill_id
    op = RefineOp(tool="patch_skill", args={"skill_id": sid, "notes": "x"}, rationale="")
    rec, reason = try_apply_op(meta, h, op, allowed=ALL_TOOLS, min_retire_samples=5, min_promote_samples=3)
    assert rec is None and "rationale" in reason


def test_apply_immutable_doctrine_rejected_cleanly():
    meta, h = _tools()
    red = h.doctrine.immutable_core()[0].section
    op = RefineOp(tool="rewrite_doctrine", args={"section": red, "new_guidance": "x"}, rationale="r")
    rec, reason = try_apply_op(meta, h, op, allowed=ALL_TOOLS, min_retire_samples=5, min_promote_samples=3)
    assert rec is None and reason and "Immutable" in reason


def test_tool_not_in_allowed_rejected():
    meta, h = _tools()
    op = RefineOp(tool="rewrite_doctrine", args={"section": "x", "new_guidance": "y"}, rationale="r")
    rec, reason = try_apply_op(meta, h, op, allowed=frozenset({"patch_skill"}),
                               min_retire_samples=5, min_promote_samples=3)
    assert rec is None and "not in" in reason
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/meta/test_apply.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'alpha.refine.apply'`

- [ ] **Step 3: Write `alpha/refine/apply.py` (move logic verbatim from `refiner.py`)**

```python
# alpha/refine/apply.py
from __future__ import annotations

from pydantic import ValidationError

from alpha.harness.edit_log import EditRecord
from alpha.harness.errors import HarnessError
from alpha.harness.memory import Lesson
from alpha.harness.metatools import MetaTools
from alpha.harness.skill import Skill
from alpha.harness.state import HarnessState
from alpha.refine.ops import PASS_TOOLS, RefineOp

ALL_TOOLS = frozenset().union(*PASS_TOOLS.values())

_DISPATCH_ERRORS = (HarnessError, KeyError, ValueError, ValidationError, TypeError, AttributeError)


def _dispatch(meta: MetaTools, op: RefineOp) -> EditRecord:
    """Map an op to its MetaTools call. Defensive: force write_skill->incubating + strip stats;
    strip importance on process_memory (the create paths the Refiner already sanitizes)."""
    tool, args, r = op.tool, dict(op.args), op.rationale
    m = meta
    if tool == "write_skill":
        args.pop("stats", None)
        args["status"] = "incubating"
        return m.write_skill(Skill.from_seed(args), rationale=r)
    if tool == "patch_skill":
        sid = args.pop("skill_id")
        return m.patch_skill(sid, rationale=r, **args)
    if tool == "retire_skill":
        sid = args.pop("skill_id")
        perm = bool(args.pop("permanent", False))
        return m.retire_skill(sid, rationale=r, permanent=perm)
    if tool == "revive_skill":
        return m.revive_skill(args.pop("skill_id"), rationale=r)
    if tool == "promote_skill":
        return m.promote_skill(args.pop("skill_id"), rationale=r)
    if tool == "process_memory":
        args.pop("importance", None)
        return m.process_memory(Lesson.from_seed(args), rationale=r)
    if tool == "update_memory":
        lid = args.pop("lesson_id")
        return m.update_memory(lid, rationale=r, **args)
    if tool == "demote_memory":
        lid = args.pop("lesson_id")
        factor = float(args.pop("factor"))
        return m.demote_memory(lid, factor, rationale=r)
    if tool == "rewrite_doctrine":
        return m.rewrite_doctrine(args.pop("section"), args.pop("new_guidance"), rationale=r)
    raise ValueError(f"unknown tool: {tool}")


def _target_id(tool: str, args: dict) -> str | None:
    if tool in ("write_skill", "patch_skill", "retire_skill", "revive_skill", "promote_skill"):
        v = args.get("skill_id")
    elif tool in ("process_memory", "update_memory", "demote_memory"):
        v = args.get("lesson_id")
    elif tool == "rewrite_doctrine":
        v = args.get("section")
    else:
        v = None
    return str(v) if v is not None else None


def try_apply_op(meta: MetaTools, harness: HarnessState, op: RefineOp, *, allowed: frozenset[str],
                 min_retire_samples: int, min_promote_samples: int) -> tuple[EditRecord | None, str | None]:
    """Gate order: whitelist -> rationale -> empty-patch -> retire/promote evidence -> dispatch
    (dispatch errors -> clean reject reason). Returns (record, None) on apply | (None, reason)."""
    tid = _target_id(op.tool, op.args)
    if op.tool not in allowed:
        return None, "tool not in this pass or unknown"
    if not op.rationale or not op.rationale.strip():
        return None, "missing rationale"
    if op.tool in ("patch_skill", "update_memory") and not (set(op.args) - {"skill_id", "lesson_id"}):
        return None, "empty patch (no fields to change)"
    if op.tool == "retire_skill" and tid is not None:
        sk = harness.skills.get(tid)
        if sk is not None and sk.stats.n < min_retire_samples:
            return None, f"retire blocked: n={sk.stats.n} < min_retire_samples={min_retire_samples}"
    if op.tool == "promote_skill" and tid is not None:
        sk = harness.skills.get(tid)
        if sk is not None:
            if sk.stats.n < min_promote_samples:
                return None, f"promote blocked: n={sk.stats.n} < min_promote_samples={min_promote_samples}"
            if sk.stats.expectancy is None or sk.stats.expectancy <= 0:
                return None, "promote blocked: expectancy (advantage) not > 0"
    try:
        rec = _dispatch(meta, op)
    except _DISPATCH_ERRORS as e:
        return None, f"{type(e).__name__}: {e}"
    return rec, None
```

- [ ] **Step 4: Refactor `refiner.py` to delegate (behavior identical)**

Replace the `_dispatch` method and the body of `_apply_op` in `alpha/refine/refiner.py`. Delete the `Refiner._dispatch` method and the module-level `_DISPATCH_ERRORS`; keep `_target_id` (still used to build `RejectedEdit`/`AppliedEdit`) OR import it. Concretely, change the top imports and `_apply_op`:

```python
# alpha/refine/refiner.py  — replace the _apply_op method body and remove _dispatch
from alpha.refine.apply import try_apply_op, _target_id   # add this import; drop local _target_id + _dispatch + _DISPATCH_ERRORS

    def _apply_op(self, op: RefineOp, pk: PassKind, allowed: frozenset) -> tuple[bool, object]:
        rec, reason = try_apply_op(self._meta, self._h, op, allowed=allowed,
                                   min_retire_samples=self._cfg.min_retire_samples,
                                   min_promote_samples=self._cfg.min_promote_samples)
        if reason is not None:
            return False, RejectedEdit(pass_kind=pk, tool=op.tool,
                                       target_id=_target_id(op.tool, op.args), reason=reason)
        return True, AppliedEdit(pass_kind=pk, tool=op.tool, target_id=str(rec.target_id),
                                 seq=rec.seq, rationale=op.rationale)
```

Remove the now-unused `_dispatch` method, the module-level `_DISPATCH_ERRORS`, the local `_target_id` function, and any now-unused imports (`EditRecord`, `Skill`, `Lesson`, `HarnessError`, `ValidationError`) from `refiner.py`.

- [ ] **Step 5: Run the new test + the full Refiner suite (the behavior-identity gate)**

Run: `pytest tests/meta/test_apply.py tests/refine -v`
Expected: PASS (new apply tests pass AND every existing `tests/refine/*` test stays green)

- [ ] **Step 6: Commit**

```bash
git add alpha/refine/apply.py alpha/refine/refiner.py tests/meta/test_apply.py
git commit -m "refactor(refine): extract shared try_apply_op (Refiner + MetaAgent), behavior-identical"
```

---

# SLICE 3 — MetaAgent (offline against MockLLMClient)

### Task 5: Prompts + brain summary + direction parser

**Files:**
- Create: `alpha/meta/prompts.py`
- Test: `tests/meta/test_agent.py` (new, prompts section)

**Interfaces:**
- Consumes: `HarnessState`, `LessonSource`, `ProposedDirection`, `new_direction_id`.
- Produces: `render_brain_summary(h) -> str`; `build_directions_prompt(h, source, comment) -> tuple[str, str]`; `build_edits_prompt(h, source, direction, comment) -> tuple[str, str]`; `build_reedit_prompt(h, source, direction, prior_edit, comment) -> tuple[str, str]`; `parse_directions(raw) -> list[ProposedDirection]`.

- [ ] **Step 1: Write the failing test**

```python
# tests/meta/test_agent.py
from alpha.harness.loader import load_seeds
from alpha.meta.models import LessonSource, ProposedDirection, ProposedEdit
from alpha.meta import prompts


def _src():
    return LessonSource(kind="text", title="squeeze writeup", text="High short interest + low float...")


def test_render_brain_summary_lists_redlines_and_skills():
    h = load_seeds("seeds")
    s = prompts.render_brain_summary(h)
    assert "RED-LINE" in s and any(sk.skill_id in s for sk in h.skills.all()[:1])


def test_build_directions_prompt_mentions_source_and_asks_json():
    h = load_seeds("seeds")
    system, user = prompts.build_directions_prompt(h, _src(), comment=None)
    assert "directions" in system.lower() and "squeeze writeup" in user


def test_parse_directions_tolerant_and_assigns_ids():
    raw = '{"directions": [{"title": "lean into squeezes", "summary": "s", "target_kinds": ["skills"]}, {"bad": 1}]}'
    out = prompts.parse_directions(raw)
    assert len(out) == 1 and out[0].title == "lean into squeezes" and out[0].direction_id
    assert prompts.parse_directions("not json") == []
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/meta/test_agent.py -k "summary or directions" -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'alpha.meta.prompts'`

- [ ] **Step 3: Write minimal implementation**

```python
# alpha/meta/prompts.py
from __future__ import annotations

import json

from alpha.harness.state import HarnessState
from alpha.llm.extract import extract_json_object
from alpha.meta.models import LessonSource, ProposedDirection, ProposedEdit, new_direction_id

_TOOLS_DOC = (
    "Allowed tools (emit ops in this exact vocabulary): "
    "write_skill(args: full skill incl skill_id,name,type,family,phases,trigger,entry,exit_stop,taboo), "
    "patch_skill(args: skill_id + fields to change), retire_skill(args: skill_id[,permanent]), "
    "revive_skill(args: skill_id), promote_skill(args: skill_id), "
    "process_memory(args: lesson incl lesson_id,outcome,lesson[,family,phases]), "
    "update_memory(args: lesson_id + fields), demote_memory(args: lesson_id, factor), "
    "rewrite_doctrine(args: section, new_guidance). "
    "NEVER rewrite an immutable [RED-LINE] doctrine section — it will be rejected."
)


def render_brain_summary(h: HarnessState) -> str:
    parts = ["DOCTRINE:"]
    for e in h.doctrine.immutable_core():
        parts.append(f"- [RED-LINE] {e.section}: {e.guidance}")
    for e in h.doctrine.mutable_entries():
        parts.append(f"- {e.section}: {e.guidance}")
    parts.append("\nSKILLS (id [status, family]):")
    for s in h.skills.all():
        parts.append(f"- {s.skill_id} [{s.status}, {s.family or 'any'}] trigger: {s.trigger}")
    parts.append("\nMEMORY (id [outcome]):")
    for l in h.memory.all():
        parts.append(f"- {l.lesson_id} [{l.outcome}] {l.lesson}")
    return "\n".join(parts)


def _source_block(source: LessonSource) -> str:
    head = f"TEACHING MATERIAL — {source.title or source.url or 'pasted text'}:\n"
    return head + source.text


def build_directions_prompt(h: HarnessState, source: LessonSource, comment: str | None) -> tuple[str, str]:
    system = (
        "You are the meta-agent's curriculum planner for a US momentum trading co-pilot. "
        "Given the co-pilot's current brain and a piece of teaching material, propose 2-4 DISTINCT, "
        "high-level evolution DIRECTIONS (not concrete edits yet). "
        'Output STRICT JSON: {"directions": [{"title": "...", "summary": "...", "rationale": "...", '
        '"target_kinds": ["skills"|"memory"|"doctrine", ...]}]}\n\n'
        + render_brain_summary(h)
    )
    user = _source_block(source)
    if comment:
        user += f"\n\nThe operator steered: {comment}"
    return system, user


def build_edits_prompt(h: HarnessState, source: LessonSource, direction: ProposedDirection,
                       comment: str | None) -> tuple[str, str]:
    system = (
        "You expand ONE chosen evolution direction into concrete edits to the trading brain. "
        + _TOOLS_DOC
        + ' Output STRICT JSON: {"ops": [{"tool": "...", "args": {...}, "rationale": "..."}]}. '
        "Every op needs a non-empty rationale citing the teaching material.\n\n"
        + render_brain_summary(h)
    )
    user = (f"CHOSEN DIRECTION: {direction.title}\n{direction.summary}\n"
            f"(target areas: {', '.join(direction.target_kinds) or 'any'})\n\n" + _source_block(source))
    if direction.target_kinds:
        user += f"\n\nPrefer edits to: {', '.join(direction.target_kinds)}."
    if comment:
        user += f"\n\nThe operator steered: {comment}"
    return system, user


def build_reedit_prompt(h: HarnessState, source: LessonSource, direction: ProposedDirection,
                        prior_edit: ProposedEdit, comment: str) -> tuple[str, str]:
    system = (
        "You revise a SINGLE proposed edit based on operator feedback. "
        + _TOOLS_DOC
        + ' Output STRICT JSON with EXACTLY ONE op: {"ops": [{"tool": "...", "args": {...}, '
        '"rationale": "..."}]}. Prefer the same tool/target as the prior edit.\n\n'
        + render_brain_summary(h)
    )
    user = (f"DIRECTION: {direction.title}\nPRIOR EDIT: tool={prior_edit.tool} "
            f"target={prior_edit.target_id} args={json.dumps(prior_edit.args)}\n"
            f"OPERATOR FEEDBACK: {comment}\n\n" + _source_block(source))
    return system, user


def parse_directions(raw: str) -> list[ProposedDirection]:
    extracted = extract_json_object(raw)
    if extracted is None:
        return []
    try:
        data = json.loads(extracted)
    except (json.JSONDecodeError, ValueError):
        return []
    items = data.get("directions") if isinstance(data, dict) else None
    if not isinstance(items, list):
        return []
    out: list[ProposedDirection] = []
    for it in items:
        if not isinstance(it, dict) or not isinstance(it.get("title"), str) or not it["title"].strip():
            continue
        tk = it.get("target_kinds")
        out.append(ProposedDirection(
            direction_id=new_direction_id(),
            title=it["title"],
            summary=it.get("summary", "") if isinstance(it.get("summary"), str) else "",
            rationale=it.get("rationale", "") if isinstance(it.get("rationale"), str) else "",
            target_kinds=[x for x in tk if isinstance(x, str)] if isinstance(tk, list) else [],
        ))
    return out
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/meta/test_agent.py -k "summary or directions" -v`
Expected: PASS (3 passed)

- [ ] **Step 5: Commit**

```bash
git add alpha/meta/prompts.py tests/meta/test_agent.py
git commit -m "feat(meta): brain-summary renderer + 3 prompt builders + direction parser"
```

---

### Task 6: MetaAgent.propose_directions

**Files:**
- Create: `alpha/meta/agent.py`
- Test: `tests/meta/test_agent.py` (append)

**Interfaces:**
- Consumes: `MetaTools`, `LLMClient`, `prompts`, `try_apply_op`/`ALL_TOOLS`.
- Produces: `MetaAgent(tools, llm, *, retire_min=5, promote_min=3)` with `propose_directions(source, *, comment=None) -> list[ProposedDirection]`.

- [ ] **Step 1: Write the failing test**

```python
# tests/meta/test_agent.py  (append)
from alpha.harness.edit_log import EditLog
from alpha.harness.metatools import MetaTools
from alpha.llm.client import MockLLMClient
from alpha.meta.agent import MetaAgent


def _agent(scripted):
    h = load_seeds("seeds")
    return MetaAgent(MetaTools(h, EditLog()), MockLLMClient(scripted)), h


def test_propose_directions_parses_cards():
    agent, _ = _agent('{"directions": [{"title": "lean into squeezes"}, {"title": "tighten stops"}]}')
    dirs = agent.propose_directions(_src())
    assert [d.title for d in dirs] == ["lean into squeezes", "tighten stops"]
    assert all(d.direction_id for d in dirs)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/meta/test_agent.py -k propose_directions -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'alpha.meta.agent'`

- [ ] **Step 3: Write minimal implementation**

```python
# alpha/meta/agent.py
from __future__ import annotations

import copy

from alpha.harness.edit_log import EditLog
from alpha.harness.metatools import MetaTools
from alpha.llm.client import LLMClient
from alpha.meta import prompts
from alpha.meta.models import (
    LessonSource, ProposedDirection, ProposedEdit, new_edit_id,
)
from alpha.refine.apply import ALL_TOOLS, try_apply_op
from alpha.refine.ops import RefineOp, parse_ops

_KIND = {
    "write_skill": "skill", "patch_skill": "skill", "retire_skill": "skill",
    "revive_skill": "skill", "promote_skill": "skill",
    "process_memory": "memory", "update_memory": "memory", "demote_memory": "memory",
    "rewrite_doctrine": "doctrine",
}


class MetaAgent:
    """Stateless, per-request. Turns curated content into proposed brain edits (dry-run preview),
    then applies the accepted ones through the SAME gated path the autonomous Refiner uses."""

    def __init__(self, tools: MetaTools, llm: LLMClient, *, retire_min: int = 5, promote_min: int = 3) -> None:
        self.tools = tools
        self.h = tools.h
        self.llm = llm
        self._retire_min = retire_min
        self._promote_min = promote_min

    def propose_directions(self, source: LessonSource, *, comment: str | None = None) -> list[ProposedDirection]:
        system, user = prompts.build_directions_prompt(self.h, source, comment)
        return prompts.parse_directions(self.llm.complete(system, user))
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/meta/test_agent.py -k propose_directions -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add alpha/meta/agent.py tests/meta/test_agent.py
git commit -m "feat(meta): MetaAgent.propose_directions"
```

---

### Task 7: MetaAgent.expand_to_edits (dry-run preview)

**Files:**
- Modify: `alpha/meta/agent.py`
- Test: `tests/meta/test_agent.py` (append)

**Interfaces:**
- Produces: `MetaAgent.expand_to_edits(source, direction, *, comment=None) -> list[ProposedEdit]`. Each edit's `op`/`target_id`/`payload` come from a dry-run `EditRecord`; a gate failure yields `status="failed"` with `apply_reason` and the live brain is untouched.

- [ ] **Step 1: Write the failing test**

```python
# tests/meta/test_agent.py  (append)
def test_expand_to_edits_previews_without_mutating_live_brain():
    h0 = load_seeds("seeds")
    sid = h0.skills.all()[0].skill_id
    scripted = ('{"ops": [{"tool": "patch_skill", "args": {"skill_id": "%s", "notes": "from article"}, '
                '"rationale": "the article shows this"}]}') % sid
    agent = MetaAgent(MetaTools(h0, EditLog()), MockLLMClient(scripted))
    direction = ProposedDirection(direction_id="d1", title="tighten")
    edits = agent.expand_to_edits(_src(), direction)
    assert len(edits) == 1
    e = edits[0]
    assert e.status == "proposed" and e.op == "update" and e.target_id == sid
    assert e.payload["after"] == {"notes": "from article"}
    assert h0.skills.get(sid).notes != "from article"          # live brain NOT mutated by preview


def test_expand_to_edits_bad_op_becomes_failed_row_not_a_crash():
    agent, _ = _agent('{"ops": [{"tool": "patch_skill", "args": {"skill_id": "nope", "notes": "x"}, "rationale": "r"}]}')
    edits = agent.expand_to_edits(_src(), ProposedDirection(direction_id="d1", title="t"))
    assert len(edits) == 1 and edits[0].status == "failed" and edits[0].apply_reason
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/meta/test_agent.py -k expand_to_edits -v`
Expected: FAIL with `AttributeError: 'MetaAgent' object has no attribute 'expand_to_edits'`

- [ ] **Step 3: Write minimal implementation (append methods to MetaAgent)**

```python
# alpha/meta/agent.py  (add methods to MetaAgent)
    def _preview(self, op: RefineOp) -> ProposedEdit:
        scratch = copy.deepcopy(self.h)
        rec, reason = try_apply_op(MetaTools(scratch, EditLog()), scratch, op, allowed=ALL_TOOLS,
                                   min_retire_samples=self._retire_min, min_promote_samples=self._promote_min)
        if rec is not None:
            return ProposedEdit(edit_id=new_edit_id(), tool=op.tool, target_kind=rec.target_kind,
                                target_id=rec.target_id, op=rec.op, summary=rec.summary,
                                payload=rec.payload, rationale=op.rationale, args=dict(op.args))
        return ProposedEdit(edit_id=new_edit_id(), tool=op.tool, target_kind=_KIND.get(op.tool, ""),
                            rationale=op.rationale, args=dict(op.args), status="failed", apply_reason=reason)

    def expand_to_edits(self, source: LessonSource, direction: ProposedDirection, *,
                        comment: str | None = None) -> list[ProposedEdit]:
        system, user = prompts.build_edits_prompt(self.h, source, direction, comment)
        return [self._preview(op) for op in parse_ops(self.llm.complete(system, user))]
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/meta/test_agent.py -k expand_to_edits -v`
Expected: PASS (2 passed)

- [ ] **Step 5: Commit**

```bash
git add alpha/meta/agent.py tests/meta/test_agent.py
git commit -m "feat(meta): expand_to_edits with dry-run preview (no live mutation)"
```

---

### Task 8: MetaAgent.apply

**Files:**
- Modify: `alpha/meta/agent.py`
- Test: `tests/meta/test_agent.py` (append)

**Interfaces:**
- Produces: `MetaAgent.apply(accepted: list[ProposedEdit]) -> tuple[list[EditRecord], list[ProposedEdit]]`. Mutates the live brain for `status=="accepted"` edits; sets each row's `status`/`applied_seq`/`apply_reason`.

- [ ] **Step 1: Write the failing test**

```python
# tests/meta/test_agent.py  (append)
def test_apply_mutates_live_brain_and_marks_rows():
    h0 = load_seeds("seeds")
    sid = h0.skills.all()[0].skill_id
    tools = MetaTools(h0, EditLog())
    agent = MetaAgent(tools, MockLLMClient("{}"))
    e = ProposedEdit(edit_id="e1", tool="patch_skill", target_id=sid,
                     args={"skill_id": sid, "notes": "applied now"}, rationale="r", status="accepted")
    applied, rows = agent.apply([e])
    assert len(applied) == 1 and h0.skills.get(sid).notes == "applied now"
    assert rows[0].status == "applied" and rows[0].applied_seq == 0 and len(tools.log) == 1
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/meta/test_agent.py -k "apply_mutates" -v`
Expected: FAIL with `AttributeError: 'MetaAgent' object has no attribute 'apply'`

- [ ] **Step 3: Write minimal implementation**

```python
# alpha/meta/agent.py  (add method + import EditRecord at top)
from alpha.harness.edit_log import EditLog, EditRecord   # update the existing import line

    def apply(self, accepted: list[ProposedEdit]) -> tuple[list[EditRecord], list[ProposedEdit]]:
        applied: list[EditRecord] = []
        for e in accepted:
            if e.status != "accepted":
                continue
            op = RefineOp(tool=e.tool, args=dict(e.args), rationale=e.rationale)
            rec, reason = try_apply_op(self.tools, self.h, op, allowed=ALL_TOOLS,
                                       min_retire_samples=self._retire_min, min_promote_samples=self._promote_min)
            if rec is not None:
                e.status, e.applied_seq, e.apply_reason = "applied", rec.seq, ""
                applied.append(rec)
            else:
                e.status, e.apply_reason = "failed", reason
        return applied, accepted
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/meta/test_agent.py -k "apply_mutates" -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add alpha/meta/agent.py tests/meta/test_agent.py
git commit -m "feat(meta): MetaAgent.apply through the gated meta-tool path"
```

---

### Task 9: MetaAgent.repropose_edit

**Files:**
- Modify: `alpha/meta/agent.py`
- Test: `tests/meta/test_agent.py` (append)

**Interfaces:**
- Produces: `MetaAgent.repropose_edit(source, direction, prior_edit, comment) -> ProposedEdit`. Returns one re-previewed edit that KEEPS `prior_edit.edit_id` and carries `user_comment=comment`; if the model emits no usable op, returns a `failed` row keeping the id.

- [ ] **Step 1: Write the failing test**

```python
# tests/meta/test_agent.py  (append)
def test_repropose_edit_replaces_one_row_keeping_id():
    h0 = load_seeds("seeds")
    sid = h0.skills.all()[0].skill_id
    scripted = ('{"ops": [{"tool": "patch_skill", "args": {"skill_id": "%s", "notes": "revised"}, '
                '"rationale": "operator asked"}]}') % sid
    agent = MetaAgent(MetaTools(h0, EditLog()), MockLLMClient(scripted))
    prior = ProposedEdit(edit_id="keep-me", tool="patch_skill", target_id=sid,
                         args={"skill_id": sid, "notes": "old"}, rationale="r")
    out = agent.repropose_edit(_src(), ProposedDirection(direction_id="d1", title="t"), prior, "make it tighter")
    assert out.edit_id == "keep-me" and out.user_comment == "make it tighter"
    assert out.payload["after"] == {"notes": "revised"} and out.status == "proposed"


def test_repropose_edit_no_op_returns_failed_keeping_id():
    agent, _ = _agent('{"ops": []}')
    prior = ProposedEdit(edit_id="keep-me", tool="patch_skill", args={"skill_id": "x"}, rationale="r")
    out = agent.repropose_edit(_src(), ProposedDirection(direction_id="d1", title="t"), prior, "no")
    assert out.edit_id == "keep-me" and out.status == "failed"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/meta/test_agent.py -k repropose -v`
Expected: FAIL with `AttributeError: 'MetaAgent' object has no attribute 'repropose_edit'`

- [ ] **Step 3: Write minimal implementation**

```python
# alpha/meta/agent.py  (add method)
    def repropose_edit(self, source: LessonSource, direction: ProposedDirection,
                       prior_edit: ProposedEdit, comment: str) -> ProposedEdit:
        system, user = prompts.build_reedit_prompt(self.h, source, direction, prior_edit, comment)
        ops = parse_ops(self.llm.complete(system, user))
        if not ops:
            prior_edit.status, prior_edit.apply_reason, prior_edit.user_comment = (
                "failed", "model returned no usable edit", comment)
            return prior_edit
        out = self._preview(ops[0])
        out.edit_id, out.user_comment = prior_edit.edit_id, comment
        return out
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/meta/test_agent.py -k repropose -v`
Expected: PASS (2 passed)

- [ ] **Step 5: Commit**

```bash
git add alpha/meta/agent.py tests/meta/test_agent.py
git commit -m "feat(meta): MetaAgent.repropose_edit (single-row re-propose, keeps edit_id)"
```

---

# SLICE 4 — Ingest

### Task 10: from_text + fetch_url

**Files:**
- Create: `alpha/meta/ingest.py`
- Test: `tests/meta/test_ingest.py`

**Interfaces:**
- Produces: `from_text(text, title="") -> LessonSource`; `fetch_url(url, *, fetcher=None) -> LessonSource`; `IngestError(Exception)`. `fetcher: Callable[[str], str]` returns raw HTML (default = stdlib urllib GET).

- [ ] **Step 1: Write the failing test**

```python
# tests/meta/test_ingest.py
import pytest
from alpha.meta.ingest import from_text, fetch_url, IngestError


def test_from_text_builds_source():
    s = from_text("hello body", title="note")
    assert s.kind == "text" and s.text == "hello body" and s.title == "note" and s.fetched_at


def test_fetch_url_strips_html_via_injected_fetcher():
    html = "<html><head><title>Squeeze 101</title></head><body><p>High SI.</p><script>x=1</script></body></html>"
    s = fetch_url("http://example.com/a", fetcher=lambda u: html)
    assert s.kind == "url" and s.url == "http://example.com/a"
    assert "High SI." in s.text and "x=1" not in s.text and s.title == "Squeeze 101"


def test_fetch_url_failure_raises_ingesterror():
    def boom(u):
        raise OSError("no network")
    with pytest.raises(IngestError):
        fetch_url("http://example.com/a", fetcher=boom)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/meta/test_ingest.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'alpha.meta.ingest'`

- [ ] **Step 3: Write minimal implementation**

```python
# alpha/meta/ingest.py
from __future__ import annotations

from datetime import datetime, timezone
from html.parser import HTMLParser
from typing import Callable
from urllib.request import Request, urlopen

from alpha.meta.models import LessonSource


class IngestError(Exception):
    """A URL could not be fetched/parsed; the route turns this into 'paste the text instead'."""


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def from_text(text: str, title: str = "") -> LessonSource:
    return LessonSource(kind="text", title=title, text=text, fetched_at=_now())


class _TextExtractor(HTMLParser):
    _SKIP = {"script", "style", "head", "noscript"}

    def __init__(self) -> None:
        super().__init__()
        self.title = ""
        self._chunks: list[str] = []
        self._skip_depth = 0
        self._in_title = False

    def handle_starttag(self, tag, attrs):
        if tag in self._SKIP:
            self._skip_depth += 1
        if tag == "title":
            self._in_title = True

    def handle_endtag(self, tag):
        if tag in self._SKIP and self._skip_depth:
            self._skip_depth -= 1
        if tag == "title":
            self._in_title = False

    def handle_data(self, data):
        if self._in_title:
            self.title += data.strip()
        elif self._skip_depth == 0 and data.strip():
            self._chunks.append(data.strip())

    def text(self) -> str:
        return "\n".join(self._chunks)


def _urllib_fetcher(url: str) -> str:
    req = Request(url, headers={"User-Agent": "evolving-alpha-cockpit/1.0"})
    with urlopen(req, timeout=15) as resp:           # noqa: S310 (operator-supplied URL, localhost tool)
        charset = resp.headers.get_content_charset() or "utf-8"
        return resp.read().decode(charset, errors="replace")


def fetch_url(url: str, *, fetcher: Callable[[str], str] | None = None) -> LessonSource:
    fetch = fetcher or _urllib_fetcher
    try:
        raw = fetch(url)
    except Exception as e:                            # network/decode/etc -> friendly route message
        raise IngestError(f"could not fetch {url}: {type(e).__name__}: {e}") from e
    parser = _TextExtractor()
    parser.feed(raw)
    return LessonSource(kind="url", url=url, title=parser.title, text=parser.text(), fetched_at=_now())
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/meta/test_ingest.py -v`
Expected: PASS (3 passed)

- [ ] **Step 5: Commit**

```bash
git add alpha/meta/ingest.py tests/meta/test_ingest.py
git commit -m "feat(meta): ingest from_text + fetch_url (stdlib html strip, injectable fetcher)"
```

---

# SLICE 5 — Live-brain read-wiring (its own slice, before the cockpit routes)

### Task 11: load_brain prefers LiveBrainStore + brain_badge + tmp conftest + test migration

**Files:**
- Modify: `alpha_web/data_access.py`
- Modify: `tests/web/conftest.py`
- Modify: `.gitignore`
- Test: `tests/web/test_data_access.py` (append)

**Interfaces:**
- Produces: `load_brain(seeds_dir=SEEDS_DIR) -> HarnessState` (now prefers `ALPHA_LIVE_BRAIN_DIR` store when live, else seeds; never writes); `brain_badge() -> dict` = `{"is_live": bool, "edit_count": int}`.

- [ ] **Step 1: Add the gitignore entry and the tmp conftest fixture**

Append to `.gitignore`:
```
# Live brain + teaching sessions (regenerable local state)
/state/
```

Append to `tests/web/conftest.py` (autouse so the suite never touches a developer's `./state/`):
```python
import pytest


@pytest.fixture(autouse=True)
def _isolate_state(tmp_path, monkeypatch):
    monkeypatch.setenv("ALPHA_LIVE_BRAIN_DIR", str(tmp_path / "brain"))
    monkeypatch.setenv("ALPHA_SESSIONS_DIR", str(tmp_path / "sessions"))
```

- [ ] **Step 2: Write the failing test**

```python
# tests/web/test_data_access.py  (append)
def test_load_brain_prefers_live_store_when_present(tmp_path, monkeypatch):
    from alpha_web import data_access as da
    from alpha.meta.store import LiveBrainStore
    store = LiveBrainStore(tmp_path / "brain")
    h, log = store.load()
    log.append("patch_skill", "skill", h.skills.all()[0].skill_id, "update", "x", rationale="r")
    store.save(h, log)
    monkeypatch.setenv("ALPHA_LIVE_BRAIN_DIR", str(tmp_path / "brain"))
    assert da.brain_badge() == {"is_live": True, "edit_count": 1}
    da.load_brain()                      # must not raise and must not write seeds over the store
    assert LiveBrainStore(tmp_path / "brain").edit_count() == 1


def test_brain_badge_seed_baseline_when_empty(tmp_path, monkeypatch):
    from alpha_web import data_access as da
    monkeypatch.setenv("ALPHA_LIVE_BRAIN_DIR", str(tmp_path / "empty"))
    assert da.brain_badge() == {"is_live": False, "edit_count": 0}
```

- [ ] **Step 3: Run test to verify it fails**

Run: `pytest tests/web/test_data_access.py -k "live_store or seed_baseline" -v`
Expected: FAIL with `AttributeError: module 'alpha_web.data_access' has no attribute 'brain_badge'`

- [ ] **Step 4: Write minimal implementation**

```python
# alpha_web/data_access.py  — replace load_brain and add brain_badge + import os
import os
from alpha.meta.store import LiveBrainStore


def _live_store() -> LiveBrainStore | None:
    root = os.environ.get("ALPHA_LIVE_BRAIN_DIR")
    return LiveBrainStore(root) if root else None


def load_brain(seeds_dir: str | Path = SEEDS_DIR) -> HarnessState:
    """The live brain: prefer the LiveBrainStore (ALPHA_LIVE_BRAIN_DIR) when it exists, else the
    frozen seeds. Side-effect-free: a GET never writes (init-from-seeds happens only on apply)."""
    store = _live_store()
    if store is not None and store.is_live():
        return store.load()[0]
    return load_seeds(seeds_dir)


def brain_badge() -> dict:
    """Live-vs-seed status + edit count for the console badge."""
    store = _live_store()
    if store is not None and store.is_live():
        return {"is_live": True, "edit_count": store.edit_count()}
    return {"is_live": False, "edit_count": 0}
```

- [ ] **Step 5: Run test + the full web suite (regression: existing pages still render on seeds when store empty)**

Run: `pytest tests/web -v`
Expected: PASS (the new tests pass; existing page/brain-count tests stay green because the autouse fixture points at an empty store → seed fallback)

- [ ] **Step 6: Commit**

```bash
git add alpha_web/data_access.py tests/web/conftest.py tests/web/test_data_access.py .gitignore
git commit -m "feat(web): load_brain prefers LiveBrainStore (seed fallback) + brain_badge; isolate state in tests"
```

---

# SLICE 6 — Cockpit routes, templates, nav

### Task 12: Nav reshuffle, `/deck`, cockpit shell at `/`

**Files:**
- Modify: `alpha_web/app.py`
- Create: `alpha_web/templates/cockpit.html`
- Test: `tests/web/test_app.py` (migrate deck test) + `tests/web/test_cockpit.py` (new)

**Interfaces:**
- Produces: `GET /deck` (former dashboard), `GET /` (cockpit shell, no LLM), nav with cockpit first; `brain_badge` injected as a template global.

- [ ] **Step 1: Migrate the existing deck assertions and write the new failing tests**

In `tests/web/test_app.py`, change the dashboard test to hit `/deck`, and update the `test_pages_render` param list to include `/deck` and assert `/` is the cockpit:
```python
# tests/web/test_app.py  — edits
@pytest.mark.parametrize("path", ["/", "/deck", "/doctrine", "/memory", "/skills", "/decisions", "/verdict", "/evolution"])
def test_pages_render(client, path):
    r = client.get(path)
    assert r.status_code == 200
    assert "text/html" in r.headers["content-type"]
    assert "<!doctype html>" in r.text.lower()


def test_dashboard_shows_brain_counts_and_the_phase_cycle(client):
    body = client.get("/deck").text            # deck moved from / to /deck
    assert "16" in body and "12" in body
    for phase in ("Washout", "Recovery", "Ignition", "Trend", "Distribution", "Flush"):
        assert phase in body
```

New cockpit test:
```python
# tests/web/test_cockpit.py
import pytest
from fastapi.testclient import TestClient
from alpha_web.app import create_app


@pytest.fixture()
def client():
    return TestClient(create_app())


def test_cockpit_is_home_and_shows_input_panel(client):
    body = client.get("/").text
    assert "Teach" in body and ("paste" in body.lower() or "url" in body.lower())


def test_seed_baseline_badge_shows_when_store_empty(client):
    body = client.get("/deck").text
    assert "seed baseline" in body.lower()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/web/test_cockpit.py tests/web/test_app.py -k "cockpit or dashboard or pages_render" -v`
Expected: FAIL (cockpit route missing / `/deck` 404)

- [ ] **Step 3: Implement the routes + nav + badge global + template**

In `alpha_web/app.py`: rewrite `NAV` (cockpit first, deck second), inject `brain_badge`, add `/deck`, change `/` to render the cockpit:
```python
# alpha_web/app.py  — NAV
NAV = [
    {"path": "/", "key": "teach", "label": "Teach"},
    {"path": "/deck", "key": "deck", "label": "Deck"},
    {"path": "/doctrine", "key": "doctrine", "label": "Doctrine"},
    {"path": "/memory", "key": "memory", "label": "Memory"},
    {"path": "/skills", "key": "skills", "label": "Skills"},
    {"path": "/decisions", "key": "decisions", "label": "Decisions"},
    {"path": "/verdict", "key": "verdict", "label": "Verdict"},
    {"path": "/evolution", "key": "evolution", "label": "Autonomous"},
]
```
In `_make_templates()` add to `t.env.globals.update(...)`: `brain_badge=da.brain_badge`.
Replace the `@app.get("/")` deck handler with a `/deck` handler of the same body, and add a new cockpit `/`:
```python
    @app.get("/deck")
    def deck(request: Request):
        state = da.load_brain()
        return render(request, "dashboard.html", {
            "active": "deck", "stats": da.brain_stats(state),
            "regime": sample.sample_regime(), "market": sample.sample_market_state(),
        })

    @app.get("/")
    def cockpit(request: Request):
        return render(request, "cockpit.html", {"active": "teach", "sessions": _session_store().list()[:20]})
```
Add the store helpers near the top of `create_app` (or module level):
```python
# alpha_web/app.py  — module level
import os, threading
from alpha.meta.store import LiveBrainStore, SessionStore

_MUTATION_LOCK = threading.Lock()

def _brain_store() -> LiveBrainStore:
    return LiveBrainStore(os.environ.get("ALPHA_LIVE_BRAIN_DIR", "./state/brain"))

def _session_store() -> SessionStore:
    return SessionStore(os.environ.get("ALPHA_SESSIONS_DIR", "./state/sessions"))
```
Create `alpha_web/templates/cockpit.html`:
```html
{% extends "base.html" %}
{% block title %}Teach{% endblock %}
{% block content %}
<div class="view-head">
  <p class="eyebrow">META-AGENT · TEACHING COCKPIT</p>
  <h1>Teach the desk.</h1>
  <p class="lede">Show it material — a writeup or a link. It proposes a direction, then concrete edits
    to its doctrine, skills and memory. You approve each one.</p>
</div>

<section class="panel" id="ingest">
  <form hx-post="/evolve/ingest" hx-target="#stage" hx-swap="innerHTML" hx-indicator="#spin">
    <label>Paste text
      <textarea name="text" rows="6" placeholder="Paste an article, a 复盘, a setup writeup…"></textarea>
    </label>
    <label>…or a URL <input type="url" name="url" placeholder="https://…"></label>
    <button type="submit">Propose directions <span id="spin" class="htmx-indicator">·thinking·</span></button>
  </form>
</section>

<section id="stage"><!-- directions / edit-queue / result partials swap in here --></section>

<section class="panel">
  <h2>Past sessions</h2>
  {% include "partials/session_list.html" %}
</section>
{% endblock %}
```
Create `alpha_web/templates/partials/session_list.html`:
```html
<ul class="session-list">
  {% for s in sessions %}
    <li><a href="/evolve/sessions/{{ s.session_id }}">{{ s.session_id }}</a>
      — <span class="pill">{{ s.status }}</span>, {{ s.applied_seqs|length }} edit(s)</li>
  {% else %}
    <li class="muted">No sessions yet.</li>
  {% endfor %}
</ul>
```
Add a small badge to `base.html` near the brand (so every page shows it): in `alpha_web/templates/base.html`, inside the rail brand block, add:
```html
{% set b = brain_badge() %}
<span class="brain-badge">{{ "live · %d edits"|format(b.edit_count) if b.is_live else "seed baseline" }}</span>
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/web/test_cockpit.py tests/web/test_app.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add alpha_web/app.py alpha_web/templates/cockpit.html alpha_web/templates/partials/session_list.html alpha_web/templates/base.html tests/web/test_cockpit.py tests/web/test_app.py
git commit -m "feat(web): cockpit at /, deck moves to /deck, nav reshuffle, live/seed badge"
```

---

### Task 13: POST /evolve/ingest → directions partial

**Files:**
- Modify: `alpha_web/app.py`
- Create: `alpha_web/templates/partials/directions.html`
- Test: `tests/web/test_cockpit.py` (append)

**Interfaces:**
- Consumes: `_session_store`, `_brain_store`, `MetaTools`, `MetaAgent`, `ingest.from_text`/`fetch_url`, `make_client`.
- Produces: `POST /evolve/ingest` (form: `text`, `url`) → creates+persists an `open` `Session`, calls `propose_directions`, returns the directions partial. Missing key → graceful panel.

- [ ] **Step 1: Write the failing test**

```python
# tests/web/test_cockpit.py  (append)
def test_ingest_text_returns_direction_cards(client, monkeypatch):
    monkeypatch.setenv("ALPHA_REFINER_PROVIDER", "mock")
    monkeypatch.setenv("ALPHA_MOCK_RESPONSE", '{"directions": [{"title": "lean into squeezes"}]}')
    r = client.post("/evolve/ingest", data={"text": "High short interest writeup"})
    assert r.status_code == 200 and "lean into squeezes" in r.text
    assert "<html" not in r.text.lower()        # partial only


def test_ingest_missing_key_shows_graceful_panel(client, monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.setenv("ALPHA_REFINER_PROVIDER", "anthropic")
    r = client.post("/evolve/ingest", data={"text": "x"})
    assert r.status_code == 200 and ("set your key" in r.text.lower() or "mock mode" in r.text.lower())
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/web/test_cockpit.py -k ingest -v`
Expected: FAIL (404 — route missing)

- [ ] **Step 3: Implement the route + a MetaAgent builder helper + partial**

In `alpha_web/app.py` add a builder and the route (inside `create_app`):
```python
# alpha_web/app.py  — imports
from fastapi import Form
from alpha.harness.metatools import MetaTools
from alpha.llm.config import make_client
from alpha.meta.agent import MetaAgent
from alpha.meta import ingest as meta_ingest
from alpha.meta.models import Session, new_session_id
from datetime import datetime, timezone


def _meta_agent():
    """Fresh per request: load the live brain, bind MetaTools, attach the refiner LLM."""
    h, log = _brain_store().load()
    return MetaAgent(MetaTools(h, log), make_client("refiner")), (h, log)


def _llm_unavailable(exc: Exception) -> bool:
    return "missing" in str(exc).lower() and "API_KEY" in str(exc)
```
Route:
```python
    @app.post("/evolve/ingest")
    def ingest(request: Request, text: str = Form(""), url: str = Form("")):
        if url.strip():
            try:
                source = meta_ingest.fetch_url(url.strip())
            except meta_ingest.IngestError as e:
                return render(request, "partials/directions.html",
                              {"error": f"{e} — paste the text instead.", "directions": [], "session": None})
        else:
            source = meta_ingest.from_text(text, title="pasted text")
        try:
            agent, _ = _meta_agent()
        except RuntimeError as e:
            if _llm_unavailable(e):
                return render(request, "partials/directions.html",
                              {"error": "No API key — set your key or use mock mode.", "directions": [], "session": None})
            raise
        dirs = agent.propose_directions(source)
        sess = Session(session_id=new_session_id(),
                       created_at=datetime.now(timezone.utc).isoformat(),
                       sources=[source], directions=dirs)
        _session_store().put(sess)
        return render(request, "partials/directions.html",
                      {"error": "", "directions": dirs, "session": sess})
```
Create `alpha_web/templates/partials/directions.html`:
```html
{% if error %}<p class="banner warn">{{ error }}</p>{% endif %}
{% if directions %}
<h2>Pick a direction</h2>
<div class="directions">
  {% for d in directions %}
  <form class="dir-card" hx-post="/evolve/{{ session.session_id }}/direction" hx-target="#stage" hx-swap="innerHTML" hx-indicator="#spin2">
    <input type="hidden" name="direction_id" value="{{ d.direction_id }}">
    <h3>{{ d.title }}</h3>
    <p>{{ d.summary }}</p>
    {% if d.rationale %}<p class="muted">{{ d.rationale }}</p>{% endif %}
    <label>Comment <input name="comment" placeholder="optional steer…"></label>
    <button type="submit">Expand to edits <span id="spin2" class="htmx-indicator">·thinking·</span></button>
  </form>
  {% endfor %}
</div>
{% endif %}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/web/test_cockpit.py -k ingest -v`
Expected: PASS (2 passed)

- [ ] **Step 5: Commit**

```bash
git add alpha_web/app.py alpha_web/templates/partials/directions.html tests/web/test_cockpit.py
git commit -m "feat(web): POST /evolve/ingest -> direction cards (+ graceful no-key)"
```

---

### Task 14: POST /evolve/{sid}/direction → edit-queue partial

**Files:**
- Modify: `alpha_web/app.py`
- Create: `alpha_web/templates/partials/edit_queue.html`, `alpha_web/templates/partials/edit_row.html`
- Test: `tests/web/test_cockpit.py` (append)

**Interfaces:**
- Produces: `POST /evolve/{session_id}/direction` (form: `direction_id`, `comment`) → `expand_to_edits` over the session's source, persists edits onto the session, returns the edit-queue partial.

- [ ] **Step 1: Write the failing test**

```python
# tests/web/test_cockpit.py  (append)
def test_direction_expands_to_edit_queue(client, monkeypatch):
    from alpha.harness.loader import load_seeds
    sid_skill = load_seeds("seeds").skills.all()[0].skill_id
    monkeypatch.setenv("ALPHA_REFINER_PROVIDER", "mock")
    monkeypatch.setenv("ALPHA_MOCK_RESPONSE", '{"directions": [{"title": "tighten"}]}')
    ingest = client.post("/evolve/ingest", data={"text": "writeup"})
    # grab the session + direction ids the server just created
    from alpha.meta.store import SessionStore
    import os
    store = SessionStore(os.environ["ALPHA_SESSIONS_DIR"])
    sess = store.list()[0]
    monkeypatch.setenv("ALPHA_MOCK_RESPONSE",
                       '{"ops": [{"tool": "patch_skill", "args": {"skill_id": "%s", "notes": "n"}, "rationale": "r"}]}' % sid_skill)
    r = client.post(f"/evolve/{sess.session_id}/direction",
                    data={"direction_id": sess.directions[0].direction_id, "comment": ""})
    assert r.status_code == 200 and "patch_skill" in r.text and sid_skill in r.text
    assert store.get(sess.session_id).edits                      # persisted
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/web/test_cockpit.py -k direction_expands -v`
Expected: FAIL (404)

- [ ] **Step 3: Implement route + partials**

```python
# alpha_web/app.py
    @app.post("/evolve/{session_id}/direction")
    def choose_direction(request: Request, session_id: str, direction_id: str = Form(...), comment: str = Form("")):
        store = _session_store()
        sess = store.get(session_id)
        if sess is None:
            return render(request, "partials/edit_queue.html", {"error": "session not found", "session": None, "edits": []})
        sess.chosen_direction_id = direction_id
        sess.direction_comment = comment
        direction = next((d for d in sess.directions if d.direction_id == direction_id), None)
        agent, _ = _meta_agent()
        sess.edits = agent.expand_to_edits(sess.sources[0], direction, comment=comment or None)
        store.put(sess)
        return render(request, "partials/edit_queue.html", {"error": "", "session": sess, "edits": sess.edits})
```
`alpha_web/templates/partials/edit_queue.html`:
```html
{% if error %}<p class="banner warn">{{ error }}</p>{% endif %}
{% if session %}
<h2>Edit queue</h2>
<div id="queue">
  {% for e in edits %}{% include "partials/edit_row.html" %}{% endfor %}
</div>
<form hx-post="/evolve/{{ session.session_id }}/apply" hx-target="#stage" hx-swap="innerHTML" hx-indicator="#spinA">
  <button type="submit">Apply accepted edits <span id="spinA" class="htmx-indicator">·applying·</span></button>
</form>
{% endif %}
```
`alpha_web/templates/partials/edit_row.html`:
```html
<div class="edit-row st-{{ e.status }}" id="row-{{ e.edit_id }}">
  <div class="edit-head"><code>{{ e.tool }}</code> · {{ e.target_kind }} · <strong>{{ e.target_id or '—' }}</strong>
    <span class="pill">{{ e.status }}</span></div>
  {% if e.payload %}<pre class="diff">{{ e.payload }}</pre>{% endif %}
  <p class="muted">{{ e.rationale }}</p>
  {% if e.apply_reason %}<p class="banner warn">{{ e.apply_reason }}</p>{% endif %}
  {% if e.status != 'failed' %}
  <div class="edit-actions">
    <button hx-post="/evolve/{{ session.session_id }}/edit/{{ e.edit_id }}" hx-vals='{"action":"accept"}'
            hx-target="#row-{{ e.edit_id }}" hx-swap="outerHTML">Accept</button>
    <button hx-post="/evolve/{{ session.session_id }}/edit/{{ e.edit_id }}" hx-vals='{"action":"reject"}'
            hx-target="#row-{{ e.edit_id }}" hx-swap="outerHTML">Reject</button>
    <input name="comment" placeholder="comment → re-propose"
           hx-post="/evolve/{{ session.session_id }}/edit/{{ e.edit_id }}" hx-vals='{"action":"comment"}'
           hx-trigger="keyup[key=='Enter']" hx-target="#row-{{ e.edit_id }}" hx-swap="outerHTML" hx-indicator="#spinR">
    <span id="spinR" class="htmx-indicator">·thinking·</span>
  </div>
  {% endif %}
</div>
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/web/test_cockpit.py -k direction_expands -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add alpha_web/app.py alpha_web/templates/partials/edit_queue.html alpha_web/templates/partials/edit_row.html tests/web/test_cockpit.py
git commit -m "feat(web): POST direction -> dry-run edit queue partial"
```

---

### Task 15: POST /evolve/{sid}/edit/{eid} — accept / reject / tweak / comment

**Files:**
- Modify: `alpha_web/app.py`
- Test: `tests/web/test_cockpit.py` (append)

**Interfaces:**
- Produces: `POST /evolve/{session_id}/edit/{edit_id}` (form: `action` ∈ accept|reject|tweak|comment, plus `comment` or tweak fields) → mutates the row, persists, returns the `edit_row.html` partial. `accept`/`reject`/`tweak` are pure-state; `comment` calls `repropose_edit`.

- [ ] **Step 1: Write the failing test**

```python
# tests/web/test_cockpit.py  (append)
def _seed_session_with_one_edit(client, monkeypatch):
    from alpha.harness.loader import load_seeds
    sid_skill = load_seeds("seeds").skills.all()[0].skill_id
    monkeypatch.setenv("ALPHA_REFINER_PROVIDER", "mock")
    monkeypatch.setenv("ALPHA_MOCK_RESPONSE", '{"directions": [{"title": "t"}]}')
    client.post("/evolve/ingest", data={"text": "writeup"})
    import os
    from alpha.meta.store import SessionStore
    store = SessionStore(os.environ["ALPHA_SESSIONS_DIR"])
    sess = store.list()[0]
    monkeypatch.setenv("ALPHA_MOCK_RESPONSE",
                       '{"ops": [{"tool": "patch_skill", "args": {"skill_id": "%s", "notes": "n"}, "rationale": "r"}]}' % sid_skill)
    client.post(f"/evolve/{sess.session_id}/direction",
                data={"direction_id": sess.directions[0].direction_id, "comment": ""})
    return store, store.get(sess.session_id), sid_skill


def test_accept_marks_row_accepted(client, monkeypatch):
    store, sess, _ = _seed_session_with_one_edit(client, monkeypatch)
    eid = sess.edits[0].edit_id
    r = client.post(f"/evolve/{sess.session_id}/edit/{eid}", data={"action": "accept"})
    assert r.status_code == 200 and "accepted" in r.text
    assert store.get(sess.session_id).edits[0].status == "accepted"


def test_comment_reproposes_row_keeping_id(client, monkeypatch):
    store, sess, sid_skill = _seed_session_with_one_edit(client, monkeypatch)
    eid = sess.edits[0].edit_id
    monkeypatch.setenv("ALPHA_MOCK_RESPONSE",
                       '{"ops": [{"tool": "patch_skill", "args": {"skill_id": "%s", "notes": "revised"}, "rationale": "r2"}]}' % sid_skill)
    r = client.post(f"/evolve/{sess.session_id}/edit/{eid}", data={"action": "comment", "comment": "tighter"})
    assert r.status_code == 200 and "revised" in r.text
    assert store.get(sess.session_id).edits[0].edit_id == eid
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/web/test_cockpit.py -k "accept_marks or comment_reproposes" -v`
Expected: FAIL (404)

- [ ] **Step 3: Implement route**

```python
# alpha_web/app.py
    @app.post("/evolve/{session_id}/edit/{edit_id}")
    def edit_action(request: Request, session_id: str, edit_id: str,
                    action: str = Form(...), comment: str = Form("")):
        store = _session_store()
        sess = store.get(session_id)
        row = next((e for e in (sess.edits if sess else [])  if e.edit_id == edit_id), None)
        if row is None:
            return render(request, "partials/edit_row.html", {"e": None, "session": sess})
        if action == "accept":
            row.status = "accepted"
        elif action == "reject":
            row.status = "rejected"
        elif action == "comment" and comment.strip():
            direction = next((d for d in sess.directions if d.direction_id == sess.chosen_direction_id), None)
            agent, _ = _meta_agent()
            new_row = agent.repropose_edit(sess.sources[0], direction, row, comment.strip())
            sess.edits = [new_row if e.edit_id == edit_id else e for e in sess.edits]
            row = new_row
        store.put(sess)
        return render(request, "partials/edit_row.html", {"e": row, "session": sess})
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/web/test_cockpit.py -k "accept_marks or comment_reproposes" -v`
Expected: PASS (2 passed)

- [ ] **Step 5: Commit**

```bash
git add alpha_web/app.py tests/web/test_cockpit.py
git commit -m "feat(web): per-row accept/reject/comment (single-row re-propose)"
```

---

### Task 16: POST /evolve/{sid}/apply — lock, snapshot, persist

**Files:**
- Modify: `alpha_web/app.py`
- Create: `alpha_web/templates/partials/apply_result.html`
- Test: `tests/web/test_cockpit.py` (append)

**Interfaces:**
- Produces: `POST /evolve/{session_id}/apply` → under `_MUTATION_LOCK`: snapshot the live brain (if live), apply accepted edits to a freshly-loaded brain, save it, record `applied_seqs`/`snapshot_before`/`status="applied"`, return the result partial. Only an `open` session may apply.

- [ ] **Step 1: Write the failing test**

```python
# tests/web/test_cockpit.py  (append)
def test_apply_mutates_live_brain_and_finalizes_session(client, monkeypatch):
    store, sess, sid_skill = _seed_session_with_one_edit(client, monkeypatch)
    eid = sess.edits[0].edit_id
    client.post(f"/evolve/{sess.session_id}/edit/{eid}", data={"action": "accept"})
    r = client.post(f"/evolve/{sess.session_id}/apply")
    assert r.status_code == 200 and "applied" in r.text.lower()
    final = store.get(sess.session_id)
    assert final.status == "applied" and final.applied_seqs == [0]
    # the live brain now reflects the edit
    from alpha.meta.store import LiveBrainStore
    import os
    h, _ = LiveBrainStore(os.environ["ALPHA_LIVE_BRAIN_DIR"]).load()
    assert h.skills.get(sid_skill).notes == "n"


def test_apply_on_already_applied_session_is_rejected(client, monkeypatch):
    store, sess, _ = _seed_session_with_one_edit(client, monkeypatch)
    sess.status = "applied"; store.put(sess)
    r = client.post(f"/evolve/{sess.session_id}/apply")
    assert r.status_code == 200 and "not open" in r.text.lower()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/web/test_cockpit.py -k "apply_mutates_live or already_applied" -v`
Expected: FAIL (404)

- [ ] **Step 3: Implement route + partial**

Add `from alpha.llm.client import MockLLMClient` to the `alpha_web/app.py` imports, then add the route:
```python
# alpha_web/app.py
    @app.post("/evolve/{session_id}/apply")
    def apply_session(request: Request, session_id: str):
        sstore = _session_store()
        sess = sstore.get(session_id)
        if sess is None or sess.status != "open":
            return render(request, "partials/apply_result.html",
                          {"error": "session is not open", "session": sess, "applied": []})
        with _MUTATION_LOCK:
            bstore = _brain_store()
            h, log = bstore.load()
            if not bstore.is_live():
                bstore.save(h, log)                       # materialize before snapshot
            sess.snapshot_before = bstore.snapshot(session_id)
            # apply makes NO LLM call, so it needs no API key — pass a mock client.
            agent = MetaAgent(MetaTools(h, log), MockLLMClient("{}"))
            accepted = [e for e in sess.edits if e.status == "accepted"]
            applied, _ = agent.apply(accepted)
            bstore.save(h, log)
            sess.applied_seqs = [r.seq for r in applied]
            sess.status = "applied"
            sstore.put(sess)
        return render(request, "partials/apply_result.html",
                      {"error": "", "session": sess, "applied": applied})
```
`alpha_web/templates/partials/apply_result.html`:
```html
{% if error %}<p class="banner warn">{{ error }}</p>
{% else %}
<h2>Applied</h2>
<p>{{ applied|length }} edit(s) committed to the live brain.</p>
<ul>{% for r in applied %}<li><code>{{ r.tool }}</code> {{ r.target_id }} (seq {{ r.seq }})</li>{% endfor %}</ul>
<form hx-post="/evolve/rollback/{{ session.session_id }}" hx-target="#stage" hx-swap="innerHTML">
  <button type="submit">Roll back this session</button>
</form>
{% endif %}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/web/test_cockpit.py -k "apply_mutates_live or already_applied" -v`
Expected: PASS (2 passed)

- [ ] **Step 5: Commit**

```bash
git add alpha_web/app.py alpha_web/templates/partials/apply_result.html tests/web/test_cockpit.py
git commit -m "feat(web): POST apply (lock + snapshot + persist live brain)"
```

---

### Task 17: Session browse + rollback + regenerate

**Files:**
- Modify: `alpha_web/app.py`
- Test: `tests/web/test_cockpit.py` (append)

**Interfaces:**
- Produces: `GET /evolve/sessions`, `GET /evolve/sessions/{session_id}`, `POST /evolve/rollback/{session_id}` (under lock, restores `snapshot_before`, appends a note), `POST /evolve/{session_id}/direction/regenerate` (form: `comment`).

- [ ] **Step 1: Write the failing test**

```python
# tests/web/test_cockpit.py  (append)
def test_rollback_restores_pre_apply_brain(client, monkeypatch):
    store, sess, sid_skill = _seed_session_with_one_edit(client, monkeypatch)
    eid = sess.edits[0].edit_id
    client.post(f"/evolve/{sess.session_id}/edit/{eid}", data={"action": "accept"})
    client.post(f"/evolve/{sess.session_id}/apply")
    r = client.post(f"/evolve/rollback/{sess.session_id}")
    assert r.status_code == 200
    from alpha.meta.store import LiveBrainStore
    import os
    assert LiveBrainStore(os.environ["ALPHA_LIVE_BRAIN_DIR"]).edit_count() == 0
    assert "rolled back" in store.get(sess.session_id).notes[0].lower()


def test_session_detail_page_renders(client, monkeypatch):
    store, sess, _ = _seed_session_with_one_edit(client, monkeypatch)
    r = client.get(f"/evolve/sessions/{sess.session_id}")
    assert r.status_code == 200 and sess.session_id in r.text
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/web/test_cockpit.py -k "rollback_restores or session_detail" -v`
Expected: FAIL (404)

- [ ] **Step 3: Implement routes**

```python
# alpha_web/app.py
    @app.post("/evolve/{session_id}/direction/regenerate")
    def regenerate_directions(request: Request, session_id: str, comment: str = Form("")):
        store = _session_store()
        sess = store.get(session_id)
        agent, _ = _meta_agent()
        sess.directions = agent.propose_directions(sess.sources[0], comment=comment or None)
        store.put(sess)
        return render(request, "partials/directions.html", {"error": "", "directions": sess.directions, "session": sess})

    @app.get("/evolve/sessions")
    def sessions_index(request: Request):
        return render(request, "cockpit.html", {"active": "teach", "sessions": _session_store().list()[:50]})

    @app.get("/evolve/sessions/{session_id}")
    def session_detail(request: Request, session_id: str):
        sess = _session_store().get(session_id)
        return render(request, "session_detail.html", {"active": "teach", "session": sess})

    @app.post("/evolve/rollback/{session_id}")
    def rollback(request: Request, session_id: str):
        sstore = _session_store()
        sess = sstore.get(session_id)
        if sess and sess.snapshot_before:
            with _MUTATION_LOCK:
                _brain_store().restore(sess.snapshot_before)
            sess.notes.append("rolled back to pre-apply snapshot")
            sstore.put(sess)
        return render(request, "partials/apply_result.html",
                      {"error": "rolled back" if sess else "no snapshot", "session": sess, "applied": []})
```
Create `alpha_web/templates/session_detail.html`:
```html
{% extends "base.html" %}
{% block title %}Session{% endblock %}
{% block content %}
<div class="view-head"><p class="eyebrow">TEACHING SESSION</p><h1>{{ session.session_id }}</h1>
  <p class="lede">{{ session.status }} · {{ session.applied_seqs|length }} applied edit(s)</p></div>
{% if session %}
<section class="panel"><h2>Edits</h2>
  {% for e in session.edits %}{% include "partials/edit_row.html" %}{% endfor %}
</section>
{% endif %}
{% endblock %}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/web/test_cockpit.py -k "rollback_restores or session_detail" -v`
Expected: PASS (2 passed)

- [ ] **Step 5: Run the whole suite**

Run: `pytest -q`
Expected: PASS (all green)

- [ ] **Step 6: Commit**

```bash
git add alpha_web/app.py alpha_web/templates/session_detail.html tests/web/test_cockpit.py
git commit -m "feat(web): session browse, rollback, regenerate directions"
```

---

### Task 18: Loading-state affordance (app.js + CSS)

**Files:**
- Modify: `alpha_web/static/app.js`
- Modify: `alpha_web/static/app.css` (append cockpit + indicator styles)
- Test: manual (covered visually in Slice 7)

**Interfaces:**
- Produces: an htmx in-flight handler that disables the submitting control and reveals `.htmx-indicator` while a request is pending.

- [ ] **Step 1: Append the handler to `app.js`**

```javascript
// alpha_web/static/app.js  (append)
document.body.addEventListener('htmx:beforeRequest', (e) => {
  const btn = e.detail.elt.querySelector('button[type=submit]') || e.detail.elt;
  if (btn && btn.tagName === 'BUTTON') btn.disabled = true;
});
document.body.addEventListener('htmx:afterRequest', (e) => {
  const btn = e.detail.elt.querySelector('button[type=submit]') || e.detail.elt;
  if (btn && btn.tagName === 'BUTTON') btn.disabled = false;
});
```

- [ ] **Step 2: Append minimal CSS for the cockpit + indicator**

```css
/* alpha_web/static/app.css  (append) */
.htmx-indicator { opacity: 0; font: 12px var(--mono); color: var(--gold); }
.htmx-request .htmx-indicator, .htmx-indicator.htmx-request { opacity: 1; }
.directions { display: grid; gap: 12px; grid-template-columns: repeat(auto-fit, minmax(220px, 1fr)); }
.dir-card, .edit-row { border: 1px solid var(--line, #2a3550); border-radius: 8px; padding: 12px; }
.edit-row.st-accepted { border-color: var(--up); }
.edit-row.st-failed, .edit-row.st-rejected { opacity: .6; }
.edit-row .diff { background: var(--ink); padding: 8px; border-radius: 6px; overflow:auto; font: 12px var(--mono); }
.brain-badge { display:block; font: 11px var(--mono); color: var(--gold); margin-top: 4px; }
```

- [ ] **Step 3: Verify the suite still passes (no behavior regression)**

Run: `pytest tests/web -q`
Expected: PASS

- [ ] **Step 4: Commit**

```bash
git add alpha_web/static/app.js alpha_web/static/app.css
git commit -m "feat(web): cockpit loading-state (disable-on-inflight) + styles"
```

---

# SLICE 7 — Visual verification

### Task 19: Playwright drive the full teaching loop

**Files:**
- Test: manual Playwright session (screenshots saved under `.playwright-mcp/`)

- [ ] **Step 1: Launch the cockpit in mock mode (fully offline)**

```bash
cd /Users/pan/Desktop/self-evolve/evolving-alpha-us
ALPHA_REFINER_PROVIDER=mock \
ALPHA_MOCK_RESPONSE='{"directions":[{"title":"Lean into squeezes","summary":"raise weight on high-SI low-float setups"}]}' \
ALPHA_LIVE_BRAIN_DIR=./state/brain ALPHA_SESSIONS_DIR=./state/sessions \
python -m alpha_web &
```

- [ ] **Step 2: Drive it in a browser and look**

Navigate to `http://127.0.0.1:8100/`, paste text, submit, screenshot the directions; pick one (the mock returns a `{"ops":[...]}` for the edits step — restart with an edits-shaped `ALPHA_MOCK_RESPONSE` or wire a two-response mock), screenshot the edit queue; accept a row; apply; screenshot the result. **Look at each screenshot** — a blank frame is a launch failure.

- [ ] **Step 3: Confirm the badge flips to "live · N edits"**

After an apply, reload `/deck` and confirm the brain badge reads `live · 1 edits` (it read `seed baseline` before).

- [ ] **Step 4: Stop the server**

```bash
kill %1
```

- [ ] **Step 5: Final full-suite gate + commit any test-only fixes**

```bash
pytest -q
git add -A && git commit -m "test(web): cockpit visual verification notes" --allow-empty
```

---

## Notes for the executor

- **Out of scope (roadmap, do not build):** image/vision ingestion; the self-learning (Refiner reflection→directions) channel; auto-resume of an in-flight draft on `GET /`; post-apply red-line lint for skills/lessons; branchable brains; auth/non-localhost. See spec §11.
- **`extract_json_object`** lives in `alpha/llm/extract.py` — reuse it (already used by `parse_ops`); do not re-implement JSON extraction.
- **MockLLMClient** accepts a `list[str]` for multi-call flows; in route tests that only make one LLM call per request, a single `ALPHA_MOCK_RESPONSE` string is enough (each request rebuilds the client).
- If a route needs two LLM responses in one process step, set `ALPHA_MOCK_RESPONSE` to the response for that step before each POST (the tests above do this).
```
