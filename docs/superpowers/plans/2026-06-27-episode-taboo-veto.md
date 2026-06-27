# Episode-Taboo → L4 Veto (§6 #3) + Episode Aggregation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** When a candidate symbol has a strong PIT-masked nuke history, the existing L4 guard hard-vetoes the new entry — plus build the shared episode-aggregation primitive (`summarize` + `is_episode_taboo`) that §6 #2 will reuse.

**Architecture:** A new leaf module `alpha/memory/aggregate.py` (pure aggregation, imports only `Episode`) + three additive touches reusing the existing L4 stack: a `CandidateContext.episode_taboo` flag (`alpha/guard/veto.py`), the veto reason, and an optional `episode_store` thread through `screen_decision` + `GuardedPolicy` (`alpha/guard/screen.py`). Default-off / PIT-masked / verdict-symmetric — exactly like episode-recall.

**Tech Stack:** Python ≥3.11, pydantic v2, pytest. Reuses `alpha/memory/episodes.py::Episode`, `alpha/memory/store.py::EpisodeStore` (`in_memory()`, `for_asof(asof)`), `alpha/guard/veto.py` (`CandidateContext`, `veto`, `VetoVerdict`), `alpha/guard/screen.py` (`screen_decision`, `GuardedPolicy`), `alpha/regime/classifier.py::RegimeRead`. Test mirrors: `tests/guard/test_veto.py`, `tests/guard/test_screen.py`.

## Global Constraints

- **Python `>=3.11`**, pydantic v2. The existing suite (currently **659 passed**) must stay green — every touch is additive (`episode_taboo=False` default, `episode_store=None` default → byte-identical veto + decisions).
- **Taboo = per-symbol, overall** (not phase-scoped). Criterion: `n >= 3` PIT-masked episodes for the symbol AND `nuke_rate >= 0.5`.
- **PIT-safe:** recall via `EpisodeStore.for_asof(state.date)` (masks `learned_asof <= state.date`). A future nuke can't taboo a past decision.
- **Vetoed = dropped** (not annotated), through the existing `screen_decision` path; the reason lands in `key_risks`.
- **Default-off / verdict-symmetric:** `episode_store=None` → no episode-taboo; when wired on, the verdict/compare arms stay symmetric (out-of-scope on-switch, shared with episode-recall).
- **`aggregate.py` is a clean leaf** — imports only `Episode` (no guard/agent deps); `summarize` is generic (`key` fn) so #2 reuses it with `key=skill_id`.
- English; mirror `tests/guard/test_veto.py` + `tests/guard/test_screen.py`.

## File Structure

- Create: `alpha/memory/aggregate.py` (`EpisodeStats`, `summarize`, `is_episode_taboo`).
- Modify: `alpha/guard/veto.py` (`CandidateContext.episode_taboo` + the reason).
- Modify: `alpha/guard/screen.py` (`screen_decision(..., episode_store=None)` + `GuardedPolicy(..., episode_store=None)`).
- Tests: `tests/memory/test_aggregate.py`, `tests/guard/test_veto_episode_taboo.py`, `tests/guard/test_screen_episode_taboo.py`.

---

### Task 1: `alpha/memory/aggregate.py` (the shared aggregation primitive)

**Files:**
- Create: `alpha/memory/aggregate.py`
- Test: `tests/memory/test_aggregate.py`

