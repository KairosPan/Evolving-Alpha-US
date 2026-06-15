# US-2d Three-Way Compare + Shadow Breaker Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Validate the self-evolution — a three-**tier** **HCH / Hexpert / Hmin** compare (Hmin is realized as two floor arms — chase-biggest-gainer + no-trade — so the report carries **four** arms) that runs the self-refining `InnerLoop` (HCH) against the frozen-seed-expert (Hexpert) and the chase-the-gainer/no-trade floor (Hmin) on the **same** data, reporting the **excess-advantage** delta + the `hch_beats_hexpert` verdict — plus the **shadow/paired** capability-floor breaker (HCH's breaker judged against the Hexpert reference series), and a **multi-window** noise-aware honest-bar diagnostic.

**Architecture:** Two new pieces + one extension. (1) **Shadow breaker path** — `alpha/loop/floor_breaker.py` gains `_shadow_eps_abs`/`_shadow_trip` (paired-diff trip: `mean(diff) < −max(λ·σ, ε)` AND a negative-day direction gate), and `InnerLoop` gains a `shadow_daily` param + `breaker_shadow_*` `LoopConfig` fields + a shadow branch that compares HCH's per-day advantage to an injected reference series (filtered `d ≤ cur_max` for anti-lookahead); `shadow_daily=None` keeps the existing fallback path byte-for-byte. (2) **`alpha/loop/compare.py`** — `compare_harnesses(...)` orchestrates the arms via **factory injection** (fresh `H`, LLM clients, and store per arm — no cross-arm pollution), runs Hexpert via a frozen `WalkForwardEval.walk()` (no Refiner), HCH via `InnerLoop`, Hmin via baselines, and returns a frozen `ComparisonReport` (per-arm `EvalReport` + deltas + verdict). When `shadow=True`, Hexpert runs **first** and its `daily_advantage` seeds HCH's shadow breaker. (3) **`multi_window`** — runs the compare over N windows and aggregates the excess deltas into a win-rate / sign-consistency diagnostic, explicitly framed as noise-level (not a significance test).

**Tech Stack:** Python ≥3.11, pydantic v2, pytest. Reuses US-2c `InnerLoop`/`LoopConfig`/`LoopReport`/`floor_breaker`, US-1d `WalkForwardEval`/`report_from_trajectory`/`EvalReport`/baselines, US-2a `LLMAgentPolicy`/`MockLLMClient`. Offline tests use `MockLLMClient` + a stub scorer + deterministic factories; no network.

**Spec:** `docs/superpowers/specs/2026-06-13-us-market-adaptation-design.md` (§4 inner loop, §7 advantage, §9/§10/§12 the honest bar). CN reference (algorithm source, reframed US-native): `reference/cn/youzi/loop/compare.py`, `reference/cn/youzi/loop/inner_loop.py` (shadow branch).

**Scope — what US-2d builds vs defers:**
- **BUILD:** the shadow/paired breaker path; the 3-arm `compare_harnesses` + `ComparisonReport`/`ArmReport` + `daily_advantage`; the `multi_window` noise-aware aggregator.
- **DEFER (documented, not built — the required "validation" slice, US-2e):** the formal statistical layer (`eval/stats.py`: moving-block-bootstrap CI, sign-permutation p-value, MDE sizing, `StatVerdict`); purged + embargoed CV; regime-stratified evaluation; the Hcredit (C4) ablation arm; and the **offense-vs-defense + per-family contribution split (SPEC-REQUIRED, §6/§9/§10 — not generic future work)**. **Why:** a single ~30-day delta is NOISE (MDE ~0.26, spec §12); the formal significance apparatus is its own slice. `multi_window`'s win-rate/sign across windows is the honest interim diagnostic, and `ComparisonReport` stays forward-compatible (the deferred `stat_verdict` is an additive Optional field later — old reports round-trip).
- **Spec-acceptance boundary (important — do not over-claim):** spec §9/§10 **define** US-2 acceptance AS the formal statistical decision procedure (multi-seed, paired HCH−Hexpert with CI, temp=0, window sized so MDE < effect, offense/defense contribution). US-2d therefore delivers the **measuring apparatus** (the compare + shadow breaker + a noise-aware direction diagnostic) but does **NOT** by itself clear the US-2 acceptance bar. The **US-2e validation slice is a required, acceptance-completing follow-on — not an optional OR with US-3.**
- **Precondition (not new code):** temp=0 for all eval LLM clients (spec §8 — kills frozen-arm resampling drift); `make_client` already defaults temp=0.

**Conventions:** all code/comments English; `from __future__ import annotations` atop every module; commit after each passing task; run via `python -m pytest`.

**Key invariants (each gets a test):**
1. `_shadow_trip(diffs,k,λ,ε)` trips iff `mean(diffs[-k:]) < −max(λ·stdev, ε)` AND the count of strictly-negative days in the window `≥ ceil(k/2)+1` (direction gate). `_shadow_eps_abs` returns `c·MAD(nonzero shadow)`, falling back to `floor` when the shadow is all-zero or constant. Pure + hand-computable.
2. The InnerLoop shadow branch (when `shadow_daily` is set) filters the reference to `d ≤ cur_max` (anti-lookahead), compares only `common` dates, and reuses the existing rollback/freeze machinery; `shadow_daily=None` is the unchanged fallback path (all US-2c tests stay green).
3. `compare_harnesses` runs all arms on the **same** source/window/horizon/scorer via **factories** (each arm gets a fresh `H`/client/store — call counts harness 2, agent 2, refiner 1, store 1); `hch_beats_hexpert = (HCH.mean_excess − Hexpert.mean_excess) > 0`.
4. When `shadow=True`, Hexpert runs **first** and its `daily_advantage` series is injected as HCH's `shadow_daily`; `report_from_trajectory` is always called with `horizon=cfg.horizon`.
5. `multi_window` aggregates per-window excess deltas into `mean_delta` / `win_rate` / `sign_consistent`, with a docstring stating few-window deltas are noise (not a significance test).

