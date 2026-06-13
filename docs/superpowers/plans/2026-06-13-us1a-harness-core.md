# US-1a Harness Core Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the read-only core of the self-evolving harness `H=(p,K,M)` — the value-object schemas (Skill, Lesson, Doctrine), their registries, the `HarnessState` container, and the seed loader — with the immutable-core write-guard reimplemented and tested.

**Architecture:** Frozen-ish pydantic v2 value objects with `validate_assignment` (mutable at runtime, but `DoctrineEntry` enforces an immutable-core write-guard via `__setattr__`). Skills/Lessons/Doctrine carry a **canonical US momentum phase** vocabulary plus an orthogonal **family** tag (runner/swing/event/meme). Registries index by id with phase/family/status queries. `HarnessState` round-trips through `to_dict`/`from_dict`. A loader assembles `HarnessState` from seed JSON.

**Tech Stack:** Python ≥3.11, pydantic v2, pytest. No LLM, no network — fully offline.

**Spec:** `docs/superpowers/specs/2026-06-13-us-market-adaptation-design.md` (US-1, harness portion). This is sub-plan **US-1a** of US-1 (sequence: 1a core → 1b meta-tools/CRUD → 1c persistence/rollback → 1d eval oracle → 1e regime machine → 1f sizing/guard → 1g seeds+DecisionPackage).

**Scope boundary (US-1a only):** read-only load + query. **Deferred:** skill lifecycle (retire/revive/promote) + doctrine/registry CRUD + **`EditLog`** (append-only edit audit; prerequisite for both CRUD audit and US-1c serialization) → US-1b; SnapshotStore/HarnessManager/atomic persistence → US-1c; the regime state machine (`cycle`) + classifier → US-1e; `G` sub-agents → US-2. `HarnessState` here is `(p=doctrine, K=skills, M=memory)`; `cycle` joins in US-1e (extend `to_dict`/`from_dict`/loader then). **Deliberately NOT expanded (YAGNI):** `GateSpec` stays minimal (gap/price/float fields added when the `rule_policy` consumer lands in US-1d); `regime_raw` provenance omitted (US seeds use clean `phases` lists; round-trip is over the normalized model, lossless).

**Conventions:** all code/comments English; `from __future__ import annotations` at the top of every module; commit after every passing task; run via `python -m pytest`.

---

### Task 1: Harness package + errors

**Files:**
- Create: `alpha/harness/__init__.py`
- Create: `alpha/harness/errors.py`
- Create: `tests/harness/__init__.py`
- Create: `tests/harness/test_errors.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/harness/test_errors.py
from alpha.harness.errors import HarnessError, ImmutableDoctrineError


def test_immutable_error_is_harness_error():
    assert issubclass(ImmutableDoctrineError, HarnessError)
    with __import__("pytest").raises(HarnessError):
        raise ImmutableDoctrineError("nope")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/harness/test_errors.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'alpha.harness'`

- [ ] **Step 3: Write minimal implementation**

```python
# alpha/harness/__init__.py
```

```python
# tests/harness/__init__.py
```

```python
# alpha/harness/errors.py
from __future__ import annotations


class HarnessError(RuntimeError):
    """Base class for harness-edit errors."""


class ImmutableDoctrineError(HarnessError):
    """Attempted to modify an immutable-core doctrine entry (a discipline red-line)."""
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/harness/test_errors.py -q`
Expected: PASS (1 passed)

- [ ] **Step 5: Commit**

```bash
git add alpha/harness/__init__.py alpha/harness/errors.py tests/harness/__init__.py tests/harness/test_errors.py
git commit -m "US-1a Task 1: harness package + errors"
```

---

### Task 2: US momentum phase vocabulary + family tags

**Files:**
- Create: `alpha/harness/regime.py`
- Create: `tests/harness/test_regime.py`

The canonical US momentum cycle (blueprint §6) is 6 states; `family` is the orthogonal playbook tag.

- [ ] **Step 1: Write the failing test**

```python
# tests/harness/test_regime.py
from alpha.harness.regime import (
    CANONICAL_PHASES, FAMILIES, normalize_phase, normalize_phases, is_family,
)


def test_canonical_sets():
    assert CANONICAL_PHASES == ["washout", "recovery", "ignition", "trend", "distribution", "flush"]
    assert FAMILIES == ["runner", "swing", "event", "meme"]


def test_normalize_phase_aliases():
    assert normalize_phase("Trend") == "trend"
    assert normalize_phase("momentum") == "trend"
    assert normalize_phase("first-green") == "recovery"
    assert normalize_phase("freeze") == "washout"
    assert normalize_phase("exhaustion") == "flush"
    assert normalize_phase("nonsense") is None
    assert normalize_phase(123) is None          # non-str does not crash


def test_normalize_phases_dedup_and_all():
    phases, applies_all = normalize_phases(["trend", "momentum", "all", "churn"])
    assert phases == ["trend", "distribution"]   # momentum->trend (dedup); churn->distribution; 'all' excluded from list
    assert applies_all is True


def test_normalize_phases_accepts_string():
    assert normalize_phases("all") == ([], True)
    assert normalize_phases("trend") == (["trend"], False)
    assert normalize_phases("momentum") == (["trend"], False)


def test_is_family():
    assert is_family("runner") is True
    assert is_family("crypto") is False
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/harness/test_regime.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'alpha.harness.regime'`

