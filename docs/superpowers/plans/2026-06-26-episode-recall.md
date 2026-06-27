# Episode Recall Into Decisions (§6 recall scoring v1) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Read the written episodes back into the agent's decisions — recall PIT-masked episodes, score them by regime relevance (recency + |advantage|, phase-matched), and inject the top-K into the agent's decision prompt.

**Architecture:** Three additive touches mirroring the existing lesson-injection path: (1) `select_episodes_for_prompt` in `alpha/agent/retrieval.py` (broad PIT-masked recall via `EpisodeStore.for_asof` + a regime-scored rank); (2) a `RECALLED EPISODES` block in `alpha/agent/prompt.py::build_system_prompt`; (3) an `episode_store` handle on `alpha/agent/agent.py::LLMAgentPolicy`, threaded into `build_system_prompt` in `decide` alongside the existing `asof=state.as_of`. Default `None` everywhere → byte-identical to today.

**Tech Stack:** Python ≥3.11, pydantic v2, pytest. Reuses `alpha/memory/store.py::EpisodeStore` (`in_memory()`, `for_asof(asof)`), `alpha/memory/episodes.py::Episode`, `alpha/harness/regime.py::normalize_phase`. Mirrors `select_for_prompt`/the lessons block/the `asof` threading.

## Global Constraints

