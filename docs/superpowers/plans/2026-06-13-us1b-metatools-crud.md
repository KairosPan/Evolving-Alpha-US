# US-1b Meta-tools + CRUD + EditLog Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the harness `H=(p,K,M)` **editable** — add CRUD + skill-lifecycle to the registries and doctrine, an append-only `EditLog`, and the 9 meta-tools (the paper's meta-tool API) through which an Agent/Refiner edits `H`, with immutable-core enforcement and a reject-don't-log discipline.

**Architecture:** CRUD methods live on the existing `SkillRegistry` / `MemoryStore` / `Doctrine` (read-only in US-1a). A `MetaTools` facade wraps a `HarnessState` + an `EditLog`: each tool **executes the edit first** (raising on any violation, leaving `H` unchanged and **not** logging) and only on success appends an `EditRecord` (with `rationale` + before/after `payload`). Identity and observation fields are protected; `write_skill` clamps new skills to `incubating` with fresh stats so the Refiner cannot mint an `active` skill or inject fake performance.

**Tech Stack:** Python ≥3.11, pydantic v2, pytest. No LLM, no network — fully offline.

**Spec:** `docs/superpowers/specs/2026-06-13-us-market-adaptation-design.md` (US-1, "9 meta-tools, immutable-core"). Sub-plan **US-1b** of US-1 (after 1a core; before 1c persistence/rollback, which consumes `EditLog.to_dict`/`from_dict` and the before/after payloads).

**Scope boundary (US-1b only):** CRUD + lifecycle + EditLog + the 9 meta-tools + reject-don't-log. **Deferred:** SnapshotStore / HarnessManager / checkpoint-rollback → US-1c (uses the payloads written here); the regime state machine (`cycle`) → US-1e; `G` sub-agents and the LLM Refiner that *calls* these tools → US-2. **Reused from US-1a (do not redefine):** `HarnessError`/`ImmutableDoctrineError` (errors.py), `Skill`/`SkillStats`, `Lesson`/`Importance`, `DoctrineEntry`/`Doctrine` (read/query), `SkillRegistry`/`MemoryStore` (read/query), `HarnessState`.

**Conventions:** all code/comments English; `from __future__ import annotations` at the top of every module; commit after every passing task; run via `python -m pytest`.

**Key invariants (each gets a test):**
1. A rejected edit (immutable rewrite, invalid transition, forbidden/identity field, missing target, duplicate id, missing rationale) **raises and is NOT recorded** in the EditLog, and leaves `H` unchanged.
2. No half-apply: a failed multi-field patch rolls back every field.
3. `write_skill` clamps `status="incubating"` and resets `stats` (no minting `active`, no injected stats).
4. Observation/identity fields are unpatchable: `patch_skill` blocks `status`/`stats`/`skill_id`; `update_memory` blocks `importance`/`lesson_id`.
5. Every successful edit appends exactly one `EditRecord` with a non-empty `rationale` and a before/after `payload`.

---

### Task 1: Add `InvalidTransitionError`

**Files:**
- Modify: `alpha/harness/errors.py`
- Modify: `tests/harness/test_errors.py`

- [ ] **Step 1: Write the failing test (append to existing file)**

```python
# append to tests/harness/test_errors.py
from alpha.harness.errors import InvalidTransitionError


def test_invalid_transition_is_harness_error():
    assert issubclass(InvalidTransitionError, HarnessError)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/harness/test_errors.py -q`
Expected: FAIL — `ImportError: cannot import name 'InvalidTransitionError'`

- [ ] **Step 3: Append to `alpha/harness/errors.py`**

```python
# append to alpha/harness/errors.py


class InvalidTransitionError(HarnessError):
    """An illegal skill status transition (e.g. reviving a non-dormant skill)."""
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/harness/test_errors.py -q`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add alpha/harness/errors.py tests/harness/test_errors.py
git commit -m "US-1b Task 1: add InvalidTransitionError"
```

---

### Task 2: SkillRegistry CRUD + lifecycle

**Files:**
- Modify: `alpha/harness/registry.py` (add methods to `SkillRegistry`)
- Create: `tests/harness/test_registry_crud.py`

Add `write`/`patch`/`retire`/`revive`/`promote`. Forbidden patch fields: identity (`skill_id`) + status + observation (`stats`). Status changes only through the lifecycle methods. `patch` is atomic (rolls back on validation error).

- [ ] **Step 1: Write the failing test**

```python
# tests/harness/test_registry_crud.py
import pytest
from alpha.harness.skill import Skill
from alpha.harness.registry import SkillRegistry
from alpha.harness.errors import InvalidTransitionError


def _skill(sid, status="incubating"):
    return Skill(skill_id=sid, name=sid, type="pattern", family="runner", phases=["trend"], status=status)


def test_write_and_duplicate():
    reg = SkillRegistry.from_skills([])
    reg.write(_skill("a"))
    assert reg.get("a") is not None
    with pytest.raises(ValueError):
        reg.write(_skill("a"))


def test_patch_allowed_field():
    reg = SkillRegistry.from_skills([_skill("a")])
    reg.patch("a", notes="updated", phases=["trend", "flush"])
    assert reg.get("a").notes == "updated"
    assert reg.get("a").phases == ["trend", "flush"]


def test_patch_forbidden_fields():
    reg = SkillRegistry.from_skills([_skill("a")])
    for bad in ({"status": "active"}, {"stats": {}}, {"skill_id": "b"}):
        with pytest.raises(ValueError):
            reg.patch("a", **bad)