---

### Task 1: Shadow breaker pure functions

**Files:**
- Modify: `alpha/loop/floor_breaker.py`
- Modify: `tests/loop/test_floor_breaker.py`

Add the paired/shadow trip functions next to the existing `_fallback_trip` (reuse `_mad`/`_MAD_EPS`).

- [ ] **Step 1: Write the failing test (append to `tests/loop/test_floor_breaker.py`)**

```python
from alpha.loop.floor_breaker import _shadow_eps_abs, _shadow_trip, _ZERO_EPS


def test_shadow_eps_abs():
    assert _ZERO_EPS == 1e-12
    assert _shadow_eps_abs([0.0, 0.0, 0.0], c=0.25, floor=0.05) == 0.05    # all-zero -> floor
    assert _shadow_eps_abs([0.3, 0.3, 0.3], c=0.25, floor=0.05) == 0.05    # constant (MAD~0) -> floor
    # varied: median=0.4; devs=[.1,0,.1]; MAD=0.1 -> eps = 0.25*0.1 = 0.025
    assert abs(_shadow_eps_abs([0.3, 0.4, 0.5], c=0.25, floor=0.01) - 0.025) < 1e-9


def test_shadow_trip_main_and_direction_gate():
    # clean degradation: all diffs -0.5, sd=0 -> thr=max(0, eps=0.1)=0.1; mean -0.5 < -0.1; n_neg=4 >= ceil(4/2)+1=3
    trip, rolling, thr, reason = _shadow_trip([-0.5, -0.5, -0.5, -0.5], k=4, lam=1.0, eps_abs=0.1)
    assert trip is True and abs(rolling - (-0.5)) < 1e-9 and "shadow" in reason


def test_shadow_direction_gate_blocks_single_big_negative():
    # lam=0 -> thr=eps_abs=0.1. mean = (0.5+0.5-1.4)/3 = -0.1333 < -0.1 (main gate PASSES)
    # but only 1 negative day; need = ceil(3/2)+1 = 3 -> direction gate BLOCKS -> no trip
    trip, _, _, _ = _shadow_trip([0.5, 0.5, -1.4], k=3, lam=0.0, eps_abs=0.1)
    assert trip is False


def test_shadow_no_trip_when_healthy():
    trip, _, _, _ = _shadow_trip([0.2, 0.2, 0.2], k=3, lam=1.0, eps_abs=0.05)
    assert trip is False
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/loop/test_floor_breaker.py -q`
Expected: FAIL — `ImportError: cannot import name '_shadow_eps_abs' from 'alpha.loop.floor_breaker'`

- [ ] **Step 3: Write the implementation**

In `alpha/loop/floor_breaker.py`, add `import math` to the imports (alongside `import statistics`), add the `_ZERO_EPS` constant under `_MAD_EPS`, and append the two functions:

```python
import math   # add alongside `import statistics`
```

```python
_ZERO_EPS = 1e-12   # a shadow advantage below this magnitude counts as exactly zero (excluded from MAD)
```

```python
def _shadow_eps_abs(shadow_vals: list[float], c: float, floor: float) -> float:
    """Absolute epsilon floor for the paired-diff trip: c * MAD(nonzero shadow values). Falls back to
    `floor` when the shadow series is all-zero (empty-position reference) or constant (MAD ~ 0)."""
    nz = [v for v in shadow_vals if abs(v) > _ZERO_EPS]
    if not nz:
        return floor
    m = _mad(nz)
    if m < _MAD_EPS:
        return floor
    return c * m


def _shadow_trip(diffs: list[float], k: int, lam: float,
                 eps_abs: float) -> tuple[bool, float, float, str]:
    """Paired/shadow capability-floor trip on the per-day (own − reference) advantage diff series.
    Trip iff mean(diffs[-k:]) < −max(lam·stdev, eps_abs) (own under the reference by a real margin) AND
    the direction sub-gate holds: #strictly-negative days in the window >= ceil(k/2)+1 (blocks a single
    big-negative day). Returns (tripped, rolling, threshold, reason) — same 4-tuple shape as _fallback_trip
    so the inner-loop rollback/freeze machinery is shared. Caller guarantees 1 <= k <= len(diffs)."""
    window = diffs[-k:]
    mean_d = sum(window) / len(window)
    sd = statistics.stdev(window) if len(window) >= 2 else 0.0
    thr = max(lam * sd, eps_abs)
    n_neg = sum(1 for d in window if d < 0.0)
    need = math.ceil(k / 2) + 1
    trip = (mean_d < -thr) and (n_neg >= need)
    return (trip, mean_d, -thr, "shadow: mean(diff) < -max(lambda*sd, eps) & direction gate")
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/loop/test_floor_breaker.py -q`
Expected: PASS (8 passed) — the 4 pre-existing fallback tests + the 4 new shadow tests.

- [ ] **Step 5: Commit**

```bash
git add alpha/loop/floor_breaker.py tests/loop/test_floor_breaker.py
git commit -m "US-2d Task 1: shadow breaker pure functions (_shadow_eps_abs / _shadow_trip; paired-diff + direction gate)"
```

---

### Task 2: Wire the shadow path into the InnerLoop

**Files:**
- Modify: `alpha/loop/inner_loop.py`
- Create: `tests/loop/test_inner_loop_shadow.py`

Add `shadow_daily` + the `breaker_shadow_*` config, and a shadow branch in the breaker block that reuses the existing rollback/freeze machinery.

- [ ] **Step 1: Write the failing test**

