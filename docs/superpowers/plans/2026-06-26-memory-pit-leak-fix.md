# Memory PIT-Leak Fix (§6 first deliverable) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Close the memory look-ahead leak on the decision path — a verdict/backtest at date D must not surface a `Lesson` that only became knowable *after* D. Add `Lesson.learned_asof`, thread the existing `state.as_of` through `decide → build_system_prompt → select_for_prompt`, and apply a causal mask (`learned_asof <= asof`) in **both** prompt-injection modes.

**Architecture:** Purely additive + plumbing. A new optional `Lesson.learned_asof: date | None` (legacy/seed lessons keep `None` = always knowable). The mask is `asof is None or l.learned_asof is None or l.learned_asof <= asof` — applied in `select_for_prompt` (retrieval mode) and in `build_system_prompt`'s `full` branch. `asof` is threaded as `date | datetime | None` and normalized to `date` once at the prompt-builder boundary (a `datetime.as_of` from `MarketState` → `.date()`). No existing behavior changes: every current lesson has `learned_asof=None`, and every current caller that omits `asof` gets `None` (no gate).

**Tech Stack:** Python ≥3.11, pydantic v2, pytest.

## Global Constraints

- **Python `>=3.11`**, pydantic v2. Deterministic tests (capture prompts via `MockLLMClient.calls`); never a live LLM.
- **Backward compatible:** `Lesson.learned_asof` defaults `None`; `select_for_prompt`/`build_system_prompt` gain an `asof` param defaulting `None` (= no gate). The existing suite (`python -m pytest -q`, currently **568 passed**) MUST stay green and unchanged.
- **The mask semantics are exactly:** a lesson is visible iff `asof is None` OR `l.learned_asof is None` OR `l.learned_asof <= asof`. (Legacy/seed lessons with `learned_asof=None` are always visible — they are doctrine-seeded, known from t0.)
- **`asof` normalization:** `MarketState.as_of` is a `datetime`; `Lesson.learned_asof` is a `date`. Comparing `date <= datetime` raises `TypeError`, so normalize to `date` at the boundary: `asof.date() if isinstance(asof, datetime) else asof`. (`datetime` is a subclass of `date`, so the `isinstance(asof, datetime)` check MUST come first.)
- **Both injection modes** (`full` and `retrieval`) must apply the mask — the `full` debug path must NOT dump unmasked `h.memory.all()`.
- English; follow existing patterns.

## File Structure

- Modify: `alpha/harness/memory.py` — add `learned_asof` to `Lesson`.
- Modify: `alpha/agent/retrieval.py` — `select_for_prompt` gains `asof` + the lesson mask.
- Modify: `alpha/agent/prompt.py` — `build_system_prompt` gains `asof`, normalizes it, passes to `select_for_prompt`, and masks the `full` branch.
- Modify: `alpha/agent/agent.py` — `decide` passes `asof=state.as_of`.
- Tests: `tests/harness/test_memory_learned_asof.py`, `tests/agent/test_retrieval_pit.py`, `tests/agent/test_prompt_pit.py`, `tests/agent/test_decide_pit.py`.

---

### Task 1: `Lesson.learned_asof` field

**Files:**
- Modify: `alpha/harness/memory.py`
- Test: `tests/harness/test_memory_learned_asof.py`

**Interfaces:**
- Produces: `Lesson.learned_asof: date | None = None` (additive; `from_seed` accepts an ISO-string or `date` for the key, coerced by pydantic; absent → `None`). Consumed by Tasks 2–4.

- [ ] **Step 1: Write the failing test**

```python
# tests/harness/test_memory_learned_asof.py
from datetime import date
from alpha.harness.memory import Lesson

def test_learned_asof_defaults_none():
    assert Lesson(lesson_id="l", outcome="win", lesson="x").learned_asof is None

def test_from_seed_coerces_learned_asof_iso_string():
    l = Lesson.from_seed({"lesson_id": "l2", "outcome": "win", "lesson": "y",
                          "learned_asof": "2026-06-12"})
    assert l.learned_asof == date(2026, 6, 12)

def test_from_seed_without_learned_asof_is_none():
    assert Lesson.from_seed({"lesson_id": "l3", "outcome": "loss", "lesson": "z"}).learned_asof is None
```