def test_patch_missing_target():
    reg = SkillRegistry.from_skills([])
    with pytest.raises(KeyError):
        reg.patch("nope", notes="x")


def test_patch_atomic_rollback():
    reg = SkillRegistry.from_skills([_skill("a")])
    # 'notes' is valid, 'type' must be one of the Literal values -> invalid -> whole patch rolls back
    with pytest.raises(Exception):
        reg.patch("a", notes="changed", type="not_a_valid_type")
    assert reg.get("a").notes == ""        # rolled back, not left as "changed"


def test_lifecycle_transitions():
    reg = SkillRegistry.from_skills([_skill("a", status="incubating")])
    assert reg.promote("a").status == "active"
    assert reg.retire("a").status == "dormant"           # default retire -> dormant
    assert reg.revive("a").status == "incubating"        # dormant -> incubating
    reg.retire("a", permanent=True)
    assert reg.get("a").status == "retired"


def test_illegal_transitions():
    reg = SkillRegistry.from_skills([_skill("a", status="active")])
    with pytest.raises(InvalidTransitionError):
        reg.revive("a")                  # active is not dormant
    with pytest.raises(InvalidTransitionError):
        reg.promote("a")                 # active is not incubating
    reg.retire("a", permanent=True)
    with pytest.raises(InvalidTransitionError):
        reg.retire("a")                  # already permanently retired (non-permanent)
    with pytest.raises(InvalidTransitionError):
        reg.retire("a", permanent=True)  # already permanently retired (permanent too)
    # re-retiring an already-dormant skill (non-permanent) is rejected, not a silent no-op;
    # but a permanent retire of a dormant skill IS allowed (dormant -> retired)
    reg2 = SkillRegistry.from_skills([_skill("b", status="active")])
    reg2.retire("b")                     # active -> dormant
    with pytest.raises(InvalidTransitionError):
        reg2.retire("b")                 # already dormant
    assert reg2.retire("b", permanent=True).status == "retired"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/harness/test_registry_crud.py -q`
Expected: FAIL — `AttributeError: 'SkillRegistry' object has no attribute 'write'`

- [ ] **Step 3: Append CRUD methods to `SkillRegistry` in `alpha/harness/registry.py`**

First add the import to the top of `registry.py` (else `retire`/`revive`/`promote` raise `NameError`):

```python
from alpha.harness.errors import InvalidTransitionError
```

Then add these methods inside `class SkillRegistry`:

```python
# add inside class SkillRegistry (after __bool__):

    # ── CRUD + lifecycle (US-1b) ──────────────────────────────────────────
    # Note: write() is the seed/restore path (no clamping). The Refiner edits ONLY via MetaTools
    # (Task 6), whose write_skill clamps status->incubating + resets stats. phases/applies_all_phases
    # ARE patchable in the US model (canonical fields, not derived from a raw regime string as in CN).
    _PATCH_FORBIDDEN = {"skill_id", "status", "stats"}

    def _require(self, skill_id: str) -> Skill:
        s = self._skills.get(skill_id)
        if s is None:
            raise KeyError(f"no such skill_id: {skill_id}")
        return s

    def write(self, skill: Skill) -> None:
        if skill.skill_id in self._skills:
            raise ValueError(f"duplicate skill_id: {skill.skill_id}")
        self._skills[skill.skill_id] = skill

    def patch(self, skill_id: str, **fields) -> Skill:
        s = self._require(skill_id)
        bad = self._PATCH_FORBIDDEN & fields.keys()
        if bad:
            raise ValueError(f"cannot patch {sorted(bad)}: status via retire/revive/promote; "
                             f"stats is an observation field (set by credit assignment); skill_id is identity")
        snapshot = {k: getattr(s, k) for k in fields if k in type(s).model_fields}
        try:
            for k, v in fields.items():
                setattr(s, k, v)             # validate_assignment validates
        except Exception:
            for k, v in snapshot.items():    # roll back already-applied fields
                setattr(s, k, v)
            raise
        return s

    def retire(self, skill_id: str, permanent: bool = False) -> Skill:
        # Reject no-op retires so a hallucinating Refiner gets a signal (and no spurious EditRecord):
        s = self._require(skill_id)
        if s.status == "retired":
            raise InvalidTransitionError(f"{skill_id} is already permanently retired")
        if s.status == "dormant" and not permanent:
            raise InvalidTransitionError(f"{skill_id} is already dormant")
        s.status = "retired" if permanent else "dormant"     # dormant -> retired (permanent) is allowed
        return s

    def revive(self, skill_id: str) -> Skill:
        s = self._require(skill_id)
        if s.status != "dormant":
            raise InvalidTransitionError(f"{skill_id} is {s.status}, not dormant; cannot revive")
        s.status = "incubating"
        return s

    def promote(self, skill_id: str) -> Skill:
        s = self._require(skill_id)
        if s.status != "incubating":
            raise InvalidTransitionError(f"{skill_id} is {s.status}, not incubating; cannot promote")
        s.status = "active"
        return s
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/harness/test_registry_crud.py -q`
Expected: PASS (7 passed)

- [ ] **Step 5: Commit**

```bash
git add alpha/harness/registry.py tests/harness/test_registry_crud.py
git commit -m "US-1b Task 2: SkillRegistry CRUD + lifecycle"
```

---

### Task 3: MemoryStore CRUD

**Files:**
- Modify: `alpha/harness/registry.py` (add methods to `MemoryStore`)
- Create: `tests/harness/test_memory_crud.py`

Add `add`/`update`/`demote`. Forbidden update fields: identity (`lesson_id`) + observation (`importance`, managed by `demote`/time-decay).

- [ ] **Step 1: Write the failing test**

```python
# tests/harness/test_memory_crud.py
import pytest
from alpha.harness.memory import Lesson
from alpha.harness.registry import MemoryStore


