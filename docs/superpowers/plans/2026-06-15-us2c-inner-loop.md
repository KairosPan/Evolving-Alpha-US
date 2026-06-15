# US-2c InnerLoop Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the self-evolving loop **come alive** — an `InnerLoop` that, per trading day, has the agent decide on the **live** harness `H`, scores at t+horizon, runs **online** credit assignment (mutating `SkillStats` in place), periodically **checkpoints + runs the Refiner** to edit `H`, and arms a **scorer-aware capability-floor breaker** that rolls back + rebinds (or freezes) when self-evolution degrades capability.

**Architecture:** Two new pieces in a new `alpha/loop/` package, plus one small refactor. (1) `score_decision()` — extracted from `WalkForwardEval._score` so the InnerLoop reuses the exact delayed-scoring/firewall plumbing without forking `walk()`. (2) `alpha/loop/floor_breaker.py` — the capability-floor breaker as pure, hand-computable functions (`_mad`, `_fallback_trip`) operating on the per-day **advantage** series (`score - same-day baseline`, which self-zeros → scorer-agnostic). (3) `alpha/loop/inner_loop.py` — `LoopConfig`/`RefineEvent`/`BreakerEvent`/`LoopReport` + the `InnerLoop` driver: one reset-free pass over the trading days on a single live `H`, interleaving act → delayed-score → online `apply_credit` → (watermark-gated) checkpoint-before-refine → breaker. On a breaker trip: first trip with a pre-degradation checkpoint → `rollback_to` + `_rebind` (rebuild agent+refiner on the restored `H`) + re-arm; second trip (or no rollback target) → permanent **freeze** (stops credit + refine, keeps scoring).

**Tech Stack:** Python ≥3.11, pydantic v2, pytest. Reuses US-1 harness (`HarnessManager`/`SnapshotStore`/`MetaTools`), US-1d eval (`WalkForwardEval`/scorer/oracle/`PoolRecord`), US-2a agent (`LLMAgentPolicy`/`make_client`), US-2b refine (`apply_credit`/`merge_credit_reports`/`extract_signatures`/`Refiner`/`Trajectory`). Offline tests use `MockLLMClient`, a stub scorer, and a deterministic `agent_factory`; no network.

**Spec:** `docs/superpowers/specs/2026-06-13-us-market-adaptation-design.md` (§4 inner loop, §7 advantage, §9/§10 the scorer-aware floor + honest bar). CN reference (algorithm source, reframed US-native): `reference/cn/youzi/loop/inner_loop.py`.

**Scope — US-2 decomposition (continuing the refined roadmap):**
- US-2a (done): LLM clients + agent (act half-loop).
- US-2b (done): Refiner + evidence substrate (trajectory/credit/signatures/4-pass refiner).
- **US-2c (THIS plan):** the InnerLoop — interleaved online credit + checkpoint-before-refine + the **fallback** scorer-aware capability-floor breaker + rollback-and-rebind / freeze. The loop self-drives.
- **US-2d (next):** the three-way **HCH/Hexpert/Hmin** compare (honest bar: HCH ≥ Hexpert OOS, multi-seed, temp=0) **and** the **shadow/paired** breaker path (`_shadow_trip` + `shadow_daily` injection) — it needs the Hexpert arm to *produce* the shadow series. `BreakerEvent.mode` already carries `'rollback'|'frozen'` so US-2d slots the shadow path in without a schema change.
- Later: wire L3 sizing / L4 guard into the agent's `DecisionPackage`; master-dispatch G sub-agents (keeps the Refiner G-pass a reserved no-op); keep-last-K checkpoint pruning (deferred debt — each checkpoint is one disk snapshot).

**Why fallback-only now:** the shadow path consumes an injected per-day `shadow_daily` series produced by a reference arm (Hexpert); that arm + the side-by-side compare is US-2d. The fallback (self-calibrating median−c·MAD floor with a `floor_abs` MAD≈0 backstop) is fully self-contained and end-to-end testable today.

**Conventions:** all code/comments English; `from __future__ import annotations` atop every module; commit after each passing task; run via `python -m pytest`.

**Key invariants (each gets a test):**
1. `score_decision()` returns `{symbol: ScoredCandidate}`; `WalkForwardEval._score` delegates to it (`list(score_decision(...).values())`) — the whole pre-existing eval suite stays green.
2. `_fallback_trip(history, k, c, floor_abs)` trips when `mean(history[-k:]) < median(history) − c·MAD(history)`; when `MAD < 1e-9` (degenerate series) it falls back to `mean(history[-k:]) < floor_abs`. Pure + hand-computable.
3. The InnerLoop runs one reset-free pass on a single live `H`: act on live `H` → delayed-score at t+horizon → `apply_credit` **once per newly-scored step** (mutating `SkillStats` cumulatively) — never double-counted.
4. Refine fires only when `enable_refine and not frozen and n_fresh ≥ evidence_min and i % refine_every == 0` (where `n_fresh` counts **candidates**, not steps); it **checkpoints before** refining and advances a non-overlapping watermark.
5. On a first breaker trip with a checkpoint before the degraded-window start → `rollback_to(target)` + `_rebind()` (agent + refiner rebuilt on the **restored** `H`, `mgr.tools` re-fetched) + re-arm (`breaker_days` cleared; the refine watermark advances past the discarded window so it is **not** re-fed). A second trip → roll back to the target if one exists, then **freeze** (no target → freeze in place): `apply_credit` stops (SkillStats stop drifting) while scoring/trajectory continue.
6. Firewall: the loop only ever scores realized t+horizon data through `GuardedSource(AsOfGuard(cursor))` with `cursor == exit_day`; no `LookaheadError`.

---

### Task 1: Extract `score_decision()` (reusable scoring)