```python
# tests/loop/test_inner_loop_shadow.py
import tempfile
from datetime import date
import pandas as pd
from alpha.data.source import FakeSource
from alpha.harness.skill import Skill
from alpha.harness.doctrine import Doctrine
from alpha.harness.registry import SkillRegistry, MemoryStore
from alpha.harness.state import HarnessState
from alpha.harness.snapshot import SnapshotStore
from alpha.harness.manager import HarnessManager
from alpha.eval.decision import Candidate, DecisionPackage
from alpha.eval.metrics import ScoredCandidate
from alpha.llm.client import MockLLMClient
from alpha.loop.inner_loop import InnerLoop, LoopConfig


class _PickRun:
    def decide(self, state, universe):
        return DecisionPackage(date=state.date,
                               candidates=[Candidate(symbol=s.symbol, pattern="gap_and_go")
                                           for s in universe.all()])


class _SchedScorer:
    def __init__(self, sched): self._sched = sched
    def score_step(self, decision, decision_mem, exit_mem, entry_day, exit_day, oracle):
        adv = self._sched.get(decision.date, 0.0)
        return {c.symbol: ScoredCandidate(decision_date=decision.date, symbol=c.symbol, pattern=c.pattern,
                                          outcome=("continued" if adv >= 0 else "nuked"),
                                          score=adv, day_baseline=0.0) for c in decision.candidates}


def _source(n):
    cal = [date(2026, 6, d) for d in range(1, 1 + n)]
    snaps, px = {}, 10.0
    closes = []
    for d in cal:
        prev = px; px = px * 1.2; closes.append(px)
        snaps[d] = pd.DataFrame({"symbol": ["RUN"], "name": ["RUN"], "open": [prev], "high": [px],
                                 "low": [prev], "close": [px], "volume": [1], "prev_close": [prev]})
    bars = {"RUN": pd.DataFrame({"date": cal, "open": [10.0] + closes[:-1], "high": closes,
                                 "low": [10.0] + closes[:-1], "close": closes, "volume": [1] * n})}
    return FakeSource(calendar=cal, bars=bars, snapshots=snaps)


def _h():
    return HarnessState(doctrine=Doctrine(),
                        skills=SkillRegistry.from_skills([Skill(skill_id="gap_and_go", name="G",
                                                               type="pattern", status="active")]),
                        memory=MemoryStore.from_lessons([]))


def _loop(src, cfg, sched, shadow_daily):
    mgr = HarnessManager(_h(), SnapshotStore(tempfile.mkdtemp()))
    return InnerLoop(mgr, src, src.trading_calendar()[0], src.trading_calendar()[-1],
                     agent_llm=MockLLMClient("{}"), refiner_llm=MockLLMClient('{"ops": []}'),
                     config=cfg, scorer=_SchedScorer(sched), agent_factory=lambda h: _PickRun(),
                     shadow_daily=shadow_daily)


def test_shadow_path_trips_when_own_below_reference():
    src = _source(8)
    cal = src.trading_calendar()
    own = {d: -0.3 for d in cal}            # HCH advantage degraded vs the reference
    shadow = {d: 0.3 for d in cal}          # frozen-expert reference is healthy -> diff = -0.6/day
    cfg = LoopConfig(horizon=2, enable_refine=False, breaker_min_days=3, breaker_k_max=3)
    loop = _loop(src, cfg, own, shadow_daily=shadow)
    report = loop.run()
    assert report.breaker_events                                # the shadow path tripped
    assert "shadow" in report.breaker_events[-1].reason         # via the paired-diff trip
    assert report.frozen_from is not None                       # no checkpoints (enable_refine=False) -> freeze


def test_shadow_none_uses_fallback_path():
    src = _source(8)
    cal = src.trading_calendar()
    own = {cal[k]: (0.3 if k < 3 else -0.9) for k in range(8)}  # degrade -> fallback floor_abs trip
    cfg = LoopConfig(horizon=2, enable_refine=False, breaker_min_days=3, breaker_k_max=3, floor_abs=0.0)
    loop = _loop(src, cfg, own, shadow_daily=None)
    report = loop.run()
    assert report.breaker_events and "shadow" not in report.breaker_events[-1].reason   # fallback, not shadow


def test_shadow_future_only_series_is_ignored_anti_lookahead():
    src = _source(8)
    # reference series keyed ONLY by dates AFTER the run window -> filtered out -> no common days -> no trip
    shadow = {date(2026, 7, d): 0.3 for d in range(1, 9)}
    own = {d: -0.5 for d in src.trading_calendar()}            # own is awful, but there's nothing to pair with
    cfg = LoopConfig(horizon=2, enable_refine=False, breaker_min_days=3, breaker_k_max=3)
    loop = _loop(src, cfg, own, shadow_daily=shadow)
    report = loop.run()
    assert report.breaker_events == [] and report.frozen_from is None   # future-only reference never trips
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/loop/test_inner_loop_shadow.py -q`
Expected: FAIL — `TypeError: InnerLoop.__init__() got an unexpected keyword argument 'shadow_daily'`

- [ ] **Step 3: Write the implementation**

In `alpha/loop/inner_loop.py`:

(a) Extend the floor_breaker import:

```python
from alpha.loop.floor_breaker import _fallback_trip, _shadow_eps_abs, _shadow_trip
```

(b) Append the three shadow fields to `LoopConfig` (after `enable_refine: bool = True`):

```python
    breaker_shadow_lambda: float = Field(default=1.0, ge=0.0)
    breaker_shadow_eps_c: float = Field(default=0.25, ge=0.0)
    breaker_shadow_eps_floor: float = Field(default=0.05, ge=0.0)
```

(c) Add the `shadow_daily` param to `InnerLoop.__init__` (after `agent_factory`) and store a defensive copy. Change the signature line and add the storage line:

```python
                 agent_factory: Callable[[HarnessState], DecisionPolicy] | None = None,
                 shadow_daily: dict[Date, float] | None = None) -> None:
```

```python
        self._agent_factory = agent_factory
        self._shadow_daily = dict(shadow_daily) if shadow_daily is not None else None
        self._rebind()
```

