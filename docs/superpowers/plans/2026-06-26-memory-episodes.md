# Memory §6 — Episodic Layer (Episode + EpisodeStore over brain.db) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the episodic layer of the "Stratum-with-edges" memory (spec §6.2–6.3, §6.9): a typed `Episode` (one row per scored pick) and an `EpisodeStore` over a NEW `brain.db` (SQLite + FTS5), written at the existing `apply_credit` seam. Episodes are observation-channel facts (like the in-place `SkillStats` update) — NOT gated H edits, NOT in `harness.to_dict()` — with `learned_asof = the realized exit date` (PIT-correct, mirroring the lesson PIT mask already shipped).

**Architecture:** New, self-contained `alpha/memory/` package (`episodes.py`, `store.py`). The only edits to existing code are additive: an optional `exit_date` field on `TrajectoryStep` (set at the InnerLoop maturity seam where `cursor` = the realized exit date), an optional `episode_store` kwarg on `apply_credit` (writes episodes after the SkillStats loop, ungated), and an optional `episode_store` on `LoopConfig`/`InnerLoop` (default-OFF). The day-agent, `try_apply_op`, `SnapshotStore`, and `harness.to_dict()` are untouched. Episodes are **never written in the verdict/`compare_harnesses` path** (verdict-neutral) — only when a `brain.db` is explicitly configured.

**Tech Stack:** Python ≥3.11, stdlib `sqlite3` (FTS5 is in the stdlib build), pydantic v2, pytest. Reuses `alpha.refine.credit.{apply_credit, resolve_skill}`, `alpha.eval.trajectory.{Trajectory, TrajectoryStep}`, `alpha.eval.metrics.ScoredCandidate`, `alpha.refine.signatures.extract_signatures`, `alpha.harness.regime.normalize_phase`.

## Global Constraints

- **Python `>=3.11`**, pydantic v2, stdlib `sqlite3`. **No new third-party dependency.** Tests use an **in-memory** `EpisodeStore` (`:memory:`) — never touch disk.
- **Additive / verdict-neutral:** episodes are written ONLY when an `episode_store` is explicitly passed. `apply_credit(traj, h)` with no store behaves byte-identically to today (the existing suite, currently **584 passed**, must stay green). Episodes MUST NOT be written in the `compare_harnesses`/verdict path.
- **Observation-channel:** episodes are NOT gated edits — they never go through `try_apply_op`, never enter `harness.to_dict()`, never participate in atomic H-rollback. (A breaker-rollback `mark_superseded` *mechanism* ships here; its call-site is deferred to the §6.6 plan.)
- **PIT key:** `Episode.learned_asof = exit_date` (the date the outcome became knowable = the realized scoring exit). The store's recall query masks `learned_asof <= :asof`, mirroring `alpha/agent/retrieval.py`'s lesson mask.
- **Shared conventions (from the roadmap):** SQLite file path via `ALPHA_BRAIN_DB`; `EpisodeStore.open(path, create_if_missing=True)` + `EpisodeStore.in_memory()`. `episode_id = f"{exit_date}:{symbol}:{skill_id}"` with `INSERT OR IGNORE`.
- English; follow existing patterns.

## File Structure

- Create: `alpha/memory/__init__.py`, `alpha/memory/episodes.py` (`Episode` + `episodes_from_step`), `alpha/memory/store.py` (`EpisodeStore`).
- Modify: `alpha/eval/trajectory.py` (`TrajectoryStep.exit_date`), `alpha/refine/credit.py` (`apply_credit` optional `episode_store`), `alpha/loop/inner_loop.py` (`LoopConfig`/`InnerLoop` optional `episode_store` + set `exit_date` at maturity).
- Create tests: `tests/memory/test_episode_model.py`, `test_episode_store.py`, `test_episodes_from_step.py`, `tests/refine/test_credit_episodes.py`, `tests/loop/test_inner_loop_episodes.py`.

---

### Task 1: `Episode` model + `TrajectoryStep.exit_date`

**Files:**
- Create: `alpha/memory/__init__.py` (empty), `alpha/memory/episodes.py`
- Modify: `alpha/eval/trajectory.py`
- Test: `tests/memory/test_episode_model.py`

**Interfaces:**
- Produces: `Episode` (frozen pydantic) with the fields below; `TrajectoryStep.exit_date: date | None = None` (additive). Consumed by Tasks 2–5.