- [ ] **Step 3: Write minimal implementation**

```python
# alpha/harness/regime.py
from __future__ import annotations

CANONICAL_PHASES = ["washout", "recovery", "ignition", "trend", "distribution", "flush"]
FAMILIES = ["runner", "swing", "event", "meme"]

# alias -> canonical phase (lowercase). Tolerant of Refiner-authored variants.
_PHASE_ALIASES = {
    "washout": "washout", "freeze": "washout", "bottom": "washout",
    "recovery": "recovery", "first-green": "recovery", "first_green": "recovery",
    "ignition": "ignition", "heating": "ignition",
    "trend": "trend", "momentum": "trend",
    "distribution": "distribution", "churn": "distribution",
    "flush": "flush", "exhaustion": "flush",
}


def normalize_phase(raw: object) -> str | None:
    """Map a raw phase token to a canonical phase, or None if unrecognized / not a string."""
    if not isinstance(raw, str):
        return None
    return _PHASE_ALIASES.get(raw.strip().lower())


def normalize_phases(raw: str | list[str] | None) -> tuple[list[str], bool]:
    """Normalize raw phase token(s) to (canonical_phases, applies_all).

    Accepts a single string (wrapped to one token, so a seed `regime: "all"` works) or a list;
    'all' (any case) sets applies_all; unrecognized tokens are dropped; first-seen order kept.
    """
    if isinstance(raw, str):
        raw = [raw]
    phases: list[str] = []
    applies_all = False
    for item in raw or []:
        if isinstance(item, str) and item.strip().lower() == "all":
            applies_all = True
            continue
        p = normalize_phase(item)
        if p is not None and p not in phases:
            phases.append(p)
    return (phases, applies_all)


def is_family(x: object) -> bool:
    return isinstance(x, str) and x in FAMILIES
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/harness/test_regime.py -q`
Expected: PASS (4 passed)

- [ ] **Step 5: Commit**

```bash
git add alpha/harness/regime.py tests/harness/test_regime.py
git commit -m "US-1a Task 2: US momentum phase vocabulary + family tags"
```

---

### Task 3: Skill + SkillStats + GateSpec

**Files:**
- Create: `alpha/harness/skill.py`
- Create: `tests/harness/test_skill.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/harness/test_skill.py
import pytest
from pydantic import ValidationError
from alpha.harness.skill import Skill, SkillStats, GateSpec


def test_stats_record_ewma():
    s = SkillStats()
    s.record(True)
    assert s.n == 1 and s.wins == 1 and s.ewma_winrate == 1.0
    s.record(False, decay=0.5)
    assert s.n == 2 and s.losses == 1 and s.ewma_winrate == 0.5  # decay*new + (1-decay)*old = 0.5*0.0 + 0.5*1.0
    with pytest.raises(ValueError):
        s.record(True, decay=0.0)


def test_gatespec_rejects_unknown_keys():
    GateSpec(min_consecutive_up_days=2, status_in=["gainer"], min_rvol=3.0)
    with pytest.raises(ValidationError):
        GateSpec(min_boards=2)            # CN field name — must be rejected (extra=forbid)


def test_skill_from_seed_normalizes_phase_and_family():
    sk = Skill.from_seed({
        "skill_id": "gap_and_go", "name": "Gap and Go", "type": "pattern",
        "family": "runner", "phases": ["ignition", "momentum", "all"],
        "trigger": "gap up, hold above prior close", "entry": "buy ORB hold",
        "exit_stop": "lose VWAP", "taboo": ["chasing in risk-off"],
    })
    assert sk.phases == ["ignition", "trend"]   # momentum->trend, dedup; 'all' -> flag
    assert sk.applies_all_phases is True
    assert sk.family == "runner"
    assert sk.status == "incubating"            # default
    assert sk.stats.n == 0


def test_skill_rejects_bad_family():
    with pytest.raises(ValueError):
        Skill.from_seed({"skill_id": "x", "name": "X", "type": "pattern", "family": "crypto"})


def test_skill_rejects_unknown_seed_key():
    with pytest.raises(ValidationError):       # extra='forbid' -> loud failure on typo'd seed key
        Skill.from_seed({"skill_id": "x", "name": "X", "type": "pattern", "bogus_key": 1})
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/harness/test_skill.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'alpha.harness.skill'`

- [ ] **Step 3: Write minimal implementation**