(d) Replace the head of the breaker block — the `if not frozen ...` line through `breaker_trips += 1` — so the trip metrics come from the shadow path (when `shadow_daily` is set) or the fallback path, then the shared rollback/freeze machinery runs unchanged. Replace:

```python
            if not frozen and len(breaker_days) >= cfg.breaker_min_days:
                k = min(len(breaker_days), cfg.breaker_k_max)
                history = [v for _, v in breaker_days]
                trip, rolling, thr, reason = _fallback_trip(history, k, cfg.breaker_mad_c, cfg.floor_abs)
                if trip:
                    window_start = breaker_days[-k][0]
                    breaker_trips += 1
```

with:

```python
            if not frozen and len(breaker_days) >= cfg.breaker_min_days:
                trip = False
                rolling = thr = 0.0
                reason = ""
                window_start = None
                if self._shadow_daily is not None:
                    # SHADOW (paired) path: judge HCH's daily advantage against the frozen-expert reference.
                    cur_max = breaker_days[-1][0]
                    own = {d: v for d, v in breaker_days}
                    shadow = {d: s for d, s in self._shadow_daily.items() if d <= cur_max}   # anti-lookahead
                    common = sorted(own.keys() & shadow.keys())
                    if len(common) >= cfg.breaker_min_days:
                        k = min(len(common), cfg.breaker_k_max)
                        diffs = [own[d] - shadow[d] for d in common]
                        eps = _shadow_eps_abs(list(shadow.values()), cfg.breaker_shadow_eps_c,
                                              cfg.breaker_shadow_eps_floor)
                        trip, rolling, thr, reason = _shadow_trip(diffs, k, cfg.breaker_shadow_lambda, eps)
                        window_start = common[-k]
                else:
                    k = min(len(breaker_days), cfg.breaker_k_max)
                    history = [v for _, v in breaker_days]
                    trip, rolling, thr, reason = _fallback_trip(history, k, cfg.breaker_mad_c, cfg.floor_abs)
                    window_start = breaker_days[-k][0]
                if trip:
                    breaker_trips += 1
```

(Everything below `breaker_trips += 1` — `target = max(...)`, the rollback/freeze branches, the `BreakerEvent` appends — is unchanged and now serves both paths. **Executor caution:** keep the new `if trip:` at the same indentation as the original so the unchanged tail stays nested under it; do NOT hoist `target = max((v for v, d in ckpts if d < window_start), default=None)` out of `if trip:` — `window_start` is `None` on the shadow no-common-days path and `None < date` would raise. Run `python -m pytest tests/loop -q` after the edit to confirm the US-2c breaker tests stay green.)

- [ ] **Step 4: Run the focused test + the full loop suite**

Run: `python -m pytest tests/loop -q`
Expected: PASS — the new shadow tests pass AND all US-2c inner-loop/breaker tests stay green (`shadow_daily=None` preserves the fallback path).

- [ ] **Step 5: Commit**

```bash
git add alpha/loop/inner_loop.py tests/loop/test_inner_loop_shadow.py
git commit -m "US-2d Task 2: wire shadow/paired breaker into InnerLoop (shadow_daily + anti-lookahead; None=fallback)"
```

---

### Task 3: The three-way compare

**Files:**
- Create: `alpha/loop/compare.py`
- Create: `tests/loop/test_compare.py`

`compare_harnesses` runs HCH/Hexpert/Hmin on the same data via factories and returns a `ComparisonReport`.

- [ ] **Step 1: Write the failing test**

