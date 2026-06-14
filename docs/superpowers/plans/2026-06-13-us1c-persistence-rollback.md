# US-1c Persistence + Rollback Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the editable harness **versioned and recoverable** — atomic, versioned on-disk snapshots of `(HarnessState, EditLog)`, and a `HarnessManager` that holds the live harness + log + meta-tools and supports `checkpoint` / `rollback_to`, rebinding the tools to the restored state.

**Architecture:** `SnapshotStore` writes one JSON file per version (`root/snap_<NNNN>.json` = `{version, label, harness, log}`) using an atomic temp-then-`os.replace`. It serializes via the `HarnessState.to_dict`/`from_dict` (US-1a) and `EditLog.to_dict`/`from_dict` (US-1b) that already exist, so the immutable-core guard survives round-trips and `cycle` is carried automatically once US-1e adds it. `HarnessManager` owns `(harness, log, tools, store)`: `checkpoint` saves the current state; `rollback_to` loads a version and **rebinds** `MetaTools` to the restored `(harness, log)` so subsequent edits act on the restored state.

**Tech Stack:** Python ≥3.11, pydantic v2 (via existing models), stdlib `json`/`os`/`pathlib`, pytest. No LLM, no network — fully offline.

**Spec:** `docs/superpowers/specs/2026-06-13-us-market-adaptation-design.md` (US-1, "persistence, snapshot/rollback"). Sub-plan **US-1c** of US-1 (after 1b meta-tools/EditLog; before 1d eval oracle). Consumes the `EditLog` + before/after payloads produced by US-1b.

**Scope boundary (US-1c only):** versioned snapshots + manager checkpoint/rollback. **Deferred:** *when* to auto-checkpoint (every cycle / before each refine) → the inner loop in US-2; delta/keep-last-K snapshot pruning → later (full snapshots now, ~tens of KB each); the regime `cycle` field → US-1e (round-trips automatically via `to_dict`/`from_dict`). **Reused (do not redefine):** `HarnessState` (+`to_dict`/`from_dict`), `EditLog` (+`to_dict`/`from_dict`), `MetaTools`, the registries/doctrine, `Skill`/`Lesson`/`Doctrine`.

**Conventions:** all code/comments English; `from __future__ import annotations` at the top of every module; commit after every passing task; run via `python -m pytest`.

**Key invariants (each gets a test):**
1. `save` → `load` round-trips `(HarnessState, EditLog)` losslessly, and the immutable-core write-guard is still in force on the restored harness.
2. Versions are monotonic on disk: each `save` writes the next `snap_<NNNN>.json`; `list_versions`/`latest` reflect disk, not memory.
3. Writes are atomic: a temp file is used and is not mistaken for a snapshot; a corrupt/missing snapshot fails loudly (`RuntimeError`/`FileNotFoundError`), never silently.
4. After `rollback_to(v)`, the manager's harness/log equal version `v`, edits made after `v` are gone, and `mgr.tools` is rebound so new edits act on the restored state.
5. Documented hazard: a reference to `mgr.tools`/`mgr.harness` cached *before* a rollback keeps operating on the discarded pre-rollback state — callers must re-fetch `mgr.tools` after a rollback.

---

### Task 1: SnapshotStore (versioned, atomic JSON)