- [ ] **Step 1: Write the failing test**

```python
# tests/memory/test_episode_model.py
from datetime import date
from alpha.memory.episodes import Episode

def test_episode_constructs_and_round_trips():
    e = Episode(episode_id="2026-06-12:RUN:gap_and_go", symbol="RUN", skill_id="gap_and_go",
                family="runner", phase="trend", narrative="ai-compute",
                entry_date=date(2026, 6, 10), exit_date=date(2026, 6, 12),
                outcome="continued", advantage=0.4, score=0.5, failure_kind="",
                reflection_text="RUN held the breakout")
    assert e.learned_asof == date(2026, 6, 12)            # learned_asof defaults to exit_date
    assert Episode.model_validate_json(e.model_dump_json()) == e

def test_learned_asof_can_be_overridden_but_defaults_to_exit_date():
    e = Episode(episode_id="x", symbol="X", skill_id="s", entry_date=date(2026, 6, 1),
                exit_date=date(2026, 6, 3), outcome="faded", advantage=0.0, score=0.0)
    assert e.learned_asof == date(2026, 6, 3)
```

- [ ] **Step 2: Run to verify it fails**

Run: `python -m pytest tests/memory/test_episode_model.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'alpha.memory'`.

- [ ] **Step 3: Implement**

`alpha/memory/__init__.py` — empty file.

```python
# alpha/memory/episodes.py
from __future__ import annotations
from datetime import date as Date
from pydantic import BaseModel, ConfigDict, Field, model_validator

class Episode(BaseModel):
    """One scored pick (observation-channel; NOT a gated H edit). learned_asof = exit_date (the date the
    outcome became knowable), the PIT key recall masks on."""
    model_config = ConfigDict(frozen=True)
    episode_id: str
    symbol: str
    skill_id: str
    family: str | None = None
    phase: str = ""
    narrative: str = ""
    entry_date: Date
    exit_date: Date
    outcome: str                       # "continued" | "faded" | "nuked" (the oracle's labels)
    advantage: float = 0.0
    score: float = 0.0
    failure_kind: str = ""
    reflection_text: str = ""
    learned_asof: Date | None = None   # defaults to exit_date (set below)

    @model_validator(mode="after")
    def _default_learned_asof(self) -> "Episode":
        if self.learned_asof is None:
            object.__setattr__(self, "learned_asof", self.exit_date)   # frozen model
        return self
```

Modify `alpha/eval/trajectory.py` — add an optional field to `TrajectoryStep` (after `scored: bool = False`):
```python
    exit_date: Date | None = None      # realized scoring exit (set at the InnerLoop maturity seam); PIT key for episodes
```

- [ ] **Step 4: Run to verify it passes**

Run: `python -m pytest tests/memory/test_episode_model.py -v`
Expected: 2 PASS.

- [ ] **Step 5: Run the trajectory tests (additive field is safe)**

Run: `python -m pytest tests/eval -q`
Expected: green (the new `exit_date` defaults `None`; existing `TrajectoryStep(**drafts)` constructions are unaffected).

- [ ] **Step 6: Commit**

```bash
git add alpha/memory/__init__.py alpha/memory/episodes.py alpha/eval/trajectory.py tests/memory/test_episode_model.py
git commit -m "feat(memory): Episode model + TrajectoryStep.exit_date (PIT key)"
```

---

### Task 2: `EpisodeStore` over `brain.db` (SQLite + FTS5)

**Files:**
- Create: `alpha/memory/store.py`
- Test: `tests/memory/test_episode_store.py`

**Interfaces:**
- Consumes: `Episode` (Task 1).
- Produces: `EpisodeStore` with `EpisodeStore.in_memory() -> EpisodeStore`, `EpisodeStore.open(path: str, *, create_if_missing: bool = True) -> EpisodeStore`, `.add(ep: Episode) -> None` (INSERT OR IGNORE), `.all() -> list[Episode]`, `.close()`. The schema: an `episodes` table (PK `episode_id`, indexed on `learned_asof`) + an FTS5 virtual table `episodes_fts(reflection_text, narrative)`. Consumed by Tasks 3, 5.

- [ ] **Step 1: Write the failing test**