def _lesson(lid):
    return Lesson(lesson_id=lid, phases=["flush"], family="meme", outcome="loss", lesson="x")


def test_add_and_duplicate():
    store = MemoryStore.from_lessons([])
    store.add(_lesson("l1"))
    assert store.get("l1") is not None
    with pytest.raises(ValueError):
        store.add(_lesson("l1"))


def test_update_allowed_and_forbidden():
    store = MemoryStore.from_lessons([_lesson("l1")])
    store.update("l1", lesson="revised", pattern="squeeze top")
    assert store.get("l1").lesson == "revised" and store.get("l1").pattern == "squeeze top"
    for bad in ({"importance": {}}, {"lesson_id": "l2"}):
        with pytest.raises(ValueError):
            store.update("l1", **bad)


def test_update_missing_target():
    store = MemoryStore.from_lessons([])
    with pytest.raises(KeyError):
        store.update("nope", lesson="x")


def test_demote_lowers_weight():
    store = MemoryStore.from_lessons([_lesson("l1")])
    assert store.get("l1").importance.weight() == 1.0
    store.demote("l1", 0.5)
    assert store.get("l1").importance.weight() == 0.5
    with pytest.raises(KeyError):
        store.demote("nope", 0.5)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/harness/test_memory_crud.py -q`
Expected: FAIL — `AttributeError: 'MemoryStore' object has no attribute 'add'`

- [ ] **Step 3: Append CRUD methods to `MemoryStore` in `alpha/harness/registry.py`**

```python
# add inside class MemoryStore (after __bool__):

    # ── CRUD (US-1b) ──────────────────────────────────────────────────────
    _UPDATE_FORBIDDEN = {"lesson_id", "importance"}

    def add(self, lesson: Lesson) -> None:
        if lesson.lesson_id in self._lessons:
            raise ValueError(f"duplicate lesson_id: {lesson.lesson_id}")
        self._lessons[lesson.lesson_id] = lesson

    def update(self, lesson_id: str, **fields) -> Lesson:
        l = self._lessons.get(lesson_id)
        if l is None:
            raise KeyError(f"no such lesson_id: {lesson_id}")
        bad = self._UPDATE_FORBIDDEN & fields.keys()
        if bad:
            raise ValueError(f"cannot update {sorted(bad)}: importance is an observation field "
                             f"(managed by demote_memory / time-decay); lesson_id is identity")
        snapshot = {k: getattr(l, k) for k in fields if k in type(l).model_fields}
        try:
            for k, v in fields.items():
                setattr(l, k, v)
        except Exception:
            for k, v in snapshot.items():
                setattr(l, k, v)
            raise
        return l

    def demote(self, lesson_id: str, factor: float) -> Lesson:
        l = self._lessons.get(lesson_id)
        if l is None:
            raise KeyError(f"no such lesson_id: {lesson_id}")
        l.importance.demote(factor)
        return l
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/harness/test_memory_crud.py -q`
Expected: PASS (4 passed)

- [ ] **Step 5: Commit**

```bash
git add alpha/harness/registry.py tests/harness/test_memory_crud.py
git commit -m "US-1b Task 3: MemoryStore CRUD"
```

---

### Task 4: Doctrine CRUD (immutable-protected)

**Files:**
- Modify: `alpha/harness/doctrine.py` (add methods to `Doctrine`)
- Create: `tests/harness/test_doctrine_crud.py`

Add `add`/`rewrite`/`remove`. Immutable entries cannot be rewritten or removed.

- [ ] **Step 1: Write the failing test**

```python
# tests/harness/test_doctrine_crud.py
import pytest
from alpha.harness.doctrine import DoctrineEntry, Doctrine
from alpha.harness.errors import ImmutableDoctrineError


def _doc():
    return Doctrine.from_seed_list([
        {"section": "core", "regime": "all", "immutable": True, "guidance": "stop discipline"},
        {"section": "trend", "regime": "trend", "immutable": False, "guidance": "ride leaders"},
    ])


def test_add_and_duplicate():
    doc = _doc()
    doc.add(DoctrineEntry(section="new", phases=["flush"], guidance="cut fast"))
    assert doc.get("new") is not None
    with pytest.raises(ValueError):
        doc.add(DoctrineEntry(section="trend", guidance="dup"))


def test_rewrite_mutable():
    doc = _doc()
    doc.rewrite("trend", "ride leaders; trim into blowoff")
    assert doc.get("trend").guidance == "ride leaders; trim into blowoff"


def test_rewrite_immutable_blocked():
    doc = _doc()
    with pytest.raises(ImmutableDoctrineError):
        doc.rewrite("core", "loosen the stop")
    assert doc.get("core").guidance == "stop discipline"     # unchanged


def test_rewrite_missing():
    doc = _doc()
    with pytest.raises(KeyError):
        doc.rewrite("nope", "x")