```python
# tests/loop/test_compare.py
import tempfile
from datetime import date
import pandas as pd
from alpha.data.source import FakeSource
from alpha.harness.loader import load_seeds
from alpha.harness.snapshot import SnapshotStore
from alpha.llm.client import MockLLMClient
from alpha.loop.inner_loop import LoopConfig
from alpha.loop.compare import compare_harnesses, ComparisonReport, daily_advantage
from pathlib import Path

SEEDS = Path(__file__).resolve().parents[2] / "seeds"


def _source(n, rate):
    cal = [date(2026, 6, d) for d in range(1, 1 + n)]
    snaps, px = {}, 10.0
    closes = []
    for d in cal:
        prev = px; px = px * rate; closes.append(px)
        snaps[d] = pd.DataFrame({"symbol": ["RUN"], "name": ["RUN"], "open": [prev], "high": [px],
                                 "low": [prev], "close": [px], "volume": [1], "prev_close": [prev]})
    bars = {"RUN": pd.DataFrame({"date": cal, "open": [10.0] + closes[:-1], "high": closes,
                                 "low": [10.0] + closes[:-1], "close": closes, "volume": [1] * n})}
    return FakeSource(calendar=cal, bars=bars, snapshots=snaps)


class _Counter:
    """Counts calls; returns a fresh object from `make` each time (factory isolation)."""
    def __init__(self, make): self._make = make; self.calls = 0
    def __call__(self): self.calls += 1; return self._make()


def _cfg():
    return LoopConfig(horizon=2, evidence_min=2, refine_every=1)


def test_four_arms_and_factory_isolation():
    src = _source(6, 1.15)                                  # +15%/day: RUN in-universe, advantage > 0
    hf = _Counter(lambda: load_seeds(SEEDS))
    af = _Counter(lambda: MockLLMClient('{"regime_read": "trend", "candidates": '
                                        '[{"symbol": "RUN", "pattern": "gap_and_go", "confidence": 0.7}]}'))
    rf = _Counter(lambda: MockLLMClient('{"ops": []}'))
    sf = _Counter(lambda: SnapshotStore(tempfile.mkdtemp()))
    cr = compare_harnesses(hf, src, src.trading_calendar()[0], src.trading_calendar()[-1],
                           agent_llm_factory=af, refiner_llm_factory=rf, store_factory=sf, loop_config=_cfg())
    assert isinstance(cr, ComparisonReport)
    assert set(cr.arms) == {"HCH", "Hexpert", "Hmin_chase", "Hmin_notrade"}
    assert hf.calls == 2 and af.calls == 2 and rf.calls == 1 and sf.calls == 1   # factory isolation
    # same agent script for HCH & Hexpert -> identical picks -> excess delta ~ 0 -> verdict False
    assert cr.hch_beats_hexpert is False and abs(cr.hch_minus_hexpert_mean_excess) < 1e-9
    assert cr.hch_loop_report is not None and cr.arms["HCH"].n_refines is not None


def test_hch_beats_hexpert_when_excess_higher():
    src = _source(6, 1.15)
    hf = lambda: load_seeds(SEEDS)
    # run-order (shadow=False) is HCH then Hexpert -> seq factory gives HCH a winner, Hexpert no-trade
    seq = iter([MockLLMClient('{"candidates": [{"symbol": "RUN", "pattern": "gap_and_go"}]}'),
                MockLLMClient('{"no_trade_reason": "flat", "candidates": []}')])
    af = lambda: next(seq)
    cr = compare_harnesses(hf, src, src.trading_calendar()[0], src.trading_calendar()[-1],
                           agent_llm_factory=af, refiner_llm_factory=lambda: MockLLMClient('{"ops": []}'),
                           store_factory=lambda: SnapshotStore(tempfile.mkdtemp()), loop_config=_cfg())
    assert cr.hch_minus_hexpert_mean_excess > 0 and cr.hch_beats_hexpert is True


def test_shadow_runs_hexpert_first_and_completes():
    src = _source(8, 1.15)
    hf = lambda: load_seeds(SEEDS)
    af = lambda: MockLLMClient('{"candidates": [{"symbol": "RUN", "pattern": "gap_and_go"}]}')
    cr = compare_harnesses(hf, src, src.trading_calendar()[0], src.trading_calendar()[-1],
                           agent_llm_factory=af, refiner_llm_factory=lambda: MockLLMClient('{"ops": []}'),
                           store_factory=lambda: SnapshotStore(tempfile.mkdtemp()), loop_config=_cfg(),
                           shadow=True)
    assert set(cr.arms) == {"HCH", "Hexpert", "Hmin_chase", "Hmin_notrade"}   # shadow path completes end-to-end


def test_daily_advantage_mirrors_breaker_formula():
    src = _source(6, 1.15)
    from alpha.eval.walk_forward import WalkForwardEval
    from alpha.eval.scorer import ReturnScorer
    from alpha.agent.agent import LLMAgentPolicy
    traj = WalkForwardEval(src, src.trading_calendar()[0], src.trading_calendar()[-1], horizon=2,
                           scorer=ReturnScorer()).walk(
        LLMAgentPolicy(load_seeds(SEEDS),
                       MockLLMClient('{"candidates": [{"symbol": "RUN", "pattern": "gap_and_go"}]}')))
    da = daily_advantage(traj)
    assert da and all(isinstance(k, date) for k in da)        # keyed by decision date, one per scored step
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/loop/test_compare.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'alpha.loop.compare'`

- [ ] **Step 3: Write the implementation**