**Files:**
- Modify: `alpha/eval/walk_forward.py`
- Create: `tests/eval/test_score_decision.py`

Extract the per-decision scoring body into a module-level function so the InnerLoop can call it; `_score` becomes a thin wrapper (preserves its list return + all existing tests).

- [ ] **Step 1: Write the failing test**

```python
# tests/eval/test_score_decision.py
from datetime import date
import pandas as pd
from alpha.data.source import FakeSource, GuardedSource
from alpha.data.firewall import AsOfGuard
from alpha.eval.oracle import PoolRecord, classify_day
from alpha.eval.scorer import ReturnScorer
from alpha.eval.walk_forward import WalkForwardEval, score_decision
from alpha.eval.decision import Candidate, DecisionPackage


def _source():
    cal = [date(2026, 6, 10), date(2026, 6, 11), date(2026, 6, 12), date(2026, 6, 15)]
    rows = {date(2026, 6, 10): [("RUN", 14.0, 10.0)], date(2026, 6, 11): [("RUN", 18.0, 14.0)],
            date(2026, 6, 12): [("RUN", 17.0, 18.0)], date(2026, 6, 15): [("RUN", 20.0, 17.0)]}
    snaps = {d: pd.DataFrame({"symbol": ["RUN"], "name": ["RUN"], "open": [r[2] for r in v],
                              "high": [r[1] for r in v], "low": [r[2] for r in v], "close": [r[1] for r in v],
                              "volume": [1], "prev_close": [r[2] for r in v]}) for d, v in rows.items()}
    bars = {"RUN": pd.DataFrame({"date": cal, "open": [10.0, 14.0, 18.0, 17.0], "high": [14, 18, 18, 20],
                                 "low": [10, 14, 17, 17], "close": [14.0, 18.0, 17.0, 20.0], "volume": [1, 1, 1, 1]})}
    return FakeSource(calendar=cal, bars=bars, snapshots=snaps)


def test_score_decision_dict_matches_score_list():
    src = _source()
    days = src.trading_calendar()
    record = PoolRecord()
    for d in days:
        record.record(d, classify_day(GuardedSource(src, AsOfGuard(d)).daily_snapshot(d)))
    dec = DecisionPackage(date=days[0], candidates=[Candidate(symbol="RUN", pattern="gap_and_go")])
    wf = WalkForwardEval(src, days[0], days[-1], horizon=2, scorer=ReturnScorer())
    as_dict = score_decision(src, wf._scorer, dec, days, 0, 2, days[2], record)   # decision j=0, exit cursor=days[2]
    as_list = wf._score(dec, days, 0, days[2], record)
    assert list(as_dict.values()) == as_list                # wrapper delegates to the function
    assert all(k == v.symbol for k, v in as_dict.items())   # keyed by symbol
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/eval/test_score_decision.py -q`
Expected: FAIL — `ImportError: cannot import name 'score_decision' from 'alpha.eval.walk_forward'`

- [ ] **Step 3: Write the implementation**

In `alpha/eval/walk_forward.py`, add the module-level function (place it just above the `WalkForwardEval` class; `ReturnOracle`, `GuardedSource`, `AsOfGuard`, `ScoredCandidate`, `PoolRecord`, `Date` are already imported in this module):

```python
def score_decision(source, scorer, decision, days: list[Date], j: int, horizon: int,
                   cursor: Date, record: PoolRecord) -> dict[str, ScoredCandidate]:
    """Score decision j (made on days[j]) at its t+horizon exit. Returns {symbol: ScoredCandidate}.
    Firewall: the oracle reads through GuardedSource(AsOfGuard(cursor)) where cursor == the exit day,
    so as_of >= exit_day (never future). Shared by WalkForwardEval._score and the US-2c InnerLoop."""
    entry_day = days[j + 1]
    exit_day = days[j + horizon]
    decision_mem = record.get(days[j])
    exit_mem = record.get(exit_day)
    oracle = ReturnOracle(GuardedSource(source, AsOfGuard(cursor)))
    return scorer.score_step(decision, decision_mem, exit_mem, entry_day, exit_day, oracle)
```

Then replace the body of `WalkForwardEval._score` with a delegation:

```python
    def _score(self, decision, days: list[Date], j: int, cursor: Date,
               record: PoolRecord) -> list[ScoredCandidate]:
        return list(score_decision(self._source, self._scorer, decision, days, j, self._horizon,
                                   cursor, record).values())
```

- [ ] **Step 4: Run the focused test + the full eval suite**

Run: `python -m pytest tests/eval -q`
Expected: PASS — the new test passes AND every pre-existing eval/walk-forward test stays green (behavior preserved).

- [ ] **Step 5: Commit**

```bash
git add alpha/eval/walk_forward.py tests/eval/test_score_decision.py
git commit -m "US-2c Task 1: extract score_decision() from WalkForwardEval._score (reusable; behavior preserved)"
```

---

### Task 2: The capability-floor breaker (pure functions)

**Files:**
- Create: `alpha/loop/__init__.py`
- Create: `alpha/loop/floor_breaker.py`
- Create: `tests/loop/__init__.py`
- Create: `tests/loop/test_floor_breaker.py`

Pure, hand-computable functions for the scorer-aware fallback floor. (Distinct from `alpha/guard/breaker.py`, the unrelated portfolio loss circuit-breaker.)

- [ ] **Step 1: Write the failing test**

```python
# tests/loop/__init__.py
```