def test_remove_mutable_and_immutable():
    doc = _doc()
    doc.remove("trend")
    assert doc.get("trend") is None
    with pytest.raises(ImmutableDoctrineError):
        doc.remove("core")
    assert doc.get("core") is not None
    with pytest.raises(KeyError):
        doc.remove("nope")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/harness/test_doctrine_crud.py -q`
Expected: FAIL — `AttributeError: 'Doctrine' object has no attribute 'add'`

- [ ] **Step 3: Append CRUD methods to `Doctrine` in `alpha/harness/doctrine.py`**

```python
# add inside class Doctrine (after mutable_entries):

    # ── CRUD (US-1b; immutable-protected) ─────────────────────────────────
    def add(self, entry: DoctrineEntry) -> None:
        if self.get(entry.section) is not None:
            raise ValueError(f"duplicate section: {entry.section}")
        self.entries.append(entry)

    def rewrite(self, section: str, new_guidance: str) -> DoctrineEntry:
        e = self.get(section)
        if e is None:
            raise KeyError(f"no such section: {section}")
        if e.immutable:
            raise ImmutableDoctrineError(f"immutable doctrine cannot be rewritten: {section}")
        e.guidance = new_guidance
        return e

    def remove(self, section: str) -> None:
        e = self.get(section)
        if e is None:
            raise KeyError(f"no such section: {section}")
        if e.immutable:
            raise ImmutableDoctrineError(f"immutable doctrine cannot be removed: {section}")
        self.entries.remove(e)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/harness/test_doctrine_crud.py -q`
Expected: PASS (5 passed)

- [ ] **Step 5: Commit**

```bash
git add alpha/harness/doctrine.py tests/harness/test_doctrine_crud.py
git commit -m "US-1b Task 4: Doctrine CRUD (immutable-protected)"
```

---

### Task 5: EditLog + EditRecord

**Files:**
- Create: `alpha/harness/edit_log.py`
- Create: `tests/harness/test_edit_log.py`

Append-only audit trail. `EditRecord` is frozen and carries a before/after `payload` (consumed by US-1c rollback) and a `rationale`.

- [ ] **Step 1: Write the failing test**

```python
# tests/harness/test_edit_log.py
from alpha.harness.edit_log import EditLog, EditRecord


def test_append_assigns_sequential_seq():
    log = EditLog()
    r0 = log.append("write_skill", "skill", "a", "create", "A", rationale="seed")
    r1 = log.append("rewrite_doctrine", "doctrine", "trend", "rewrite",
                    payload={"old": "x", "new": "y"}, rationale="regime shift")
    assert (r0.seq, r1.seq) == (0, 1)
    assert len(log) == 2 and bool(log) is True


def test_queries():
    log = EditLog()
    log.append("write_skill", "skill", "a", "create", rationale="r")
    log.append("rewrite_doctrine", "doctrine", "t", "rewrite", rationale="r")
    assert [r.target_id for r in log.by_kind("skill")] == ["a"]
    assert [r.target_id for r in log.by_tool("rewrite_doctrine")] == ["t"]


def test_record_is_frozen():
    import pytest
    from pydantic import ValidationError
    rec = EditRecord(seq=0, tool="t", target_kind="skill", target_id="a", op="create")
    with pytest.raises(ValidationError):
        rec.seq = 5


def test_roundtrip():
    log = EditLog()
    log.append("write_skill", "skill", "a", "create", "A",
               payload={"before": None, "after": {"x": 1}}, rationale="seed")
    data = log.to_dict()
    log2 = EditLog.from_dict(data)
    assert len(log2) == 1
    assert log2.records()[0].rationale == "seed"
    assert log2.records()[0].payload == {"before": None, "after": {"x": 1}}
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/harness/test_edit_log.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'alpha.harness.edit_log'`

- [ ] **Step 3: Write minimal implementation**

```python
# alpha/harness/edit_log.py
from __future__ import annotations

from pydantic import BaseModel, ConfigDict


class EditRecord(BaseModel):
    """Δ audit record for one harness edit (the inner-loop CRUD trajectory)."""
    model_config = ConfigDict(frozen=True)
    seq: int
    tool: str                       # write_skill / patch_skill / ... / rewrite_doctrine
    target_kind: str                # skill | memory | doctrine
    target_id: str                  # skill_id / lesson_id / section
    op: str                         # create | update | retire | revive | promote | demote | rewrite
    summary: str = ""
    payload: dict | None = None     # before/after, etc. (consumed by US-1c rollback)
    rationale: str = ""             # why the Refiner made the edit