**Interfaces:**
- Consumes: `Episode` (`.outcome` ∈ {continued, faded, nuked}, `.advantage: float`).
- Produces: `EpisodeStats(n, continued, faded, nuked, mean_advantage)` with computed `nuke_rate`/`win_rate`; `summarize(episodes, *, key) -> dict[str, EpisodeStats]`; `is_episode_taboo(stats, *, min_samples=3, nuke_rate=0.5) -> bool`. Consumed by Task 3 (and §6 #2 later).

- [ ] **Step 1: Write the failing test**

```python
# tests/memory/test_aggregate.py
from datetime import date
from alpha.memory.episodes import Episode
from alpha.memory.aggregate import EpisodeStats, summarize, is_episode_taboo

def _ep(sym, outcome, adv, skill="gap_and_go"):
    return Episode(episode_id=f"{sym}:{outcome}:{adv}", symbol=sym, skill_id=skill,
                   entry_date=date(2026, 6, 1), exit_date=date(2026, 6, 3), outcome=outcome, advantage=adv)

def test_summarize_groups_and_tallies_by_key():
    eps = [_ep("RUN", "nuked", -2.0), _ep("RUN", "nuked", -1.0), _ep("RUN", "continued", 3.0),
           _ep("AAA", "faded", 0.0)]
    stats = summarize(eps, key=lambda e: e.symbol)
    run = stats["RUN"]
    assert run.n == 3 and run.nuked == 2 and run.continued == 1 and run.faded == 0
    assert abs(run.mean_advantage - 0.0) < 1e-9             # (-2 -1 +3)/3
    assert abs(run.nuke_rate - 2 / 3) < 1e-9 and abs(run.win_rate - 1 / 3) < 1e-9
    assert stats["AAA"].n == 1 and stats["AAA"].nuke_rate == 0.0

def test_empty_stats_rates_are_zero():
    s = EpisodeStats(n=0, continued=0, faded=0, nuked=0, mean_advantage=0.0)
    assert s.nuke_rate == 0.0 and s.win_rate == 0.0

def test_summarize_by_skill_key():
    eps = [_ep("RUN", "nuked", -1.0, skill="gap_and_go"), _ep("AAA", "continued", 2.0, skill="vwap_reclaim")]
    stats = summarize(eps, key=lambda e: e.skill_id)
    assert set(stats) == {"gap_and_go", "vwap_reclaim"} and stats["gap_and_go"].nuked == 1

def test_is_episode_taboo_thresholds():
    assert is_episode_taboo(None) is False
    two_nuked = summarize([_ep("X", "nuked", -1.0), _ep("X", "nuked", -1.0)], key=lambda e: e.symbol)["X"]
    assert is_episode_taboo(two_nuked) is False             # n=2 < min_samples=3
    half = summarize([_ep("Y", "nuked", -1.0), _ep("Y", "nuked", -1.0),
                      _ep("Y", "continued", 1.0), _ep("Y", "faded", 0.0)], key=lambda e: e.symbol)["Y"]
    assert is_episode_taboo(half) is True                   # n=4, nuke_rate=0.5 >= 0.5
    one_quarter = summarize([_ep("Z", "nuked", -1.0)] + [_ep("Z", "continued", 1.0)] * 3,
                            key=lambda e: e.symbol)["Z"]
    assert is_episode_taboo(one_quarter) is False           # n=4, nuke_rate=0.25 < 0.5
```

- [ ] **Step 2: Run to verify it fails**

Run: `python -m pytest tests/memory/test_aggregate.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'alpha.memory.aggregate'`.

- [ ] **Step 3: Implement**

```python
# alpha/memory/aggregate.py
from __future__ import annotations
from typing import Callable
from pydantic import BaseModel, ConfigDict
from alpha.memory.episodes import Episode

class EpisodeStats(BaseModel):
    """Aggregate outcome stats for a group of episodes (per symbol / skill / narrative)."""
    model_config = ConfigDict(frozen=True)
    n: int
    continued: int
    faded: int
    nuked: int
    mean_advantage: float

    @property
    def nuke_rate(self) -> float:
        return self.nuked / self.n if self.n else 0.0

    @property
    def win_rate(self) -> float:
        return self.continued / self.n if self.n else 0.0

def summarize(episodes: list[Episode], *, key: Callable[[Episode], str]) -> dict[str, EpisodeStats]:
    """Group episodes by `key` and tally outcomes + mean advantage. Pure + deterministic."""
    buckets: dict[str, list[Episode]] = {}
    for e in episodes:
        buckets.setdefault(key(e), []).append(e)
    out: dict[str, EpisodeStats] = {}
    for k, eps in buckets.items():
        n = len(eps)
        out[k] = EpisodeStats(
            n=n,
            continued=sum(1 for e in eps if e.outcome == "continued"),
            faded=sum(1 for e in eps if e.outcome == "faded"),
            nuked=sum(1 for e in eps if e.outcome == "nuked"),
            mean_advantage=(sum(e.advantage for e in eps) / n) if n else 0.0)
    return out

def is_episode_taboo(stats: EpisodeStats | None, *, min_samples: int = 3, nuke_rate: float = 0.5) -> bool:
    """A symbol/skill is taboo when it has enough history (>= min_samples) that mostly nukes (>= nuke_rate)."""
    return stats is not None and stats.n >= min_samples and stats.nuke_rate >= nuke_rate
```

- [ ] **Step 4: Run to verify it passes**

Run: `python -m pytest tests/memory/test_aggregate.py -v`
Expected: 4 PASS.

- [ ] **Step 5: Commit**

```bash
git add alpha/memory/aggregate.py tests/memory/test_aggregate.py
git commit -m "feat(memory): episode aggregation (summarize + is_episode_taboo) — shared §6 primitive"
```

---

### Task 2: `CandidateContext.episode_taboo` + veto reason

**Files:**
- Modify: `alpha/guard/veto.py`
- Test: `tests/guard/test_veto_episode_taboo.py`

**Interfaces:**
- Produces: `CandidateContext(..., episode_taboo: bool = False)`; `veto()` appends `"episode taboo: strong nuke history (don't chase)"` when `ctx.episode_taboo`. Consumed by Task 3.

- [ ] **Step 1: Write the failing test**

```python
# tests/guard/test_veto_episode_taboo.py
from alpha.regime.classifier import RegimeRead
from alpha.guard.veto import CandidateContext, veto

def _ok_regime():
    # a frontside, risk-on regime so NOTHING else vetoes — isolate the episode-taboo reason.
    return RegimeRead(phase="trend", frontside=True, risk_gate=0.8)

def test_episode_taboo_vetoes():
    v = veto(CandidateContext(symbol="RUN", regime=_ok_regime(), episode_taboo=True))
    assert v.vetoed is True and any("episode taboo" in r for r in v.reasons)

def test_no_taboo_no_veto():
    v = veto(CandidateContext(symbol="RUN", regime=_ok_regime(), episode_taboo=False))
    assert v.vetoed is False                                # default — nothing fires under a clean regime
```

> **Implementer note:** read `tests/guard/test_veto.py` + `alpha/regime/classifier.py::RegimeRead` for the exact `RegimeRead` constructor (fields `phase`, `frontside`, `risk_gate`, and any others — supply all required). The regime must NOT itself veto (`risk_gate >= 0.2`, `frontside=True`) so the test isolates `episode_taboo`.

- [ ] **Step 2: Run to verify it fails**

Run: `python -m pytest tests/guard/test_veto_episode_taboo.py -v`
Expected: FAIL — `CandidateContext.__init__() got an unexpected keyword argument 'episode_taboo'`.

- [ ] **Step 3: Implement** — `alpha/guard/veto.py`:

Add the field to `CandidateContext` (after the existing flags):
```python
    episode_taboo: bool = False             # from §6: strong PIT-masked nuke history for this symbol
```
Add the reason in `veto()` (after the existing per-flag checks, before `return`):
```python
    if ctx.episode_taboo:
        reasons.append("episode taboo: strong nuke history (don't chase)")
```

- [ ] **Step 4: Run to verify it passes + guard tests green**

Run: `python -m pytest tests/guard/test_veto_episode_taboo.py tests/guard/test_veto.py -q`
Expected: green (the new field defaults False; existing veto tests unaffected).

- [ ] **Step 5: Commit**

```bash
git add alpha/guard/veto.py tests/guard/test_veto_episode_taboo.py
git commit -m "feat(guard): CandidateContext.episode_taboo + L4 veto reason"
```

---

### Task 3: thread `episode_store` through `screen_decision` + `GuardedPolicy`

**Files:**
- Modify: `alpha/guard/screen.py`
- Test: `tests/guard/test_screen_episode_taboo.py`

**Interfaces:**
- Consumes: `summarize`/`is_episode_taboo` (T1), `CandidateContext.episode_taboo` (T2), `EpisodeStore.for_asof`.
- Produces: `screen_decision(decision, *, source, state, episode_store=None)` — sets `ctx.episode_taboo` per candidate from PIT-masked per-symbol stats; `GuardedPolicy(inner, source, *, episode_store=None)` threads it.

- [ ] **Step 1: Write the failing test**

```python
# tests/guard/test_screen_episode_taboo.py
from datetime import date
from alpha.memory.episodes import Episode
from alpha.memory.store import EpisodeStore
from alpha.eval.decision import Candidate, DecisionPackage
from alpha.guard.screen import screen_decision
# read tests/guard/test_screen.py for the exact MarketState + source fixtures; reuse them here.
from tests.guard.test_screen import <STATE_FIXTURE>, <SOURCE_FIXTURE>   # implementer: import the real names

def _nuked_store(symbol="RUN", n=3, exit_d=date(2026, 6, 3)):
    s = EpisodeStore.in_memory()
    for i in range(n):
        s.add(Episode(episode_id=f"{symbol}:{i}", symbol=symbol, skill_id="gap_and_go",
                      entry_date=date(2026, 6, 1), exit_date=exit_d, outcome="nuked", advantage=-2.0))
    return s

def test_episode_taboo_drops_the_candidate(...):
    state = <STATE_FIXTURE at a date AFTER 2026-06-03>; source = <SOURCE_FIXTURE>
    decision = DecisionPackage(date=state.date, candidates=[Candidate(symbol="RUN", pattern="gap_and_go")])
    out = screen_decision(decision, source=source, state=state, episode_store=_nuked_store())
    assert all(c.symbol != "RUN" for c in out.candidates)            # RUN dropped
    assert any("episode taboo" in n for n in out.key_risks)

def test_pit_future_nuke_does_not_taboo(...):
    # nukes whose exit_date/learned_asof is AFTER state.date must not veto
    state = <STATE_FIXTURE at a date BEFORE the nukes>; source = <SOURCE_FIXTURE>
    decision = DecisionPackage(date=state.date, candidates=[Candidate(symbol="RUN", pattern="gap_and_go")])
    out = screen_decision(decision, source=source, state=state,
                          episode_store=_nuked_store(exit_d=date(2026, 9, 1)))
    assert any(c.symbol == "RUN" for c in out.candidates)            # not vetoed (PIT)

def test_no_store_unchanged(...):
    state = <STATE_FIXTURE>; source = <SOURCE_FIXTURE>
    decision = DecisionPackage(date=state.date, candidates=[Candidate(symbol="RUN", pattern="gap_and_go")])
    out = screen_decision(decision, source=source, state=state)      # no episode_store
    out2 = screen_decision(decision, source=source, state=state, episode_store=EpisodeStore.in_memory())
    assert [c.symbol for c in out.candidates] == [c.symbol for c in out2.candidates]   # no taboo either way
```

> **Implementer note:** read `tests/guard/test_screen.py` for the real `MarketState`/`source` construction (so RUN is NOT vetoed for OTHER reasons — pick a date/regime where the only veto is the episode-taboo). Use a state date AFTER the seeded nukes' `exit_date` for the positive test, and BEFORE for the PIT test. Import the actual fixture names. If the existing tests build state inline, replicate that inline.

- [ ] **Step 2: Run to verify it fails**

Run: `python -m pytest tests/guard/test_screen_episode_taboo.py -v`
Expected: FAIL — `screen_decision() got an unexpected keyword argument 'episode_store'`.

- [ ] **Step 3: Implement** — `alpha/guard/screen.py`:

Add the import:
```python
from alpha.memory.aggregate import is_episode_taboo, summarize
```
Add `episode_store=None` to `screen_decision`'s signature. Before the candidate loop, compute the per-symbol stats once:
```python
    taboo_stats = (summarize(episode_store.for_asof(as_of), key=lambda e: e.symbol)
                   if episode_store is not None else {})
```
In the `CandidateContext(...)` construction, add:
```python
                               episode_taboo=is_episode_taboo(taboo_stats.get(c.symbol)),
```
Add `episode_store=None` to `GuardedPolicy.__init__` (keyword), store `self._episode_store = episode_store`, and pass it in `decide`:
```python
        return screen_decision(decision, source=self._source, state=state,
                               episode_store=self._episode_store)
```

- [ ] **Step 4: Run to verify it passes + full suite green**

Run: `python -m pytest tests/guard/test_screen_episode_taboo.py -v && python -m pytest -q`
Expected: PASS; full suite green (default `episode_store=None` → existing screen/GuardedPolicy/verdict tests unchanged).

- [ ] **Step 5: Commit**

```bash
git add alpha/guard/screen.py tests/guard/test_screen_episode_taboo.py
git commit -m "feat(guard): episode-taboo veto wired through screen_decision + GuardedPolicy (default-off, PIT)"
```

---

## Self-Review

**Spec coverage:**
- Shared aggregation primitive (`EpisodeStats`/`summarize`/`is_episode_taboo`, clean leaf) → Task 1. ✓
- `CandidateContext.episode_taboo` + veto reason → Task 2. ✓
- `screen_decision`/`GuardedPolicy` thread `episode_store`, per-symbol PIT-masked taboo → Task 3. ✓
- PIT (recall at `state.date`; future nuke doesn't taboo) → Task 3 test. ✓
- Per-symbol overall, `min_samples=3`/`nuke_rate≥0.5` → Tasks 1/3. ✓
- Default-off / verdict-symmetric (no store → byte-identical) → all tasks (659 stays green). ✓
- Out of scope (#2 auto-promote/demote, phase-scope, recency-window, live/verdict on-switch) → not built. ✓

**Placeholder scan:** Tasks 1 + 2 are fully exact-code. Task 3's test uses `<STATE_FIXTURE>`/`<SOURCE_FIXTURE>` tokens that the Step-1 note explicitly resolves to the real fixtures in `tests/guard/test_screen.py` (an instruction to reuse named fixtures + pick PIT-correct dates, not a vague placeholder); the production code in Task 3 is exact.

**Type consistency:** `summarize(episodes, *, key) -> dict[str, EpisodeStats]` + `is_episode_taboo(EpisodeStats | None)` (T1) are called by `screen_decision` (T3) with `key=lambda e: e.symbol` + `taboo_stats.get(c.symbol)`. `CandidateContext.episode_taboo` (T2) is set in T3's ctx construction and read by `veto` (T2). `EpisodeStore.for_asof(as_of)` returns `list[Episode]`; `as_of = state.date` is the PIT key. `GuardedPolicy(inner, source, *, episode_store=None)` matches the existing 2-arg ctor + the additive kwarg.
