# Self-Evolution §5 — Edit Provenance + Conflict→User Adjudication Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement spec §5.3/§5.4 against the EXISTING proposers (Refiner = self-study, Sonia + the B-WIDE converse write tool = teaching): every gated edit carries a frozen `EditProvenance` block stamped at the gate; a self-study op that contests a **teaching-owned** H element is **held** (enqueued to a `ConflictQueue` for user adjudication, NOT applied), not silently rejected.

**Architecture:** The gate `try_apply_op` **keeps its 2-tuple return** `(record, reason)` (decided: minimize blast radius on the system's spine). It gains two optional keyword params — `provenance` and `conflict_queue` — both default `None` (existing callers and tests are byte-unchanged). On a successful dispatch the provenance is stamped onto the just-appended `EditRecord` via `model_copy` + an in-log replacement (the 9 `MetaTools` `log.append` sites stay untouched). Before dispatch, if a self-study op contests a teaching-owned element, the gate enqueues it to `conflict_queue` and returns `(None, "held_for_review: …")` **without applying**. No GEPA, no Hermes, no memory work.

**Tech Stack:** Python ≥3.11, pydantic v2, pytest. Edits: `alpha/harness/edit_log.py` (+`EditProvenance`, +`EditRecord.provenance`, +`latest_for`/`stamp_last`), `alpha/refine/apply.py` (+stamp, +held-enqueue), new `alpha/refine/conflict.py`, new `alpha/meta/conflict_store.py`, and the 3 proposers (`refiner.py`, `meta/agent.py`, `converse/tools.py`).

## Global Constraints

- **Python `>=3.11`**, pydantic v2. Deterministic tests (no LLM).
- **2-tuple PRESERVED:** `try_apply_op(...) -> tuple[EditRecord | None, str | None]` unchanged. New params `provenance=None`, `conflict_queue=None` are keyword-only + optional. With both `None`, behavior is **byte-identical** to today — the existing suite (currently **596 passed**) MUST stay green, and NO existing caller/test changes its unpacking.
- **Additive provenance:** `EditRecord.provenance: EditProvenance | None = None` (default `None`; `to_dict`/`from_dict` still round-trip). The 9 `MetaTools` `log.append` call sites are NOT touched — provenance is stamped post-dispatch by the gate.
- **Asymmetry (spec §5.4):** only a **self-study** op can be held; a **teaching** op applies directly. Only **mutate/retire/demote** verbs of an EXISTING element count as a contest — create verbs (`write_skill`, `process_memory`) never conflict.
- **Held ≠ applied:** a held op is enqueued and NOT dispatched (live H unchanged). Held is distinguished from a plain reject by the `"held_for_review:"` reason prefix + the queue side-effect.
- **Out of scope (deferred to a §5 follow-up):** the Sonia FastAPI `/conflicts` adjudication UI; LLM-generated conflict framing; auto-re-apply on "accept self-study" (record intent only). `parent_checkpoint_version` is read from `HarnessManager.latest_version()` when reachable, else `None`.
- English; follow existing patterns (mirror `alpha/meta/store.py::SessionStore` for the queue).

## File Structure

- Modify: `alpha/harness/edit_log.py` (`EditProvenance`, `EditRecord.provenance`, `EditLog.latest_for`, `EditLog.stamp_last`).
- Modify: `alpha/refine/apply.py` (`provenance` + `conflict_queue` params; stamp; held-enqueue).
- Create: `alpha/refine/conflict.py` (`_KIND` tool→kind map, `is_conflict`).
- Create: `alpha/meta/conflict_store.py` (`HeldConflict` model + `ConflictQueue`).
- Modify: `alpha/refine/refiner.py`, `alpha/meta/agent.py`, `alpha/converse/tools.py` (thread `provenance` from the 3 proposers).
- Tests: `tests/harness/test_edit_provenance.py`, `tests/refine/test_conflict.py`, `tests/refine/test_apply_provenance_held.py`, `tests/meta/test_conflict_store.py`, `tests/refine/test_proposer_provenance.py`.

---

### Task 1: `EditProvenance` + `EditRecord.provenance` + `EditLog.latest_for`/`stamp_last`

**Files:**
- Modify: `alpha/harness/edit_log.py`
- Test: `tests/harness/test_edit_provenance.py`

**Interfaces:**
- Produces: `EditProvenance` (frozen pydantic); `EditRecord.provenance: EditProvenance | None = None`; `EditLog.latest_for(target_kind, target_id) -> EditRecord | None` (most recent record for an element); `EditLog.stamp_last(provenance) -> EditRecord` (replace the last record with a provenance-stamped copy). Consumed by Tasks 2–6.

- [ ] **Step 1: Write the failing test**

```python
# tests/harness/test_edit_provenance.py
from alpha.harness.edit_log import EditLog, EditRecord, EditProvenance

def test_provenance_defaults_none_and_round_trips():
    log = EditLog()
    rec = log.append("patch_skill", "skill", "s1", "update", rationale="r")
    assert rec.provenance is None
    p = EditProvenance(path="self_study", proposer="refiner", parent_checkpoint_version=3)
    stamped = log.stamp_last(p)
    assert stamped.provenance == p and log.records()[-1].provenance == p
    assert EditLog.from_dict(log.to_dict()).records()[-1].provenance == p   # serializes

def test_latest_for_returns_most_recent_for_element():
    log = EditLog()
    log.append("process_memory", "memory", "m1", "create", rationale="r")
    log.stamp_last(EditProvenance(path="teaching", proposer="sonia"))
    log.append("update_memory", "memory", "m1", "update", rationale="r")
    log.stamp_last(EditProvenance(path="self_study", proposer="refiner"))
    log.append("patch_skill", "skill", "s1", "update", rationale="r")
    latest = log.latest_for("memory", "m1")
    assert latest is not None and latest.op == "update" and latest.provenance.proposer == "refiner"
    assert log.latest_for("skill", "nope") is None
```

- [ ] **Step 2: Run to verify it fails**

Run: `python -m pytest tests/harness/test_edit_provenance.py -v`
Expected: FAIL — `ImportError: cannot import name 'EditProvenance'`.

- [ ] **Step 3: Implement** — edit `alpha/harness/edit_log.py`:

Add the import + model (after the existing imports):
```python
from typing import Literal

class EditProvenance(BaseModel):
    """Who proposed an edit and on what basis (spec §5.3). Stamped at the gate, never by MetaTools."""
    model_config = ConfigDict(frozen=True)
    path: Literal["self_study", "teaching"]
    proposer: Literal["refiner", "forge", "sonia", "hermes"]
    evidence_ref: dict | None = None
    reflection_lm_id: str | None = None
    reflection_seed: int | None = None
    human_approver: str | None = None
    parent_checkpoint_version: int | None = None
    resolution: str | None = None
```
Add the field to `EditRecord` (after `rationale: str = ""`):
```python
    provenance: EditProvenance | None = None    # stamped at the gate (§5.3); None for legacy/ungated records
```
Add two methods to `EditLog`:
```python
    def stamp_last(self, provenance: "EditProvenance") -> EditRecord:
        """Replace the most-recently-appended record with a provenance-stamped copy (frozen-safe)."""
        if not self._records:
            raise IndexError("no record to stamp")
        self._records[-1] = self._records[-1].model_copy(update={"provenance": provenance})
        return self._records[-1]

    def latest_for(self, target_kind: str, target_id: str) -> EditRecord | None:
        """The most recent record touching (target_kind, target_id), or None."""
        for r in reversed(self._records):
            if r.target_kind == target_kind and r.target_id == target_id:
                return r
        return None
```

- [ ] **Step 4: Run to verify it passes + harness tests green**

Run: `python -m pytest tests/harness/test_edit_provenance.py tests/harness -q`
Expected: green (the new optional field is back-compat; existing EditLog/EditRecord tests unaffected).

- [ ] **Step 5: Commit**

```bash
git add alpha/harness/edit_log.py tests/harness/test_edit_provenance.py
git commit -m "feat(self-evo): EditProvenance + EditRecord.provenance + EditLog.latest_for/stamp_last"
```

---

### Task 2: Stamp provenance inside `try_apply_op` (2-tuple preserved)

**Files:**
- Modify: `alpha/refine/apply.py`
- Test: `tests/refine/test_apply_provenance_held.py` (the provenance half)

**Interfaces:**
- Produces: `try_apply_op(..., *, allowed, min_retire_samples, min_promote_samples, provenance=None, conflict_queue=None)` — on a successful dispatch, if `provenance is not None`, the appended `EditRecord` is stamped via `meta.log.stamp_last(provenance)` and that stamped record is returned. Still a 2-tuple. (`conflict_queue` is wired in Task 4.)

- [ ] **Step 1: Write the failing test**

```python
# tests/refine/test_apply_provenance_held.py
from alpha.harness.doctrine import Doctrine
from alpha.harness.registry import SkillRegistry, MemoryStore
from alpha.harness.state import HarnessState
from alpha.harness.metatools import MetaTools
from alpha.harness.edit_log import EditLog, EditProvenance
from alpha.refine.apply import try_apply_op
from alpha.refine.ops import RefineOp, PASS_TOOLS

def _h():
    return HarnessState(doctrine=Doctrine(), skills=SkillRegistry.from_skills([]),
                        memory=MemoryStore.from_lessons([]))

def test_apply_stamps_provenance_on_the_record():
    h = _h(); log = EditLog(); meta = MetaTools(h, log)
    op = RefineOp(tool="process_memory", args={"lesson_id": "m1", "phases": ["trend"],
                  "outcome": "win", "lesson": "x"}, rationale="learned")
    p = EditProvenance(path="teaching", proposer="sonia")
    rec, reason = try_apply_op(meta, h, op, allowed=PASS_TOOLS["M"],
                               min_retire_samples=5, min_promote_samples=3, provenance=p)
    assert reason is None and rec is not None and rec.provenance == p
    assert log.records()[-1].provenance == p

def test_apply_without_provenance_is_unchanged():
    h = _h(); log = EditLog(); meta = MetaTools(h, log)
    op = RefineOp(tool="process_memory", args={"lesson_id": "m2", "phases": ["trend"],
                  "outcome": "win", "lesson": "y"}, rationale="learned")
    rec, reason = try_apply_op(meta, h, op, allowed=PASS_TOOLS["M"],
                               min_retire_samples=5, min_promote_samples=3)   # no provenance
    assert reason is None and rec is not None and rec.provenance is None
```

- [ ] **Step 2: Run to verify it fails**

Run: `python -m pytest tests/refine/test_apply_provenance_held.py::test_apply_stamps_provenance_on_the_record -v`
Expected: FAIL — `try_apply_op() got an unexpected keyword argument 'provenance'`.

- [ ] **Step 3: Implement** — edit `alpha/refine/apply.py`:

Add the import:
```python
from alpha.harness.edit_log import EditRecord, EditProvenance
```
Change the signature (add the two keyword params):
```python
def try_apply_op(meta: MetaTools, harness: HarnessState, op: RefineOp, *, allowed: frozenset[str],
                 min_retire_samples: int, min_promote_samples: int,
                 provenance: EditProvenance | None = None,
                 conflict_queue=None) -> tuple[EditRecord | None, str | None]:
```
Change the dispatch tail (the `try: rec = _dispatch(...) ... return rec, None`) to stamp provenance:
```python
    try:
        rec = _dispatch(meta, op)
    except _DISPATCH_ERRORS as e:
        return None, f"{type(e).__name__}: {e}"
    if provenance is not None:
        rec = meta.log.stamp_last(provenance)
    return rec, None
```

- [ ] **Step 4: Run to verify it passes**

Run: `python -m pytest tests/refine/test_apply_provenance_held.py -k provenance -v`
Expected: 2 PASS.

- [ ] **Step 5: Commit**

```bash
git add alpha/refine/apply.py tests/refine/test_apply_provenance_held.py
git commit -m "feat(self-evo): try_apply_op stamps provenance (2-tuple preserved, additive)"
```

---

### Task 3: Conflict-detection predicate (`alpha/refine/conflict.py`)

**Files:**
- Create: `alpha/refine/conflict.py`
- Test: `tests/refine/test_conflict.py`

**Interfaces:**
- Consumes: `EditLog.latest_for` (Task 1), `_target_id` (from `apply.py`), `EditProvenance`.
- Produces: `is_conflict(log: EditLog, op: RefineOp, provenance: EditProvenance | None) -> bool` — True iff `provenance.path == "self_study"` AND `op.tool` is a contest verb AND the element's latest authoritative edit has `path == "teaching"`. Consumed by Task 4.

- [ ] **Step 1: Write the failing test**

```python
# tests/refine/test_conflict.py
from alpha.harness.edit_log import EditLog, EditProvenance
from alpha.refine.ops import RefineOp
from alpha.refine.conflict import is_conflict

def _log_with_teaching_lesson():
    log = EditLog()
    log.append("process_memory", "memory", "m1", "create", rationale="r")
    log.stamp_last(EditProvenance(path="teaching", proposer="sonia"))
    return log

SELF = EditProvenance(path="self_study", proposer="refiner")
TEACH = EditProvenance(path="teaching", proposer="sonia")

def test_self_study_contesting_teaching_owned_is_conflict():
    log = _log_with_teaching_lesson()
    op = RefineOp(tool="demote_memory", args={"lesson_id": "m1", "factor": 0.5}, rationale="data says weak")
    assert is_conflict(log, op, SELF) is True

def test_teaching_op_never_conflicts():
    log = _log_with_teaching_lesson()
    op = RefineOp(tool="demote_memory", args={"lesson_id": "m1", "factor": 0.5}, rationale="r")
    assert is_conflict(log, op, TEACH) is False           # teaching applies directly (asymmetry)

def test_create_verb_never_conflicts():
    log = _log_with_teaching_lesson()
    op = RefineOp(tool="process_memory", args={"lesson_id": "m2", "outcome": "win", "lesson": "z"}, rationale="r")
    assert is_conflict(log, op, SELF) is False            # a brand-new element can't contest existing teaching

def test_self_study_on_self_study_owned_is_not_conflict():
    log = EditLog()
    log.append("process_memory", "memory", "m3", "create", rationale="r")
    log.stamp_last(EditProvenance(path="self_study", proposer="refiner"))
    op = RefineOp(tool="demote_memory", args={"lesson_id": "m3", "factor": 0.5}, rationale="r")
    assert is_conflict(log, op, SELF) is False

def test_untouched_element_is_not_conflict():
    op = RefineOp(tool="demote_memory", args={"lesson_id": "ghost", "factor": 0.5}, rationale="r")
    assert is_conflict(EditLog(), op, SELF) is False
```

- [ ] **Step 2: Run to verify it fails**

Run: `python -m pytest tests/refine/test_conflict.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'alpha.refine.conflict'`.

- [ ] **Step 3: Implement**

```python
# alpha/refine/conflict.py
from __future__ import annotations
from alpha.harness.edit_log import EditLog, EditProvenance
from alpha.refine.ops import RefineOp
from alpha.refine.apply import _target_id

# tool -> the H element kind it targets (mirrors apply._dispatch / _target_id)
_KIND: dict[str, str] = {
    "write_skill": "skill", "patch_skill": "skill", "retire_skill": "skill",
    "revive_skill": "skill", "promote_skill": "skill",
    "process_memory": "memory", "update_memory": "memory", "demote_memory": "memory",
    "rewrite_doctrine": "doctrine",
}
# verbs that MUTATE/RETIRE/DEMOTE an EXISTING element (create verbs are excluded — they can't contest)
_CONTEST_VERBS: frozenset[str] = frozenset({
    "patch_skill", "retire_skill", "revive_skill", "promote_skill",
    "demote_memory", "update_memory", "rewrite_doctrine",
})

def is_conflict(log: EditLog, op: RefineOp, provenance: EditProvenance | None) -> bool:
    """True iff a self-study op contests a teaching-owned existing H element (spec §5.4 asymmetry)."""
    if provenance is None or provenance.path != "self_study":
        return False                                   # only self-study can be held; teaching applies
    if op.tool not in _CONTEST_VERBS:
        return False                                   # create verbs never contest
    tid = _target_id(op.tool, op.args)
    if tid is None:
        return False
    latest = log.latest_for(_KIND.get(op.tool, ""), tid)
    return latest is not None and latest.provenance is not None and latest.provenance.path == "teaching"
```

- [ ] **Step 4: Run to verify it passes**

Run: `python -m pytest tests/refine/test_conflict.py -v`
Expected: 5 PASS.

- [ ] **Step 5: Commit**

```bash
git add alpha/refine/conflict.py tests/refine/test_conflict.py
git commit -m "feat(self-evo): conflict detection (self-study contesting teaching-owned H)"
```

---

### Task 4: Held-for-review enqueue in `try_apply_op`

**Files:**
- Modify: `alpha/refine/apply.py`
- Modify: `tests/refine/test_apply_provenance_held.py` (the held half)

**Interfaces:**
- Consumes: `is_conflict` (Task 3), `ConflictQueue` (Task 5 — but the gate only needs an object with `.add(...)`; the test uses a tiny fake/list).
- Produces: when `conflict_queue is not None` and `is_conflict(meta.log, op, provenance)`, the gate enqueues `(op, provenance, contested_record)` and returns `(None, "held_for_review: <detail>")` WITHOUT dispatching.

- [ ] **Step 1: Write the failing tests** (append to `tests/refine/test_apply_provenance_held.py`)

```python
from alpha.harness.edit_log import EditLog as _EL

class _FakeQueue:
    def __init__(self): self.items = []
    def add(self, **kw): self.items.append(kw)

def test_self_study_contesting_teaching_is_held_not_applied():
    h = _h(); log = EditLog(); meta = MetaTools(h, log)
    # teaching first creates m1
    try_apply_op(meta, h, RefineOp(tool="process_memory",
                 args={"lesson_id": "m1", "phases": ["trend"], "outcome": "win", "lesson": "human says key"},
                 rationale="taught"), allowed=PASS_TOOLS["M"], min_retire_samples=5, min_promote_samples=3,
                 provenance=EditProvenance(path="teaching", proposer="sonia"))
    q = _FakeQueue()
    # self-study tries to demote the teaching-owned m1 -> HELD
    rec, reason = try_apply_op(meta, h, RefineOp(tool="demote_memory", args={"lesson_id": "m1", "factor": 0.5},
                 rationale="data weak"), allowed=PASS_TOOLS["M"], min_retire_samples=5, min_promote_samples=3,
                 provenance=EditProvenance(path="self_study", proposer="refiner"), conflict_queue=q)
    assert rec is None and reason.startswith("held_for_review")
    assert len(q.items) == 1                              # enqueued for the user
    assert h.memory.get("m1").importance.time_decay == 1.0  # NOT demoted (live H unchanged)

def test_no_conflict_queue_means_no_held_path():
    # without a conflict_queue the gate behaves as before (the op applies or rejects on its own merits)
    h = _h(); log = EditLog(); meta = MetaTools(h, log)
    try_apply_op(meta, h, RefineOp(tool="process_memory",
                 args={"lesson_id": "m1", "outcome": "win", "lesson": "x"}, rationale="t"),
                 allowed=PASS_TOOLS["M"], min_retire_samples=5, min_promote_samples=3,
                 provenance=EditProvenance(path="teaching", proposer="sonia"))
    rec, reason = try_apply_op(meta, h, RefineOp(tool="demote_memory", args={"lesson_id": "m1", "factor": 0.5},
                 rationale="r"), allowed=PASS_TOOLS["M"], min_retire_samples=5, min_promote_samples=3,
                 provenance=EditProvenance(path="self_study", proposer="refiner"))   # no queue
    assert reason is None and rec is not None             # applies (no held path without a queue)
```

> **Implementer note:** confirm `HarnessState.memory.get(lesson_id)` returns the `Lesson` and that `Lesson.importance.time_decay` is the demote target (read `alpha/harness/memory.py`); if the accessor differs, assert "not demoted" via the real accessor. The point is: a held op must NOT mutate live H.

- [ ] **Step 2: Run to verify they fail**

Run: `python -m pytest tests/refine/test_apply_provenance_held.py -k held -v`
Expected: FAIL — the op currently applies (no held path yet).

- [ ] **Step 3: Implement** — edit `alpha/refine/apply.py`:

Add the import:
```python
from alpha.refine.conflict import is_conflict
```
Insert the held check AFTER the evidence-floor gates and BEFORE the `try: rec = _dispatch(...)`:
```python
    if conflict_queue is not None and is_conflict(meta.log, op, provenance):
        contested = meta.log.latest_for(_target_kind(op.tool), tid) if tid else None
        conflict_queue.add(op=op.model_dump(), provenance=provenance.model_dump() if provenance else None,
                           contested=contested.model_dump() if contested else None)
        return None, "held_for_review: self-study contests a teaching-owned element"
```
Add a tiny `_target_kind` helper next to `_target_id` (reuse `conflict._KIND`):
```python
def _target_kind(tool: str) -> str:
    from alpha.refine.conflict import _KIND
    return _KIND.get(tool, "")
```

> **Implementer note:** avoid a circular import — `conflict.py` imports `_target_id` from `apply.py`, and `apply.py` imports `is_conflict` from `conflict.py`. Both imports are at module top level and Python handles this as long as neither uses the other at import time (they only call at runtime). If a circular-import error appears, make `apply.py`'s `from alpha.refine.conflict import is_conflict` a function-local import inside `try_apply_op` (and keep `_target_kind`'s `_KIND` import local, as written).