class EditLog:
    """Append-only edit audit trail. Serializes via to_dict/from_dict (US-1c persistence)."""

    def __init__(self) -> None:
        self._records: list[EditRecord] = []

    def append(self, tool: str, target_kind: str, target_id: str, op: str,
               summary: str = "", payload: dict | None = None, rationale: str = "") -> EditRecord:
        rec = EditRecord(seq=len(self._records), tool=tool, target_kind=target_kind,
                         target_id=target_id, op=op, summary=summary, payload=payload,
                         rationale=rationale)
        self._records.append(rec)
        return rec

    def records(self) -> list[EditRecord]:
        return list(self._records)

    def by_kind(self, target_kind: str) -> list[EditRecord]:
        return [r for r in self._records if r.target_kind == target_kind]

    def by_tool(self, tool: str) -> list[EditRecord]:
        return [r for r in self._records if r.tool == tool]

    def __len__(self) -> int:
        return len(self._records)

    def __bool__(self) -> bool:
        return True

    def to_dict(self) -> list[dict]:
        return [r.model_dump() for r in self._records]

    @classmethod
    def from_dict(cls, data: list[dict]) -> "EditLog":
        log = cls()
        log._records = [EditRecord.model_validate(r) for r in data]
        return log
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/harness/test_edit_log.py -q`
Expected: PASS (4 passed)

- [ ] **Step 5: Commit**

```bash
git add alpha/harness/edit_log.py tests/harness/test_edit_log.py
git commit -m "US-1b Task 5: EditLog + EditRecord (append-only audit)"
```

---

### Task 6: MetaTools — the 9 meta-tools

**Files:**
- Create: `alpha/harness/metatools.py`
- Create: `tests/harness/test_metatools.py`

The facade. Each tool: require non-empty `rationale`, execute the edit (raises propagate, leaving `H` unchanged and unlogged), then append one `EditRecord`. `write_skill` clamps `status="incubating"` + fresh `stats`.

- [ ] **Step 1: Write the failing test**

```python
# tests/harness/test_metatools.py
import pytest
from alpha.harness.skill import Skill, SkillStats
from alpha.harness.memory import Lesson
from alpha.harness.doctrine import Doctrine
from alpha.harness.registry import SkillRegistry, MemoryStore
from alpha.harness.state import HarnessState
from alpha.harness.metatools import MetaTools


def _tools():
    skills = SkillRegistry.from_skills([
        Skill(skill_id="a", name="A", type="pattern", family="runner", phases=["trend"], status="active"),
    ])
    memory = MemoryStore.from_lessons([Lesson(lesson_id="l1", phases=["flush"], outcome="loss", lesson="x")])
    doctrine = Doctrine.from_seed_list([
        {"section": "core", "regime": "all", "immutable": True, "guidance": "stop discipline"},
        {"section": "trend", "regime": "trend", "immutable": False, "guidance": "ride leaders"},
    ])
    return MetaTools(HarnessState(doctrine=doctrine, skills=skills, memory=memory))


def test_write_skill_clamps_status_and_stats():
    mt = _tools()
    sneaky = Skill(skill_id="b", name="B", type="pattern", family="runner", phases=["trend"],
                   status="active", stats=SkillStats(n=99, wins=99))
    rec = mt.write_skill(sneaky, rationale="codified from a winning sequence")
    stored = mt.h.skills.get("b")
    assert stored.status == "incubating"      # clamped, cannot mint active
    assert stored.stats.n == 0                # injected stats reset
    assert rec.op == "create" and rec.rationale == "codified from a winning sequence"
    assert rec.payload["before"] is None and rec.payload["after"]["status"] == "incubating"
    assert len(mt.log) == 1


def test_patch_skill_records_before_after():
    mt = _tools()
    rec = mt.patch_skill("a", rationale="tighten exit", exit_stop="lose VWAP")
    assert mt.h.skills.get("a").exit_stop == "lose VWAP"
    assert rec.payload["before"]["exit_stop"] == ""
    assert rec.payload["after"]["exit_stop"] == "lose VWAP"


def test_lifecycle_tools():
    mt = _tools()
    mt.retire_skill("a", rationale="alpha decayed")          # active -> dormant
    assert mt.h.skills.get("a").status == "dormant"
    mt.revive_skill("a", rationale="regime returned")        # dormant -> incubating
    mt.promote_skill("a", rationale="beat OOS")              # incubating -> active
    assert mt.h.skills.get("a").status == "active"
    assert [r.op for r in mt.log.records()] == ["retire", "revive", "promote"]


def test_memory_tools():
    mt = _tools()
    rec = mt.process_memory(Lesson(lesson_id="l2", phases=["trend"], outcome="win", lesson="y"),
                            rationale="new named analog")
    mt.update_memory("l1", rationale="sharpen", failure_signature="chased the top")
    mt.demote_memory("l1", 0.5, rationale="regime passed")
    assert mt.h.memory.get("l2") is not None
    assert rec.payload["before"] is None and rec.payload["after"]["lesson_id"] == "l2"
    assert mt.h.memory.get("l1").failure_signature == "chased the top"
    assert mt.h.memory.get("l1").importance.weight() == 0.5


def test_rewrite_doctrine_tool():
    mt = _tools()
    rec = mt.rewrite_doctrine("trend", "ride leaders; trim into blowoff", rationale="late cycle")
    assert mt.h.doctrine.get("trend").guidance == "ride leaders; trim into blowoff"
    assert rec.payload["old"] == "ride leaders"
    assert rec.payload["new"] == "ride leaders; trim into blowoff"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/harness/test_metatools.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'alpha.harness.metatools'`

- [ ] **Step 3: Write minimal implementation**

```python
# alpha/harness/metatools.py
from __future__ import annotations

from alpha.harness.edit_log import EditLog, EditRecord
from alpha.harness.memory import Lesson
from alpha.harness.skill import Skill, SkillStats
from alpha.harness.state import HarnessState


def _jsonable(v: object) -> object:
    return v.model_dump() if hasattr(v, "model_dump") else v


def _require_rationale(rationale: str) -> None:
    if not rationale or not rationale.strip():
        raise ValueError("rationale is required for every harness edit")