```python
# alpha/harness/skill.py
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from alpha.harness.regime import is_family, normalize_phases

SkillType = Literal["pattern", "feature", "failure_detector"]
SkillStatus = Literal["active", "incubating", "dormant", "retired"]


class GateSpec(BaseModel):
    """Machine-readable trigger gate: deterministic match against a StockSnapshot (US fields).

    Strongly typed (extra='forbid') so a typo key from a Refiner patch is rejected, not silently
    swallowed. All fields optional; None = unconstrained (all-None matches any snapshot).
    Match semantics live in the consumer (eval/rule_policy), not here (avoid harness->universe dep).
    """
    model_config = ConfigDict(extra="forbid")
    min_consecutive_up_days: int | None = None
    max_consecutive_up_days: int | None = None
    status_in: list[str] | None = None       # StockStatus values: gainer/gap_up/loser/runner
    min_rvol: float | None = None


class SkillStats(BaseModel):
    """Rolling skill performance (mutable, updated at runtime by credit assignment in US-1d/2)."""
    n: int = 0
    wins: int = 0
    losses: int = 0
    nukes: int = 0                       # times the pick got nuked; nuke_rate = nukes/n
    ewma_winrate: float | None = None
    pnl_ratio: float | None = None
    expectancy: float | None = None      # advantage (score - same-day baseline); set in US-1d
    expectancy_raw: float | None = None  # raw score mean (legacy lens); set in US-1d
    oracle_gap: float | None = None

    def record(self, win: bool, decay: float = 0.1) -> None:
        """Record one outcome. First sample seeds the EWMA; then ewma = decay*x + (1-decay)*ewma."""
        if not 0.0 < decay <= 1.0:
            raise ValueError(f"decay must be in (0, 1], got {decay}")
        x = 1.0 if win else 0.0
        self.n += 1
        self.wins += int(win)
        self.losses += int(not win)
        self.ewma_winrate = x if self.ewma_winrate is None else decay * x + (1 - decay) * self.ewma_winrate


class Skill(BaseModel):
    """A K skill (mutable harness state; the Refiner edits these in later phases)."""
    model_config = ConfigDict(extra="forbid", validate_assignment=True)
    skill_id: str
    name: str
    type: SkillType
    family: str | None = None                                    # runner|swing|event|meme
    phases: list[str] = Field(default_factory=list)             # canonical US phases
    applies_all_phases: bool = False                            # phases contained 'all'
    trigger: str = ""
    entry: str = ""
    exit_stop: str = ""
    taboo: list[str] = Field(default_factory=list)
    depends_on: list[str] = Field(default_factory=list)
    examples: list[str] = Field(default_factory=list)
    status: SkillStatus = "incubating"
    notes: str = ""
    stats: SkillStats = Field(default_factory=SkillStats)
    gate: GateSpec | None = None

    @classmethod
    def from_seed(cls, d: dict) -> "Skill":
        raw_phases = d.get("phases", d.get("applicable_regime", []))
        phases, applies_all = normalize_phases(raw_phases)
        family = d.get("family")
        if family is not None and not is_family(family):
            raise ValueError(f"unknown family: {family!r}")
        rest = {k: v for k, v in d.items() if k not in ("phases", "applicable_regime", "applies_all_phases")}
        return cls(**rest, phases=phases, applies_all_phases=applies_all)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/harness/test_skill.py -q`
Expected: PASS (4 passed)

- [ ] **Step 5: Commit**

```bash
git add alpha/harness/skill.py tests/harness/test_skill.py
git commit -m "US-1a Task 3: Skill + SkillStats + GateSpec"
```

---

### Task 4: Lesson + Importance (memory `M`)

**Files:**
- Create: `alpha/harness/memory.py`
- Create: `tests/harness/test_memory.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/harness/test_memory.py
import pytest
from alpha.harness.memory import Lesson, Importance


def test_importance_weight_and_demote():
    imp = Importance(base=0.8, time_decay=1.0, regime_decay=1.0)
    assert imp.weight() == 0.8
    imp.demote(0.5)
    assert imp.weight() == 0.4
    with pytest.raises(ValueError):
        imp.demote(0.0)


def test_lesson_from_seed():
    le = Lesson.from_seed({
        "lesson_id": "ssr_squeeze_top", "phases": ["flush"], "family": "meme",
        "outcome": "loss", "failure_signature": "chased squeeze top",
        "named_analog": "GME 2021 blowoff", "lesson": "don't chase parabolic squeeze into the flush",
    })
    assert le.phases == ["flush"] and le.family == "meme"
    assert le.outcome == "loss"
    assert le.importance.weight() == 1.0          # default


def test_lesson_from_seed_string_regime():
    le = Lesson.from_seed({"lesson_id": "x", "regime": "momentum", "outcome": "principle", "lesson": "y"})
    assert le.phases == ["trend"] and le.applies_all_phases is False


def test_lesson_bad_family_rejected():
    with pytest.raises(ValueError):
        Lesson.from_seed({"lesson_id": "x", "outcome": "principle", "lesson": "y", "family": "forex"})
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/harness/test_memory.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'alpha.harness.memory'`

