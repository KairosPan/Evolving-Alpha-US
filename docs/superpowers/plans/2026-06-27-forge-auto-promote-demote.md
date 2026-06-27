# The Forge — Gated Auto-Promote/Demote from Episodes (§6 #2) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A deterministic, LLM-free episode-evidence proposer that promotes `incubating` skills with strong history and demotes (soft-retires → `dormant`) `active` skills with a strong nuke history — each routed through the existing gate (double-floored on the skill's own stats + the §5 `conflict_queue` for teaching-owned contests).

**Architecture:** New `alpha/refine/forge.py` (`propose_skill_ops` pure proposer + `forge_skills` gated applier + `ForgeReport`) reusing `summarize` (§6 #3) and `try_apply_op` (the one gate). A standalone runner `scripts/evolve_from_episodes.py` mirrors `refine_live` (lock→load→forge→save), LLM-free. A small additive wire closes the write→read loop: `refine_live` opens an `EpisodeStore` and writes episodes to `ALPHA_EPISODES_DB`.

**Tech Stack:** Python ≥3.11, pydantic v2, pytest. Reuses `alpha/memory/aggregate.py::summarize`, `alpha/memory/store.py::EpisodeStore`, `alpha/refine/apply.py::try_apply_op`, `alpha/refine/ops.py::RefineOp`, `alpha/harness/edit_log.py::EditProvenance`, `alpha/harness/metatools.py::MetaTools`, `alpha/meta/store.py::LiveBrainStore`, `alpha/meta/conflict_store.py::ConflictQueue`. Mirrors `scripts/refine_live.py`.

## Global Constraints

- **Python `>=3.11`**, pydantic v2. The existing suite (currently **669 passed**) must stay green — every change is additive (new files + an additive `episodes_db=None` on `run_refine_live`).
- **Deterministic + LLM-free:** the forge proposes from `summarize(episode_store.for_asof(asof), key=skill_id)` — no LLM, no PIT window.
- **Demote = soft:** `retire_skill(permanent=False)` → `active → dormant` (revivable). Never `retired`.
- **Thresholds:** promote = `incubating` + `n≥promote_min_samples(5)` + `win_rate≥promote_min_winrate(0.5)` + `mean_advantage>0`; retire = `active` + `n≥retire_min_samples(5)` + `nuke_rate≥retire_min_nukerate(0.5)`.
- **Double-gate:** the episode aggregate proposes; `try_apply_op` independently enforces the skill's OWN stats floor (promote: `skill.stats.n≥min_promote_samples` AND `expectancy>0`; retire: `skill.stats.n≥min_retire_samples`). Apply only if both agree.
- **Provenance `path="self_study", proposer="forge"`** on every forge op; teaching-owned contests → HELD to the `conflict_queue` (§5), never auto-applied.
- **Runner holds `LiveBrainStore.lock()`** across load→forge→save (serialized vs Sonia/workbench/refine_live). Operator script — errors propagate (fail loud).
- English; mirror `scripts/refine_live.py`.

## File Structure

- Create: `alpha/refine/forge.py` (`propose_skill_ops`, `ForgeReport`, `forge_skills`).
- Create: `scripts/evolve_from_episodes.py` (`run_evolve_from_episodes` + `main`).
- Modify: `scripts/refine_live.py` (additive `episodes_db=None` → write episodes via `EpisodeStore`).
- Tests: `tests/refine/test_forge_propose.py`, `tests/refine/test_forge_apply.py`, `tests/scripts/test_evolve_from_episodes.py`, `tests/scripts/test_refine_live_episodes.py`.

---

### Task 1: `propose_skill_ops` (the deterministic proposer)

**Files:**
- Create: `alpha/refine/forge.py`
- Test: `tests/refine/test_forge_propose.py`

**Interfaces:**
- Consumes: `summarize` (§6), `EpisodeStore.for_asof`, `RefineOp`, `harness.skills.get(skill_id) -> Skill | None` (`.status`, `.stats`), `EpisodeStats` (`.n/.win_rate/.nuke_rate/.mean_advantage`).
- Produces: `propose_skill_ops(harness, episode_store, *, asof, promote_min_samples=5, promote_min_winrate=0.5, retire_min_samples=5, retire_min_nukerate=0.5) -> list[RefineOp]`. Consumed by Task 2.

- [ ] **Step 1: Write the failing test**

```python
# tests/refine/test_forge_propose.py
from datetime import date
from alpha.harness.doctrine import Doctrine
from alpha.harness.skill import Skill, SkillStats
from alpha.harness.registry import SkillRegistry, MemoryStore
from alpha.harness.state import HarnessState
from alpha.memory.episodes import Episode
from alpha.memory.store import EpisodeStore
from alpha.refine.forge import propose_skill_ops

def _skill(sid, status, stats=None):
    return Skill(skill_id=sid, name=sid, type="pattern", family="runner", phases=["trend"],
                 status=status, stats=stats or SkillStats())

def _h(*skills):
    return HarnessState(doctrine=Doctrine(), skills=SkillRegistry.from_skills(list(skills)),
                        memory=MemoryStore.from_lessons([]))

def _store(*eps):
    s = EpisodeStore.in_memory()
    for e in eps:
        s.add(e)
    return s

def _ep(skill_id, outcome, adv, sym="RUN", exit_d=date(2026, 6, 3)):
    return Episode(episode_id=f"{skill_id}:{sym}:{outcome}:{adv}:{exit_d}", symbol=sym, skill_id=skill_id,
                   entry_date=date(2026, 6, 1), exit_date=exit_d, outcome=outcome, advantage=adv)

def test_incubating_strong_positive_proposes_promote():
    h = _h(_skill("s1", "incubating"))
    eps = [_ep("s1", "continued", 2.0)] * 4 + [_ep("s1", "faded", 0.5)]   # n=5, win_rate=0.8, mean_adv>0
    ops = propose_skill_ops(h, _store(*eps), asof=date(2026, 6, 20))
    assert len(ops) == 1 and ops[0].tool == "promote_skill" and ops[0].args["skill_id"] == "s1"
    assert ops[0].rationale                                              # carries evidence

def test_active_strong_negative_proposes_soft_retire():
    h = _h(_skill("s2", "active"))
    eps = [_ep("s2", "nuked", -2.0)] * 3 + [_ep("s2", "continued", 1.0)] * 2   # n=5, nuke_rate=0.6
    ops = propose_skill_ops(h, _store(*eps), asof=date(2026, 6, 20))
    assert len(ops) == 1 and ops[0].tool == "retire_skill"
    assert ops[0].args["skill_id"] == "s2" and ops[0].args["permanent"] is False   # soft demote

def test_status_gates_the_direction():
    # an ACTIVE skill with great stats is NOT promoted; an INCUBATING skill with nukes is NOT retired
    h = _h(_skill("act", "active"), _skill("inc", "incubating"))
    eps = ([_ep("act", "continued", 2.0)] * 5) + ([_ep("inc", "nuked", -2.0)] * 5)
    ops = propose_skill_ops(h, _store(*eps), asof=date(2026, 6, 20))
    assert ops == []

def test_below_sample_floor_no_op():
    h = _h(_skill("s5", "incubating"))
    eps = [_ep("s5", "continued", 2.0)] * 2                              # n=2 < 5
    assert propose_skill_ops(h, _store(*eps), asof=date(2026, 6, 20)) == []

def test_pit_excludes_future_episodes():
    h = _h(_skill("s1", "incubating"))
    eps = [_ep("s1", "continued", 2.0, exit_d=date(2026, 9, 1))] * 5     # learned_asof in the future
    assert propose_skill_ops(h, _store(*eps), asof=date(2026, 6, 20)) == []
```

- [ ] **Step 2: Run to verify it fails**

Run: `python -m pytest tests/refine/test_forge_propose.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'alpha.refine.forge'`.

- [ ] **Step 3: Implement**

```python
# alpha/refine/forge.py
from __future__ import annotations
from datetime import date as Date
from alpha.harness.state import HarnessState
from alpha.memory.aggregate import summarize
from alpha.refine.ops import RefineOp

def propose_skill_ops(harness: HarnessState, episode_store, *, asof: Date,
                      promote_min_samples: int = 5, promote_min_winrate: float = 0.5,
                      retire_min_samples: int = 5, retire_min_nukerate: float = 0.5) -> list[RefineOp]:
    """Deterministic per-skill episode-evidence proposer: promote strong incubating skills, soft-retire
    strong-negative active skills. PIT-masked via for_asof(asof). Pure (reads, never writes)."""
    stats = summarize(episode_store.for_asof(asof), key=lambda e: e.skill_id)
    ops: list[RefineOp] = []
    for skill_id, s in stats.items():
        sk = harness.skills.get(skill_id)
        if sk is None:
            continue
        if (sk.status == "incubating" and s.n >= promote_min_samples
                and s.win_rate >= promote_min_winrate and s.mean_advantage > 0):
            ops.append(RefineOp(tool="promote_skill", args={"skill_id": skill_id},
                                rationale=(f"forge: episode evidence n={s.n} win_rate={s.win_rate:.2f} "
                                           f"mean_adv={s.mean_advantage:+.2f}")))
        elif (sk.status == "active" and s.n >= retire_min_samples and s.nuke_rate >= retire_min_nukerate):
            ops.append(RefineOp(tool="retire_skill", args={"skill_id": skill_id, "permanent": False},
                                rationale=(f"forge: episode evidence n={s.n} nuke_rate={s.nuke_rate:.2f} "
                                           f"mean_adv={s.mean_advantage:+.2f}")))
    return ops
```

- [ ] **Step 4: Run to verify it passes**

Run: `python -m pytest tests/refine/test_forge_propose.py -v`
Expected: 5 PASS.

- [ ] **Step 5: Commit**

```bash
git add alpha/refine/forge.py tests/refine/test_forge_propose.py
git commit -m "feat(forge): propose_skill_ops — deterministic episode-evidence promote/soft-retire proposer"
```

---

### Task 2: `forge_skills` + `ForgeReport` (the gated applier, double-gate + held)

**Files:**
- Modify: `alpha/refine/forge.py`
- Test: `tests/refine/test_forge_apply.py`

**Interfaces:**
- Consumes: `propose_skill_ops` (T1), `try_apply_op`, `EditProvenance`, `MetaTools`.
- Produces: `ForgeReport(applied: list[str], held: list[str], rejected: list[tuple[str, str]])`; `forge_skills(harness, episode_store, meta, *, asof, conflict_queue=None, min_promote_samples=3, min_retire_samples=5, **proposer_kwargs) -> ForgeReport`. Consumed by Task 3.

- [ ] **Step 1: Write the failing test**

```python
# tests/refine/test_forge_apply.py
from datetime import date
from alpha.harness.doctrine import Doctrine
from alpha.harness.skill import Skill, SkillStats
from alpha.harness.registry import SkillRegistry, MemoryStore
from alpha.harness.state import HarnessState
from alpha.harness.edit_log import EditLog, EditProvenance
from alpha.harness.metatools import MetaTools
from alpha.memory.episodes import Episode
from alpha.memory.store import EpisodeStore
from alpha.refine.forge import forge_skills

def _skill(sid, status, stats=None):
    return Skill(skill_id=sid, name=sid, type="pattern", family="runner", phases=["trend"],
                 status=status, stats=stats or SkillStats())

def _h(*skills):
    return HarnessState(doctrine=Doctrine(), skills=SkillRegistry.from_skills(list(skills)),
                        memory=MemoryStore.from_lessons([]))

def _store(*eps):
    s = EpisodeStore.in_memory()
    for e in eps:
        s.add(e)
    return s

def _wins(skill_id, n=5):
    return [Episode(episode_id=f"{skill_id}:{i}", symbol="RUN", skill_id=skill_id,
                    entry_date=date(2026, 6, 1), exit_date=date(2026, 6, 3), outcome="continued", advantage=2.0)
            for i in range(n)]

def _nukes(skill_id, n=5):
    return [Episode(episode_id=f"{skill_id}:{i}", symbol="RUN", skill_id=skill_id,
                    entry_date=date(2026, 6, 1), exit_date=date(2026, 6, 3), outcome="nuked", advantage=-2.0)
            for i in range(n)]

def test_applies_when_both_floors_agree():
    # incubating, episode evidence promotes AND skill.stats clears the gate (n>=3, expectancy>0)
    h = _h(_skill("s1", "incubating", SkillStats(n=5, expectancy=1.0)))
    log = EditLog()
    rep = forge_skills(h, _store(*_wins("s1")), MetaTools(h, log), asof=date(2026, 6, 20))
    assert rep.applied == ["s1"] and h.skills.get("s1").status == "active"   # promoted

def test_double_gate_rejects_when_skill_stats_disagree():
    # episodes say promote, but skill.stats.expectancy <= 0 -> the gate blocks it
    h = _h(_skill("s2", "incubating", SkillStats(n=5, expectancy=-0.5)))
    log = EditLog()
    rep = forge_skills(h, _store(*_wins("s2")), MetaTools(h, log), asof=date(2026, 6, 20))
    assert rep.applied == [] and any(sid == "s2" for sid, _ in rep.rejected)
    assert h.skills.get("s2").status == "incubating"                        # unchanged

def test_teaching_owned_contest_is_held():
    # an active teaching-owned skill the episodes want to retire -> HELD (with a conflict_queue), not retired
    h = _h(_skill("s3", "active", SkillStats(n=10, expectancy=0.1)))
    log = EditLog()
    # stamp s3 as teaching-owned in the log (a prior teaching create/promote)
    log.append("promote_skill", "skill", "s3", "promote")
    log.stamp_last(EditProvenance(path="teaching", proposer="sonia"))
    class _Q:
        def __init__(self): self.items = []
        def add(self, **kw): self.items.append(kw)
    q = _Q()
    rep = forge_skills(h, _store(*_nukes("s3")), MetaTools(h, log), asof=date(2026, 6, 20), conflict_queue=q)
    assert rep.held == ["s3"] and len(q.items) == 1
    assert h.skills.get("s3").status == "active"                            # not retired (held)
```

- [ ] **Step 2: Run to verify it fails**

Run: `python -m pytest tests/refine/test_forge_apply.py -v`
Expected: FAIL — `ImportError: cannot import name 'forge_skills'`.

- [ ] **Step 3: Implement** — add to `alpha/refine/forge.py`:

```python
from pydantic import BaseModel, Field
from alpha.harness.edit_log import EditProvenance
from alpha.refine.apply import try_apply_op

_FORGE_ALLOWED = frozenset({"promote_skill", "retire_skill"})

class ForgeReport(BaseModel):
    applied: list[str] = Field(default_factory=list)
    held: list[str] = Field(default_factory=list)
    rejected: list[tuple[str, str]] = Field(default_factory=list)   # (skill_id, reason)

def forge_skills(harness: HarnessState, episode_store, meta, *, asof: Date, conflict_queue=None,
                 min_promote_samples: int = 3, min_retire_samples: int = 5, **proposer_kwargs) -> ForgeReport:
    """Apply the proposed promote/retire ops through the one gate: the episode evidence proposes, the gate
    independently confirms on the skill's own stats; a teaching-owned contest is HELD (§5)."""
    report = ForgeReport()
    for op in propose_skill_ops(harness, episode_store, asof=asof, **proposer_kwargs):
        sid = op.args["skill_id"]
        rec, reason = try_apply_op(meta, harness, op, allowed=_FORGE_ALLOWED,
                                   min_promote_samples=min_promote_samples,
                                   min_retire_samples=min_retire_samples,
                                   provenance=EditProvenance(path="self_study", proposer="forge"),
                                   conflict_queue=conflict_queue)
        if rec is not None:
            report.applied.append(sid)
        elif reason and reason.startswith("held_for_review"):
            report.held.append(sid)
        else:
            report.rejected.append((sid, reason or ""))
    return report
```

- [ ] **Step 4: Run to verify it passes + full suite green**

Run: `python -m pytest tests/refine/test_forge_apply.py -v && python -m pytest -q`
Expected: 3 PASS; full suite green (new file only).

- [ ] **Step 5: Commit**

```bash
git add alpha/refine/forge.py tests/refine/test_forge_apply.py
git commit -m "feat(forge): forge_skills gated applier (double-gate + teaching-owned held) + ForgeReport"
```

---

### Task 3: `scripts/evolve_from_episodes.py` (the standalone runner)

**Files:**
- Create: `scripts/evolve_from_episodes.py`
- Test: `tests/scripts/test_evolve_from_episodes.py`

**Interfaces:**
- Consumes: `forge_skills` (T2), `LiveBrainStore` (`.lock()/.load()/.save()`), `EpisodeStore.open`, `ConflictQueue`, `MetaTools`.
- Produces: `run_evolve_from_episodes(*, brain_dir, conflicts_dir, episodes_db, asof, **kwargs) -> dict` (`{"applied","held","rejected"}`) + `main()` CLI. Mirrors `scripts/refine_live.py`.

- [ ] **Step 1: Write the failing test**

```python
# tests/scripts/test_evolve_from_episodes.py
from datetime import date
import importlib
from alpha.harness.doctrine import Doctrine
from alpha.harness.skill import Skill, SkillStats
from alpha.harness.registry import SkillRegistry, MemoryStore
from alpha.harness.state import HarnessState
from alpha.harness.edit_log import EditLog
from alpha.memory.episodes import Episode
from alpha.memory.store import EpisodeStore
from alpha.meta.store import LiveBrainStore

def _seed_brain(brain_dir):
    h = HarnessState(doctrine=Doctrine(),
                     skills=SkillRegistry.from_skills([Skill(skill_id="s1", name="s1", type="pattern",
                            family="runner", phases=["trend"], status="incubating",
                            stats=SkillStats(n=5, expectancy=1.0))]),
                     memory=MemoryStore.from_lessons([]))
    LiveBrainStore(str(brain_dir)).save(h, EditLog())

def _seed_episodes(db_path):
    s = EpisodeStore.open(str(db_path))
    for i in range(5):
        s.add(Episode(episode_id=f"s1:{i}", symbol="RUN", skill_id="s1", entry_date=date(2026, 6, 1),
                      exit_date=date(2026, 6, 3), outcome="continued", advantage=2.0))
    s.close()

def test_run_evolve_promotes_in_saved_brain(tmp_path):
    brain_dir = tmp_path / "brain"; db = tmp_path / "brain.db"; conflicts = tmp_path / "conflicts"
    _seed_brain(brain_dir); _seed_episodes(db)
    mod = importlib.import_module("scripts.evolve_from_episodes")
    out = mod.run_evolve_from_episodes(brain_dir=str(brain_dir), conflicts_dir=str(conflicts),
                                       episodes_db=str(db), asof=date(2026, 6, 20))
    assert out["applied"] == ["s1"]
    h, _ = LiveBrainStore(str(brain_dir)).load()
    assert h.skills.get("s1").status == "active"                    # promotion persisted to the live brain
```

> **Implementer note:** read `scripts/refine_live.py` and mirror `run_refine_live`'s shape exactly — `bstore = LiveBrainStore(brain_dir)`, `with bstore.lock(): h, log = bstore.load(); report = forge_skills(h, EpisodeStore.open(episodes_db), MetaTools(h, log), asof=asof, conflict_queue=ConflictQueue(conflicts_dir)); bstore.save(h, log)`. `main()` mirrors refine_live's argparse (`--asof` defaulting to `date.today()`; env `ALPHA_LIVE_BRAIN_DIR`/`ALPHA_CONFLICTS_DIR`/`ALPHA_EPISODES_DB` default `./state/brain`/`./state/conflicts`/`./state/brain.db`). Create `tests/scripts/__init__.py` only if the existing `tests/scripts/` package needs it (it already exists from refine_live).

- [ ] **Step 2: Run to verify it fails**

Run: `python -m pytest tests/scripts/test_evolve_from_episodes.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'scripts.evolve_from_episodes'`.

- [ ] **Step 3: Implement** `scripts/evolve_from_episodes.py` per the interface + the note (mirror `refine_live.py`: imports, `run_evolve_from_episodes` under `bstore.lock()`, `main()` argparse + env). Return `{"applied": report.applied, "held": report.held, "rejected": report.rejected}`. `main()` prints e.g. `f"{len(out['applied'])} promoted/retired · {len(out['held'])} held · {len(out['rejected'])} rejected"`.

- [ ] **Step 4: Run to verify it passes + full suite green**

Run: `python -m pytest tests/scripts/test_evolve_from_episodes.py -v && python -m pytest -q`
Expected: PASS; full suite green.

- [ ] **Step 5: Commit**

```bash
git add scripts/evolve_from_episodes.py tests/scripts/test_evolve_from_episodes.py
git commit -m "feat(scripts): evolve_from_episodes — the forge runner (lock->load->forge->save), LLM-free"
```

---

### Task 4: close the write→read loop in `refine_live`

**Files:**
- Modify: `scripts/refine_live.py`
- Test: `tests/scripts/test_refine_live_episodes.py`

**Interfaces:**
- Consumes: `EpisodeStore.open`, `InnerLoop(..., episode_store=…)` (already accepts it).
- Produces: `run_refine_live(..., episodes_db=None)` — when given, opens `EpisodeStore.open(episodes_db)` and passes `episode_store=` into the `InnerLoop` so episodes are written. `None` → no episode store (existing behavior).

- [ ] **Step 1: Write the failing test**

```python
# tests/scripts/test_refine_live_episodes.py
# reuse the offline fixtures from the existing refine_live e2e test
import importlib
from alpha.memory.store import EpisodeStore

def test_refine_live_writes_episodes_when_db_given(tmp_path, monkeypatch):
    rl = importlib.import_module("scripts.refine_live")
    # build the SAME offline setup the existing e2e uses (seed brain dir + FakeSource + Mock LLM factories +
    # agent_factory=_PickRun + a window that scores >= a few candidates so episodes are written at apply_credit)
    # — import/replicate from tests/scripts/test_refine_live.py.
    db = tmp_path / "brain.db"
    <... build brain_dir, conflicts_dir, source, factories, loop_config exactly as tests/scripts/test_refine_live.py ...>
    rl.run_refine_live(<source>, <start>, <end>, brain_dir=str(<brain_dir>), conflicts_dir=str(<conflicts>),
                       agent_factory=<_PickRun factory>, agent_llm_factory=<...>, refiner_llm_factory=<...>,
                       loop_config=<...>, episodes_db=str(db))
    s = EpisodeStore.open(str(db))
    assert len(s.all()) > 0                                         # episodes were written to brain.db
```

> **Implementer note:** READ `tests/scripts/test_refine_live.py` and reuse its exact seed/source/factory/loop_config (the working window that produces scored steps → episodes at `apply_credit`). The ONLY new assertion is that, with `episodes_db` set, `EpisodeStore.open(db).all()` is non-empty after the run. Also add a negative: with `episodes_db=None`, the run still works (no db created / no error) — the existing refine_live e2e already covers the `None` path, so a 1-liner that `run_refine_live(..., episodes_db=None)` still returns a report suffices.

- [ ] **Step 2: Run to verify it fails**

Run: `python -m pytest tests/scripts/test_refine_live_episodes.py -v`
Expected: FAIL — `run_refine_live() got an unexpected keyword argument 'episodes_db'`.

- [ ] **Step 3: Implement** — `scripts/refine_live.py`:
- Add `episodes_db: str | None = None` to `run_refine_live`'s keyword params.
- Import `EpisodeStore` (`from alpha.memory.store import EpisodeStore`).
- Inside the `with bstore.lock():` block, before constructing the `InnerLoop`, open the store: `episode_store = EpisodeStore.open(episodes_db) if episodes_db else None`; add `episode_store=episode_store` to the `InnerLoop(...)` constructor (next to `conflict_queue=cq`). (The InnerLoop already threads `episode_store` to `apply_credit`.)
- In `main()`, read `ALPHA_EPISODES_DB` (default `./state/brain.db`) and pass `episodes_db=` (so the live refine_live run writes episodes; keep a `--no-episodes` escape or just default to the env). Match the existing `main()` structure.

- [ ] **Step 4: Run to verify it passes + full suite green**

Run: `python -m pytest tests/scripts/test_refine_live_episodes.py -v && python -m pytest -q`
Expected: PASS; full suite green (the existing refine_live e2e — which passes no `episodes_db` — is unchanged).

- [ ] **Step 5: Commit**

```bash
git add scripts/refine_live.py tests/scripts/test_refine_live_episodes.py
git commit -m "feat(scripts): refine_live writes episodes to ALPHA_EPISODES_DB (close the forge write->read loop)"
```

---

## Self-Review

**Spec coverage:**
- `propose_skill_ops` (promote incubating / soft-retire active, thresholds, PIT, status-gated) → Task 1. ✓
- `forge_skills` double-gate (episode trigger + skill-stats floor) + teaching-owned held + `ForgeReport` → Task 2. ✓
- `scripts/evolve_from_episodes.py` runner (lock→load→forge→save, LLM-free) → Task 3. ✓
- Close the write→read loop (refine_live writes episodes) → Task 4. ✓
- Soft demote (`permanent=False` → dormant) → Task 1 (op) + Task 2 (applied). ✓
- Provenance forge/self_study; conflict_queue → Task 2. ✓
- Additive (669 green; refine_live `episodes_db=None` default) → Tasks 2/3/4. ✓
- Out of scope (lesson demote, patch-on-promote, UI trigger, phase-scoped) → not built. ✓

**Placeholder scan:** Tasks 1, 2 are fully exact-code. Task 3's runner is "mirror refine_live" with the exact `with bstore.lock(): … forge_skills(…) … save` body spelled out in the note. Task 4's test uses `<…>` tokens explicitly resolved to "reuse the exact fixtures in `tests/scripts/test_refine_live.py`" — a named-fixture reuse instruction (the working window that produces episodes), not a vague placeholder; the production code is exact.

**Type consistency:** `propose_skill_ops(harness, episode_store, *, asof, …) -> list[RefineOp]` (T1) is called by `forge_skills` (T2), which `run_evolve_from_episodes` (T3) calls with `MetaTools(h, log)` + `ConflictQueue`. `ForgeReport(applied/held/rejected)` (T2) is unpacked into the runner's dict (T3). `try_apply_op(allowed=_FORGE_ALLOWED, min_promote_samples, min_retire_samples, provenance, conflict_queue) -> (rec, reason)` distinguishes applied (`rec`), held (`reason.startswith("held_for_review")`), rejected. `EpisodeStore.open(episodes_db)` is used by both the runner (T3) and refine_live (T4); `InnerLoop(..., episode_store=…)` is the existing param. `retire_skill` op carries `permanent=False` (T1) → `MetaTools.retire_skill(permanent=False)` → dormant.