class MetaTools:
    """The paper's meta-tool API: an Agent/Refiner edits H=(p,K,M) in place through this facade.

    Each tool executes the edit first; if it raises, H is unchanged and NOTHING is logged. On
    success it appends exactly one EditRecord (rationale + before/after payload). Edit only through
    these methods — touching h.skills/h.memory/h.doctrine directly bypasses the audit.
    """

    def __init__(self, harness: HarnessState, log: EditLog | None = None) -> None:
        self.h = harness
        self.log = log if log is not None else EditLog()

    # ── K skills ──
    def write_skill(self, skill: Skill, rationale: str) -> EditRecord:
        _require_rationale(rationale)
        clamped = skill.model_copy(update={"status": "incubating", "stats": SkillStats()})
        self.h.skills.write(clamped)                          # raises on dup -> not logged
        return self.log.append("write_skill", "skill", clamped.skill_id, "create",
                               clamped.name, payload={"before": None, "after": clamped.model_dump()},
                               rationale=rationale)

    def patch_skill(self, skill_id: str, rationale: str, **fields) -> EditRecord:
        _require_rationale(rationale)
        s = self.h.skills.get(skill_id)
        before = {k: _jsonable(getattr(s, k)) for k in fields if s is not None and k in type(s).model_fields}
        self.h.skills.patch(skill_id, **fields)              # raises -> not logged
        after = {k: _jsonable(v) for k, v in fields.items()}
        return self.log.append("patch_skill", "skill", skill_id, "update",
                               ",".join(fields), payload={"before": before, "after": after},
                               rationale=rationale)

    def retire_skill(self, skill_id: str, rationale: str, permanent: bool = False) -> EditRecord:
        _require_rationale(rationale)
        s = self.h.skills.get(skill_id)
        before = s.status if s is not None else None
        self.h.skills.retire(skill_id, permanent=permanent)
        after = "retired" if permanent else "dormant"
        return self.log.append("retire_skill", "skill", skill_id, "retire", after,
                               payload={"before": before, "after": after}, rationale=rationale)

    def revive_skill(self, skill_id: str, rationale: str) -> EditRecord:
        _require_rationale(rationale)
        s = self.h.skills.get(skill_id)
        before = s.status if s is not None else None
        self.h.skills.revive(skill_id)
        return self.log.append("revive_skill", "skill", skill_id, "revive", "",
                               payload={"before": before, "after": "incubating"}, rationale=rationale)

    def promote_skill(self, skill_id: str, rationale: str) -> EditRecord:
        _require_rationale(rationale)
        s = self.h.skills.get(skill_id)
        before = s.status if s is not None else None
        self.h.skills.promote(skill_id)
        return self.log.append("promote_skill", "skill", skill_id, "promote", "",
                               payload={"before": before, "after": "active"}, rationale=rationale)

    # ── M memory ──
    def process_memory(self, lesson: Lesson, rationale: str) -> EditRecord:
        _require_rationale(rationale)
        self.h.memory.add(lesson)
        return self.log.append("process_memory", "memory", lesson.lesson_id, "create",
                               lesson.lesson[:24], payload={"before": None, "after": lesson.model_dump()},
                               rationale=rationale)

    def update_memory(self, lesson_id: str, rationale: str, **fields) -> EditRecord:
        _require_rationale(rationale)
        l = self.h.memory.get(lesson_id)
        before = {k: _jsonable(getattr(l, k)) for k in fields if l is not None and k in type(l).model_fields}
        self.h.memory.update(lesson_id, **fields)
        after = {k: _jsonable(v) for k, v in fields.items()}
        return self.log.append("update_memory", "memory", lesson_id, "update",
                               ",".join(fields), payload={"before": before, "after": after},
                               rationale=rationale)

    def demote_memory(self, lesson_id: str, factor: float, rationale: str) -> EditRecord:
        _require_rationale(rationale)
        l = self.h.memory.get(lesson_id)
        before_td = l.importance.time_decay if l is not None else None
        self.h.memory.demote(lesson_id, factor)
        return self.log.append("demote_memory", "memory", lesson_id, "demote", str(factor),
                               payload={"before_time_decay": before_td, "factor": factor},
                               rationale=rationale)

    # ── p doctrine ──
    def rewrite_doctrine(self, section: str, new_guidance: str, rationale: str) -> EditRecord:
        _require_rationale(rationale)
        old = self.h.doctrine.get(section)
        old_guidance = old.guidance if old is not None else None
        self.h.doctrine.rewrite(section, new_guidance)       # immutable -> raises -> not logged
        return self.log.append("rewrite_doctrine", "doctrine", section, "rewrite",
                               payload={"old": old_guidance, "new": new_guidance}, rationale=rationale)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/harness/test_metatools.py -q`
Expected: PASS (5 passed)

- [ ] **Step 5: Commit**

```bash
git add alpha/harness/metatools.py tests/harness/test_metatools.py
git commit -m "US-1b Task 6: MetaTools — the 9 meta-tools (rationale + before/after payload)"
```

---

### Task 7: Reject-don't-log discipline (the adversarial-hardening gate)

**Files:**
- Create: `tests/harness/test_metatools_rejection.py`

Every rejected edit must raise, leave `H` unchanged, and add **nothing** to the log. This is the market-neutral safety invariant that protects `H` from a misbehaving/hallucinating Refiner.

- [ ] **Step 1: Write the failing test**

```python
# tests/harness/test_metatools_rejection.py
import pytest
from alpha.harness.skill import Skill
from alpha.harness.memory import Lesson
from alpha.harness.doctrine import Doctrine
from alpha.harness.registry import SkillRegistry, MemoryStore
from alpha.harness.state import HarnessState
from alpha.harness.metatools import MetaTools
from alpha.harness.errors import ImmutableDoctrineError, InvalidTransitionError