- [ ] **Step 3: Write minimal implementation**

```python
# alpha/harness/memory.py
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from alpha.harness.regime import is_family, normalize_phases

Outcome = Literal["win", "loss", "principle"]


class Importance(BaseModel):
    """Memory importance (mutable). weight = base * time_decay * regime_decay (double decay)."""
    model_config = ConfigDict(validate_assignment=True)
    base: float = 1.0
    time_decay: float = 1.0
    regime_decay: float = 1.0

    def weight(self) -> float:
        return self.base * self.time_decay * self.regime_decay

    def demote(self, factor: float) -> None:
        if not 0.0 < factor <= 1.0:
            raise ValueError(f"demote factor must be in (0, 1], got {factor}")
        self.time_decay *= factor


class Lesson(BaseModel):
    """An M memory entry (mutable). Phase/family tagged; double-decay importance."""
    model_config = ConfigDict(extra="forbid", validate_assignment=True)
    lesson_id: str
    phases: list[str] = Field(default_factory=list)
    applies_all_phases: bool = False
    family: str | None = None
    pattern: str = ""
    outcome: Outcome
    failure_signature: str = ""
    named_analog: str = ""
    lesson: str
    importance: Importance = Field(default_factory=Importance)

    @classmethod
    def from_seed(cls, d: dict) -> "Lesson":
        phases, applies_all = normalize_phases(d.get("phases", d.get("regime", [])))
        family = d.get("family")
        if family is not None and not is_family(family):
            raise ValueError(f"unknown family: {family!r}")
        rest = {k: v for k, v in d.items() if k not in ("phases", "regime", "applies_all_phases")}
        return cls(**rest, phases=phases, applies_all_phases=applies_all)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/harness/test_memory.py -q`
Expected: PASS (3 passed)

- [ ] **Step 5: Commit**

```bash
git add alpha/harness/memory.py tests/harness/test_memory.py
git commit -m "US-1a Task 4: Lesson + Importance (memory M)"
```

---

### Task 5: DoctrineEntry + Doctrine + immutable-core guard

**Files:**
- Create: `alpha/harness/doctrine.py`
- Create: `tests/harness/test_doctrine.py`

The immutable-core write-guard is a market-neutral safety mechanism (spec §4): construction is allowed (pydantic writes the dict directly), but post-construction edits to an `immutable=True` entry raise. Read/query only here; CRUD (add/rewrite/remove) is US-1b.

- [ ] **Step 1: Write the failing test**

```python
# tests/harness/test_doctrine.py
import pytest
from alpha.harness.doctrine import DoctrineEntry, Doctrine
from alpha.harness.errors import ImmutableDoctrineError


def test_immutable_entry_blocks_post_construction_edit():
    e = DoctrineEntry(section="risk_redline", phases=["flush"], immutable=True,
                      guidance="respect the regime; no chasing in risk-off")
    with pytest.raises(ImmutableDoctrineError):
        e.guidance = "changed"


def test_mutable_entry_allows_edit():
    e = DoctrineEntry(section="trend_play", phases=["trend"], immutable=False, guidance="ride leaders")
    e.guidance = "ride leaders, trim into blowoff"
    assert e.guidance == "ride leaders, trim into blowoff"


def test_doctrine_queries():
    doc = Doctrine.from_seed_list([
        {"section": "core", "regime": "all", "immutable": True, "guidance": "stop discipline"},
        {"section": "trend", "regime": "trend", "immutable": False, "guidance": "ride leaders"},
    ])
    assert {e.section for e in doc.immutable_core()} == {"core"}
    assert {e.section for e in doc.mutable_entries()} == {"trend"}
    # 'all' entry applies to any phase; 'trend' entry applies to trend
    sections = {e.section for e in doc.for_phase("trend")}
    assert sections == {"core", "trend"}
    assert doc.get("core").immutable is True


def test_doctrine_from_seed_normalizes_phase():
    doc = Doctrine.from_seed_list([{"section": "s", "regime": "momentum", "guidance": "g"}])
    assert doc.get("s").phases == ["trend"]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/harness/test_doctrine.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'alpha.harness.doctrine'`

- [ ] **Step 3: Write minimal implementation**