- [ ] **Step 4: Run to verify they pass + full suite green**

Run: `python -m pytest tests/refine/test_apply_provenance_held.py -v && python -m pytest -q`
Expected: held + provenance tests PASS; full suite green (no `conflict_queue` is passed anywhere existing → the held path is dormant; every existing `try_apply_op` caller is byte-identical).

- [ ] **Step 5: Commit**

```bash
git add alpha/refine/apply.py tests/refine/test_apply_provenance_held.py
git commit -m "feat(self-evo): held-for-review enqueue (conflict -> queue, not applied; 2-tuple kept)"
```

---

### Task 5: `ConflictQueue` store

**Files:**
- Create: `alpha/meta/conflict_store.py`
- Test: `tests/meta/test_conflict_store.py`

**Interfaces:**
- Produces: `HeldConflict` (pydantic: `conflict_id, created_at, op: dict, provenance: dict | None, contested: dict | None`) + `ConflictQueue(root)` mirroring `alpha/meta/store.py::SessionStore`: `.add(op, provenance=None, contested=None) -> HeldConflict` (assigns id + timestamp, persists), `.all() -> list[HeldConflict]` (newest-first), `.get(conflict_id)`, `.resolve(conflict_id)` (delete; the §5-followup adjudication records intent). Consumed by Task 6 / the autonomous Refiner path.