- **Python `>=3.11`**, pydantic v2. The existing suite (currently **647 passed**) must stay green — all three touches are additive (`episode_store=None` default → unchanged prompt + decisions).
- **PIT-safe by construction:** recall goes through `EpisodeStore.for_asof(asof)` which masks `learned_asof <= asof`; the agent passes `asof = state.as_of` (the same key lessons use). No episode whose outcome became knowable after the decision date can surface.
- **Regime-scored rank, read-path only:** recall broadly, rank by `(phase_match, learned_asof desc, abs(advantage) desc)` where `phase_match = normalize_phase(episode.phase) == normalize_phase(phase_prior)` (episodes store the RAW `regime_read`, `phase_prior` is the canonical token — normalize BOTH sides; NO SQL `phase=` filter). No write-path / episode-schema change.
- **Default-off + symmetric verdict:** v1 ships the capability; it does NOT flip the store on in the live decide / verdict path (a separate noted follow-up). When wired, the `compare_harnesses`/verdict arms must be symmetric.
- **Scope:** recall-into-decisions ONLY. Auto-promote/demote (#2) and taboo→L4 veto (#3) are out.
- English; mirror `alpha/agent/retrieval.py::select_for_prompt` + the lessons block in `build_system_prompt`.

## File Structure

- Modify: `alpha/agent/retrieval.py` (`DEFAULT_EPISODE_BUDGET`, `select_episodes_for_prompt`).
- Modify: `alpha/agent/prompt.py` (`build_system_prompt(..., episode_store=None, episode_budget=…)` + the `RECALLED EPISODES` block).
- Modify: `alpha/agent/agent.py` (`LLMAgentPolicy(..., episode_store=None)` + thread into `decide`).
- Tests: `tests/agent/test_select_episodes.py`, `tests/agent/test_prompt_episodes.py`, `tests/agent/test_agent_episode_recall.py`.

---

### Task 1: `select_episodes_for_prompt` (recall + regime-scored rank)

**Files:**
- Modify: `alpha/agent/retrieval.py`
- Test: `tests/agent/test_select_episodes.py`

**Interfaces:**
- Consumes: an `EpisodeStore`-shaped object (`.for_asof(asof) -> list[Episode]`), `normalize_phase`, `Episode` (`.phase/.learned_asof/.exit_date/.advantage`).
- Produces: `DEFAULT_EPISODE_BUDGET = 8`; `select_episodes_for_prompt(episode_store, *, phase_prior: str | None, asof: date | datetime | None = None, budget: int = DEFAULT_EPISODE_BUDGET) -> list[Episode]`. Consumed by Tasks 2/3.

- [ ] **Step 1: Write the failing test**

```python
# tests/agent/test_select_episodes.py
from datetime import date
from alpha.memory.episodes import Episode
from alpha.memory.store import EpisodeStore
from alpha.agent.retrieval import select_episodes_for_prompt

def _ep(eid, phase, exit_d, adv, skill="gap_and_go", sym="RUN"):
    return Episode(episode_id=eid, symbol=sym, skill_id=skill, phase=phase,
                   entry_date=date(2026, 6, 1), exit_date=exit_d, outcome="continued", advantage=adv)

def _store(*eps):
    s = EpisodeStore.in_memory()
    for e in eps:
        s.add(e)
    return s

def test_none_store_returns_empty():
    assert select_episodes_for_prompt(None, phase_prior="trend", asof=date(2026, 6, 20)) == []

def test_none_asof_returns_empty():
    s = _store(_ep("e1", "trend frontside", date(2026, 6, 5), 1.0))
    assert select_episodes_for_prompt(s, phase_prior="trend", asof=None) == []

def test_pit_mask_excludes_future_learned_asof():
    s = _store(_ep("past", "trend frontside", date(2026, 6, 5), 1.0),
               _ep("future", "trend frontside", date(2026, 6, 25), 9.0))   # learned_asof defaults to exit_date
    out = select_episodes_for_prompt(s, phase_prior="trend", asof=date(2026, 6, 10))
    ids = {e.episode_id for e in out}
    assert "past" in ids and "future" not in ids                          # future not knowable at asof

def test_phase_match_ranks_first_then_recency_then_advantage():
    s = _store(_ep("off_phase", "chop", date(2026, 6, 9), 5.0),
               _ep("trend_old", "trend frontside", date(2026, 6, 5), 1.0),
               _ep("trend_new", "trend backside", date(2026, 6, 8), 0.5))
    out = select_episodes_for_prompt(s, phase_prior="trend", asof=date(2026, 6, 20))
    # both 'trend' episodes (canonical phase match) outrank the off-phase one despite its bigger advantage;
    # within the matched phase, the newer (trend_new) ranks before the older (trend_old)
    assert [e.episode_id for e in out[:2]] == ["trend_new", "trend_old"]
    assert out[-1].episode_id == "off_phase"

def test_budget_caps():
    eps = [_ep(f"e{i}", "trend frontside", date(2026, 6, 2 + i), float(i)) for i in range(5)]
    out = select_episodes_for_prompt(_store(*eps), phase_prior="trend", asof=date(2026, 6, 20), budget=3)
    assert len(out) == 3

def test_phase_prior_none_recalls_across_phases_by_recency():
    s = _store(_ep("a", "trend frontside", date(2026, 6, 5), 1.0),
               _ep("b", "chop", date(2026, 6, 9), 1.0))
    out = select_episodes_for_prompt(s, phase_prior=None, asof=date(2026, 6, 20))
    assert out[0].episode_id == "b"                                       # newest first, no phase boost
```

> **Implementer note:** confirm `normalize_phase("trend frontside")` and `normalize_phase("trend")` both canonicalize to the same token (read `alpha/harness/regime.py`); if the canonical token differs, adjust the test's `phase_prior`/episode `phase` strings so a real regime read and its canonical prior match. The point is: normalize BOTH sides and compare.

- [ ] **Step 2: Run to verify it fails**

Run: `python -m pytest tests/agent/test_select_episodes.py -v`
Expected: FAIL — `ImportError: cannot import name 'select_episodes_for_prompt'`.

- [ ] **Step 3: Implement** — `alpha/agent/retrieval.py`:

Add the import (it already imports `normalize_phase`):
```python
DEFAULT_EPISODE_BUDGET = 8
```
Add the function:
```python
def select_episodes_for_prompt(episode_store, *, phase_prior: str | None,
                               asof: date | datetime | None = None,
                               budget: int = DEFAULT_EPISODE_BUDGET) -> list:
    """Recall PIT-masked episodes for the current regime, ranked (phase-match, recency, |advantage|), top
    budget. `episode_store` is duck-typed (.for_asof(asof) -> list[Episode]); None/asof-None -> []."""
    if episode_store is None:
        return []
    if isinstance(asof, datetime):
        asof = asof.date()
    if asof is None:
        return []
    canon = normalize_phase(phase_prior) if phase_prior else None
    pool = episode_store.for_asof(asof)                          # PIT-masked (learned_asof <= asof)
    def _key(e):
        match = 1 if (canon is not None and normalize_phase(e.phase or "") == canon) else 0
        return (match, e.learned_asof or e.exit_date, abs(e.advantage))
    pool.sort(key=_key, reverse=True)
    return pool[:budget]
```

- [ ] **Step 4: Run to verify it passes**

Run: `python -m pytest tests/agent/test_select_episodes.py -v`
Expected: 6 PASS.

- [ ] **Step 5: Commit**

```bash
git add alpha/agent/retrieval.py tests/agent/test_select_episodes.py
git commit -m "feat(agent): select_episodes_for_prompt (PIT-masked, regime-scored episode recall)"
```

---

### Task 2: `RECALLED EPISODES` block in `build_system_prompt`

**Files:**
- Modify: `alpha/agent/prompt.py`
- Test: `tests/agent/test_prompt_episodes.py`

**Interfaces:**
- Consumes: `select_episodes_for_prompt` + `DEFAULT_EPISODE_BUDGET` (T1).
- Produces: `build_system_prompt(h, *, …, asof=None, episode_store=None, episode_budget: int = DEFAULT_EPISODE_BUDGET)` — renders a `RECALLED EPISODES` block (after the lessons block) when `episode_store` is given. Consumed by Task 3.

- [ ] **Step 1: Write the failing test**

```python
# tests/agent/test_prompt_episodes.py
from datetime import date
from alpha.harness.doctrine import Doctrine
from alpha.harness.registry import SkillRegistry, MemoryStore
from alpha.harness.state import HarnessState
from alpha.memory.episodes import Episode
from alpha.memory.store import EpisodeStore
from alpha.agent.prompt import build_system_prompt

def _h():
    return HarnessState(doctrine=Doctrine(), skills=SkillRegistry.from_skills([]), memory=MemoryStore.from_lessons([]))

def _store(*eps):
    s = EpisodeStore.in_memory()
    for e in eps:
        s.add(e)
    return s

def _ep(eid, phase, exit_d, adv, refl=""):
    return Episode(episode_id=eid, symbol="RUN", skill_id="gap_and_go", phase=phase,
                   entry_date=date(2026, 6, 1), exit_date=exit_d, outcome="continued", advantage=adv,
                   reflection_text=refl)

def test_no_store_no_block():
    p = build_system_prompt(_h(), asof=date(2026, 6, 20))
    assert "RECALLED EPISODES" not in p

def test_store_renders_recalled_block():
    s = _store(_ep("e1", "trend frontside", date(2026, 6, 5), 1.5, refl="held the gap into close"))
    p = build_system_prompt(_h(), phase_prior="trend", asof=date(2026, 6, 20), episode_store=s)
    assert "RECALLED EPISODES" in p
    assert "RUN/gap_and_go" in p and "continued" in p and "+1.5" in p and "held the gap into close" in p

def test_block_honors_asof_pit():
    s = _store(_ep("future", "trend frontside", date(2026, 6, 25), 9.0))   # learned_asof 06-25
    p = build_system_prompt(_h(), phase_prior="trend", asof=date(2026, 6, 10), episode_store=s)
    assert "RECALLED EPISODES" not in p                                    # nothing knowable at asof -> no block
```

- [ ] **Step 2: Run to verify it fails**

Run: `python -m pytest tests/agent/test_prompt_episodes.py -v`
Expected: FAIL — `build_system_prompt() got an unexpected keyword argument 'episode_store'`.

- [ ] **Step 3: Implement** — `alpha/agent/prompt.py`:

Extend the retrieval import:
```python
from alpha.agent.retrieval import (DEFAULT_MEMORY_BUDGET, DEFAULT_SKILL_BUDGET, DEFAULT_TRIAL_SLOTS,
                                   DEFAULT_EPISODE_BUDGET, Selection, select_for_prompt,
                                   select_episodes_for_prompt)
```
(Match the file's actual existing import line for retrieval names; add `DEFAULT_EPISODE_BUDGET` + `select_episodes_for_prompt`.)
Add the two params to `build_system_prompt`'s signature (after `asof`):
```python
                        asof: date | datetime | None = None,
                        episode_store=None, episode_budget: int = DEFAULT_EPISODE_BUDGET) -> str:
```
Insert the block AFTER the lessons block and BEFORE `parts.append("\n" + _OUTPUT_CONTRACT)`:
```python
    if episode_store is not None:
        eps = select_episodes_for_prompt(episode_store, phase_prior=phase_prior, asof=asof_d,
                                         budget=episode_budget)
        if eps:
            parts.append("\nRECALLED EPISODES (what happened last time in this regime):")
            for e in eps:
                refl = f": {e.reflection_text}" if e.reflection_text else ""
                parts.append(f"- [{e.phase}] {e.symbol}/{e.skill_id} -> {e.outcome} "
                             f"(adv {e.advantage:+.1f}){refl}")
```

- [ ] **Step 4: Run to verify it passes + full suite green**

Run: `python -m pytest tests/agent/test_prompt_episodes.py -v && python -m pytest -q`
Expected: 3 PASS; full suite green (the default `episode_store=None` leaves every existing prompt test unchanged).

- [ ] **Step 5: Commit**

```bash
git add alpha/agent/prompt.py tests/agent/test_prompt_episodes.py
git commit -m "feat(agent): RECALLED EPISODES prompt block (default-off, PIT-masked)"
```

---

### Task 3: `LLMAgentPolicy` episode_store handle + threading

**Files:**
- Modify: `alpha/agent/agent.py`
- Test: `tests/agent/test_agent_episode_recall.py`

**Interfaces:**
- Consumes: `build_system_prompt(..., episode_store=…)` (T2).
- Produces: `LLMAgentPolicy(harness, llm, injection="retrieval", …, episode_store=None)` — stores `self._episode_store`; `decide` passes `episode_store=self._episode_store` into `build_system_prompt` (alongside `asof=state.as_of`). Default `None` → off.

- [ ] **Step 1: Write the failing test**

```python
# tests/agent/test_agent_episode_recall.py
from datetime import date, datetime
import pandas as pd
from alpha.harness.doctrine import Doctrine
from alpha.harness.skill import Skill
from alpha.harness.registry import SkillRegistry, MemoryStore
from alpha.harness.state import HarnessState
from alpha.memory.episodes import Episode
from alpha.memory.store import EpisodeStore
from alpha.agent.agent import LLMAgentPolicy
from alpha.state.builder import build_market_state
from alpha.universe.universe import build_universe
from alpha.data.source import FakeSource

class _CaptureLLM:
    """Records the system prompt it was asked to complete; returns a minimal valid decision."""
    def __init__(self): self.system = ""
    def complete(self, system, user):
        self.system = system
        return '{"regime_read": "trend frontside", "candidates": [{"symbol": "RUN", "pattern": "gap_and_go"}]}'

def _h():
    return HarnessState(doctrine=Doctrine(),
                        skills=SkillRegistry.from_skills([Skill(skill_id="gap_and_go", name="Gap and Go",
                                                               type="pattern", status="active")]),
                        memory=MemoryStore.from_lessons([]))

def _src():
    cal = [date(2026, 6, 10)]
    snaps = {cal[0]: pd.DataFrame({"symbol": ["RUN"], "name": ["RUN"], "open": [1.0], "high": [1.0],
                                   "low": [1.0], "close": [1.0], "volume": [1], "prev_close": [1.0]})}
    bars = {"RUN": pd.DataFrame({"date": cal, "open": [1.0], "high": [1.0], "low": [1.0], "close": [1.0], "volume": [1]})}
    return FakeSource(calendar=cal, bars=bars, snapshots=snaps)

def test_decide_threads_episode_store_and_asof():
    s = EpisodeStore.in_memory()
    s.add(Episode(episode_id="e1", symbol="RUN", skill_id="gap_and_go", phase="trend frontside",
                  entry_date=date(2026, 6, 1), exit_date=date(2026, 6, 5), outcome="continued", advantage=2.0,
                  reflection_text="ran into close"))
    day = date(2026, 6, 10)
    src = _src(); universe = build_universe(src, day)
    state = build_market_state(universe, day, as_of=datetime(2026, 6, 10, 16, 0))
    llm = _CaptureLLM()
    LLMAgentPolicy(_h(), llm, injection="full", episode_store=s).decide(state, universe)
    assert "RECALLED EPISODES" in llm.system and "RUN/gap_and_go" in llm.system   # store + as_of were threaded

def test_decide_without_store_has_no_episode_block():
    day = date(2026, 6, 10)
    src = _src(); universe = build_universe(src, day)
    state = build_market_state(universe, day, as_of=datetime(2026, 6, 10, 16, 0))
    llm = _CaptureLLM()
    LLMAgentPolicy(_h(), llm, injection="full").decide(state, universe)        # no episode_store
    assert "RECALLED EPISODES" not in llm.system
```

> **Implementer note:** read `alpha/agent/agent.py` for the exact `LLMAgentPolicy.__init__` keyword list + the `build_system_prompt(...)` call in `decide` (it already passes `asof=state.as_of`). Add `episode_store=None` as a keyword param + `self._episode_store = episode_store`, and add `episode_store=self._episode_store` to the `build_system_prompt` call. The `_CaptureLLM` works because `decide` calls `self._llm.complete(system, user)`; confirm the method name (`complete`) matches `LLMClient`.

- [ ] **Step 2: Run to verify it fails**

Run: `python -m pytest tests/agent/test_agent_episode_recall.py -v`
Expected: FAIL — `LLMAgentPolicy.__init__() got an unexpected keyword argument 'episode_store'`.

- [ ] **Step 3: Implement** — `alpha/agent/agent.py`:
- Add `episode_store=None` to `LLMAgentPolicy.__init__`'s keyword params; store `self._episode_store = episode_store`.
- In `decide`, add `episode_store=self._episode_store` to the `build_system_prompt(...)` call (next to `asof=state.as_of`).

- [ ] **Step 4: Run to verify it passes + full suite green**

Run: `python -m pytest tests/agent/test_agent_episode_recall.py -v && python -m pytest -q`
Expected: 2 PASS; full suite green (default `episode_store=None` → every existing agent/decide/verdict test unchanged).

- [ ] **Step 5: Commit**

```bash
git add alpha/agent/agent.py tests/agent/test_agent_episode_recall.py
git commit -m "feat(agent): LLMAgentPolicy episode_store handle -> recall into decide (default-off)"
```

---

## Self-Review

**Spec coverage:**
- `select_episodes_for_prompt` (PIT-masked recall + regime-scored rank, normalize both phase sides, broad recall not SQL filter) → Task 1. ✓
- `RECALLED EPISODES` block in `build_system_prompt`, default-off → Task 2. ✓
- `LLMAgentPolicy` episode_store handle threaded with `asof=state.as_of` → Task 3. ✓
- PIT safety (`for_asof` mask + `state.as_of`) → Tasks 1/2/3 tests (future-learned_asof excluded). ✓
- Additive / default-off / verdict untouched when no store → all tasks (647 stays green). ✓
- Out of scope (#2 auto-promote/demote, #3 taboo→L4, narrative-scope, live/verdict on-switch) → not built. ✓

**Placeholder scan:** every code step shows exact code. The two implementer notes (confirm `normalize_phase` canonicalization; confirm the `decide` call site + `complete` method name) are verification instructions against named files, not placeholders.

**Type consistency:** `DEFAULT_EPISODE_BUDGET` + `select_episodes_for_prompt(episode_store, *, phase_prior, asof, budget)` (T1) are imported + called by `build_system_prompt` (T2), which `LLMAgentPolicy.decide` calls with `episode_store=self._episode_store` (T3). `EpisodeStore.for_asof(asof)`/`Episode.phase/.learned_asof/.exit_date/.advantage/.reflection_text` are the real shapes. `normalize_phase` is applied to BOTH `phase_prior` and `episode.phase`. The recall returns `list[Episode]`; the block renders `e.phase/.symbol/.skill_id/.outcome/.advantage/.reflection_text`.