```python
# tests/memory/test_episode_store.py
from datetime import date
from alpha.memory.episodes import Episode
from alpha.memory.store import EpisodeStore

def _ep(eid, exit_d, sym="RUN", text="held the breakout"):
    return Episode(episode_id=eid, symbol=sym, skill_id="gap_and_go", entry_date=date(2026, 6, 1),
                   exit_date=exit_d, outcome="continued", advantage=0.3, score=0.4,
                   reflection_text=text, narrative="ai-compute")

def test_add_and_all_round_trip():
    s = EpisodeStore.in_memory()
    s.add(_ep("a", date(2026, 6, 3)))
    s.add(_ep("b", date(2026, 6, 5)))
    got = s.all()
    assert {e.episode_id for e in got} == {"a", "b"}
    assert got[0] == _ep("a", date(2026, 6, 3)) or got[1] == _ep("a", date(2026, 6, 3))

def test_insert_or_ignore_dedups_by_id():
    s = EpisodeStore.in_memory()
    s.add(_ep("a", date(2026, 6, 3), text="first"))
    s.add(_ep("a", date(2026, 6, 3), text="second"))   # same id -> ignored
    assert len(s.all()) == 1 and s.all()[0].reflection_text == "first"
```

- [ ] **Step 2: Run to verify it fails**

Run: `python -m pytest tests/memory/test_episode_store.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'alpha.memory.store'`.

- [ ] **Step 3: Implement**

```python
# alpha/memory/store.py
from __future__ import annotations
import sqlite3
from datetime import date as Date
from alpha.memory.episodes import Episode

_COLS = ("episode_id", "symbol", "skill_id", "family", "phase", "narrative",
         "entry_date", "exit_date", "outcome", "advantage", "score",
         "failure_kind", "reflection_text", "learned_asof", "superseded")

_SCHEMA = """
CREATE TABLE IF NOT EXISTS episodes (
  episode_id TEXT PRIMARY KEY, symbol TEXT, skill_id TEXT, family TEXT, phase TEXT, narrative TEXT,
  entry_date TEXT, exit_date TEXT, outcome TEXT, advantage REAL, score REAL,
  failure_kind TEXT, reflection_text TEXT, learned_asof TEXT NOT NULL, superseded INTEGER DEFAULT 0);
CREATE INDEX IF NOT EXISTS ix_episodes_learned_asof ON episodes(learned_asof);
CREATE VIRTUAL TABLE IF NOT EXISTS episodes_fts USING fts5(reflection_text, narrative, content='');
"""

def _row_to_episode(r: sqlite3.Row) -> Episode:
    return Episode(episode_id=r["episode_id"], symbol=r["symbol"], skill_id=r["skill_id"],
                   family=r["family"], phase=r["phase"] or "", narrative=r["narrative"] or "",
                   entry_date=Date.fromisoformat(r["entry_date"]), exit_date=Date.fromisoformat(r["exit_date"]),
                   outcome=r["outcome"], advantage=r["advantage"], score=r["score"],
                   failure_kind=r["failure_kind"] or "", reflection_text=r["reflection_text"] or "",
                   learned_asof=Date.fromisoformat(r["learned_asof"]))

class EpisodeStore:
    """SQLite (+FTS5) store of observation-channel episodes. Brain.db lives outside the JSON H snapshot."""
    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn
        self._conn.row_factory = sqlite3.Row
        self._conn.executescript(_SCHEMA)
        self._conn.commit()

    @classmethod
    def in_memory(cls) -> "EpisodeStore":
        return cls(sqlite3.connect(":memory:"))

    @classmethod
    def open(cls, path: str, *, create_if_missing: bool = True) -> "EpisodeStore":
        import os
        if not create_if_missing and not os.path.exists(path):
            raise FileNotFoundError(path)
        return cls(sqlite3.connect(path))

    def add(self, ep: Episode) -> None:
        d = ep.model_dump()
        d["superseded"] = 0
        for k in ("entry_date", "exit_date", "learned_asof"):
            d[k] = d[k].isoformat()
        cur = self._conn.execute(
            f"INSERT OR IGNORE INTO episodes ({','.join(_COLS)}) VALUES ({','.join('?' for _ in _COLS)})",
            tuple(d[c] for c in _COLS))
        if cur.rowcount:                                  # only index FTS for genuinely-new rows
            self._conn.execute("INSERT INTO episodes_fts (rowid, reflection_text, narrative) "
                               "SELECT rowid, reflection_text, narrative FROM episodes WHERE episode_id=?",
                               (ep.episode_id,))
        self._conn.commit()

    def all(self) -> list[Episode]:
        return [_row_to_episode(r) for r in self._conn.execute("SELECT * FROM episodes")]

    def close(self) -> None:
        self._conn.close()
```