```python
# alpha/loop/compare.py
from __future__ import annotations

from datetime import date as Date
from typing import Callable

from pydantic import BaseModel, ConfigDict, Field

from alpha.agent.agent import LLMAgentPolicy
from alpha.eval.baselines import ChaseBiggestGainerPolicy, NoTradePolicy
from alpha.eval.metrics import EvalReport
from alpha.eval.scorer import ReturnScorer
from alpha.eval.trajectory import Trajectory, report_from_trajectory
from alpha.eval.walk_forward import WalkForwardEval
from alpha.harness.manager import HarnessManager
from alpha.harness.snapshot import SnapshotStore
from alpha.harness.state import HarnessState
from alpha.llm.client import LLMClient
from alpha.loop.inner_loop import InnerLoop, LoopConfig, LoopReport
from alpha.refine.refiner import RefinerConfig


def daily_advantage(traj: Trajectory) -> dict[Date, float]:
    """Per-decision-day mean advantage from a Trajectory (empty/no-trade day -> 0.0, NOT excluded).
    Byte-identical to InnerLoop's internal breaker_days rule, so the Hexpert series and HCH's own
    series are the same lens — this is the shadow reference for HCH's paired breaker."""
    out: dict[Date, float] = {}
    for step in traj.scored_steps():
        advs = [c.advantage for c in step.outcomes.values()]
        out[step.date] = sum(advs) / len(advs) if advs else 0.0
    return out


class ArmReport(BaseModel):
    """One arm's result. n_refines/n_breaker_trips/frozen_from are HCH-only (None for frozen/baseline arms)."""
    model_config = ConfigDict(frozen=True)
    name: str
    report: EvalReport
    n_refines: int | None = None
    n_breaker_trips: int | None = None
    frozen_from: Date | None = None


class ComparisonReport(BaseModel):
    """Three-way compare. The North-Star verdict is on the EXCESS (advantage) delta, de-market-beta."""
    model_config = ConfigDict(frozen=True)
    arms: dict[str, ArmReport] = Field(default_factory=dict)
    hch_minus_hexpert_mean_excess: float
    hch_minus_hexpert_mean_score: float
    hch_minus_hexpert_hit_rate: float
    hch_minus_hexpert_nuke_rate: float
    hch_beats_hexpert: bool
    hch_loop_report: LoopReport | None = None


def compare_harnesses(harness_factory: Callable[[], HarnessState], source, start: Date, end: Date, *,
                      agent_llm_factory: Callable[[], LLMClient],
                      refiner_llm_factory: Callable[[], LLMClient],
                      store_factory: Callable[[], SnapshotStore],
                      loop_config: LoopConfig | None = None,
                      refiner_config: RefinerConfig | None = None,
                      scorer_factory: Callable[[], object] | None = None,
                      shadow: bool = False) -> ComparisonReport:
    """Run HCH (self-refining InnerLoop) vs Hexpert (frozen seed H + agent, NO Refiner) vs Hmin
    (chase-biggest-gainer + no-trade) on the SAME source/window/horizon/scorer. All inputs are FACTORIES
    so each arm gets a fresh H / LLM client / store (no cross-arm pollution; MockLLMClient is stateful).
    When shadow=True, Hexpert runs FIRST and its daily_advantage seeds HCH's paired breaker.
    scorer_factory MUST return a STATELESS scorer (the wf instance's scorer is shared across Hexpert +
    both Hmin arms); ReturnScorer (the default) is stateless."""
    cfg = loop_config or LoopConfig()
    scorer_factory = scorer_factory or (lambda: ReturnScorer())
    wf = WalkForwardEval(source, start, end, horizon=cfg.horizon, scorer=scorer_factory())

    # Hexpert FIRST when shadow (its series seeds HCH); frozen H = bare agent walk, no Refiner/manager.
    hexpert_traj = wf.walk(LLMAgentPolicy(harness_factory(), agent_llm_factory())) if shadow else None

    # HCH = self-refining InnerLoop (optionally shadow-gated against the Hexpert reference series)
    mgr = HarnessManager(harness_factory(), store_factory())
    loop = InnerLoop(mgr, source, start, end, agent_llm_factory(), refiner_llm_factory(),
                     config=cfg, refiner_config=refiner_config, scorer=scorer_factory(),
                     shadow_daily=(daily_advantage(hexpert_traj) if shadow else None))
    lr = loop.run()
    hch_eval = report_from_trajectory(lr.trajectory, horizon=cfg.horizon)

    # Hexpert (reuse the shadow pre-run trajectory, else run it now)
    if hexpert_traj is None:
        hexpert_traj = wf.walk(LLMAgentPolicy(harness_factory(), agent_llm_factory()))
    hexpert_eval = report_from_trajectory(hexpert_traj, horizon=cfg.horizon)

    # Hmin floor baselines (deterministic, no LLM/H/store)
    hmin_chase = wf.run(ChaseBiggestGainerPolicy())
    hmin_notrade = wf.run(NoTradePolicy())

    arms = {
        "HCH": ArmReport(name="HCH", report=hch_eval, n_refines=len(lr.refine_events),
                         n_breaker_trips=len(lr.breaker_events), frozen_from=lr.frozen_from),
        "Hexpert": ArmReport(name="Hexpert", report=hexpert_eval),
        "Hmin_chase": ArmReport(name="Hmin_chase", report=hmin_chase),
        "Hmin_notrade": ArmReport(name="Hmin_notrade", report=hmin_notrade),
    }
    d_excess = hch_eval.mean_excess - hexpert_eval.mean_excess
    return ComparisonReport(
        arms=arms,
        hch_minus_hexpert_mean_excess=d_excess,
        hch_minus_hexpert_mean_score=hch_eval.mean_score - hexpert_eval.mean_score,
        hch_minus_hexpert_hit_rate=hch_eval.hit_rate - hexpert_eval.hit_rate,
        hch_minus_hexpert_nuke_rate=hch_eval.nuke_rate - hexpert_eval.nuke_rate,
        hch_beats_hexpert=(d_excess > 0.0),
        hch_loop_report=lr,
    )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/loop/test_compare.py -q`
Expected: PASS (4 passed) — this file grows to 5 in Task 4.

- [ ] **Step 5: Commit**

```bash
git add alpha/loop/compare.py tests/loop/test_compare.py
git commit -m "US-2d Task 3: three-way compare (compare_harnesses / ComparisonReport / daily_advantage; factory isolation)"
```

---

### Task 4: Multi-window honest-bar diagnostic

**Files:**
- Modify: `alpha/loop/compare.py`
- Modify: `tests/loop/test_compare.py`

`multi_window` runs the compare over N windows and aggregates the excess deltas into a noise-aware win-rate / sign diagnostic (NOT a significance test).

- [ ] **Step 1: Write the failing test (append to `tests/loop/test_compare.py`)**

```python
from alpha.loop.compare import multi_window, MultiWindowReport


def test_multi_window_aggregates_deltas():
    src = _source(10, 1.15)
    cal = src.trading_calendar()
    windows = [(cal[0], cal[4]), (cal[5], cal[9])]              # two non-overlapping windows
    hf = lambda: load_seeds(SEEDS)
    af = lambda: MockLLMClient('{"candidates": [{"symbol": "RUN", "pattern": "gap_and_go"}]}')
    mw = multi_window(hf, src, windows, agent_llm_factory=af,
                      refiner_llm_factory=lambda: MockLLMClient('{"ops": []}'),
                      store_factory=lambda: SnapshotStore(tempfile.mkdtemp()), loop_config=_cfg())
    assert isinstance(mw, MultiWindowReport)
    assert mw.n_windows == 2 and len(mw.deltas) == 2
    assert 0.0 <= mw.win_rate <= 1.0
    assert abs(mw.mean_delta - sum(mw.deltas) / 2) < 1e-9
    assert isinstance(mw.sign_consistent, bool)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/loop/test_compare.py::test_multi_window_aggregates_deltas -q`
Expected: FAIL — `ImportError: cannot import name 'multi_window' from 'alpha.loop.compare'`

- [ ] **Step 3: Write the implementation (append to `alpha/loop/compare.py`)**