```python
# alpha/harness/doctrine.py
from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from alpha.harness.errors import ImmutableDoctrineError
from alpha.harness.regime import is_family, normalize_phases


class DoctrineEntry(BaseModel):
    """A p doctrine entry (mutable; immutable=True = a discipline red-line, write-protected)."""
    model_config = ConfigDict(extra="forbid", validate_assignment=True)
    section: str
    phases: list[str] = Field(default_factory=list)
    applies_all_phases: bool = False
    family: str | None = None
    immutable: bool = False
    guidance: str

    @classmethod
    def from_seed(cls, d: dict) -> "DoctrineEntry":
        phases, applies_all = normalize_phases(d.get("phases", d.get("regime", [])))
        family = d.get("family")
        if family is not None and not is_family(family):
            raise ValueError(f"unknown family: {family!r}")
        rest = {k: v for k, v in d.items() if k not in ("phases", "regime", "applies_all_phases")}
        return cls(**rest, phases=phases, applies_all_phases=applies_all)

    def __setattr__(self, name: str, value: object) -> None:
        # Construction writes __dict__ directly (not via this path); this only blocks
        # post-construction edits to a discipline red-line.
        if self.__dict__.get("immutable", False):
            raise ImmutableDoctrineError(f"immutable doctrine entry cannot be modified (field {name})")
        super().__setattr__(name, value)


class Doctrine(BaseModel):
    """Doctrine container (read/query only here; CRUD is US-1b)."""
    entries: list[DoctrineEntry] = Field(default_factory=list)

    @classmethod
    def from_seed_list(cls, items: list[dict]) -> "Doctrine":
        return cls(entries=[DoctrineEntry.from_seed(d) for d in items])

    def get(self, section: str) -> DoctrineEntry | None:
        return next((e for e in self.entries if e.section == section), None)

    def for_phase(self, phase: str) -> list[DoctrineEntry]:
        return [e for e in self.entries if phase in e.phases or e.applies_all_phases]

    def immutable_core(self) -> list[DoctrineEntry]:
        return [e for e in self.entries if e.immutable]

    def mutable_entries(self) -> list[DoctrineEntry]:
        return [e for e in self.entries if not e.immutable]
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/harness/test_doctrine.py -q`
Expected: PASS (4 passed)

- [ ] **Step 5: Commit**

```bash
git add alpha/harness/doctrine.py tests/harness/test_doctrine.py
git commit -m "US-1a Task 5: DoctrineEntry + Doctrine + immutable-core guard"
```

---

### Task 6: SkillRegistry + MemoryStore (read + query)

**Files:**
- Create: `alpha/harness/registry.py`
- Create: `tests/harness/test_registry.py`

Read + query only. Lifecycle (retire/revive/promote) and write/patch are US-1b.

- [ ] **Step 1: Write the failing test**

```python
# tests/harness/test_registry.py
import pytest
from alpha.harness.skill import Skill
from alpha.harness.memory import Lesson
from alpha.harness.registry import SkillRegistry, MemoryStore


def _skill(sid, family="runner", phases=("trend",), status="active", type_="pattern"):
    return Skill(skill_id=sid, name=sid, type=type_, family=family, phases=list(phases), status=status)


def test_skill_registry_queries():
    reg = SkillRegistry.from_skills([
        _skill("a", family="runner", phases=["trend"], status="active"),
        _skill("b", family="swing", phases=["recovery"], status="incubating", type_="feature"),
    ])
    assert reg.get("a").skill_id == "a"
    assert len(reg) == 2 and bool(reg) is True
    assert [s.skill_id for s in reg.by_status("active")] == ["a"]
    assert [s.skill_id for s in reg.by_type("feature")] == ["b"]
    assert [s.skill_id for s in reg.by_phase("trend")] == ["a"]
    assert [s.skill_id for s in reg.by_family("swing")] == ["b"]


def test_skill_registry_applies_all_phases():
    s = _skill("z", phases=[])
    s.applies_all_phases = True
    reg = SkillRegistry.from_skills([s])
    assert [x.skill_id for x in reg.by_phase("flush")] == ["z"]   # applies_all matches any phase


def test_duplicate_skill_id_rejected():
    with pytest.raises(ValueError):
        SkillRegistry.from_skills([_skill("dup"), _skill("dup")])


def test_memory_store_queries():
    store = MemoryStore.from_lessons([
        Lesson(lesson_id="l1", phases=["flush"], family="meme", outcome="loss", lesson="x"),
        Lesson(lesson_id="l2", phases=["trend"], family="runner", outcome="win", lesson="y"),
    ])
    assert store.get("l1").lesson_id == "l1"
    assert [l.lesson_id for l in store.by_phase("flush")] == ["l1"]
    assert [l.lesson_id for l in store.by_family("runner")] == ["l2"]
    assert [l.lesson_id for l in store.by_outcome("loss")] == ["l1"]
    assert len(store) == 2 and bool(store) is True
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/harness/test_registry.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'alpha.harness.registry'`

- [ ] **Step 3: Write minimal implementation**