**Files:**
- Create: `alpha/harness/snapshot.py`
- Create: `tests/harness/test_snapshot.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/harness/test_snapshot.py
import json
import pytest
from alpha.harness.skill import Skill
from alpha.harness.memory import Lesson
from alpha.harness.doctrine import Doctrine
from alpha.harness.registry import SkillRegistry, MemoryStore
from alpha.harness.state import HarnessState
from alpha.harness.edit_log import EditLog
from alpha.harness.errors import ImmutableDoctrineError
from alpha.harness.snapshot import SnapshotStore


def _state():
    skills = SkillRegistry.from_skills([
        Skill(skill_id="a", name="A", type="pattern", family="runner", phases=["trend"], status="active"),
    ])
    memory = MemoryStore.from_lessons([Lesson(lesson_id="l1", phases=["flush"], outcome="loss", lesson="x")])
    doctrine = Doctrine.from_seed_list([
        {"section": "core", "regime": "all", "immutable": True, "guidance": "stop discipline"},
    ])
    return HarnessState(doctrine=doctrine, skills=skills, memory=memory)


def _log():
    log = EditLog()
    log.append("write_skill", "skill", "a", "create", "A",
               payload={"before": None, "after": {"x": 1}}, rationale="seed")
    return log


def test_empty_store():
    store = SnapshotStore(__import__("tempfile").mkdtemp())
    assert store.list_versions() == []
    assert store.latest() is None
    with pytest.raises(FileNotFoundError):
        store.load(0)


def test_save_increments_version(tmp_path):
    store = SnapshotStore(tmp_path)
    assert store.save(_state(), _log(), label="v0") == 0
    assert store.save(_state(), _log(), label="v1") == 1
    assert store.list_versions() == [0, 1]
    assert store.latest() == 1


def test_roundtrip_lossless_and_immutable_survives(tmp_path):
    store = SnapshotStore(tmp_path)
    v = store.save(_state(), _log(), label="cp")
    h2, log2 = store.load(v)
    assert h2.skills.get("a").status == "active"
    assert h2.memory.get("l1").lesson == "x"
    assert len(log2) == 1 and log2.records()[0].rationale == "seed"
    with pytest.raises(ImmutableDoctrineError):           # guard restored after load
        h2.doctrine.get("core").guidance = "tampered"


def test_atomic_write_leaves_no_temp(tmp_path):
    store = SnapshotStore(tmp_path)
    store.save(_state(), _log())
    # only the final snapshot file is present; no .tmp leftover, and the temp is not glob-matched
    files = sorted(p.name for p in tmp_path.iterdir())
    assert files == ["snap_0000.json"]
    assert store.list_versions() == [0]


def test_corrupt_snapshot_fails_loudly(tmp_path):
    store = SnapshotStore(tmp_path)
    store.save(_state(), _log())
    (tmp_path / "snap_0000.json").write_text("{ not valid json", encoding="utf-8")
    with pytest.raises(RuntimeError):
        store.load(0)
    # missing top-level key also fails loudly
    (tmp_path / "snap_0000.json").write_text(json.dumps({"version": 0}), encoding="utf-8")
    with pytest.raises(RuntimeError):
        store.load(0)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/harness/test_snapshot.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'alpha.harness.snapshot'`

- [ ] **Step 3: Write minimal implementation**

```python
# alpha/harness/snapshot.py
from __future__ import annotations

import json
import os
from pathlib import Path

from alpha.harness.edit_log import EditLog
from alpha.harness.state import HarnessState


class SnapshotStore:
    """Versioned disk snapshots: one JSON per version at root/snap_<NNNN>.json,
    containing {version, label, harness, log}."""

    def __init__(self, root: str | Path) -> None:
        self._root = Path(root)

    def _path(self, version: int) -> Path:
        return self._root / f"snap_{version:04d}.json"

    def list_versions(self) -> list[int]:
        if not self._root.is_dir():
            return []
        out: list[int] = []
        for p in self._root.glob("snap_*.json"):
            try:
                out.append(int(p.stem.split("_")[1]))
            except (IndexError, ValueError):
                continue
        return sorted(out)

    def latest(self) -> int | None:
        vs = self.list_versions()
        return vs[-1] if vs else None

    def save(self, harness: HarnessState, log: EditLog, label: str = "") -> int:
        self._root.mkdir(parents=True, exist_ok=True)
        latest = self.latest()
        version = 0 if latest is None else latest + 1
        payload = {"version": version, "label": label,
                   "harness": harness.to_dict(), "log": log.to_dict()}
        final = self._path(version)
        tmp = final.with_suffix(".tmp")     # snap_NNNN.tmp -> not matched by snap_*.json glob
        tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        os.replace(tmp, final)              # atomic same-dir rename
        return version

    def load(self, version: int) -> tuple[HarnessState, EditLog]:
        p = self._path(version)
        if not p.exists():
            raise FileNotFoundError(f"no such snapshot version: {version} ({p})")
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
            return (HarnessState.from_dict(data["harness"]), EditLog.from_dict(data["log"]))
        except (json.JSONDecodeError, KeyError) as e:
            raise RuntimeError(f"snapshot {p.name} is corrupt or malformed: {e}") from e
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/harness/test_snapshot.py -q`
Expected: PASS (5 passed)