- [ ] **Step 4: Run to verify it passes**

Run: `python -m pytest tests/memory/test_episode_store.py -v`
Expected: 2 PASS.

- [ ] **Step 5: Commit**

```bash
git add alpha/memory/store.py tests/memory/test_episode_store.py
git commit -m "feat(memory): EpisodeStore over brain.db (SQLite + FTS5)"
```

---

### Task 3: PIT-masked recall query on `EpisodeStore`

**Files:**
- Modify: `alpha/memory/store.py`
- Test: `tests/memory/test_episode_store_query.py`

**Interfaces:**
- Produces: `EpisodeStore.for_asof(asof: date, *, phase: str | None = None, narrative: str | None = None, limit: int = 50) -> list[Episode]` — returns non-superseded episodes with `learned_asof <= asof` (the PIT mask), optionally filtered by phase/narrative, newest exit first. Consumed by the future §6.5 recall plan.

- [ ] **Step 1: Write the failing test**

```python
# tests/memory/test_episode_store_query.py
from datetime import date
from alpha.memory.episodes import Episode
from alpha.memory.store import EpisodeStore

def _ep(eid, exit_d, phase="trend", narr="ai-compute"):
    return Episode(episode_id=eid, symbol="RUN", skill_id="s", entry_date=date(2026, 6, 1),
                   exit_date=exit_d, outcome="continued", advantage=0.1, score=0.1,
                   phase=phase, narrative=narr, reflection_text="t")

def test_for_asof_masks_future_episodes():
    s = EpisodeStore.in_memory()
    s.add(_ep("early", date(2026, 6, 3)))
    s.add(_ep("future", date(2026, 6, 12)))
    ids = {e.episode_id for e in s.for_asof(date(2026, 6, 5))}
    assert ids == {"early"}                               # the 06-12 episode is invisible at 06-05
    assert {e.episode_id for e in s.for_asof(date(2026, 6, 12))} == {"early", "future"}

def test_for_asof_filters_phase_and_narrative():
    s = EpisodeStore.in_memory()
    s.add(_ep("a", date(2026, 6, 3), phase="trend", narr="ai-compute"))
    s.add(_ep("b", date(2026, 6, 3), phase="chop", narr="biotech"))
    assert {e.episode_id for e in s.for_asof(date(2026, 6, 9), phase="trend")} == {"a"}
    assert {e.episode_id for e in s.for_asof(date(2026, 6, 9), narrative="biotech")} == {"b"}
```

- [ ] **Step 2: Run to verify it fails**

Run: `python -m pytest tests/memory/test_episode_store_query.py -v`
Expected: FAIL — `AttributeError: 'EpisodeStore' object has no attribute 'for_asof'`.

- [ ] **Step 3: Implement** — add to `EpisodeStore`:

```python
    def for_asof(self, asof, *, phase: str | None = None, narrative: str | None = None,
                 limit: int = 50) -> list[Episode]:
        """PIT-safe recall: non-superseded episodes knowable by `asof` (learned_asof <= asof), newest first."""
        clauses = ["superseded = 0", "learned_asof <= ?"]
        params: list = [asof.isoformat()]
        if phase is not None:
            clauses.append("phase = ?"); params.append(phase)
        if narrative is not None:
            clauses.append("narrative = ?"); params.append(narrative)
        params.append(limit)
        sql = f"SELECT * FROM episodes WHERE {' AND '.join(clauses)} ORDER BY exit_date DESC LIMIT ?"
        return [_row_to_episode(r) for r in self._conn.execute(sql, params)]

    def mark_superseded(self, *, after) -> int:
        """Mechanism for a breaker rollback (call-site deferred to §6.6): mark episodes learned after a
        checkpoint date as superseded so recall skips them. Returns the number marked."""
        cur = self._conn.execute("UPDATE episodes SET superseded = 1 WHERE learned_asof > ?", (after.isoformat(),))
        self._conn.commit()
        return cur.rowcount
```