```python
# alpha/harness/registry.py
from __future__ import annotations

from alpha.harness.memory import Lesson
from alpha.harness.skill import Skill


class SkillRegistry:
    """K skill library indexed by id. US-1a: read + query only (CRUD/lifecycle in US-1b)."""

    def __init__(self, skills: dict[str, Skill]) -> None:
        self._skills = dict(skills)

    @classmethod
    def from_skills(cls, skills: list[Skill]) -> "SkillRegistry":
        index: dict[str, Skill] = {}
        for s in skills:
            if s.skill_id in index:
                raise ValueError(f"duplicate skill_id: {s.skill_id}")
            index[s.skill_id] = s
        return cls(index)

    def get(self, skill_id: str) -> Skill | None:
        return self._skills.get(skill_id)

    def all(self) -> list[Skill]:
        return list(self._skills.values())

    def by_status(self, status: str) -> list[Skill]:
        return [s for s in self._skills.values() if s.status == status]

    def by_type(self, type_: str) -> list[Skill]:
        return [s for s in self._skills.values() if s.type == type_]

    def by_phase(self, phase: str) -> list[Skill]:
        return [s for s in self._skills.values() if phase in s.phases or s.applies_all_phases]

    def by_family(self, family: str) -> list[Skill]:
        return [s for s in self._skills.values() if s.family == family]

    def __len__(self) -> int:
        return len(self._skills)

    def __bool__(self) -> bool:
        return True


class MemoryStore:
    """M memory library indexed by lesson id. US-1a: read + query only."""

    def __init__(self, lessons: dict[str, Lesson]) -> None:
        self._lessons = dict(lessons)

    @classmethod
    def from_lessons(cls, lessons: list[Lesson]) -> "MemoryStore":
        index: dict[str, Lesson] = {}
        for l in lessons:
            if l.lesson_id in index:
                raise ValueError(f"duplicate lesson_id: {l.lesson_id}")
            index[l.lesson_id] = l
        return cls(index)

    def get(self, lesson_id: str) -> Lesson | None:
        return self._lessons.get(lesson_id)

    def all(self) -> list[Lesson]:
        return list(self._lessons.values())

    def by_phase(self, phase: str) -> list[Lesson]:
        return [l for l in self._lessons.values() if phase in l.phases or l.applies_all_phases]

    def by_family(self, family: str) -> list[Lesson]:
        return [l for l in self._lessons.values() if l.family == family]

    def by_outcome(self, outcome: str) -> list[Lesson]:
        return [l for l in self._lessons.values() if l.outcome == outcome]

    def __len__(self) -> int:
        return len(self._lessons)

    def __bool__(self) -> bool:
        return True
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/harness/test_registry.py -q`
Expected: PASS (4 passed)

- [ ] **Step 5: Commit**

```bash
git add alpha/harness/registry.py tests/harness/test_registry.py
git commit -m "US-1a Task 6: SkillRegistry + MemoryStore (read + query)"
```

---

### Task 7: HarnessState container + round-trip

**Files:**
- Create: `alpha/harness/state.py`
- Create: `tests/harness/test_state.py`

`HarnessState = (p=doctrine, K=skills, M=memory)`. (`cycle` joins in US-1e.) The round-trip must preserve the immutable-core guard.

- [ ] **Step 1: Write the failing test**

```python
# tests/harness/test_state.py
import pytest
from alpha.harness.skill import Skill
from alpha.harness.memory import Lesson
from alpha.harness.doctrine import Doctrine
from alpha.harness.registry import SkillRegistry, MemoryStore
from alpha.harness.state import HarnessState
from alpha.harness.errors import ImmutableDoctrineError


def _state():
    skills = SkillRegistry.from_skills([
        Skill(skill_id="a", name="A", type="pattern", family="runner", phases=["trend"], status="active"),
        Skill(skill_id="b", name="B", type="pattern", family="runner", phases=["trend"], status="incubating"),
    ])
    memory = MemoryStore.from_lessons([Lesson(lesson_id="l1", phases=["trend"], outcome="win", lesson="x")])
    doctrine = Doctrine.from_seed_list([
        {"section": "core", "regime": "all", "immutable": True, "guidance": "stop discipline"},
    ])
    return HarnessState(doctrine=doctrine, skills=skills, memory=memory)


def test_active_skills_for_phase():
    st = _state()
    assert [s.skill_id for s in st.active_skills_for("trend")] == ["a"]   # 'b' is incubating


def test_roundtrip_preserves_immutable_guard():
    st = _state()
    d = st.to_dict()
    st2 = HarnessState.from_dict(d)
    assert len(st2.skills) == 2 and len(st2.memory) == 1
    core = st2.doctrine.get("core")
    assert core.immutable is True
    with pytest.raises(ImmutableDoctrineError):       # guard restored after rebuild
        core.guidance = "tampered"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/harness/test_state.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'alpha.harness.state'`

- [ ] **Step 3: Write minimal implementation**