```python
# tests/loop/test_floor_breaker.py
from alpha.loop.floor_breaker import _mad, _fallback_trip, _MAD_EPS


def test_mad():
    assert _mad([1.0, 1.0, 1.0]) == 0.0
    # median=2; abs devs=[1,0,1]; median of devs = 1
    assert _mad([1.0, 2.0, 3.0]) == 1.0


def test_fallback_trip_via_median_minus_c_mad():
    # history with spread: median & MAD nonzero -> threshold = median - c*MAD
    hist = [0.4, 0.5, 0.6, 0.5, -0.9]            # median=0.5; devs=[.1,0,.1,0,1.4]; MAD=0.1
    trip, rolling, thr, reason = _fallback_trip(hist, k=2, c=2.0, floor_abs=-0.2)
    # rolling=mean(last2)=mean(0.5,-0.9)=-0.2 ; thr=0.5-2*0.1=0.3 ; -0.2 < 0.3 -> trip
    assert trip is True and abs(rolling - (-0.2)) < 1e-9 and abs(thr - 0.3) < 1e-9
    assert "MAD" in reason


def test_fallback_trip_mad_zero_uses_floor_abs():
    hist = [0.3, 0.3, 0.3, -0.5]                  # median=0.3; devs=[0,0,0,0.8]; MAD=0 (<eps)
    trip, rolling, thr, reason = _fallback_trip(hist, k=2, c=2.0, floor_abs=-0.2)
    # MAD~0 -> threshold is floor_abs; rolling=mean(0.3,-0.5)=-0.1 ; -0.1 < -0.2? NO
    assert trip is False and abs(thr - (-0.2)) < 1e-9 and "floor_abs" in reason
    # push rolling below the floor
    trip2, rolling2, _, _ = _fallback_trip([0.3, 0.3, 0.3, -0.9], k=2, c=2.0, floor_abs=-0.2)
    assert trip2 is True and rolling2 < -0.2     # mean(0.3,-0.9)=-0.3 < -0.2


def test_fallback_no_trip_when_healthy():
    trip, _, _, _ = _fallback_trip([0.3, 0.3, 0.3, 0.3], k=3, c=2.0, floor_abs=-0.2)
    assert trip is False and _MAD_EPS == 1e-9
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/loop/test_floor_breaker.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'alpha.loop'`

- [ ] **Step 3: Write minimal implementation**

```python
# alpha/loop/__init__.py
```

```python
# alpha/loop/floor_breaker.py
from __future__ import annotations

import statistics

# Scorer-aware CAPABILITY-floor breaker (self-evolution-degrades-capability). Distinct from the
# portfolio loss circuit-breaker in alpha/guard/breaker.py — different concern, different module.

_MAD_EPS = 1e-9   # MAD below this => degenerate (near-constant) series -> use the absolute floor


def _mad(xs: list[float]) -> float:
    """Median absolute deviation (raw, not scaled): median(|x - median(x)|). Robust scale."""
    m = statistics.median(xs)
    return statistics.median([abs(x - m) for x in xs])


def _fallback_trip(history: list[float], k: int, c: float,
                   floor_abs: float) -> tuple[bool, float, float, str]:
    """Self-calibrating capability floor on the per-day ADVANTAGE series (no shadow arm).

    history = full daily-advantage series (ascending); caller guarantees 1 <= k <= len(history).
    Trip when mean(history[-k:]) < median(history) - c*MAD(history). When MAD ~ 0 (degenerate
    constant series, no robust scale) fall back to the absolute floor: mean(history[-k:]) < floor_abs.
    Returns (tripped, rolling, threshold, reason)."""
    window = history[-k:]
    rolling = sum(window) / len(window)
    mad = _mad(history)
    if mad < _MAD_EPS:
        return (rolling < floor_abs, rolling, floor_abs, "rolling < floor_abs (MAD~0 backstop)")
    threshold = statistics.median(history) - c * mad
    return (rolling < threshold, rolling, threshold, "rolling < median - c*MAD")
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/loop/test_floor_breaker.py -q`
Expected: PASS (4 passed)

- [ ] **Step 5: Commit**

```bash
git add alpha/loop/__init__.py alpha/loop/floor_breaker.py tests/loop/__init__.py tests/loop/test_floor_breaker.py
git commit -m "US-2c Task 2: capability-floor breaker pure functions (_mad / _fallback_trip; MAD~0 floor backstop)"
```

---

### Task 3: LoopConfig / events / report + the InnerLoop skeleton

**Files:**
- Create: `alpha/loop/inner_loop.py`
- Create: `tests/loop/test_inner_loop.py`

The config + audit models + the driver skeleton (act → delayed-score → online credit → trajectory). Refine and the breaker are added in Tasks 4–5.

- [ ] **Step 1: Write the failing test**

```python
# tests/loop/test_inner_loop.py
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
from alpha.eval.scorer import ReturnScorer
from alpha.llm.client import MockLLMClient
from alpha.loop.inner_loop import InnerLoop, LoopConfig, LoopReport


class _PickRun:
    """Deterministic LLM-free policy: pick every universe symbol as gap_and_go."""
    def decide(self, state, universe):
        return DecisionPackage(date=state.date,
                               candidates=[Candidate(symbol=s.symbol, pattern="gap_and_go")
                                           for s in universe.all()])


def _h():
    skills = SkillRegistry.from_skills([Skill(skill_id="gap_and_go", name="Gap and Go", type="pattern",
                                              status="active")])
    return HarnessState(doctrine=Doctrine(), skills=skills, memory=MemoryStore.from_lessons([]))


def _source(n=6):
    cal = [date(2026, 6, d) for d in range(1, 1 + n)]
    snaps, opens = {}, 10.0
    closes = []
    px = 10.0
    for d in cal:
        prev = px
        px = px * 1.2                      # +20% gainer every day (screens in)
        closes.append(px)
        snaps[d] = pd.DataFrame({"symbol": ["RUN"], "name": ["RUN"], "open": [prev], "high": [px],
                                 "low": [prev], "close": [px], "volume": [1], "prev_close": [prev]})
    bars = {"RUN": pd.DataFrame({"date": cal, "open": [10.0] + closes[:-1], "high": closes,
                                 "low": [10.0] + closes[:-1], "close": closes, "volume": [1] * n})}
    return FakeSource(calendar=cal, bars=bars, snapshots=snaps)


def _loop(src, cfg):
    import tempfile
    mgr = HarnessManager(_h(), SnapshotStore(tempfile.mkdtemp()))
    return InnerLoop(mgr, src, src.trading_calendar()[0], src.trading_calendar()[-1],
                     agent_llm=MockLLMClient("{}"), refiner_llm=MockLLMClient('{"ops": []}'),
                     config=cfg, scorer=ReturnScorer(), agent_factory=lambda h: _PickRun()), mgr


def test_skeleton_runs_and_credits_cumulatively():
    src = _source(6)
    loop, mgr = _loop(src, LoopConfig(horizon=2, enable_refine=False))
    report = loop.run()
    assert isinstance(report, LoopReport)
    assert len(report.trajectory.steps) == 6                  # one step per day
    # horizon=2 over 6 days -> decisions 0..3 scored (4 scored steps); RUN attributed to gap_and_go
    assert len(report.trajectory.scored_steps()) == 4
    assert mgr.harness.skills.get("gap_and_go").stats.n == 4  # online credit ran once per scored step
    assert report.refine_events == [] and report.breaker_events == []   # disabled / not tripped
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/loop/test_inner_loop.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'alpha.loop.inner_loop'`