- [ ] **Step 4: Run to verify it passes**

Run: `python -m pytest tests/memory/test_episode_store_query.py -v`
Expected: 2 PASS.

- [ ] **Step 5: Commit**

```bash
git add alpha/memory/store.py tests/memory/test_episode_store_query.py
git commit -m "feat(memory): PIT-masked recall query (for_asof) + mark_superseded mechanism"
```

---

### Task 4: `episodes_from_step` builder

**Files:**
- Modify: `alpha/memory/episodes.py`
- Test: `tests/memory/test_episodes_from_step.py`

**Interfaces:**
- Consumes: `TrajectoryStep` (Task 1), `alpha.refine.credit.resolve_skill`, `alpha.refine.signatures.extract_signatures`.
- Produces: `episodes_from_step(step: TrajectoryStep, h: HarnessState) -> list[Episode]` — one `Episode` per scored pick in `step.outcomes`, using `step.exit_date` for `exit_date`/`learned_asof`. Returns `[]` if `step.exit_date is None` or `step` not scored. Consumed by Task 5.

- [ ] **Step 1: Write the failing test**

```python
# tests/memory/test_episodes_from_step.py
from datetime import date, datetime
from alpha.harness.skill import Skill
from alpha.harness.doctrine import Doctrine
from alpha.harness.registry import SkillRegistry, MemoryStore
from alpha.harness.state import HarnessState
from alpha.eval.decision import DecisionPackage, Candidate
from alpha.eval.metrics import ScoredCandidate
from alpha.eval.trajectory import TrajectoryStep
from alpha.state.market import MarketState
from alpha.memory.episodes import episodes_from_step

def _h():
    return HarnessState(doctrine=Doctrine(),
                        skills=SkillRegistry.from_skills([Skill(skill_id="gap_and_go", name="Gap and Go",
                            type="pattern", family="runner", phases=["trend"], status="active")]),
                        memory=MemoryStore.from_lessons([]))

def _state():
    return MarketState(date=date(2026, 6, 10), gainer_count=1, gap_up_count=0, loser_count=0,
                       failed_breakout_count=0, max_runner_tier=1, echelon=[], breadth_raw=1.0,
                       sentiment_norm=0.6, as_of=datetime(2026, 6, 10, 16, 0))

def _step(exit_date):
    decision = DecisionPackage(date=date(2026, 6, 10), regime_read="trend frontside",
                               candidates=[Candidate(symbol="RUN", pattern="gap_and_go",
                                                     confidence=0.7, narrative="ai-compute")])
    outcomes = {"RUN": ScoredCandidate(symbol="RUN", pattern="gap_and_go", outcome="continued",
                                       advantage=0.4, score=0.5)}
    return TrajectoryStep(date=date(2026, 6, 10), market=_state(), decision=decision,
                          outcomes=outcomes, scored=True, exit_date=exit_date)

def test_builds_one_episode_per_scored_pick():
    eps = episodes_from_step(_step(date(2026, 6, 12)), _h())
    assert len(eps) == 1
    e = eps[0]
    assert e.symbol == "RUN" and e.skill_id == "gap_and_go" and e.narrative == "ai-compute"
    assert e.exit_date == date(2026, 6, 12) and e.learned_asof == date(2026, 6, 12)
    assert e.entry_date == date(2026, 6, 10) and e.outcome == "continued" and e.advantage == 0.4
    assert e.episode_id == "2026-06-12:RUN:gap_and_go"

def test_no_exit_date_yields_no_episodes():
    assert episodes_from_step(_step(None), _h()) == []
```

> **Implementer note:** confirm the exact constructor signatures of `Candidate` (`alpha/eval/decision.py`) and `ScoredCandidate` (`alpha/eval/metrics.py`) by reading those files — the test above uses the fields the codebase exposes (`symbol`/`pattern`/`confidence`/`narrative` on `Candidate`; `symbol`/`pattern`/`outcome`/`advantage`/`score` on `ScoredCandidate`). If a field name differs, match the real model (do not change the models).

- [ ] **Step 2: Run to verify it fails**

Run: `python -m pytest tests/memory/test_episodes_from_step.py -v`
Expected: FAIL — `ImportError: cannot import name 'episodes_from_step'`.

- [ ] **Step 3: Implement** — add to `alpha/memory/episodes.py`:

```python
def episodes_from_step(step, h) -> list["Episode"]:
    """Build one Episode per scored pick in a matured TrajectoryStep. Uses step.exit_date as the PIT key.
    [] if the step is unscored or has no exit_date (the last `horizon` steps never mature)."""
    from alpha.refine.credit import resolve_skill
    from alpha.refine.signatures import extract_signatures   # local import: avoid a heavy import at module load
    if not step.scored or step.exit_date is None:
        return []
    narratives = {c.symbol: getattr(c, "narrative", "") for c in step.decision.candidates}
    phase = getattr(step.decision, "regime_read", "") or ""
    out: list[Episode] = []
    for symbol, sc in step.outcomes.items():
        skill = resolve_skill(getattr(sc, "pattern", ""), h)
        skill_id = skill.skill_id if skill is not None else (getattr(sc, "pattern", "") or "__unattributed__")
        family = skill.family if skill is not None else None
        out.append(Episode(
            episode_id=f"{step.exit_date.isoformat()}:{symbol}:{skill_id}",
            symbol=symbol, skill_id=skill_id, family=family, phase=phase,
            narrative=narratives.get(symbol, "") or "",
            entry_date=step.date, exit_date=step.exit_date,
            outcome=getattr(sc, "outcome", ""), advantage=getattr(sc, "advantage", 0.0),
            score=getattr(sc, "score", 0.0),
            failure_kind=getattr(sc, "failure_signature", "") or "",
            reflection_text=getattr(sc, "reflection", "") or "",
        ))
    return out
```

> Note: `phase` is taken from the decision's `regime_read` (a per-day phase read). `extract_signatures` is imported but the per-pick `failure_kind` is read from the `ScoredCandidate` if present; if `ScoredCandidate` has no `failure_signature`/`reflection` field, those `getattr` defaults yield `""` — confirm by reading `alpha/eval/metrics.py` and use the real field if one exists (do not invent one).

- [ ] **Step 4: Run to verify it passes**

Run: `python -m pytest tests/memory/test_episodes_from_step.py -v`
Expected: 2 PASS.

- [ ] **Step 5: Commit**

```bash
git add alpha/memory/episodes.py tests/memory/test_episodes_from_step.py
git commit -m "feat(memory): episodes_from_step builder (scored TrajectoryStep -> Episodes)"
```

---

### Task 5: Write episodes at `apply_credit` (optional, additive, ungated)

**Files:**
- Modify: `alpha/refine/credit.py`
- Test: `tests/refine/test_credit_episodes.py`

**Interfaces:**
- Consumes: `episodes_from_step` (Task 4), `EpisodeStore` (Task 2).
- Produces: `apply_credit(traj, h, decay=0.1, *, episode_store=None)` — when `episode_store` is not None, after the SkillStats loop it writes `episodes_from_step(step, h)` for each scored step. When `episode_store is None`, behavior is byte-identical to today.

- [ ] **Step 1: Write the failing test**

```python
# tests/refine/test_credit_episodes.py
from datetime import date, datetime
from alpha.harness.skill import Skill
from alpha.harness.doctrine import Doctrine
from alpha.harness.registry import SkillRegistry, MemoryStore
from alpha.harness.state import HarnessState
from alpha.eval.decision import DecisionPackage, Candidate
from alpha.eval.metrics import ScoredCandidate
from alpha.eval.trajectory import Trajectory, TrajectoryStep
from alpha.state.market import MarketState
from alpha.refine.credit import apply_credit
from alpha.memory.store import EpisodeStore

def _h():
    return HarnessState(doctrine=Doctrine(),
                        skills=SkillRegistry.from_skills([Skill(skill_id="gap_and_go", name="Gap and Go",
                            type="pattern", family="runner", phases=["trend"], status="active")]),
                        memory=MemoryStore.from_lessons([]))

def _traj(exit_date):
    st = MarketState(date=date(2026, 6, 10), gainer_count=1, gap_up_count=0, loser_count=0,
                     failed_breakout_count=0, max_runner_tier=1, echelon=[], breadth_raw=1.0,
                     sentiment_norm=0.6, as_of=datetime(2026, 6, 10, 16, 0))
    dec = DecisionPackage(date=date(2026, 6, 10), regime_read="trend frontside",
                          candidates=[Candidate(symbol="RUN", pattern="gap_and_go", confidence=0.7)])
    step = TrajectoryStep(date=date(2026, 6, 10), market=st, decision=dec,
                          outcomes={"RUN": ScoredCandidate(symbol="RUN", pattern="gap_and_go",
                                                           outcome="continued", advantage=0.4, score=0.5)},
                          scored=True, exit_date=exit_date)
    return Trajectory(steps=[step])

def test_episodes_written_when_store_given():
    s = EpisodeStore.in_memory()
    apply_credit(_traj(date(2026, 6, 12)), _h(), episode_store=s)
    eps = s.all()
    assert len(eps) == 1 and eps[0].symbol == "RUN" and eps[0].exit_date == date(2026, 6, 12)

def test_no_store_is_byte_identical_no_episodes():
    # the default path writes nothing and returns the same CreditReport shape as today
    rep = apply_credit(_traj(date(2026, 6, 12)), _h())     # no episode_store
    assert rep.n_scored == 1                                # credit still computed; no store touched
```