```python
# alpha/harness/state.py
from __future__ import annotations

from dataclasses import dataclass

from alpha.harness.doctrine import Doctrine
from alpha.harness.memory import Lesson
from alpha.harness.registry import MemoryStore, SkillRegistry
from alpha.harness.skill import Skill


@dataclass
class HarnessState:
    """Harness state H = (p=doctrine, K=skills, M=memory).

    The regime state machine (cycle) and G sub-agents join in US-1e / US-2.
    """
    doctrine: Doctrine          # p
    skills: SkillRegistry       # K
    memory: MemoryStore         # M

    def active_skills_for(self, phase: str) -> list[Skill]:
        return [s for s in self.skills.by_phase(phase) if s.status == "active"]

    def to_dict(self) -> dict:
        return {
            "skills": [s.model_dump() for s in self.skills.all()],
            "memory": [l.model_dump() for l in self.memory.all()],
            "doctrine": self.doctrine.model_dump(),
        }

    @classmethod
    def from_dict(cls, d: dict) -> "HarnessState":
        # model_validate rebuilds immutable entries via the core constructor (bypassing the
        # __setattr__ guard at build time); the guard is back in force on the rebuilt object.
        # US-1e: add a `cycle` field above and a "cycle" key in to_dict/from_dict here.
        return cls(
            doctrine=Doctrine.model_validate(d["doctrine"]),
            skills=SkillRegistry.from_skills([Skill.model_validate(x) for x in d["skills"]]),
            memory=MemoryStore.from_lessons([Lesson.model_validate(x) for x in d["memory"]]),
        )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/harness/test_state.py -q`
Expected: PASS (2 passed)

- [ ] **Step 5: Commit**

```bash
git add alpha/harness/state.py tests/harness/test_state.py
git commit -m "US-1a Task 7: HarnessState container + round-trip (immutable guard preserved)"
```

---

### Task 8: Seed loader

**Files:**
- Create: `alpha/harness/loader.py`
- Create: `tests/harness/test_loader.py`