- [ ] **Step 3: Write minimal implementation**

```python
# alpha/loop/inner_loop.py
from __future__ import annotations

from datetime import date as Date, datetime as DateTime
from typing import Callable, Literal

from pydantic import BaseModel, ConfigDict, Field

from alpha.agent.agent import LLMAgentPolicy
from alpha.data.calendar import trading_days_between
from alpha.data.firewall import AsOfGuard
from alpha.data.source import GuardedSource
from alpha.eval.decision import DecisionPolicy
from alpha.eval.oracle import PoolRecord, classify_day
from alpha.eval.scorer import ReturnScorer
from alpha.eval.trajectory import Trajectory, TrajectoryStep
from alpha.eval.walk_forward import score_decision
from alpha.harness.manager import HarnessManager
from alpha.harness.state import HarnessState
from alpha.llm.client import LLMClient
from alpha.refine.credit import CreditReport, apply_credit, merge_credit_reports
from alpha.refine.refiner import RefineReport, Refiner, RefinerConfig
from alpha.refine.signatures import extract_signatures
from alpha.loop.floor_breaker import _fallback_trip
from alpha.state.builder import build_market_state
from alpha.universe.universe import build_universe


class LoopConfig(BaseModel):
    """Inner-loop knobs. Dropped from CN: 4 B2-deprecated fields (breaker_window / baseline_window /
    floor_rel_margin / breaker_min_samples) + credit_window (A3: superseded by the watermark). The 3
    shadow_* fields (the paired-arm breaker) are US-2d — they need the Hexpert reference arm."""
    horizon: int = Field(default=2, ge=2)          # US: no same-day round-trip (WalkForwardEval enforces >=2)
    refine_every: int = Field(default=1, ge=1)
    evidence_min: int = Field(default=6, ge=1)     # min FRESH candidates (not steps) before a refine
    credit_decay: float = Field(default=0.1, gt=0.0, le=1.0)
    breaker_min_days: int = Field(default=3, ge=1)
    breaker_k_max: int = Field(default=5, ge=1)
    breaker_mad_c: float = Field(default=2.0, ge=0.0)
    floor_abs: float = Field(default=-0.2, ge=-1.0, le=1.0)
    enable_refine: bool = True


class RefineEvent(BaseModel):
    model_config = ConfigDict(frozen=True)
    date: Date
    checkpoint_version: int | None
    report: RefineReport


class BreakerEvent(BaseModel):
    model_config = ConfigDict(frozen=True)
    date: Date
    rolling: float
    baseline: float | None
    reason: str
    rolled_back_to: int | None
    mode: Literal["rollback", "frozen"]


class LoopReport(BaseModel):
    model_config = ConfigDict(frozen=True)
    trajectory: Trajectory
    refine_events: list[RefineEvent] = Field(default_factory=list)
    breaker_events: list[BreakerEvent] = Field(default_factory=list)
    frozen_from: Date | None = None
    n_edits: int = 0


class InnerLoop:
    """Interleaved self-evolution driver over one date range on a single LIVE H. Reset-free: the agent
    decides on the live H, edits become visible the next day. checkpoint/rollback + the capability-floor
    breaker live HERE (the Refiner only edits in place). After every rollback _rebind() re-fetches
    mgr.harness/mgr.tools and rebuilds the agent + refiner (the cached-handle-after-rollback hazard)."""

    def __init__(self, manager: HarnessManager, source, start: Date, end: Date,
                 agent_llm: LLMClient, refiner_llm: LLMClient, config: LoopConfig | None = None,
                 refiner_config: RefinerConfig | None = None, scorer=None,
                 agent_factory: Callable[[HarnessState], DecisionPolicy] | None = None) -> None:
        self._mgr = manager
        self._source = source
        self._start = start
        self._end = end
        self._agent_llm = agent_llm
        self._refiner_llm = refiner_llm
        self._cfg = config or LoopConfig()
        self._refiner_cfg = refiner_config or RefinerConfig()
        self._scorer = scorer or ReturnScorer()   # spec §7: forward-return oracle is PRIMARY (CN defaulted PoolScorer)
        self._agent_factory = agent_factory
        self._rebind()

    def _rebind(self) -> None:
        """(Re)build agent + refiner from the CURRENT mgr.harness/mgr.tools. Call at startup and after
        EVERY rollback (rollback_to rebinds mgr.harness/mgr.tools to the restored objects)."""
        h = self._mgr.harness
        self._agent = self._agent_factory(h) if self._agent_factory is not None \
            else LLMAgentPolicy(h, self._agent_llm)
        self._refiner = Refiner(h, self._refiner_llm, self._mgr.tools, self._refiner_cfg)

    def run(self) -> LoopReport:
        cfg = self._cfg
        days = trading_days_between(self._source.trading_calendar(), self._start, self._end)
        record = PoolRecord()
        drafts: list[dict] = []
        pending: list[int] = []
        scored_steps: list[TrajectoryStep] = []
        per_step_credits: list[CreditReport] = []
        refine_events: list[RefineEvent] = []
        breaker_events: list[BreakerEvent] = []
        breaker_days: list[tuple[Date, float]] = []
        ckpts: list[tuple[int, Date]] = []
        last_refined_idx = 0
        breaker_trips = 0
        frozen = False
        frozen_from: Date | None = None

        for i, cursor in enumerate(days):
            guarded = GuardedSource(self._source, AsOfGuard(cursor))
            universe = build_universe(guarded, cursor)
            state = build_market_state(universe, cursor,
                                       as_of=DateTime(cursor.year, cursor.month, cursor.day, 16, 0))
            record.record(cursor, classify_day(guarded.daily_snapshot(cursor)))
            decision = self._agent.decide(state, universe)
            entries = {c.symbol: snap for c in decision.candidates
                       if (snap := universe.get(c.symbol)) is not None}
            drafts.append({"date": cursor, "market": state, "decision": decision,
                           "entries": entries, "outcomes": {}, "scored": False})
            pending.append(i)

            # delayed scoring: mature any decision j that has reached its t+horizon exit
            newly: list[TrajectoryStep] = []
            still: list[int] = []
            for j in pending:
                if i >= j + cfg.horizon:
                    outcomes = score_decision(self._source, self._scorer, drafts[j]["decision"],
                                              days, j, cfg.horizon, cursor, record)
                    drafts[j]["outcomes"] = outcomes
                    drafts[j]["scored"] = True
                    step_j = TrajectoryStep(**drafts[j])
                    scored_steps.append(step_j)
                    newly.append(step_j)
                else:
                    still.append(j)
            pending = still

            # online credit (once per newly-scored step) + breaker evidence — gated on NOT frozen
            for step in newly:
                if frozen:
                    continue
                per_step_credits.append(apply_credit(Trajectory(steps=[step]), self._mgr.harness,
                                                     decay=cfg.credit_decay))
                advs = [c.advantage for c in step.outcomes.values()]
                breaker_days.append((step.date, sum(advs) / len(advs) if advs else 0.0))

            # [Task 5 inserts the BREAKER block here]

            # [Task 4 inserts the REFINE block here]

        traj = Trajectory(steps=[TrajectoryStep(**d) for d in drafts])
        # n_edits = edits in the LIVE log (after any rollback rebinds mgr.log to the restored, shorter
        # log) — a current-state count, not a cumulative-across-rollbacks total.
        return LoopReport(trajectory=traj, refine_events=refine_events, breaker_events=breaker_events,
                          frozen_from=frozen_from, n_edits=len(self._mgr.log))
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/loop/test_inner_loop.py -q`
Expected: PASS (1 passed)