- [ ] **Step 2: Run to verify it fails**

Run: `python -m pytest tests/refine/test_credit_episodes.py -v`
Expected: FAIL — `apply_credit() got an unexpected keyword argument 'episode_store'`.

- [ ] **Step 3: Implement** — edit `alpha/refine/credit.py`:

Change the `apply_credit` signature:
```python
def apply_credit(traj: Trajectory, h: HarnessState, decay: float = 0.1, *, episode_store=None) -> CreditReport:
```
At the END of the `for step in traj.scored_steps():` loop body — i.e. right before the loop's next iteration, after the `for sc in step.outcomes.values():` inner loop closes — add the episode write (a clearly-delimited block so the future §6.6 auto-adjust merge is mechanical):
```python
        if episode_store is not None:                       # observation-channel episode write (§6.3); ungated
            from alpha.memory.episodes import episodes_from_step
            for ep in episodes_from_step(step, h):
                episode_store.add(ep)
```

- [ ] **Step 4: Run to verify it passes + full suite green**

Run: `python -m pytest tests/refine/test_credit_episodes.py -v && python -m pytest -q`
Expected: the new tests PASS; the full suite stays green (the `episode_store=None` default leaves every existing `apply_credit` caller byte-identical).

- [ ] **Step 5: Commit**

```bash
git add alpha/refine/credit.py tests/refine/test_credit_episodes.py
git commit -m "feat(memory): apply_credit optionally writes episodes (ungated, default-off)"
```

---

### Task 6: Wire `episode_store` into `InnerLoop` (default-off) + set `exit_date` at maturity

**Files:**
- Modify: `alpha/loop/inner_loop.py`
- Test: `tests/loop/test_inner_loop_episodes.py`

**Interfaces:**
- Consumes: `apply_credit(episode_store=…)` (Task 5); `EpisodeStore`.
- Produces: `InnerLoop(..., episode_store=None)` (constructor kwarg, default-off) — when set, (a) the maturity seam stamps `exit_date=cursor` on each newly-scored step, and (b) the per-step `apply_credit` call passes `episode_store`. The verdict/`compare_harnesses` path never sets it → verdict-neutral.

- [ ] **Step 1: Write the failing test**

```python
# tests/loop/test_inner_loop_episodes.py
# Mirror an existing InnerLoop acceptance test's setup (see tests/refine/test_us2b_acceptance.py or
# tests/loop/*) to build a short FakeSource walk with a MockLLM. Drive InnerLoop with episode_store set
# and assert episodes were written with exit_date == the realized maturity date (cursor), not decision date.
from alpha.memory.store import EpisodeStore
# ... build mgr/source/start/end/agent_llm/refiner_llm exactly as the nearest existing InnerLoop test ...

def test_inner_loop_writes_episodes_with_realized_exit_date():
    store = EpisodeStore.in_memory()
    loop = InnerLoop(mgr, source, start, end, agent_llm, refiner_llm, config=LoopConfig(enable_refine=False),
                     episode_store=store)
    loop.run()
    eps = store.all()
    assert eps, "expected episodes for the scored steps"
    # exit_date is the maturity cursor (decision_date + horizon trading days), strictly after entry_date
    assert all(e.exit_date > e.entry_date for e in eps)
    assert all(e.learned_asof == e.exit_date for e in eps)
```