Loads `skills.json` / `memory.json` / `doctrine.json` from a directory into a `HarnessState`. (The real seed content is US-1g; here it's tested with small fixture JSON written to `tmp_path`.)

- [ ] **Step 1: Write the failing test**

```python
# tests/harness/test_loader.py
import json
import pytest
from alpha.harness.loader import load_seeds


def _write_seeds(d):
    (d / "skills.json").write_text(json.dumps([
        {"skill_id": "gap_and_go", "name": "Gap and Go", "type": "pattern",
         "family": "runner", "phases": ["ignition", "trend"], "trigger": "t", "entry": "e",
         "exit_stop": "x", "status": "active"},
    ]), encoding="utf-8")
    (d / "memory.json").write_text(json.dumps([
        {"lesson_id": "l1", "phases": ["flush"], "family": "meme", "outcome": "loss",
         "lesson": "don't chase the squeeze top"},
    ]), encoding="utf-8")
    (d / "doctrine.json").write_text(json.dumps([
        {"section": "core", "regime": "all", "immutable": True, "guidance": "stop discipline"},
    ]), encoding="utf-8")


def test_load_seeds_assembles_state(tmp_path):
    _write_seeds(tmp_path)
    st = load_seeds(tmp_path)
    assert len(st.skills) == 1 and len(st.memory) == 1
    assert st.skills.get("gap_and_go").family == "runner"
    assert st.skills.get("gap_and_go").phases == ["ignition", "trend"]
    assert st.doctrine.get("core").immutable is True
    assert [s.skill_id for s in st.active_skills_for("trend")] == ["gap_and_go"]


def test_load_seeds_missing_dir_raises(tmp_path):
    with pytest.raises(FileNotFoundError):
        load_seeds(tmp_path / "nope")


def test_load_seeds_missing_file_raises(tmp_path):
    (tmp_path / "skills.json").write_text("[]", encoding="utf-8")
    # memory.json and doctrine.json absent
    with pytest.raises(FileNotFoundError):
        load_seeds(tmp_path)


def test_load_seeds_non_list_top_level_raises(tmp_path):
    _write_seeds(tmp_path)
    (tmp_path / "skills.json").write_text('{"not": "a list"}', encoding="utf-8")
    with pytest.raises(ValueError):
        load_seeds(tmp_path)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/harness/test_loader.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'alpha.harness.loader'`

- [ ] **Step 3: Write minimal implementation**

```python
# alpha/harness/loader.py
from __future__ import annotations

import json
from pathlib import Path

from alpha.harness.doctrine import Doctrine
from alpha.harness.memory import Lesson
from alpha.harness.registry import MemoryStore, SkillRegistry
from alpha.harness.skill import Skill
from alpha.harness.state import HarnessState


def _read_json_list(path: Path) -> list[dict]:
    if not path.exists():
        raise FileNotFoundError(f"missing seed file: {path}")
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, list):
        raise ValueError(f"seed file top level must be a JSON array, got {type(data).__name__}: {path}")
    return data


def load_seeds(seeds_dir: str | Path) -> HarnessState:
    """Read skills.json / memory.json / doctrine.json, normalize + validate, assemble HarnessState."""
    d = Path(seeds_dir)
    if not d.is_dir():
        raise FileNotFoundError(f"missing seeds directory: {d}")
    skills = SkillRegistry.from_skills([Skill.from_seed(x) for x in _read_json_list(d / "skills.json")])
    memory = MemoryStore.from_lessons([Lesson.from_seed(x) for x in _read_json_list(d / "memory.json")])
    doctrine = Doctrine.from_seed_list(_read_json_list(d / "doctrine.json"))
    # US-1e adds: cycle = StateMachine.from_seed_list(_read_json_list(d / "state_machine.json"))
    return HarnessState(doctrine=doctrine, skills=skills, memory=memory)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/harness/test_loader.py -q`
Expected: PASS (4 passed)

- [ ] **Step 5: Commit**

```bash
git add alpha/harness/loader.py tests/harness/test_loader.py
git commit -m "US-1a Task 8: seed loader -> HarnessState"
```

---

### Task 9: US-1a acceptance gate + docs update

**Files:**
- Create: `tests/harness/test_us1a_acceptance.py`
- Modify: `docs/PROJECT_STATE.md` (mark US-1a done)

- [ ] **Step 1: Write the acceptance test**

```python
# tests/harness/test_us1a_acceptance.py
"""US-1a acceptance: a harness H=(p,K,M) loads from seeds, queries by phase/family, and
the immutable-core guard survives a to_dict/from_dict round-trip."""
import json
from alpha.harness.loader import load_seeds
from alpha.harness.state import HarnessState
from alpha.harness.errors import ImmutableDoctrineError
import pytest


def _seed_dir(d):
    (d / "skills.json").write_text(json.dumps([
        {"skill_id": "gap_and_go", "name": "Gap and Go", "type": "pattern", "family": "runner",
         "phases": ["trend"], "trigger": "t", "entry": "e", "exit_stop": "x", "status": "active"},
        {"skill_id": "squeeze", "name": "Squeeze", "type": "pattern", "family": "meme",
         "phases": ["ignition"], "status": "incubating"},
    ]), encoding="utf-8")
    (d / "memory.json").write_text(json.dumps([
        {"lesson_id": "l1", "phases": ["flush"], "family": "meme", "outcome": "loss", "lesson": "z"},
    ]), encoding="utf-8")
    (d / "doctrine.json").write_text(json.dumps([
        {"section": "core", "regime": "all", "immutable": True, "guidance": "stop discipline"},
    ]), encoding="utf-8")
    return d


def test_end_to_end_harness_core(tmp_path):
    st = load_seeds(_seed_dir(tmp_path))
    # query by phase and family
    assert [s.skill_id for s in st.active_skills_for("trend")] == ["gap_and_go"]
    assert [s.skill_id for s in st.skills.by_family("meme")] == ["squeeze"]
    assert [l.lesson_id for l in st.memory.by_family("meme")] == ["l1"]
    # immutable core survives round-trip
    st2 = HarnessState.from_dict(st.to_dict())
    with pytest.raises(ImmutableDoctrineError):
        st2.doctrine.get("core").guidance = "tampered"
```

- [ ] **Step 2: Run the full suite**

Run: `python -m pytest -q`
Expected: PASS — all US-0 + US-1a tests green.

- [ ] **Step 3: Update `docs/PROJECT_STATE.md`**

Add a line under the roadmap/milestone section marking **US-1a (harness core) done** with the date and a one-line summary (schemas + registries + HarnessState + loader; read-only load+query; immutable-core guard reimplemented + round-trip tested). Note next is **US-1b (meta-tools CRUD)**.

- [ ] **Step 4: Commit**

```bash
git add tests/harness/test_us1a_acceptance.py docs/PROJECT_STATE.md
git commit -m "US-1a Task 9: acceptance gate (load + query + immutable round-trip) + PROJECT_STATE"
```

---

## Self-Review (run after writing, fix inline)

**Spec coverage (US-1 harness core portion):** Skill/SkillStats/GateSpec (Task 3) ✓ · Lesson/Importance (Task 4) ✓ · Doctrine + immutable-core guard (Task 5) ✓ · registries (Task 6) ✓ · HarnessState + round-trip (Task 7) ✓ · loader (Task 8) ✓ · family tag flows seed→registry query (Tasks 3/4/6/8) ✓ · US 6-phase vocabulary (Task 2) ✓. **Deferred & documented:** CRUD/lifecycle → US-1b; persistence/rollback → US-1c; state machine/cycle → US-1e; G sub-agents → US-2.

**Type consistency:** `normalize_phases(raw) -> (phases, applies_all)` used identically in Skill/Lesson/DoctrineEntry `from_seed`. `applies_all_phases` field name consistent across Skill/Lesson/DoctrineEntry and queried identically in `by_phase`/`for_phase`/`active_skills_for`. `family` validated via `is_family` in all three `from_seed`. `from_skills`/`from_lessons`/`from_seed_list` constructors consistent. `to_dict`/`from_dict` keys (`skills`/`memory`/`doctrine`) match.

**Placeholder scan:** no TBD/TODO; every code step shows full code; the only deferrals are explicit scope-boundary notes pointing at later sub-plans.

**Scope:** read-only load + query only; no CRUD, no persistence store, no LLM. Produces an independently-testable harness-core layer.