- [ ] **Step 5: Commit**

```bash
git add alpha/loop/inner_loop.py tests/loop/test_inner_loop.py
git commit -m "US-2c Task 3: LoopConfig/events/report + InnerLoop skeleton (act->score->online-credit->trajectory)"
```

---

### Task 4: Periodic refine (checkpoint-before-refine + watermark)

**Files:**
- Modify: `alpha/loop/inner_loop.py`
- Modify: `tests/loop/test_inner_loop.py`

Insert the refine block: when enough FRESH candidates have accrued, checkpoint then run the Refiner over the non-overlapping window, and advance the watermark.

- [ ] **Step 1: Write the failing test (append to `tests/loop/test_inner_loop.py`)**

```python
def test_refine_fires_after_evidence_and_checkpoints_before():
    import tempfile
    src = _source(6)
    # evidence_min=2 -> refine fires once 2 fresh candidates have scored; refiner rewrites a doctrine line
    mgr = HarnessManager(
        HarnessState(doctrine=Doctrine.from_seed_list(
            [{"section": "trend_play", "regime": "trend", "immutable": False, "guidance": "ride"}]),
            skills=SkillRegistry.from_skills([Skill(skill_id="gap_and_go", name="G", type="pattern",
                                                    status="active")]),
            memory=MemoryStore.from_lessons([])),
        SnapshotStore(tempfile.mkdtemp()))
    loop = InnerLoop(mgr, src, src.trading_calendar()[0], src.trading_calendar()[-1],
                     agent_llm=MockLLMClient("{}"),
                     refiner_llm=MockLLMClient('{"ops": [{"tool": "rewrite_doctrine", "args": '
                                               '{"section": "trend_play", "new_guidance": "ride (refined)"}, '
                                               '"rationale": "evidence"}]}'),
                     config=LoopConfig(horizon=2, evidence_min=2, refine_every=1),
                     scorer=ReturnScorer(), agent_factory=lambda h: _PickRun())
    report = loop.run()
    assert report.refine_events                              # at least one refine fired
    ev = report.refine_events[0]
    assert ev.checkpoint_version is not None                # checkpoint taken BEFORE refining
    assert report.n_edits >= 1 and "refined" in mgr.harness.doctrine.get("trend_play").guidance


def test_no_refine_when_disabled():
    src = _source(6)
    loop, mgr = _loop(src, LoopConfig(horizon=2, enable_refine=False))
    report = loop.run()
    assert report.refine_events == [] and report.n_edits == 0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/loop/test_inner_loop.py::test_refine_fires_after_evidence_and_checkpoints_before -q`