```python
class MultiWindowReport(BaseModel):
    """Honest-bar DIAGNOSTIC across N (start, end) windows. NOTE: few/short-window excess deltas are
    NOISE (MDE ~0.26 at ~30 trading days, spec §12) — this surfaces the direction/distribution
    (win-rate, sign-consistency), it is NOT a significance test. Formal CI/MDE/purged-CV are deferred."""
    model_config = ConfigDict(frozen=True)
    n_windows: int
    deltas: list[float] = Field(default_factory=list)   # hch_minus_hexpert_mean_excess per window
    mean_delta: float = 0.0
    win_rate: float = 0.0                                # fraction of windows with delta > 0
    sign_consistent: bool = False                       # all deltas strictly same sign


def multi_window(harness_factory: Callable[[], HarnessState], source,
                 windows: list[tuple[Date, Date]], *,
                 agent_llm_factory: Callable[[], LLMClient],
                 refiner_llm_factory: Callable[[], LLMClient],
                 store_factory: Callable[[], SnapshotStore],
                 loop_config: LoopConfig | None = None,
                 refiner_config: RefinerConfig | None = None,
                 scorer_factory: Callable[[], object] | None = None,
                 shadow: bool = False) -> MultiWindowReport:
    """Run compare_harnesses over each window; aggregate the excess deltas. A direction diagnostic, not
    a significance test (see MultiWindowReport)."""
    deltas: list[float] = []
    for (start, end) in windows:
        cr = compare_harnesses(harness_factory, source, start, end, agent_llm_factory=agent_llm_factory,
                               refiner_llm_factory=refiner_llm_factory, store_factory=store_factory,
                               loop_config=loop_config, refiner_config=refiner_config,
                               scorer_factory=scorer_factory, shadow=shadow)
        deltas.append(cr.hch_minus_hexpert_mean_excess)
    n = len(deltas)
    mean_delta = sum(deltas) / n if n else 0.0
    win_rate = sum(1 for d in deltas if d > 0.0) / n if n else 0.0
    sign_consistent = n > 0 and (all(d > 0.0 for d in deltas) or all(d < 0.0 for d in deltas))
    return MultiWindowReport(n_windows=n, deltas=deltas, mean_delta=mean_delta,
                             win_rate=win_rate, sign_consistent=sign_consistent)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/loop/test_compare.py -q`
Expected: PASS (5 passed)

- [ ] **Step 5: Commit**

```bash
git add alpha/loop/compare.py tests/loop/test_compare.py
git commit -m "US-2d Task 4: multi_window honest-bar diagnostic (win-rate / sign across windows; noise-aware)"
```

---

### Task 5: US-2d acceptance gate + docs update

**Files:**
- Create: `tests/loop/test_us2d_acceptance.py`
- Modify: `docs/PROJECT_STATE.md` (mark US-2d done)

End-to-end on the real seeds: the three-way compare runs HCH/Hexpert/Hmin (with the shadow breaker armed off the Hexpert series) and produces a `ComparisonReport`; a `multi_window` diagnostic aggregates across windows; the firewall holds.

- [ ] **Step 1: Write the acceptance test**

```python
# tests/loop/test_us2d_acceptance.py
"""US-2d acceptance: the three-way HCH/Hexpert/Hmin compare runs end-to-end on the SEEDED harness with
the SHADOW breaker armed off the Hexpert reference, produces a ComparisonReport (excess delta + verdict
+ all four arms), and a multi_window diagnostic aggregates across windows. Validates the loop's measuring
apparatus; real efficacy needs temp=0 Claude/DeepSeek (MockLLM ignores prompts)."""
import tempfile
from pathlib import Path
from datetime import date
import pandas as pd
from alpha.data.source import FakeSource
from alpha.harness.loader import load_seeds
from alpha.harness.snapshot import SnapshotStore
from alpha.llm.client import MockLLMClient
from alpha.loop.inner_loop import LoopConfig
from alpha.loop.compare import compare_harnesses, multi_window, ComparisonReport

SEEDS = Path(__file__).resolve().parents[2] / "seeds"


def _source(n=10):
    cal = [date(2026, 6, d) for d in range(1, 1 + n)]
    snaps, px = {}, 10.0
    closes = []
    for d in cal:
        prev = px; px = px * 1.15; closes.append(px)         # +15%/day: in-universe, advantage > 0, no breaker trip
        snaps[d] = pd.DataFrame({"symbol": ["RUN"], "name": ["RUN"], "open": [prev], "high": [px],
                                 "low": [prev], "close": [px], "volume": [1], "prev_close": [prev]})
    bars = {"RUN": pd.DataFrame({"date": cal, "open": [10.0] + closes[:-1], "high": closes,
                                 "low": [10.0] + closes[:-1], "close": closes, "volume": [1] * n})}
    return FakeSource(calendar=cal, bars=bars, snapshots=snaps)


def _agent():
    return MockLLMClient('{"regime_read": "trend", "candidates": '
                         '[{"symbol": "RUN", "pattern": "gap_and_go", "confidence": 0.7}]}')


def test_three_way_compare_with_shadow_end_to_end():
    src = _source(10)
    cal = src.trading_calendar()
    cr = compare_harnesses(lambda: load_seeds(SEEDS), src, cal[0], cal[-1],
                           agent_llm_factory=_agent,
                           refiner_llm_factory=lambda: MockLLMClient('{"ops": []}'),
                           store_factory=lambda: SnapshotStore(tempfile.mkdtemp()),
                           loop_config=LoopConfig(horizon=2, evidence_min=2, refine_every=1),
                           shadow=True)
    assert isinstance(cr, ComparisonReport)
    assert set(cr.arms) == {"HCH", "Hexpert", "Hmin_chase", "Hmin_notrade"}
    # every arm produced a real EvalReport over the same window
    assert all(a.report.n_decisions == 10 for a in cr.arms.values())
    assert isinstance(cr.hch_beats_hexpert, bool) and cr.hch_loop_report is not None
    # HCH is the only arm carrying loop telemetry; the shadow breaker did not spuriously trip on a healthy run
    assert cr.arms["HCH"].n_refines is not None and cr.arms["HCH"].frozen_from is None


def test_multi_window_diagnostic_end_to_end():
    src = _source(10)
    cal = src.trading_calendar()
    mw = multi_window(lambda: load_seeds(SEEDS), src, [(cal[0], cal[4]), (cal[5], cal[9])],
                      agent_llm_factory=_agent,
                      refiner_llm_factory=lambda: MockLLMClient('{"ops": []}'),
                      store_factory=lambda: SnapshotStore(tempfile.mkdtemp()),
                      loop_config=LoopConfig(horizon=2, evidence_min=2, refine_every=1))
    assert mw.n_windows == 2 and len(mw.deltas) == 2 and 0.0 <= mw.win_rate <= 1.0
```