- [ ] **Step 2: Run to verify it fails**

Run: `python -m pytest tests/harness/test_memory_learned_asof.py -v`
Expected: FAIL — `AttributeError: 'Lesson' object has no attribute 'learned_asof'`.

- [ ] **Step 3: Implement** — edit `alpha/harness/memory.py`:

Add to the imports at the top (line 3 area):
```python
from datetime import date
```
Add the field to `Lesson` (after `importance: Importance = Field(default_factory=Importance)`):
```python
    learned_asof: date | None = None   # PIT key: the date this lesson became KNOWABLE (None = seed/always-known)
```

- [ ] **Step 4: Run to verify it passes**

Run: `python -m pytest tests/harness/test_memory_learned_asof.py -v`
Expected: 3 PASS.

- [ ] **Step 5: Commit**

```bash
git add alpha/harness/memory.py tests/harness/test_memory_learned_asof.py
git commit -m "feat(memory): add Lesson.learned_asof PIT key (defaults None)"
```

---

### Task 2: `select_for_prompt` causal mask

**Files:**
- Modify: `alpha/agent/retrieval.py`
- Test: `tests/agent/test_retrieval_pit.py`

**Interfaces:**
- Consumes: `Lesson.learned_asof` (Task 1).
- Produces: `select_for_prompt(h, *, phase_prior, skill_budget=…, memory_budget=…, trial_slots=…, asof: date | None = None)` — lessons now also filtered by `asof is None or l.learned_asof is None or l.learned_asof <= asof`. Consumed by Task 3.

- [ ] **Step 1: Write the failing test**

```python
# tests/agent/test_retrieval_pit.py
from datetime import date
from alpha.harness.doctrine import Doctrine
from alpha.harness.registry import SkillRegistry, MemoryStore
from alpha.harness.memory import Lesson
from alpha.harness.state import HarnessState
from alpha.agent.retrieval import select_for_prompt

def _h_with_lessons():
    lessons = [
        Lesson(lesson_id="seed", outcome="principle", lesson="seed rule"),                  # learned_asof None
        Lesson(lesson_id="future", outcome="loss", lesson="learned on D",
               learned_asof=date(2026, 6, 12)),
    ]
    return HarnessState(doctrine=Doctrine(), skills=SkillRegistry.from_skills([]),
                        memory=MemoryStore.from_lessons(lessons))

def test_future_lesson_masked_before_its_asof():
    sel = select_for_prompt(_h_with_lessons(), phase_prior=None, asof=date(2026, 6, 11))
    ids = {l.lesson_id for l in sel.lessons}
    assert ids == {"seed"}                       # the future lesson is hidden at D-1; the seed stays

def test_future_lesson_visible_on_its_asof():
    sel = select_for_prompt(_h_with_lessons(), phase_prior=None, asof=date(2026, 6, 12))
    assert {l.lesson_id for l in sel.lessons} == {"seed", "future"}

def test_no_asof_means_no_gate():
    sel = select_for_prompt(_h_with_lessons(), phase_prior=None)   # asof omitted
    assert {l.lesson_id for l in sel.lessons} == {"seed", "future"}
```

- [ ] **Step 2: Run to verify it fails**

Run: `python -m pytest tests/agent/test_retrieval_pit.py -v`
Expected: FAIL — `TypeError: select_for_prompt() got an unexpected keyword argument 'asof'`.

- [ ] **Step 3: Implement** — edit `alpha/agent/retrieval.py`:

Add the import at the top:
```python
from datetime import date
```
Change the signature (add `asof`):
```python
def select_for_prompt(h: HarnessState, *, phase_prior: str | None,
                      skill_budget: int = DEFAULT_SKILL_BUDGET,
                      memory_budget: int = DEFAULT_MEMORY_BUDGET,
                      trial_slots: int = DEFAULT_TRIAL_SLOTS,
                      asof: date | None = None) -> Selection:
```
Change the `lessons = sorted(...)` line to add the temporal mask:
```python
    lessons = sorted(
        (l for l in h.memory.all()
         if l.importance.weight() >= MIN_MEMORY_WEIGHT
         and (asof is None or l.learned_asof is None or l.learned_asof <= asof)),
        key=lambda l: (-l.importance.weight(), l.lesson_id))
```
(Update the docstring `lessons:` line to mention the `learned_asof <= asof` mask.)

- [ ] **Step 4: Run to verify it passes**

Run: `python -m pytest tests/agent/test_retrieval_pit.py -v`
Expected: 3 PASS.

- [ ] **Step 5: Commit**

```bash
git add alpha/agent/retrieval.py tests/agent/test_retrieval_pit.py
git commit -m "fix(memory): PIT mask on select_for_prompt (learned_asof <= asof)"
```

---

### Task 3: `build_system_prompt` threads `asof` + masks the `full` branch

**Files:**
- Modify: `alpha/agent/prompt.py`
- Test: `tests/agent/test_prompt_pit.py`

**Interfaces:**
- Consumes: `select_for_prompt(asof=…)` (Task 2); `Lesson.learned_asof` (Task 1).
- Produces: `build_system_prompt(h, *, injection='full', phase_prior=None, …, available_signals=None, asof: date | datetime | None = None)` — normalizes `asof` to a `date` once, passes it to `select_for_prompt` (retrieval mode), and applies the same mask to `h.memory.all()` in the `full` branch. Consumed by Task 4.

- [ ] **Step 1: Write the failing tests** (both injection modes)

```python
# tests/agent/test_prompt_pit.py
from datetime import date, datetime
from alpha.harness.doctrine import Doctrine
from alpha.harness.registry import SkillRegistry, MemoryStore
from alpha.harness.memory import Lesson
from alpha.harness.state import HarnessState
from alpha.agent.prompt import build_system_prompt

def _h():
    lessons = [
        Lesson(lesson_id="seed", outcome="principle", lesson="SEED_RULE_TEXT"),
        Lesson(lesson_id="future", outcome="loss", lesson="FUTURE_LESSON_TEXT",
               learned_asof=date(2026, 6, 12)),
    ]
    return HarnessState(doctrine=Doctrine(), skills=SkillRegistry.from_skills([]),
                        memory=MemoryStore.from_lessons(lessons))

def test_full_mode_masks_future_lesson():
    before = build_system_prompt(_h(), injection="full", asof=datetime(2026, 6, 11, 16, 0))
    on = build_system_prompt(_h(), injection="full", asof=datetime(2026, 6, 12, 16, 0))
    assert "FUTURE_LESSON_TEXT" not in before and "SEED_RULE_TEXT" in before
    assert "FUTURE_LESSON_TEXT" in on

def test_retrieval_mode_masks_future_lesson():
    before = build_system_prompt(_h(), injection="retrieval", asof=datetime(2026, 6, 11, 16, 0))
    on = build_system_prompt(_h(), injection="retrieval", asof=datetime(2026, 6, 12, 16, 0))
    assert "FUTURE_LESSON_TEXT" not in before and "SEED_RULE_TEXT" in before
    assert "FUTURE_LESSON_TEXT" in on

def test_no_asof_renders_all_lessons():
    out = build_system_prompt(_h(), injection="full")     # asof omitted -> no gate
    assert "FUTURE_LESSON_TEXT" in out and "SEED_RULE_TEXT" in out
```

- [ ] **Step 2: Run to verify they fail**

Run: `python -m pytest tests/agent/test_prompt_pit.py -v`
Expected: FAIL — `test_full_mode_masks_future_lesson` / `test_retrieval_mode_masks_future_lesson` fail (the future lesson is currently rendered before its asof); also `build_system_prompt()` does not yet accept `asof`.