- [ ] **Step 5: Commit**

```bash
git add alpha/harness/snapshot.py tests/harness/test_snapshot.py
git commit -m "US-1c Task 1: SnapshotStore (versioned, atomic JSON, corrupt-load guard)"
```

---

### Task 2: HarnessManager (checkpoint / rollback / rebind)

**Files:**
- Create: `alpha/harness/manager.py`
- Create: `tests/harness/test_manager.py`

`HarnessManager` owns the live `(harness, log, tools, store)`. `rollback_to` loads a version and rebinds `MetaTools` to the restored `(harness, log)`.

- [ ] **Step 1: Write the failing test**

```python
# tests/harness/test_manager.py
import pytest
from alpha.harness.skill import Skill
from alpha.harness.memory import Lesson
from alpha.harness.doctrine import Doctrine
from alpha.harness.registry import SkillRegistry, MemoryStore
from alpha.harness.state import HarnessState
from alpha.harness.snapshot import SnapshotStore
from alpha.harness.manager import HarnessManager


def _mgr(tmp_path):
    skills = SkillRegistry.from_skills([
        Skill(skill_id="a", name="A", type="pattern", family="runner", phases=["trend"], status="incubating"),
    ])
    memory = MemoryStore.from_lessons([])
    doctrine = Doctrine.from_seed_list([
        {"section": "trend", "regime": "trend", "immutable": False, "guidance": "ride leaders"},
    ])
    h = HarnessState(doctrine=doctrine, skills=skills, memory=memory)
    return HarnessManager(h, SnapshotStore(tmp_path))


def test_checkpoint_returns_version(tmp_path):
    mgr = _mgr(tmp_path)
    assert mgr.checkpoint("baseline") == 0
    assert mgr.latest_version() == 0


def test_rollback_restores_state_and_rebinds_tools(tmp_path):
    mgr = _mgr(tmp_path)
    v0 = mgr.checkpoint("baseline")                 # skill 'a' is incubating, log empty
    mgr.tools.promote_skill("a", rationale="beat OOS")    # incubating -> active (log has 1)
    mgr.tools.write_skill(Skill(skill_id="b", name="B", type="pattern", family="meme", phases=["flush"]),
                          rationale="new")
    assert mgr.harness.skills.get("a").status == "active"
    assert mgr.harness.skills.get("b") is not None
    assert len(mgr.log) == 2

    mgr.rollback_to(v0)
    assert mgr.harness.skills.get("a").status == "incubating"   # restored
    assert mgr.harness.skills.get("b") is None                  # post-checkpoint edit gone
    assert len(mgr.log) == 0                                    # log restored to v0

    # tools are rebound: a new edit acts on the restored harness and its log
    mgr.tools.promote_skill("a", rationale="re-promote on restored state")
    assert mgr.harness.skills.get("a").status == "active"
    assert len(mgr.log) == 1
    assert mgr.tools.h is mgr.harness and mgr.tools.log is mgr.log


def test_checkpoint_after_rollback_appends_new_version(tmp_path):
    mgr = _mgr(tmp_path)
    mgr.checkpoint("v0")
    mgr.tools.promote_skill("a", rationale="x")
    mgr.checkpoint("v1")
    mgr.rollback_to(0)
    assert mgr.checkpoint("v2-after-rollback") == 2   # version is disk-monotonic, not reset


def test_stale_tools_reference_operates_on_discarded_state(tmp_path):
    mgr = _mgr(tmp_path)
    v0 = mgr.checkpoint("v0")
    stale_tools = mgr.tools                  # cached BEFORE rollback
    mgr.tools.promote_skill("a", rationale="x")
    mgr.rollback_to(v0)
    # the stale reference still points at the discarded pre-rollback harness, not mgr.harness
    assert stale_tools.h is not mgr.harness
    stale_tools.write_skill(Skill(skill_id="ghost", name="G", type="pattern", family="meme", phases=["flush"]),
                            rationale="leaked")
    assert mgr.harness.skills.get("ghost") is None    # did NOT touch the live harness
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/harness/test_manager.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'alpha.harness.manager'`