- [ ] **Step 1: Write the failing test**

```python
# tests/meta/test_conflict_store.py
import pytest
from alpha.meta.conflict_store import ConflictQueue, HeldConflict

def test_add_get_all_resolve_round_trip(tmp_path):
    q = ConflictQueue(tmp_path)
    h = q.add(op={"tool": "demote_memory"}, provenance={"path": "self_study"}, contested={"target_id": "m1"})
    assert isinstance(h, HeldConflict) and h.conflict_id and h.created_at
    assert q.get(h.conflict_id) == h
    assert [c.conflict_id for c in q.all()] == [h.conflict_id]
    q.resolve(h.conflict_id)
    assert q.get(h.conflict_id) is None and q.all() == []

def test_path_traversal_guard(tmp_path):
    with pytest.raises(ValueError):
        ConflictQueue(tmp_path)._path("../escape")
```

- [ ] **Step 2: Run to verify it fails**

Run: `python -m pytest tests/meta/test_conflict_store.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'alpha.meta.conflict_store'`.

- [ ] **Step 3: Implement** — mirror `alpha/meta/store.py::SessionStore` (read it first for the exact `_atomic_write` + `_path` traversal-guard idiom). `conflict_id` from a uuid-ish helper, `created_at` UTC isoformat (reuse `alpha/meta/models.py` helpers if present, else inline). Persist one `HeldConflict` JSON per id; `all()` newest-first, tolerant of garbage files; `resolve` = unlink (missing_ok). Keep the `_path` `.resolve()` + `is_relative_to` guard verbatim (ids may come from a URL param later).