> **Implementer note:** copy the `mgr/source/start/end/agent_llm/refiner_llm` construction VERBATIM from the nearest existing `InnerLoop` test (e.g. `tests/refine/test_us2b_acceptance.py`) so the walk is realistic and offline. Use a window long enough that at least one step matures (≥ horizon+1 trading days with a scoreable candidate).

- [ ] **Step 2: Run to verify it fails**

Run: `python -m pytest tests/loop/test_inner_loop_episodes.py -v`
Expected: FAIL — `InnerLoop.__init__() got an unexpected keyword argument 'episode_store'`.

- [ ] **Step 3: Implement** — edit `alpha/loop/inner_loop.py`:

Add `episode_store=None` to `InnerLoop.__init__` params and store it as `self._episode_store = episode_store`.

In `run()`, at the maturity seam (the `for j in pending:` block where a step is scored), set the realized exit date BEFORE building the step. The existing code is:
```python
                outcomes = score_decision(self._source, self._scorer, drafts[j]["decision"],
                                          days, j, cfg.horizon, cursor, record)
                drafts[j]["outcomes"] = outcomes
                drafts[j]["scored"] = True
                step_j = TrajectoryStep(**drafts[j])
```
Change it to stamp `exit_date` from the maturity cursor:
```python
                outcomes = score_decision(self._source, self._scorer, drafts[j]["decision"],
                                          days, j, cfg.horizon, cursor, record)
                drafts[j]["outcomes"] = outcomes
                drafts[j]["scored"] = True
                drafts[j]["exit_date"] = cursor          # the realized scoring exit date (PIT key for episodes)
                step_j = TrajectoryStep(**drafts[j])
```
And in the credit block (`for step in newly:`), pass the store to `apply_credit`:
```python
                per_step_credits.append(apply_credit(Trajectory(steps=[step]), self._mgr.harness,
                                                     decay=cfg.credit_decay, episode_store=self._episode_store))
```

- [ ] **Step 4: Run to verify it passes + full suite green**

Run: `python -m pytest tests/loop/test_inner_loop_episodes.py -v && python -m pytest -q`
Expected: the new test PASS; full suite green (episode_store defaults None everywhere else, incl. the verdict/`compare_harnesses` path — verdict-neutral).

- [ ] **Step 5: Commit**

```bash
git add alpha/loop/inner_loop.py tests/loop/test_inner_loop_episodes.py
git commit -m "feat(memory): InnerLoop optionally records episodes (exit_date=maturity cursor, default-off)"
```

---

## Self-Review

**Spec coverage (§6.2–6.3, §6.9):**
- Typed `Episode`, one per scored pick → Task 1 + Task 4. ✓
- `EpisodeStore` over a `brain.db` (SQLite + FTS5), separate from the JSON H snapshot → Task 2. ✓
- `learned_asof = exit_date` (realized), PIT-masked recall → Task 1 (default) + Task 3 (`for_asof`) + Task 6 (realized cursor). ✓
- Written at `apply_credit`, observation-channel, ungated, NOT in `harness.to_dict()` → Task 5. ✓
- Verdict-neutral / default-off → Tasks 5 + 6 (`episode_store=None` default; the verdict path never sets it). ✓
- `mark_superseded` mechanism (call-site deferred to §6.6) → Task 3. ✓

**Placeholder scan:** No "TBD"/"TODO". Three implementer notes (Task 4/6: confirm `Candidate`/`ScoredCandidate` field names by reading the models; Task 6: copy an existing InnerLoop test's fixture) name the exact file to read and the fallback — they protect against guessing real model fields, not placeholders.

**Type consistency:** `Episode` fields (Task 1) are read by `_row_to_episode`/`add` (Task 2), `for_asof` (Task 3), `episodes_from_step` (Task 4). `TrajectoryStep.exit_date` (Task 1) is set in `InnerLoop.run` (Task 6) and read in `episodes_from_step` (Task 4). `apply_credit(..., episode_store=None)` (Task 5) is called by `InnerLoop` (Task 6). `EpisodeStore.in_memory()`/`.add()`/`.all()`/`.for_asof()` are used identically across the tests. `episode_id = f"{exit_date}:{symbol}:{skill_id}"` is consistent between Task 4 (build) and Task 1/2 (the test ids).
```