def _tools():
    skills = SkillRegistry.from_skills([
        Skill(skill_id="a", name="A", type="pattern", family="runner", phases=["trend"], status="active"),
    ])
    memory = MemoryStore.from_lessons([Lesson(lesson_id="l1", phases=["flush"], outcome="loss", lesson="x")])
    doctrine = Doctrine.from_seed_list([
        {"section": "core", "regime": "all", "immutable": True, "guidance": "stop discipline"},
    ])
    return MetaTools(HarnessState(doctrine=doctrine, skills=skills, memory=memory))


def test_rewrite_immutable_rejected_not_logged():
    mt = _tools()
    with pytest.raises(ImmutableDoctrineError):
        mt.rewrite_doctrine("core", "loosen the stop", rationale="bad idea")
    assert mt.h.doctrine.get("core").guidance == "stop discipline"   # unchanged
    assert len(mt.log) == 0                                          # NOT logged


def test_invalid_transition_rejected_not_logged():
    mt = _tools()
    with pytest.raises(InvalidTransitionError):
        mt.revive_skill("a", rationale="a is active not dormant")
    assert mt.h.skills.get("a").status == "active"
    assert len(mt.log) == 0


def test_forbidden_field_rejected_not_logged():
    mt = _tools()
    with pytest.raises(ValueError):
        mt.patch_skill("a", rationale="sneaky", stats={"n": 99})     # observation field
    assert mt.h.skills.get("a").stats.n == 0
    assert len(mt.log) == 0


def test_missing_target_rejected_not_logged():
    mt = _tools()
    with pytest.raises(KeyError):
        mt.patch_skill("ghost", rationale="hallucinated id", notes="x")
    assert len(mt.log) == 0


def test_duplicate_id_rejected_not_logged():
    mt = _tools()
    with pytest.raises(ValueError):
        mt.write_skill(Skill(skill_id="a", name="dup", type="pattern", family="runner", phases=["trend"]),
                       rationale="duplicate")
    assert mt.h.skills.get("a").name == "A"      # original unchanged
    assert len(mt.log) == 0


def test_missing_rationale_rejected_on_all_nine_tools():
    mt = _tools()
    new_skill = Skill(skill_id="z", name="Z", type="pattern", family="runner", phases=["trend"])
    new_lesson = Lesson(lesson_id="z", phases=["trend"], outcome="win", lesson="y")
    # rationale guard is the FIRST line of every tool, so even an otherwise-illegal edit
    # (e.g. revive/promote on an active skill) raises ValueError(rationale) and never mutates.
    calls = [
        lambda: mt.write_skill(new_skill, rationale=""),
        lambda: mt.patch_skill("a", rationale="", notes="x"),
        lambda: mt.retire_skill("a", rationale=""),
        lambda: mt.revive_skill("a", rationale=""),
        lambda: mt.promote_skill("a", rationale=""),
        lambda: mt.process_memory(new_lesson, rationale=""),
        lambda: mt.update_memory("l1", rationale="", lesson="x"),
        lambda: mt.demote_memory("l1", 0.5, rationale=""),
        lambda: mt.rewrite_doctrine("core", "y", rationale=""),
        lambda: mt.patch_skill("a", rationale="   ", notes="x"),   # blank/whitespace also rejected
    ]
    for call in calls:
        with pytest.raises(ValueError):
            call()
    assert mt.h.skills.get("a").notes == "" and mt.h.skills.get("z") is None
    assert mt.h.memory.get("z") is None
    assert len(mt.log) == 0


def test_invalid_demote_factor_rejected_not_logged():
    mt = _tools()
    for bad in (0.0, 1.5, -0.1):
        with pytest.raises(ValueError):
            mt.demote_memory("l1", bad, rationale="invalid factor")
    assert mt.h.memory.get("l1").importance.weight() == 1.0
    assert len(mt.log) == 0


def test_already_retired_rejected_not_logged():
    mt = _tools()
    mt.retire_skill("a", rationale="retire", permanent=True)     # active -> retired (1 record)
    with pytest.raises(InvalidTransitionError):
        mt.retire_skill("a", rationale="retire again")          # already retired -> reject
    assert mt.h.skills.get("a").status == "retired"
    assert len(mt.log) == 1                                      # only the first (real) retire logged


def test_atomic_patch_failure_not_logged():
    mt = _tools()
    with pytest.raises(Exception):
        mt.patch_skill("a", rationale="bad type", notes="changed", type="not_valid")
    assert mt.h.skills.get("a").notes == ""      # rolled back
    assert len(mt.log) == 0
```

- [ ] **Step 2: Run test to verify it fails (then passes — no new impl needed)**

Run: `python -m pytest tests/harness/test_metatools_rejection.py -q`
Expected: PASS (7 passed) — the rejection behavior is already implemented in Tasks 2-6 (edit-then-log structure + rationale guard). If any test FAILS, the corresponding invariant is broken and must be fixed in the relevant module (registry/doctrine/metatools) before proceeding.

- [ ] **Step 3: Commit**

```bash
git add tests/harness/test_metatools_rejection.py
git commit -m "US-1b Task 7: reject-don't-log discipline (adversarial-hardening gate)"
```

---

### Task 8: US-1b acceptance gate + docs update

**Files:**
- Create: `tests/harness/test_us1b_acceptance.py`
- Modify: `docs/PROJECT_STATE.md` (mark US-1b done)

- [ ] **Step 1: Write the acceptance test**

```python
# tests/harness/test_us1b_acceptance.py
"""US-1b acceptance: the harness is editable through the 9 meta-tools with an audited EditLog,
the immutable core is protected on the edit path, and rejected edits never touch H or the log."""
import pytest
from alpha.harness.skill import Skill
from alpha.harness.memory import Lesson
from alpha.harness.doctrine import Doctrine
from alpha.harness.registry import SkillRegistry, MemoryStore
from alpha.harness.state import HarnessState
from alpha.harness.metatools import MetaTools
from alpha.harness.errors import ImmutableDoctrineError