- [ ] **Step 3: Implement** — edit `alpha/agent/prompt.py`:

Add the import at the top:
```python
from datetime import date, datetime
```
Change the `build_system_prompt` signature (add `asof`):
```python
def build_system_prompt(h: HarnessState, *, injection: str = "full", phase_prior: str | None = None,
                        skill_budget: int = DEFAULT_SKILL_BUDGET,
                        memory_budget: int = DEFAULT_MEMORY_BUDGET,
                        trial_slots: int = DEFAULT_TRIAL_SLOTS,
                        available_signals: frozenset[str] | None = None,
                        asof: date | datetime | None = None) -> str:
```
Replace the injection-mode block (the `if injection == "retrieval": … else: …` that sets `skills/trials/lessons`) with:
```python
    asof_d = asof.date() if isinstance(asof, datetime) else asof   # PIT key compares date<=date
    if injection == "retrieval":
        sel = select_for_prompt(h, phase_prior=phase_prior, skill_budget=skill_budget,
                                memory_budget=memory_budget, trial_slots=trial_slots, asof=asof_d)
        skills, trials, lessons = sel.skills, sel.trials, sel.lessons
    else:
        skills = [s for s in h.skills.all() if s.status == "active"]
        trials = [s for s in h.skills.all() if s.status == "incubating"]
        lessons = [l for l in h.memory.all()
                   if asof_d is None or l.learned_asof is None or l.learned_asof <= asof_d]
```

- [ ] **Step 4: Run to verify they pass**

Run: `python -m pytest tests/agent/test_prompt_pit.py -v`
Expected: 3 PASS.

- [ ] **Step 5: Commit**

```bash
git add alpha/agent/prompt.py tests/agent/test_prompt_pit.py
git commit -m "fix(memory): build_system_prompt threads asof + masks both injection modes"
```

---

### Task 4: `decide` threads `state.as_of` + end-to-end PIT regression

**Files:**
- Modify: `alpha/agent/agent.py`
- Test: `tests/agent/test_decide_pit.py`

**Interfaces:**
- Consumes: `build_system_prompt(asof=…)` (Task 3).
- Produces: `decide` passes `asof=state.as_of` so the live decision path is PIT-safe. End-to-end: a lesson `learned_asof=D` is absent from the system prompt when the agent decides at `as_of < D`.

- [ ] **Step 1: Write the failing test** (captures the system prompt the agent actually built, via `MockLLMClient.calls`; covers both injection modes)

```python
# tests/agent/test_decide_pit.py
from datetime import date, datetime
import pytest
from alpha.harness.doctrine import Doctrine
from alpha.harness.registry import SkillRegistry, MemoryStore
from alpha.harness.memory import Lesson
from alpha.harness.state import HarnessState
from alpha.state.market import MarketState
from alpha.universe.stock import StockSnapshot
from alpha.universe.universe import CandidateUniverse
from alpha.llm.client import MockLLMClient
from alpha.agent.agent import LLMAgentPolicy

def _h():
    lessons = [Lesson(lesson_id="future", outcome="loss", lesson="FUTURE_LESSON_TEXT",
                      learned_asof=date(2026, 6, 12))]
    return HarnessState(doctrine=Doctrine(), skills=SkillRegistry.from_skills([]),
                        memory=MemoryStore.from_lessons(lessons))

def _state(asof_day: int) -> MarketState:
    return MarketState(date=date(2026, 6, asof_day), gainer_count=1, gap_up_count=0, loser_count=0,
                       failed_breakout_count=0, max_runner_tier=1, echelon=[], breadth_raw=1.0,
                       sentiment_norm=0.6, as_of=datetime(2026, 6, asof_day, 16, 0))

def _uni():
    return CandidateUniverse.from_stocks([StockSnapshot(symbol="RUN", name="Runner", status="gainer")])

@pytest.mark.parametrize("injection", ["full", "retrieval"])
def test_decide_does_not_leak_future_lesson(injection):
    llm = MockLLMClient('{"regime_read": "", "candidates": []}')
    agent = LLMAgentPolicy(_h(), llm, injection=injection)
    agent.decide(_state(11), _uni())                      # as_of = 2026-06-11 (before the lesson's asof)
    system_before, _user = llm.calls[0]
    assert "FUTURE_LESSON_TEXT" not in system_before      # the look-ahead leak is closed

@pytest.mark.parametrize("injection", ["full", "retrieval"])
def test_decide_shows_lesson_on_or_after_asof(injection):
    llm = MockLLMClient('{"regime_read": "", "candidates": []}')
    agent = LLMAgentPolicy(_h(), llm, injection=injection)
    agent.decide(_state(12), _uni())                      # as_of = 2026-06-12 (the lesson's asof)
    system_on, _user = llm.calls[0]
    assert "FUTURE_LESSON_TEXT" in system_on
```