- [ ] **Step 2: Run the full suite**

Run: `python -m pytest -q`
Expected: PASS — all prior tests plus the new US-2d compare/shadow tests green.

- [ ] **Step 3: Update `docs/PROJECT_STATE.md`**

Add a **US-2d** entry under the US-2 section: the compare + shadow breaker **measuring apparatus** is complete — `floor_breaker._shadow_eps_abs`/`_shadow_trip` (paired-diff trip + direction gate); `InnerLoop` shadow path (`shadow_daily` + `breaker_shadow_*` config + anti-lookahead `d ≤ cur_max` filter; `None` = fallback); `alpha/loop/compare.py` (`compare_harnesses` factory-injected runner over the three TIERS HCH/Hexpert/Hmin — Hmin realized as two floor arms, so `len(arms)==4`; `ArmReport`/`ComparisonReport` with the **excess** verdict `hch_beats_hexpert`; `daily_advantage` shadow-series helper; `multi_window` noise-aware aggregator). Note the full-suite test count. State the **honest bar** explicitly (HCH ≥ Hexpert OOS; parity is the honest expectation, beating frozen seeds is the research frontier; a single short-window delta is noise). **CRITICAL — do not imply US-2 acceptance is met:** spec §9/§10 define US-2 acceptance as the formal statistical procedure, which US-2d defers; US-2d builds the apparatus, the **acceptance gate remains OPEN**. Set the "Next" pointer to the **required US-2e validation slice** (formal stats layer: bootstrap CI / permutation-p / MDE / `StatVerdict` + purged-embargoed CV + regime-stratified eval + the **SPEC-REQUIRED offense/defense + per-family contribution split**) as the acceptance-completing step, **then** US-3 (intraday/halts/short-interest/SSR/social enrichment). Keep the rest of the deferred list: Hcredit ablation, sizing/guard→DecisionPackage wiring, master-dispatch G sub-agents.

- [ ] **Step 4: Commit**

```bash
git add tests/loop/test_us2d_acceptance.py docs/PROJECT_STATE.md
git commit -m "US-2d Task 5: acceptance gate (three-way compare + shadow + multi_window end-to-end) + PROJECT_STATE"
```

---

## Self-Review (run after writing, fix inline)

**Spec coverage (§4/§7/§9):** shadow paired-diff trip + direction gate (Task 1) ✓ · InnerLoop shadow path with anti-lookahead + None-fallback (Task 2) ✓ · 3-arm factory-injected compare with the excess verdict (Task 3) ✓ · multi-window noise-aware honest-bar diagnostic (Task 4) ✓ · end-to-end on real seeds (Task 5) ✓. **Deferred & documented:** the formal statistical layer (`eval/stats.py`: bootstrap CI / permutation-p / MDE / `StatVerdict`), purged+embargoed CV, regime-stratification, the Hcredit ablation arm, the offense/defense + per-family split → a later validation/analysis slice; `ComparisonReport` stays forward-compatible (add an Optional `stat_verdict` later).

**Type consistency:** `_shadow_trip(diffs,k,lam,eps_abs) -> (trip,rolling,thr,reason)` matches `_fallback_trip`'s 4-tuple so the shared rollback/freeze machinery is unchanged. `daily_advantage(traj) -> dict[Date,float]` mirrors the InnerLoop `breaker_days` rule and feeds `shadow_daily`. `compare_harnesses(...) -> ComparisonReport`; `ArmReport.report: EvalReport`; verdict on `mean_excess`. `report_from_trajectory(traj, horizon=cfg.horizon)` (never the default 2). `InnerLoop(..., shadow_daily=...)` is the new 10th ctor arg; `LoopConfig` gains 3 `breaker_shadow_*` fields. Factories typed `Callable[[], ...]`.

**Placeholder scan:** no TBD/TODO; every code step is complete; the shadow branch is a guarded addition (`shadow_daily is not None`) that leaves the fallback path byte-identical (US-2c tests stay green); factory call counts (2/2/1/1) are asserted; the shadow run-order (Hexpert first) is exercised.

**Scope:** compare machine + shadow breaker + multi-window diagnostic only. No formal significance testing, no ablation arm, no offense/defense split. Produces the apparatus that measures whether self-evolution (HCH) clears the frozen-expert (Hexpert) bar — honestly framed as noise at short windows.

**Adversarial-review fixes folded (2026-06-15, 4-lens review — reviewers built+ran every module; no critical findings):**
- **[important] spec-acceptance boundary:** spec §9/§10 define US-2 acceptance AS the formal statistical procedure, which US-2d defers. Reworded the scope + Task 5 PROJECT_STATE step so US-2d is the **measuring apparatus** and the **US-2e validation slice is a REQUIRED, acceptance-completing follow-on** (not an optional OR with US-3); the acceptance gate stays OPEN.
- **[minor] offense/defense + per-family split** tagged **SPEC-REQUIRED (§6/§9/§10)** in the deferred list (not generic future work).
- **[minor] doc/clarity:** "three-way" clarified as three TIERS → four arms (`len(arms)==4`); `compare_harnesses` docstring notes `scorer_factory` must be stateless; an executor caution on the breaker-block edit (keep `target=max(...)` inside `if trip:` — `window_start` is `None` on the shadow no-common path); Task 3 pass-count annotated (grows 4→5 in Task 4); `ComparisonReport` forward-compat for `stat_verdict` noted (additive Optional later, no field added now).