- [ ] **Step 3: Write minimal implementation**

```python
# alpha/harness/manager.py
from __future__ import annotations

from alpha.harness.edit_log import EditLog
from alpha.harness.metatools import MetaTools
from alpha.harness.snapshot import SnapshotStore
from alpha.harness.state import HarnessState


class HarnessManager:
    """Holds the live H + EditLog + MetaTools + SnapshotStore; unifies checkpoint / rollback.

    Rollback = load a whole version snapshot and rebind the tools to the restored (H, log);
    subsequent edits act on the restored state.

    HAZARD: a reference to mgr.tools / mgr.harness cached BEFORE a rollback keeps operating on the
    discarded pre-rollback state. Always re-fetch mgr.tools after a rollback.
    """

    def __init__(self, harness: HarnessState, store: SnapshotStore, log: EditLog | None = None) -> None:
        self.harness = harness
        self.log = log if log is not None else EditLog()
        self.store = store
        self.tools = MetaTools(self.harness, self.log)

    def checkpoint(self, label: str = "") -> int:
        return self.store.save(self.harness, self.log, label)

    def rollback_to(self, version: int) -> None:
        self.harness, self.log = self.store.load(version)
        self.tools = MetaTools(self.harness, self.log)     # rebind to restored state

    def latest_version(self) -> int | None:
        """Latest version on disk (not the in-memory version currently rolled back to)."""
        return self.store.latest()
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/harness/test_manager.py -q`
Expected: PASS (4 passed)

- [ ] **Step 5: Commit**

```bash
git add alpha/harness/manager.py tests/harness/test_manager.py
git commit -m "US-1c Task 2: HarnessManager (checkpoint / rollback / tool rebind)"
```

---

### Task 3: US-1c acceptance gate + docs update

**Files:**
- Create: `tests/harness/test_us1c_acceptance.py`
- Modify: `docs/PROJECT_STATE.md` (mark US-1c done)

- [ ] **Step 1: Write the acceptance test**