- [ ] **Step 2: Run to verify it fails**

Run: `python -m pytest tests/agent/test_decide_pit.py -v`
Expected: FAIL on `test_decide_does_not_leak_future_lesson` (both params) — `decide` does not yet pass `asof`, so the future lesson leaks into the prompt at `as_of=2026-06-11`.

- [ ] **Step 3: Implement** — edit `alpha/agent/agent.py` `decide` (add `asof=state.as_of` to the `build_system_prompt` call):

```python
        system = build_system_prompt(self._harness, injection=self._injection,
                                     phase_prior=self._phase_prior, skill_budget=self._skill_budget,
                                     memory_budget=self._memory_budget, trial_slots=self._trial_slots,
                                     available_signals=available_data_signals(universe),
                                     asof=state.as_of)
```

- [ ] **Step 4: Run to verify it passes**

Run: `python -m pytest tests/agent/test_decide_pit.py -v`
Expected: 4 PASS (2 params × 2 tests).

- [ ] **Step 5: Run the whole suite (no regressions)**

Run: `python -m pytest -q`
Expected: the prior **568 passed** PLUS the new PIT tests, all green (every pre-existing lesson has `learned_asof=None`, so masking changes nothing for them).

- [ ] **Step 6: Commit**

```bash
git add alpha/agent/agent.py tests/agent/test_decide_pit.py
git commit -m "fix(memory): decide threads state.as_of -> PIT-safe memory recall (closes the leak)"
```

---

## Self-Review

**Spec coverage (§6.1, §6.5 first deliverable):**
- Thread `asof` through `decide → build_system_prompt → select_for_prompt` → Tasks 4 + 3 + 2. ✓
- Causal mask `WHERE learned_asof <= asof` on lessons → Tasks 2 (retrieval) + 3 (full). ✓
- Cover BOTH injection modes (the `full` path must not dump unmasked memory) → Task 3 masks the `full` branch; Task 4 parametrizes both modes end-to-end. ✓
- `learned_asof` on `Lesson`, legacy/seed lessons stay visible → Task 1 (defaults `None`) + the `learned_asof is None` clause in every mask. ✓
- A dedicated PIT-leak regression test → Task 4 (`test_decide_does_not_leak_future_lesson`), plus retrieval-level (Task 2) and prompt-level (Task 3) regressions. ✓

**Placeholder scan:** No "TBD"/"TODO"; every code step shows the exact edit.

**Type consistency:** `select_for_prompt(…, asof: date | None)` (Task 2) is called by `build_system_prompt` (Task 3) with the normalized `asof_d` (a `date`). `build_system_prompt(…, asof: date | datetime | None)` (Task 3) is called by `decide` (Task 4) with `state.as_of` (a `datetime`). The mask expression `asof[_d] is None or l.learned_asof is None or l.learned_asof <= asof[_d]` is byte-identical in Tasks 2 and 3. `Lesson.learned_asof: date | None` (Task 1) is read in Tasks 2–4. The `isinstance(asof, datetime)` check precedes the `date` fallback (datetime ⊂ date).