def _tools():
    skills = SkillRegistry.from_skills([
        Skill(skill_id="a", name="A", type="pattern", family="runner", phases=["trend"], status="incubating"),
    ])
    memory = MemoryStore.from_lessons([])
    doctrine = Doctrine.from_seed_list([
        {"section": "core", "regime": "all", "immutable": True, "guidance": "stop discipline"},
        {"section": "trend", "regime": "trend", "immutable": False, "guidance": "ride leaders"},
    ])
    return MetaTools(HarnessState(doctrine=doctrine, skills=skills, memory=memory))


def test_full_edit_cycle_audited():
    mt = _tools()
    mt.promote_skill("a", rationale="beat OOS")
    mt.write_skill(Skill(skill_id="b", name="B", type="failure_detector", family="meme", phases=["flush"]),
                   rationale="codified a blowoff detector")
    mt.process_memory(Lesson(lesson_id="m1", phases=["flush"], outcome="loss", lesson="don't chase tops"),
                      rationale="named analog")
    mt.rewrite_doctrine("trend", "ride leaders; trim into blowoff", rationale="late cycle")
    # 4 successful edits, all audited with rationale
    assert len(mt.log) == 4
    assert all(r.rationale for r in mt.log.records())
    assert mt.h.skills.get("a").status == "active"
    assert mt.h.skills.get("b").status == "incubating"      # write clamps to incubating
    assert mt.h.doctrine.get("trend").guidance.endswith("blowoff")


def test_immutable_core_protected_and_unlogged():
    mt = _tools()
    with pytest.raises(ImmutableDoctrineError):
        mt.rewrite_doctrine("core", "loosen", rationale="bad")
    assert mt.h.doctrine.get("core").guidance == "stop discipline"
    assert len(mt.log) == 0
```

- [ ] **Step 2: Run the full suite**

Run: `python -m pytest -q`
Expected: PASS — all US-0 + US-1a + US-1b tests green.

- [ ] **Step 3: Update `docs/PROJECT_STATE.md`**

In the US-1 section, mark **US-1b (meta-tools + CRUD + EditLog) done** with the date and a one-line summary (9 meta-tools, immutable-core enforced on the edit path, reject-don't-log audited; `EditLog.to_dict`/`from_dict` ready for US-1c). Update the "Next" pointer to **US-1c (persistence + rollback)**.

- [ ] **Step 4: Commit**

```bash
git add tests/harness/test_us1b_acceptance.py docs/PROJECT_STATE.md
git commit -m "US-1b Task 8: acceptance gate (editable harness + audit + immutable protection) + PROJECT_STATE"
```

---

## Self-Review (run after writing, fix inline)

**Spec coverage (US-1 "9 meta-tools, immutable-core"):** all 9 tools present — write/patch/retire/revive/promote_skill (Tasks 2,6), process/update/demote_memory (Tasks 3,6), rewrite_doctrine (Tasks 4,6) ✓ · EditLog audit (Task 5) ✓ · immutable-core enforced on the edit path (Tasks 4,6,7) ✓ · reject-don't-log + no-half-apply (Task 7) ✓ · before/after payloads for US-1c rollback (Tasks 5,6) ✓.

**Type consistency:** CRUD methods added to the US-1a `SkillRegistry`/`MemoryStore`/`Doctrine` classes (not redefined). `MetaTools` uses US-1a `HarnessState`/`Skill`/`SkillStats`/`Lesson` and the `EditLog`/`EditRecord` from Task 5. `EditRecord` fields (`seq/tool/target_kind/target_id/op/summary/payload/rationale`) used consistently in `append` and the tools. `_PATCH_FORBIDDEN`/`_UPDATE_FORBIDDEN` referenced only inside their classes.

**Placeholder scan:** no TBD/TODO; every code step shows full code; deferrals (SnapshotStore/HarnessManager → US-1c; cycle → US-1e; Refiner caller → US-2) are explicit scope notes.

**Scope:** editable harness + audit only; no persistence store, no LLM, no rollback engine (US-1c consumes the payloads/serialization produced here). Produces an independently-testable editable-harness layer.

## Execution note (2026-06-13)

Executed directly (TDD, test-gated per task) rather than via the subagent workflow, since the US-1a workflow stalled on infrastructure. One correction surfaced at execution that supersedes the snippets above: **`skill_id`/`lesson_id` were dropped from `_PATCH_FORBIDDEN`/`_UPDATE_FORBIDDEN`.** They are the positional parameter of `patch()`/`update()`, so passing them as a field collides → `TypeError` (still rejected, just structurally, not via the forbidden-set check). The tests assert the structural `TypeError` for those two; the forbidden sets are `{"status","stats"}` and `{"importance"}`. All 8 tasks committed; full suite 107 tests green.