Expected: FAIL — `assert report.refine_events` fails (the refine block isn't wired yet).

- [ ] **Step 3: Write the implementation**

Replace the `# [Task 4 inserts the REFINE block here]` placeholder in `run()` with:

```python
            # periodic refine: checkpoint BEFORE editing H, over the non-overlapping watermark window
            fresh = scored_steps[last_refined_idx:]
            n_fresh = sum(len(s.outcomes) for s in fresh)        # count CANDIDATES (empty days add 0)
            if cfg.enable_refine and not frozen and n_fresh >= cfg.evidence_min and i % cfg.refine_every == 0:
                ver = self._mgr.checkpoint(label=f"pre-refine {cursor}")
                ckpts.append((ver, cursor))
                win_traj = Trajectory(steps=fresh)
                credit = merge_credit_reports(per_step_credits[last_refined_idx:])
                sigs = extract_signatures(win_traj, self._mgr.harness)
                report = self._refiner.refine(win_traj, credit, sigs)
                refine_events.append(RefineEvent(date=cursor, checkpoint_version=ver, report=report))
                last_refined_idx = len(scored_steps)             # advance watermark (non-overlapping)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/loop/test_inner_loop.py -q`
Expected: PASS (3 passed) — skeleton + both new refine tests green.

- [ ] **Step 5: Commit**

```bash
git add alpha/loop/inner_loop.py tests/loop/test_inner_loop.py
git commit -m "US-2c Task 4: periodic refine (checkpoint-before-refine; candidate-counted evidence; non-overlapping watermark)"
```

---

### Task 5: Capability-floor breaker + rollback / re-arm / freeze

**Files:**
- Modify: `alpha/loop/inner_loop.py`
- Create: `tests/loop/test_inner_loop_breaker.py`

Insert the breaker block (before the refine block in `run()`): evaluate the fallback floor on the daily-advantage series; on a trip, roll back to the latest checkpoint before the degraded window (first trip) or freeze (second trip / no checkpoint).

- [ ] **Step 1: Write the failing test**

```python
# tests/loop/test_inner_loop_breaker.py
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
    """Returns a controlled advantage per decision date (day_baseline=0 so advantage == score)."""
    def __init__(self, sched: dict): self._sched = sched
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
    return HarnessState(doctrine=Doctrine.from_seed_list(
        [{"section": "trend_play", "regime": "trend", "immutable": False, "guidance": "ride"}]),
        skills=SkillRegistry.from_skills([Skill(skill_id="gap_and_go", name="G", type="pattern",
                                                status="active")]),
        memory=MemoryStore.from_lessons([]))


def _loop(src, cfg, sched, refiner_script='{"ops": []}'):
    mgr = HarnessManager(_h(), SnapshotStore(tempfile.mkdtemp()))
    loop = InnerLoop(mgr, src, src.trading_calendar()[0], src.trading_calendar()[-1],
                     agent_llm=MockLLMClient("{}"), refiner_llm=MockLLMClient(refiner_script),
                     config=cfg, scorer=_SchedScorer(sched), agent_factory=lambda h: _PickRun())
    return loop, mgr


def test_breaker_freezes_without_checkpoint():
    # enable_refine=False -> no checkpoints ever -> the first trip must FREEZE (no rollback target).
    cal = [date(2026, 6, d) for d in range(1, 8)]               # 7 days
    sched = {cal[0]: 0.3, cal[1]: 0.3, cal[2]: 0.3, cal[3]: -0.9, cal[4]: -0.9}
    cfg = LoopConfig(horizon=2, enable_refine=False, breaker_min_days=3, breaker_k_max=3,
                     breaker_mad_c=2.0, floor_abs=0.0)
    loop, mgr = _loop(_source(7), cfg, sched)
    report = loop.run()
    assert report.frozen_from is not None
    assert report.breaker_events and report.breaker_events[-1].mode == "frozen"
    assert report.breaker_events[-1].rolled_back_to is None
    # credit stopped at freeze: fewer credited samples than total scored steps
    n_scored = len(report.trajectory.scored_steps())
    assert mgr.harness.skills.get("gap_and_go").stats.n < n_scored


def test_breaker_rolls_back_to_pre_degradation_checkpoint():
    # enable_refine=True (refine fires -> checkpoints exist). A healthy stretch builds checkpoints, then
    # degradation trips the breaker which rolls back to a checkpoint BEFORE the degraded window.
    cal = [date(2026, 6, d) for d in range(1, 12)]             # 11 days
    sched = {cal[k]: (0.3 if k < 6 else -0.9) for k in range(11)}
    cfg = LoopConfig(horizon=2, enable_refine=True, evidence_min=1, refine_every=1,
                     breaker_min_days=3, breaker_k_max=3, breaker_mad_c=2.0, floor_abs=0.0)
    loop, mgr = _loop(_source(11), cfg, sched)
    report = loop.run()
    modes = [e.mode for e in report.breaker_events]
    assert modes and modes[0] == "rollback"
    assert report.breaker_events[0].rolled_back_to is not None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/loop/test_inner_loop_breaker.py -q`
Expected: FAIL — no `BreakerEvent`s emitted (the breaker block isn't wired yet).

- [ ] **Step 3: Write the implementation**

Replace the `# [Task 5 inserts the BREAKER block here]` placeholder in `run()` with:

```python
            # capability-floor breaker (fallback path): judge the daily-advantage series; on a trip,
            # roll back to the latest checkpoint BEFORE the degraded window (1st trip) or freeze.
            if not frozen and len(breaker_days) >= cfg.breaker_min_days:
                k = min(len(breaker_days), cfg.breaker_k_max)
                history = [v for _, v in breaker_days]
                trip, rolling, thr, reason = _fallback_trip(history, k, cfg.breaker_mad_c, cfg.floor_abs)
                if trip:
                    window_start = breaker_days[-k][0]
                    breaker_trips += 1
                    target = max((v for v, d in ckpts if d < window_start), default=None)
                    if breaker_trips == 1 and target is not None:
                        self._mgr.rollback_to(target)
                        self._rebind()
                        ckpts = [(v, d) for v, d in ckpts if v <= target]   # drop discarded-timeline ckpts
                        breaker_days.clear()                                # re-arm: need breaker_min_days again
                        last_refined_idx = len(scored_steps)                # drop the discarded window so the
                        #   next refine is NOT re-fed the degraded evidence that caused this rollback (this
                        #   also makes the same-day refine's window empty, so no `continue` is needed). The
                        #   final LoopReport.trajectory still contains the pre-rollback steps by design.
                        breaker_events.append(BreakerEvent(date=cursor, rolling=rolling, baseline=thr,
                                                           reason=reason, rolled_back_to=target,
                                                           mode="rollback"))
                    else:
                        rolled = None
                        if target is not None:
                            self._mgr.rollback_to(target)
                            self._rebind()
                            rolled = target
                        frozen = True
                        frozen_from = cursor
                        breaker_events.append(BreakerEvent(date=cursor, rolling=rolling, baseline=thr,
                                                           reason=reason, rolled_back_to=rolled,
                                                           mode="frozen"))
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/loop/test_inner_loop_breaker.py tests/loop/test_inner_loop.py -q`
Expected: PASS — both breaker tests + the Task 3/4 tests green. (The trip days are hand-verified deterministic: the constant-then-drop schedules give MAD≈0, so the `floor_abs=0.0` backstop fires cleanly — FREEZE trips at `i=5`, ROLLBACK at `i=8` with target = the checkpoint dated before the degraded window start. No adjustment expected; the trip math is also pinned by Task 2.)

- [ ] **Step 5: Commit**

```bash
git add alpha/loop/inner_loop.py tests/loop/test_inner_loop_breaker.py
git commit -m "US-2c Task 5: capability-floor breaker wiring (rollback+rebind+re-arm; second-trip/no-ckpt freeze)"
```

---

### Task 6: US-2c acceptance gate + docs update

**Files:**
- Create: `tests/loop/test_us2c_acceptance.py`
- Modify: `docs/PROJECT_STATE.md` (mark US-2c done)

End-to-end: the real seeded `H` + a real `LLMAgentPolicy` (MockLLM) + a real `Refiner` (MockLLM) self-evolve over a `WalkForwardEval`-style walk through one `InnerLoop.run()` — credit mutates `H`, a refine fires and edits `H` (audited in the `EditLog`, checkpointed), the firewall holds, and a healthy series does not trip the breaker.

- [ ] **Step 1: Write the acceptance test**

```python
# tests/loop/test_us2c_acceptance.py
"""US-2c acceptance: the InnerLoop self-evolves the SEEDED harness end-to-end on a MockLLM agent +
MockLLM refiner — online credit mutates H, a checkpointed refine edits H (audited), the firewall holds,
and a healthy advantage series does not trip the breaker. This is the loop US-2d will compare arm-vs-arm."""
import tempfile
from pathlib import Path
from datetime import date
import pandas as pd
from alpha.data.source import FakeSource
from alpha.harness.loader import load_seeds
from alpha.harness.snapshot import SnapshotStore
from alpha.harness.manager import HarnessManager
from alpha.llm.client import MockLLMClient
from alpha.eval.scorer import ReturnScorer
from alpha.loop.inner_loop import InnerLoop, LoopConfig

SEEDS = Path(__file__).resolve().parents[2] / "seeds"


def _source(n=8):
    cal = [date(2026, 6, d) for d in range(1, 1 + n)]
    snaps, px = {}, 10.0
    closes = []
    for d in cal:
        prev = px; px = px * 1.15; closes.append(px)        # +15%/day: RUN screens in (>10%) and keeps gaining
        snaps[d] = pd.DataFrame({"symbol": ["RUN"], "name": ["RUN"], "open": [prev], "high": [px],
                                 "low": [prev], "close": [px], "volume": [1], "prev_close": [prev]})
    bars = {"RUN": pd.DataFrame({"date": cal, "open": [10.0] + closes[:-1], "high": closes,
                                 "low": [10.0] + closes[:-1], "close": closes, "volume": [1] * n})}
    # +15% < the EXOGENOUS 20% gainer gate, so the decision-day pool is empty -> day_baseline None ->
    # advantage == raw forward return (positive), comfortably above floor_abs -> the breaker never trips.
    return FakeSource(calendar=cal, bars=bars, snapshots=snaps)


def test_inner_loop_self_evolves_seeded_harness_end_to_end():
    mgr = HarnessManager(load_seeds(SEEDS), SnapshotStore(tempfile.mkdtemp()))
    src = _source(8)
    loop = InnerLoop(
        mgr, src, src.trading_calendar()[0], src.trading_calendar()[-1],
        agent_llm=MockLLMClient('{"regime_read": "trend", "candidates": '
                                '[{"symbol": "RUN", "pattern": "gap_and_go", "confidence": 0.7}]}'),
        refiner_llm=MockLLMClient('{"ops": [{"tool": "rewrite_doctrine", "args": {"section": "trend_play", '
                                  '"new_guidance": "ride the lead runner; trim into blowoffs (refined)"}, '
                                  '"rationale": "evidence"}]}'),
        config=LoopConfig(horizon=2, evidence_min=2, refine_every=1), scorer=ReturnScorer())
    report = loop.run()
    # the loop walked every day and scored the matured decisions
    assert len(report.trajectory.steps) == 8 and report.trajectory.scored_steps()
    # online credit populated the seed skill's stats
    assert mgr.harness.skills.get("gap_and_go").stats.n >= 1
    # at least one checkpointed refine fired and edited H (audited in the EditLog)
    assert report.refine_events and report.refine_events[0].checkpoint_version is not None
    assert report.n_edits >= 1 and "refined" in mgr.harness.doctrine.get("trend_play").guidance
    # a healthy advantage series does not trip the breaker (no LookaheadError raised => firewall held)
    assert report.frozen_from is None and report.breaker_events == []
```

- [ ] **Step 2: Run the full suite**

Run: `python -m pytest -q`
Expected: PASS — all prior tests plus the new US-2c loop tests green.

- [ ] **Step 3: Update `docs/PROJECT_STATE.md`**

Add a **US-2c** entry under the US-2 section: the InnerLoop is complete — `score_decision()` extracted; `alpha/loop/floor_breaker.py` (pure `_mad`/`_fallback_trip`, MAD≈0 `floor_abs` backstop, advantage-based scorer-aware floor); `alpha/loop/inner_loop.py` (`LoopConfig`/`RefineEvent`/`BreakerEvent`/`LoopReport` + `InnerLoop`) driving act → delayed-score → online `apply_credit` → checkpoint-before-refine → fallback breaker with rollback-and-`_rebind` (re-fetch `mgr.tools`/`mgr.harness`) / re-arm / second-trip-freeze. Note the full-suite test count. Update the "Next" pointer to **US-2d (three-way HCH/Hexpert/Hmin compare + the shadow/paired breaker path + the honest statistical bar)**. Keep the deferred items (sizing/guard→DecisionPackage wiring; master-dispatch G sub-agents; keep-last-K checkpoint pruning).

- [ ] **Step 4: Commit**

```bash
git add tests/loop/test_us2c_acceptance.py docs/PROJECT_STATE.md
git commit -m "US-2c Task 6: acceptance gate (InnerLoop self-evolves seeded H end-to-end) + PROJECT_STATE"
```

---

## Self-Review (run after writing, fix inline)

**Spec coverage (§4 inner loop, §7 advantage, §9 floor):** `score_decision` reuse (Task 1) ✓ · scorer-aware fallback floor on advantage with MAD≈0 backstop (Task 2) ✓ · reset-free act→score→online-credit driver (Task 3) ✓ · checkpoint-before-refine + candidate-counted evidence + non-overlapping watermark (Task 4) ✓ · rollback-to-pre-degradation-checkpoint + `_rebind` + re-arm + second-trip/no-checkpoint freeze (Task 5) ✓ · end-to-end self-evolution on seeded `H` (Task 6) ✓. **Deferred & documented:** the shadow/paired breaker path + `shadow_daily` injection → US-2d (needs the Hexpert arm); the three-way compare → US-2d; sizing/guard→DecisionPackage wiring; master-dispatch G sub-agents; keep-last-K checkpoint pruning.

**Type consistency:** `score_decision(source, scorer, decision, days, j, horizon, cursor, record) -> dict[str, ScoredCandidate]` consumed by `_score` (list) and the loop (dict→`TrajectoryStep.outcomes`). `_fallback_trip(history, k, c, floor_abs) -> (trip, rolling, threshold, reason)`. `apply_credit(Trajectory(steps=[step]), h, decay=...)` (no `horizon` kwarg — US `Trajectory` has none). `Refiner(mgr.harness, refiner_llm, mgr.tools, refiner_cfg)`; `LLMAgentPolicy(mgr.harness, agent_llm)`; both rebuilt in `_rebind` after every `rollback_to`. `HarnessManager.checkpoint(label)->int` / `rollback_to(version)` / `.log` (`__len__`). `LoopConfig.horizon` defaults 2 (ge=2) to match `WalkForwardEval`.

**Placeholder scan:** no TBD/TODO; every code step is complete; the breaker block is placed before the refine block in `run()` (execution order: credit → breaker → refine), while built in Task 5 after Task 4 so its rollback tests have checkpoints to target. The breaker integration tests are hand-traced (schedules chosen so the MAD≈0 `floor_abs` backstop fires deterministically); if a trip day drifts on execution, adjust the test schedule — the production trip math is pinned by Task 2.

**Scope:** InnerLoop + fallback floor-breaker + checkpoint/rollback/freeze only. No compare arm, no shadow path, no sizing/guard wiring. Produces the live self-evolving loop US-2d compares (HCH) against the frozen-expert (Hexpert) and minimum (Hmin) arms.

**Adversarial-review fixes folded (2026-06-15, 4-lens review — reviewers built+ran every module; no critical findings):**
- **[important] rollback didn't drop the degraded evidence window**: a first-trip rollback cleared `breaker_days` + pruned `ckpts` but left the refine watermark, so the same-day/next refine re-fed the degraded window onto the restored `H` (partially undoing the rollback). Folded `last_refined_idx = len(scored_steps)` into the rollback branch — drops the discarded window from future refines and makes the same-day refine window empty (no `continue` needed). A deliberate, documented improvement over CN (which keeps the watermark).
- **[important] Task 4 pass-count** corrected `4 → 3` (three test functions).
- **[minor] hygiene**: inlined `SnapshotStore(tempfile.mkdtemp())` (dropped the define-after-use `SnapshotStore_tmp` helper); documented `n_edits` as live-log (not cumulative-across-rollbacks); aligned invariant 5 prose to "second trip → rollback-to-target-if-any then freeze"; tightened the breaker-test note (trip days are deterministic, no adjustment expected); split the dropped-LoopConfig-fields count (4 B2-deprecated + `credit_window`); documented the `ReturnScorer` default as a spec-§7 divergence from CN's `PoolScorer`; dropped the unused `LAG` symbol from the acceptance fixture + added a comment on why advantage stays positive (below the 20% exogenous gate).