> **Implementer note:** read `alpha/meta/store.py` and `alpha/meta/models.py` and copy the store idiom + id/timestamp helpers faithfully (inline `_atomic_write` to avoid importing private names). Do NOT invent a new persistence pattern.

- [ ] **Step 4: Run to verify it passes**

Run: `python -m pytest tests/meta/test_conflict_store.py -v`
Expected: 2 PASS.

- [ ] **Step 5: Commit**

```bash
git add alpha/meta/conflict_store.py tests/meta/test_conflict_store.py
git commit -m "feat(self-evo): ConflictQueue store (held conflicts, mirrors SessionStore)"
```

---

### Task 6: Thread `provenance` from the three proposers

**Files:**
- Modify: `alpha/refine/refiner.py` (self-study), `alpha/meta/agent.py` (teaching — Sonia preview/apply), `alpha/converse/tools.py` (teaching — the B-WIDE write tool)
- Test: `tests/refine/test_proposer_provenance.py`

**Interfaces:**
- Produces: each proposer now passes a `provenance` to `try_apply_op` (Refiner → `path="self_study", proposer="refiner"`; Sonia → `path="teaching", proposer="sonia"`; converse write tool → `path="teaching", proposer="hermes"`). The autonomous Refiner also passes a `conflict_queue` when one is configured (so its held conflicts aren't silently dropped) — wire it as an optional `Refiner(..., conflict_queue=None)` attribute threaded into its `try_apply_op` call.

- [ ] **Step 1: Read the three proposers' `try_apply_op` call sites**

Read `alpha/refine/refiner.py` (find its `try_apply_op` call — likely in an `_apply_op`/refine loop), `alpha/meta/agent.py` (`preview_op` uses a scratch harness; `MetaAgent.apply` applies accepted edits), and `alpha/converse/tools.py::make_gated_write_tool` (its `try_apply_op` call). Note the exact call signature at each.

- [ ] **Step 2: Write the failing test**

```python
# tests/refine/test_proposer_provenance.py
# For each proposer, drive its gated apply and assert the resulting EditRecord carries the right provenance
# path/proposer. Use the existing test fixtures for each (mirror tests/meta/test_apply.py for Sonia/MetaAgent,
# tests/converse/test_tools.py for the converse write tool). At minimum assert:
#   - a Refiner-applied edit -> log record provenance.path == "self_study", proposer == "refiner"
#   - a converse propose_memory_edit applied edit -> provenance.path == "teaching", proposer == "hermes"
# (Build the harness + a valid op exactly as those existing tests do; after apply, read the EditLog's last
#  record's provenance.)
```

> **Implementer note:** this test is necessarily proposer-specific — model each assertion on the nearest existing test for that proposer (`tests/meta/test_apply.py`, `tests/converse/test_tools.py`, and the Refiner's test). Assert on `log.records()[-1].provenance.path`/`.proposer` after a successful gated apply.

- [ ] **Step 3: Run to verify it fails**

Run: `python -m pytest tests/refine/test_proposer_provenance.py -v`
Expected: FAIL — the proposers don't pass provenance yet, so `provenance` is `None`.

- [ ] **Step 4: Implement** — at each proposer's `try_apply_op(...)` call, add `provenance=EditProvenance(path=…, proposer=…)`:
- `refiner.py`: `provenance=EditProvenance(path="self_study", proposer="refiner", parent_checkpoint_version=<HarnessManager.latest_version() if reachable else None>)`, plus thread an optional `conflict_queue` (a `Refiner(..., conflict_queue=None)` ctor attr passed to the call).
- `meta/agent.py` (`MetaAgent.apply` / wherever the accepted Sonia edit is applied through the gate): `provenance=EditProvenance(path="teaching", proposer="sonia")`.
- `converse/tools.py` (`make_gated_write_tool` → `propose_memory_edit`): `provenance=EditProvenance(path="teaching", proposer="hermes")`.
Keep each call's 2-tuple unpack unchanged.

- [ ] **Step 5: Run to verify it passes + full suite green**

Run: `python -m pytest tests/refine/test_proposer_provenance.py -v && python -m pytest -q`
Expected: PASS; full suite green (provenance is additive; the held path stays dormant unless a `conflict_queue` is configured).

- [ ] **Step 6: Commit**

```bash
git add alpha/refine/refiner.py alpha/meta/agent.py alpha/converse/tools.py tests/refine/test_proposer_provenance.py
git commit -m "feat(self-evo): thread provenance from Refiner/Sonia/converse proposers"
```

---

## Self-Review

**Spec coverage (§5.3, §5.4):**
- `EditProvenance` block on `EditRecord`, stamped at the gate → Tasks 1 + 2. ✓
- Two learning paths tagged (self_study/teaching; refiner/sonia/hermes) → Tasks 1 + 6. ✓
- Conflict = self-study contesting teaching-owned existing element (asymmetry; create verbs excluded) → Task 3. ✓
- `held_for_review` = enqueue + not-applied (2-tuple preserved) → Task 4 + 5. ✓
- Autonomous Refiner's held conflicts not silently dropped (optional `conflict_queue`) → Task 6. ✓
- Deferred (noted): Sonia `/conflicts` UI, LLM framing, auto-re-apply. ✓

**Placeholder scan:** Tasks 5 + 6's tests are described against the nearest existing fixtures (with the implementer note naming the exact files) rather than fully inlined — they are proposer/store-specific and must mirror real fixtures; this is a deliberate "match the real model" instruction, not a placeholder. Every production code step shows exact code.

**Type consistency:** `EditProvenance` (Task 1) is consumed by `try_apply_op(provenance=…)` (Task 2), `is_conflict(…, provenance)` (Task 3), the held enqueue (Task 4), and the proposers (Task 6). `EditLog.stamp_last`/`latest_for` (Task 1) are used in Tasks 2/4/3. `try_apply_op` keeps its `tuple[EditRecord | None, str | None]` return throughout. `conflict_queue` only needs `.add(op=…, provenance=…, contested=…)` — satisfied by `ConflictQueue.add` (Task 5) and the test's `_FakeQueue`. `_KIND`/`_CONTEST_VERBS` (Task 3) and `_target_id`/`_target_kind` (apply.py) are the single source for tool→kind/id.