```python
# tests/harness/test_us1c_acceptance.py
"""US-1c acceptance: a full checkpoint -> edit -> rollback cycle restores H + log exactly,
rebinds the meta-tools, survives a process boundary (fresh manager from the same store), and
preserves the immutable-core guard across persistence."""
import pytest
from alpha.harness.skill import Skill
from alpha.harness.memory import Lesson
from alpha.harness.doctrine import Doctrine
from alpha.harness.registry import SkillRegistry, MemoryStore
from alpha.harness.state import HarnessState
from alpha.harness.snapshot import SnapshotStore
from alpha.harness.manager import HarnessManager
from alpha.harness.errors import ImmutableDoctrineError


def _state():
    skills = SkillRegistry.from_skills([
        Skill(skill_id="a", name="A", type="pattern", family="runner", phases=["trend"], status="incubating"),
    ])
    doctrine = Doctrine.from_seed_list([
        {"section": "core", "regime": "all", "immutable": True, "guidance": "stop discipline"},
    ])
    return HarnessState(doctrine=doctrine, skills=skills, memory=MemoryStore.from_lessons([]))


def test_checkpoint_edit_rollback_cycle(tmp_path):
    store = SnapshotStore(tmp_path)
    mgr = HarnessManager(_state(), store)
    good = mgr.checkpoint("good")
    # a "bad" refine: promote + add a skill + (try to) damage discipline
    mgr.tools.promote_skill("a", rationale="maybe overfit")
    mgr.tools.write_skill(Skill(skill_id="junk", name="J", type="pattern", family="meme", phases=["flush"]),
                          rationale="noise")
    assert mgr.harness.skills.get("junk") is not None and len(mgr.log) == 2
    # roll back the bad refine
    mgr.rollback_to(good)
    assert mgr.harness.skills.get("a").status == "incubating"
    assert mgr.harness.skills.get("junk") is None
    assert len(mgr.log) == 0
    with pytest.raises(ImmutableDoctrineError):
        mgr.harness.doctrine.get("core").guidance = "loosen"


def test_reload_from_store_across_fresh_manager(tmp_path):
    store = SnapshotStore(tmp_path)
    mgr = HarnessManager(_state(), store)
    mgr.tools.promote_skill("a", rationale="promote")
    v = mgr.checkpoint("active-state")
    # a brand-new manager over the same store loads the persisted state (simulated restart)
    mgr2 = HarnessManager(_state(), SnapshotStore(tmp_path))
    mgr2.rollback_to(v)
    assert mgr2.harness.skills.get("a").status == "active"
    assert mgr2.tools.h is mgr2.harness
```

- [ ] **Step 2: Run the full suite**

Run: `python -m pytest -q`
Expected: PASS — all US-0 + US-1a + US-1b + US-1c tests green.

- [ ] **Step 3: Update `docs/PROJECT_STATE.md`**

In the US-1 section, mark **US-1c (persistence + rollback) done** with the date and a one-line summary (versioned atomic SnapshotStore + HarnessManager checkpoint/rollback with tool rebind; immutable guard survives persistence; round-trips `(H, EditLog)`). Update the "Next" pointer to **US-1d (eval oracle: return + delist→terminal-loss + horizon≥2)**.

- [ ] **Step 4: Commit**

```bash
git add tests/harness/test_us1c_acceptance.py docs/PROJECT_STATE.md
git commit -m "US-1c Task 3: acceptance gate (checkpoint/edit/rollback cycle + restart reload) + PROJECT_STATE"
```

---

## Self-Review (run after writing, fix inline)

**Spec coverage (US-1 "persistence, snapshot/rollback"):** versioned atomic `SnapshotStore` save/load/list/latest (Task 1) ✓ · corrupt-load + atomic-temp guards (Task 1) ✓ · `HarnessManager` checkpoint/rollback_to/latest_version + tool rebind (Task 2) ✓ · immutable guard survives persistence (Tasks 1,3) ✓ · `(HarnessState, EditLog)` + before/after payloads round-trip (Tasks 1,3) ✓ · stale-reference hazard documented + tested (Task 2) ✓.

**Type consistency:** `SnapshotStore.save(harness, log, label) -> int` and `load(version) -> (HarnessState, EditLog)` used identically in `HarnessManager`. Serializes via the existing `HarnessState.to_dict`/`from_dict` (US-1a) and `EditLog.to_dict`/`from_dict` (US-1b) — no new serialization formats. `MetaTools(harness, log)` constructor matches US-1b. `mgr.tools.h`/`mgr.tools.log` identity checks match the `MetaTools.__init__` assignments.

**Placeholder scan:** no TBD/TODO; every code step shows full code; deferrals (auto-checkpoint policy → US-2 inner loop; delta/pruning → later; cycle → US-1e, auto-carried) are explicit scope notes.

**Scope:** persistence + rollback only; no LLM, no inner-loop checkpoint policy, no eval. Produces an independently-testable versioning/recovery layer that US-2's inner loop will drive (checkpoint-before-refine, rollback-on-floor-breaker).
