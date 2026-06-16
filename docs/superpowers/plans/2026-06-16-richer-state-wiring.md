# Richer-State Perception Wiring + screen-default-on Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Wire the **richer L1 perception build** (sentiment_raw / sentiment_norm / follow_through_rate / gap_and_go_count) into the live drivers so `GCycle` reads **frontside** on genuine uptrends, then flip `LoopConfig.screen` default **ON** with a **symmetric guard** in `compare_harnesses` — completing the production posture where the L4 guard veto is always live (and correct, not over-firing).

**Architecture:** Today both live drivers (`WalkForwardEval.walk`, `InnerLoop.run`) call the *minimal* `state/builder.build_market_state(universe, day, *, as_of)`, which leaves `sentiment_norm=None`/`follow_through_rate=None`; `GCycle.read` then falls back to a low-confidence breadth proxy that reads even a persistent runner as **backside** (which is exactly why US-3b kept `screen` opt-in/default-off). The *richer* `features/builder.build_market_state` computes the full feature set but takes a different signature and builds the universe itself (a double-build vs the driver). This plan **unifies** on one builder that takes the **prebuilt universe** + optional `history`/`prev_gainers` (back-compat defaults reproduce the minimal behavior), threads `history`(append `sentiment_raw`)/`prev_gainers`(prior-day gainer set) across the driver loops, then — staged separately — flips `screen` default-on and wraps the non-HCH `compare_harnesses` arms in `GuardedPolicy` for symmetry. The decisive property: with the richer builder, `follow_through_rate>0` on a persistent runner ⇒ `GCycle` reads **trend/frontside** ⇒ the regime veto no longer fires ⇒ `screen`-on keeps frontside runners (so the synthetic-runner apparatus tests stay green) while still vetoing real SSR / reverse-split / dilution / halt-then-dump / genuine-backside names.

**Tech Stack:** Python ≥ 3.11, pydantic v2, pandas, pytest. Deterministic, offline (`FakeSource`); firewall-clean (the richer builder reads only `<= as_of` — `build_universe` calendar-filters; `history` is threaded input, never re-fetched).

---

## Context: why this is the orthogonal closeout

US-3a–3f activated every daily-cadence enrichment + the four guard-veto flags, but the guard (`screen`) stayed **opt-in/default-off** because the minimal builder made `GCycle` over-fire backside (`LoopConfig.screen` comment says exactly this; `tests/loop/test_screen_wiring.py::test_screen_on_vetoes_backside_entries` *documents* the over-fire). This plan removes that blocker by feeding `GCycle` the real regime features, then turns the guard on.

- `alpha/state/builder.py::build_market_state(universe, day, *, as_of)` — the minimal builder the drivers use; sets `sentiment_norm=None`, no `follow_through_rate`/`sentiment_raw`/`gap_and_go_count`.
- `alpha/features/builder.py::build_market_state(day, source, history, as_of, prev_gainers=…, min_samples=…)` — the richer builder (calls `build_universe` internally); used only by `tests/features/test_builder.py` + `tests/regime/test_us1e_acceptance.py`.
- `alpha/regime/classifier.py::GCycle.read` — frontside set `{recovery, ignition, trend}`. On strong tape (`proxy ≥ 0.6`): `trend` (frontside) iff `fb_rate < 0.4 AND ft ≥ 0.4`, else `distribution`/`flush` (backside). With the minimal builder `ft = 0.0` (None→0) ⇒ always backside on a single gainer; with the richer builder `ft = 1.0` on a persistent runner ⇒ **trend/frontside**.
- `alpha/loop/compare.py::compare_harnesses` — HCH via `InnerLoop` (auto-wraps `GuardedPolicy` when `cfg.screen`), Hexpert/Hmin via `WalkForwardEval.walk/run` with **bare** policies (no guard) — an asymmetry that must be fixed when `screen` defaults on.

**Honest scope.** `sentiment_norm` needs `≥ min_samples` (default 60) history days; synthetic test windows (6–10 days) keep it `None` (the breadth proxy still applies) — that's correct, not a regression. The richer builder is wired; the **real** vendor feeds remain deferred (US-3 already deferred those). No new data source.

---

## File Structure

| File | Change | Responsibility |
|---|---|---|
| `alpha/features/sentiment.py` | Modify | **Task 1 Step 3a:** host `DEFAULT_MIN_SAMPLES` here (moved down from `features/builder.py`) — the pure leaf both builders import, breaking the would-be shim cycle. |
| `alpha/state/builder.py` | Modify | The **unified** builder: `build_market_state(universe, day, *, as_of, history=(), prev_gainers=frozenset(), min_samples=DEFAULT_MIN_SAMPLES)` — counts + runner echelon + follow_through + sentiment_raw/norm + gap_and_go. Back-compat defaults reproduce the old minimal output for asserted fields. |
| `alpha/features/builder.py` | Modify | Becomes a thin **shim**: builds the universe then delegates to the unified builder (keeps its `(day, source, history, …)` signature for existing callers/tests); imports `DEFAULT_MIN_SAMPLES` from `sentiment`, does not re-export it (no cycle). |
| `alpha/eval/walk_forward.py` | Modify | `walk` threads `history`/`prev_gainers` and calls the unified builder. |
| `alpha/loop/inner_loop.py` | Modify | `run` threads `history`/`prev_gainers`; **Task 2:** `LoopConfig.screen` default → `True`. |
| `alpha/loop/compare.py` | Modify | **Task 2:** wrap the non-HCH policy arms in `GuardedPolicy` when `cfg.screen` (symmetry). |
| `tests/state/test_builder.py` | Verify | Stays green (asserts only `sentiment_norm is None`, true with empty history). |
| `tests/loop/test_screen_wiring.py` | Modify | **Task 1 Step 7:** replace the over-fire test (`test_screen_on_vetoes_backside_entries`, which this task breaks) with the corrected behavior (richer builder ⇒ frontside runner KEPT under `screen=True`). **Task 2 Step 5:** rename the now-misnamed default-state test. |
| `tests/state/test_richer_state.py` | Create | The richer builder + threading: `history`/`prev_gainers` populate `follow_through_rate`/`sentiment_raw`; `GCycle` reads frontside on a persistent runner via a driver walk. |
| `tests/loop/test_screen_default_on.py` | Create | **Task 2:** `screen` defaults on; a frontside runner is kept; `compare_harnesses` arms are symmetric. |
| `tests/eval/test_richer_state_acceptance.py` | Create | End-to-end: richer state → frontside regime → `screen` (default-on) keeps a clean frontside runner AND drops a real SSR name. |
| `docs/PROJECT_STATE.md`, `docs/blueprint.md` | Modify | Record the perception wiring + screen-default-on; refresh the "minimal builder / screen opt-in" notes. |

**No `veto.py`/`screen.py::screen_decision` change** (the guard logic is done). No new data source.

**TDD framing.** Task 1 (richer builder + threading, `screen` still default-off) has low blast radius — `GCycle` isn't consumed when `screen` is off, so only `MarketState` fields + prompt text change (MockLLM ignores the prompt). Task 2 (flip default-on + symmetric guard) is the higher-risk step, isolated to its own commit with a full-suite gate; the richer builder (Task 1) ensures the synthetic runner reads frontside so the guard keeps it (apparatus tests stay green). Full-suite run after every task.

---

## Task 1: Unify the builder + thread history/prev_gainers (screen still default-off)

**Files:** Modify `alpha/state/builder.py`, `alpha/features/builder.py`, `alpha/eval/walk_forward.py`, `alpha/loop/inner_loop.py`; Create `tests/state/test_richer_state.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/state/test_richer_state.py`:

```python
"""Richer-state wiring: the unified builder computes follow_through_rate / sentiment_raw from a prebuilt
universe + threaded prev_gainers/history, and the live walk threads them so GCycle reads frontside on a
persistent runner (the precondition for screen-default-on)."""
from datetime import date, datetime
import pandas as pd
from alpha.data.source import FakeSource
from alpha.universe.universe import build_universe
from alpha.state.builder import build_market_state
from alpha.regime.classifier import GCycle


def _uni(day):
    src = FakeSource(calendar=[day], bars={}, snapshots={day: pd.DataFrame({
        "symbol": ["RUN"], "name": ["R"], "open": [10.0], "high": [13.0], "low": [10.0],
        "close": [12.0], "volume": [1], "prev_close": [10.0]})})           # +20% gainer
    return build_universe(src, day, gainer_pct=10.0, gap_pct=5.0, rvol_window=2)


def test_unified_builder_threads_follow_through_and_sentiment():
    day = date(2026, 6, 12)
    uni = _uni(day)
    ms = build_market_state(uni, day, as_of=datetime(2026, 6, 12, 16, 0),
                            prev_gainers=frozenset({"RUN"}), history=[])
    assert ms.follow_through_rate == 1.0          # RUN was a prior gainer and still is
    assert ms.sentiment_raw != 0.0                # composite computed (not the default)
    assert ms.sentiment_norm is None              # empty history < min_samples -> None (never fabricated)


def test_unified_builder_backcompat_defaults_match_minimal():
    day = date(2026, 6, 12)
    ms = build_market_state(_uni(day), day, as_of=datetime(2026, 6, 12, 16, 0))   # no history/prev_gainers
    assert ms.follow_through_rate is None and ms.sentiment_norm is None   # defaults reproduce the minimal


def test_gcycle_reads_frontside_on_persistent_runner():
    day = date(2026, 6, 12)
    ms = build_market_state(_uni(day), day, as_of=datetime(2026, 6, 12, 16, 0),
                            prev_gainers=frozenset({"RUN"}), history=[])
    read = GCycle().read(ms)
    assert read.frontside is True and read.phase == "trend"   # ft=1.0 + strong tape -> trend (was backside)
```

- [ ] **Step 2: Run to verify failure**

Run: `python -m pytest tests/state/test_richer_state.py -v`
Expected: FAIL — `build_market_state` does not accept `history`/`prev_gainers` (TypeError: unexpected keyword argument).

- [ ] **Step 3a: Relocate `DEFAULT_MIN_SAMPLES` to the leaf module `alpha/features/sentiment.py`**

This must happen FIRST and is load-bearing for correctness, not cosmetic. `DEFAULT_MIN_SAMPLES = 60` currently lives in `alpha/features/builder.py:12` (verified by grep). In this plan `features/builder.py` becomes a **shim that imports `build_market_state` from `state/builder`** (Step 4). If `state/builder` then imported `DEFAULT_MIN_SAMPLES` *from* `features/builder`, we'd create a real import cycle: `features/builder → state/builder → features/builder`. Moving the constant down to the pure leaf `features/sentiment.py` (confirmed: zero imports — it only defines `raw_sentiment`/`normalize_sentiment`, and `normalize_sentiment` already takes `min_samples`) breaks the cycle and gives both modules a single shared source.

In `alpha/features/sentiment.py`, add the constant near the top (after `from __future__ import annotations`):

```python
DEFAULT_MIN_SAMPLES = 60   # regime-relative normalization needs >= this many trailing sentiment_raw days
```

In `alpha/features/builder.py`, delete its local `DEFAULT_MIN_SAMPLES = 60` line and import it instead (this keeps the module importable between Step 3a and Step 4):

```python
from alpha.features.sentiment import DEFAULT_MIN_SAMPLES, normalize_sentiment, raw_sentiment
```

- [ ] **Step 3b: Make `alpha/state/builder.py` the unified builder**

Replace the entire body of `alpha/state/builder.py` with:

```python
from __future__ import annotations

from collections.abc import Sequence
from datetime import date as Date, datetime as DateTime

from alpha.features.breadth import counts, failed_breakout_count, follow_through_rate, gap_and_go_count
from alpha.features.runner import runner_echelon
from alpha.features.sentiment import DEFAULT_MIN_SAMPLES, normalize_sentiment, raw_sentiment
from alpha.state.market import MarketState
from alpha.universe.universe import CandidateUniverse


def build_market_state(universe: CandidateUniverse, day: Date, *, as_of: DateTime,
                       history: Sequence[float] = (),
                       prev_gainers: frozenset[str] = frozenset(),
                       min_samples: int = DEFAULT_MIN_SAMPLES) -> MarketState:
    """The L1 perception build from the day's (prebuilt) universe: breadth counts + runner echelon +
    follow-through + sentiment composite. The driver threads `history` (prior-day sentiment_raw, <= day)
    and `prev_gainers` (the previous day's gainer symbols); with the empty defaults this reproduces the
    earlier minimal build (follow_through_rate=None, sentiment_norm=None) for back-compat. Firewall: reads
    only the passed universe + threaded history — no >day fetch.
    """
    g, gu, lo = counts(universe)
    ft = follow_through_rate(universe, prev_gainers)
    fb = failed_breakout_count(universe)
    echelon = runner_echelon(universe.by_status("gainer"))
    max_tier = echelon[0].tier if echelon else 0
    raw = raw_sentiment(gainer_count=g, max_runner_tier=max_tier, follow_through=(ft or 0.0),
                        failed_breakout_rate=(fb / g if g else 0.0), loser_count=lo)
    return MarketState(
        date=day, gainer_count=g, gap_up_count=gu, loser_count=lo, failed_breakout_count=fb,
        max_runner_tier=max_tier, echelon=echelon, breadth_raw=float(g - lo), sentiment_raw=raw,
        sentiment_norm=normalize_sentiment(raw, list(history), min_samples),
        follow_through_rate=ft, gap_and_go_count=gap_and_go_count(universe), as_of=as_of)
```

(After Step 3a, `DEFAULT_MIN_SAMPLES` lives in `alpha/features/sentiment.py`, so this import resolves. `list(history)` materializes the `Sequence` for `normalize_sentiment` (typed `list[float] | None`, but only iterated/`len`-ed — accepts any sequence at runtime).)

- [ ] **Step 4: Make `alpha/features/builder.py` a shim**

Replace its `build_market_state` body so it builds the universe then delegates (keeping its existing `(day, source, history, as_of, prev_gainers, min_samples)` signature so `tests/features/test_builder.py` + `tests/regime/test_us1e_acceptance.py` stay green):

```python
from __future__ import annotations

from datetime import date as Date, datetime as DateTime

from alpha.data.source import MarketDataSource
from alpha.features.sentiment import DEFAULT_MIN_SAMPLES
from alpha.state.builder import build_market_state as _build_market_state
from alpha.state.market import MarketState
from alpha.universe.universe import build_universe


def build_market_state(day: Date, source: MarketDataSource, history: list[float], as_of: DateTime,
                       prev_gainers: frozenset[str] = frozenset(),
                       min_samples: int = DEFAULT_MIN_SAMPLES) -> MarketState:
    """Back-compat shim: build the day's universe then delegate to the unified state builder. Prefer
    calling alpha.state.builder.build_market_state with a prebuilt universe on the live path (avoids a
    second build_universe). FIREWALL: the caller must pass a GuardedSource(AsOfGuard(day))."""
    return _build_market_state(build_universe(source, day), day, as_of=as_of,
                               history=history, prev_gainers=prev_gainers, min_samples=min_samples)
```

(Both `state/builder` and this shim now import `DEFAULT_MIN_SAMPLES` from the leaf `features/sentiment` — see Step 3a. This shim imports `build_market_state` from `state/builder`; the constant is NOT re-exported from here, so there is no `features/builder → state/builder → features/builder` cycle.)

- [ ] **Step 5: Thread history/prev_gainers in `WalkForwardEval.walk`**

In `alpha/eval/walk_forward.py::walk`, initialize the threaded state before the loop and use it:

```python
        days = trading_days_between(self._source.trading_calendar(), self._start, self._end)
        record = PoolRecord()
        decisions: list = []
        markets: list = []
        universes: list = []
        scored_by_day: dict = {}
        history: list[float] = []                 # prior-day sentiment_raw (regime-relative context)
        prev_gainers: frozenset[str] = frozenset()
        for i, cursor in enumerate(days):
            guarded = GuardedSource(self._source, AsOfGuard(cursor))
            universe = build_universe(guarded, cursor)
            state = build_market_state(universe, cursor,
                                       as_of=DateTime(cursor.year, cursor.month, cursor.day, 16, 0),
                                       history=history, prev_gainers=prev_gainers)
            history.append(state.sentiment_raw)
            prev_gainers = frozenset(s.symbol for s in universe.by_status("gainer"))
            record.record(cursor, classify_day(guarded.daily_snapshot(cursor)))
            decision = policy.decide(state, universe)
            decisions.append(decision); markets.append(state); universes.append(universe)
            ...  # (the j = i - horizon scoring block is unchanged)
```

- [ ] **Step 6: Thread history/prev_gainers in `InnerLoop.run`**

In `alpha/loop/inner_loop.py::run`, before the `for i, cursor in enumerate(days):` loop add `history: list[float] = []` and `prev_gainers: frozenset[str] = frozenset()`. Inside the loop, replace the `build_market_state(...)` call and append/rotate immediately after it:

```python
            universe = build_universe(guarded, cursor)
            state = build_market_state(universe, cursor,
                                       as_of=DateTime(cursor.year, cursor.month, cursor.day, 16, 0),
                                       history=history, prev_gainers=prev_gainers)
            history.append(state.sentiment_raw)
            prev_gainers = frozenset(s.symbol for s in universe.by_status("gainer"))
```

Notes on the threading semantics (add a one-line code comment at the `history.append` site capturing the gist):
- **Bootstrap (day 1):** `prev_gainers` starts empty, so `follow_through_rate(universe, frozenset())` returns `None` on the first day (same as the old minimal builder). A persistent runner therefore reads **frontside from day 2 onward**, not day 1 — this is bootstrap, not a regression. (The unit tests in `test_richer_state.py` pre-populate `prev_gainers` to exercise the day-2+ asymptotic case directly.)
- **Data flow:** `sentiment_raw` is appended to `history` to feed *next* day's `sentiment_norm` percentile; **today's** regime read is driven by `follow_through_rate` (the `ft ≥ 0.4` arm of `GCycle.read`), not by `sentiment_raw`. `sentiment_norm` stays `None` until `history` reaches `min_samples` (60) — on synthetic windows the breadth proxy carries the read.
- **Rollback:** `history`/`prev_gainers` are loop-locals that accumulate monotonically across the run; a breaker rollback (`_rebind`) does NOT rewind them. Acceptable and safe: the regime context is a forward-only read, not part of `H`, and `sentiment_norm` is `None` on the short windows where rollbacks are exercised (so no normalized value can drift).

- [ ] **Step 7: Repair the over-fire test that this task legitimately breaks**

**Critical (caught in review):** `tests/loop/test_screen_wiring.py::test_screen_on_vetoes_backside_entries` forces `screen=True` on a *persistent* +15%/day runner and asserts `all(not s.entries ...)`. That assertion held only because the *minimal* builder gave `ft=0` ⇒ backside ⇒ everything vetoed. **This task changes that:** once `InnerLoop.run` threads `prev_gainers` (Step 6), day 2+ get `ft=1.0` ⇒ `GCycle` reads **frontside** ⇒ `GuardedPolicy` keeps RUN ⇒ entries appear ⇒ the test fails. The breakage lands on **Task 1** (the moment the builder + threading land), independent of the default flip in Task 2 — so the fix belongs here. RUN trips no *data* veto (every day up ⇒ no SSR; `close==high>prev` ⇒ no halt-then-dump; no corp actions), so the kept-runner outcome is correct, not a masked failure.

In `tests/loop/test_screen_wiring.py`, replace `test_screen_on_vetoes_backside_entries` with the corrected behavior (leave `test_screen_off_by_default_keeps_entries` untouched — `screen` still defaults off in Task 1, so its name is still accurate until Task 2 renames it):

```python
def test_screen_on_keeps_frontside_runner():
    # the richer state builder threads prev_gainers -> follow_through=1.0 on day 2+ -> GCycle reads frontside,
    # so the wired veto NO LONGER over-fires on a clean persistent runner (this is the fix the wiring delivers;
    # SSR / reverse-split / halt-then-dump data vetoes are exercised in tests/guard/test_screen.py).
    lr = _loop(_source(6), screen=True).run()
    assert any(s.entries for s in lr.trajectory.steps)             # frontside runner kept despite screen on
    assert any(s.decision.regime is not None for s in lr.trajectory.steps)  # structured regime still populated
```

- [ ] **Step 8: Run the new + repaired tests, then the full suite**

Run: `python -m pytest tests/state/test_richer_state.py tests/state/test_builder.py tests/features/test_builder.py tests/regime/test_us1e_acceptance.py tests/loop/test_screen_wiring.py -v`
Expected: all PASS (new richer-state tests green; `test_builder` asserts only `sentiment_norm is None`; `features/test_builder` + US-1e go through the shim; the repaired `test_screen_wiring` asserts the runner is kept).

Run: `python -m pytest -q`
Expected: green. Baseline is 367 tests; this task adds 3 (`test_richer_state.py`) and replaces 1 in-place (`test_screen_wiring.py`), so expect ~370 passing — record the exact count from the run rather than asserting a hard number. `screen` is still default-off, so `GCycle` is not consumed in the loop — only `MarketState` fields + (MockLLM-ignored) prompt text change. The only test that legitimately changes premise is the `test_screen_wiring` over-fire case repaired in Step 7; if any *other* test asserts a driver-produced `MarketState.follow_through_rate`/`sentiment_raw` is None/0, update it to the now-computed value and note why.

- [ ] **Step 9: Commit**

```bash
git add alpha/features/sentiment.py alpha/state/builder.py alpha/features/builder.py \
        alpha/eval/walk_forward.py alpha/loop/inner_loop.py \
        tests/state/test_richer_state.py tests/loop/test_screen_wiring.py
git commit -m "richer-state Task 1: unify on prebuilt-universe builder + thread history/prev_gainers in the live drivers (screen still off)"
```

---

## Task 2: Flip `screen` default-on + symmetric `compare_harnesses` guard

**Files:** Modify `alpha/loop/inner_loop.py`, `alpha/loop/compare.py`, `tests/loop/test_screen_wiring.py`; Create `tests/loop/test_screen_default_on.py`

- [ ] **Step 1: Write the failing / updated tests**

Create `tests/loop/test_screen_default_on.py`:

```python
"""screen now defaults ON (the richer builder makes GCycle read frontside, so the guard no longer over-fires).
A frontside runner is KEPT; compare_harnesses wraps the non-HCH arms symmetrically."""
import tempfile
from datetime import date
from pathlib import Path
import pandas as pd
from alpha.data.source import FakeSource
from alpha.harness.loader import load_seeds
from alpha.harness.manager import HarnessManager
from alpha.harness.snapshot import SnapshotStore
from alpha.llm.client import MockLLMClient
from alpha.loop.inner_loop import InnerLoop, LoopConfig

SEEDS = Path(__file__).resolve().parents[2] / "seeds"


def _runner_source(n=6):
    cal = [date(2026, 6, d) for d in range(1, 1 + n)]
    snaps, px = {}, 10.0
    closes = []
    for d in cal:
        prev = px; px = px * 1.15; closes.append(px)
        snaps[d] = pd.DataFrame({"symbol": ["RUN"], "name": ["RUN"], "open": [prev], "high": [px],
                                 "low": [prev], "close": [px], "volume": [1], "prev_close": [prev]})
    bars = {"RUN": pd.DataFrame({"date": cal, "open": [10.0] + closes[:-1], "high": closes,
                                 "low": [10.0] + closes[:-1], "close": closes, "volume": [1] * n})}
    return FakeSource(calendar=cal, bars=bars, snapshots=snaps)


def test_screen_defaults_on():
    assert LoopConfig().screen is True


def test_screen_on_keeps_frontside_runner():
    # default LoopConfig (screen=True). The richer builder -> follow_through=1.0 -> GCycle frontside ->
    # the regime veto does NOT fire, and RUN trips no data veto -> RUN is entered (not dropped).
    src = _runner_source(6)
    mgr = HarnessManager(load_seeds(SEEDS), SnapshotStore(tempfile.mkdtemp()))
    loop = InnerLoop(mgr, src, src.trading_calendar()[0], src.trading_calendar()[-1],
                     MockLLMClient('{"candidates": [{"symbol": "RUN", "pattern": "gap_and_go"}]}'),
                     MockLLMClient('{"ops": []}'),
                     config=LoopConfig(horizon=2, evidence_min=2, refine_every=1))   # screen defaults True
    lr = loop.run()
    assert any(s.entries for s in lr.trajectory.steps)          # frontside runner kept despite screen on
```

- [ ] **Step 2: Run to verify failure**

Run: `python -m pytest tests/loop/test_screen_default_on.py -v`
Expected: `test_screen_defaults_on` FAILS (`LoopConfig().screen` is still `False`).

- [ ] **Step 3: Flip the default in `alpha/loop/inner_loop.py`**

In `LoopConfig`, change:

```python
    screen: bool = False        # US-3b: when True, wrap the agent in GuardedPolicy (L4 hard veto). OFF by
    #   default — the regime arm over-fires on the minimal state builder (follow_through/sentiment None ->
    #   GCycle reads backside) until the richer features/builder is on the live path (a later US-3 slice).
    #   The SSR/reverse-split data-flag vetoes are exact today.
```

to:

```python
    screen: bool = True         # L4 hard veto ON by default — the richer state builder now feeds GCycle
    #   follow_through/sentiment so the regime arm reads frontside on genuine uptrends (no longer over-fires).
    #   Set screen=False to run an unguarded baseline.
```

- [ ] **Step 4: Symmetrize `compare_harnesses` (wrap non-HCH arms when screen)**

Why wrap here: `WalkForwardEval.walk/run` take only `(policy, ...)` — they do **not** accept or read a `LoopConfig`, so there is no guard hook inside the evaluator. HCH gets its guard because `InnerLoop._rebind` wraps the agent in `GuardedPolicy` when `cfg.screen`; the Hexpert/Hmin arms go straight through `WalkForwardEval` with **bare** policies. To make the comparison fair once `screen` defaults on, the guard must be composed onto each arm's policy **at the `compare_harnesses` call site**, before it is handed to `wf.walk`/`wf.run`. This is policy-level composition, not a `WalkForwardEval` change.

In `alpha/loop/compare.py`, import `GuardedPolicy` (`from alpha.guard.screen import GuardedPolicy`). After `cfg = loop_config or LoopConfig()` define:

```python
    def _guard(policy):                       # match HCH's guard when screen is on (fair comparison)
        return GuardedPolicy(policy, source) if cfg.screen else policy
```

and wrap **every** policy passed to `wf.walk`/`wf.run` — both Hexpert walk sites (shadow and re-run branches) and both Hmin arms:
- `wf.walk(_guard(LLMAgentPolicy(harness_factory(), agent_llm_factory())))` (each Hexpert walk),
- `wf.run(_guard(ChaseBiggestGainerPolicy()))` and `wf.run(_guard(NoTradePolicy()))` (Hmin arms).

Read the current `compare_harnesses` body first and confirm you have wrapped all four call sites (grep `wf.walk(` / `wf.run(` inside the function); a missed site reintroduces the asymmetry.

- [ ] **Step 5: Rename the now-misnamed default-state test in `tests/loop/test_screen_wiring.py`**

The over-fire test was already corrected in Task 1 Step 7 (it is now `test_screen_on_keeps_frontside_runner`). The only remaining edit is cosmetic: after this task flips the default to `True`, `test_screen_off_by_default_keeps_entries` is misnamed (it passes `screen=False` explicitly, so it still passes — but "by_default" is now false). Rename it and keep the explicit override:

```python
def test_screen_off_keeps_entries():
    lr = _loop(_source(6), screen=False).run()
    assert any(s.entries for s in lr.trajectory.steps)             # explicit unguarded baseline enters normally
```

(The "screen defaults ON" assertion is covered by `tests/loop/test_screen_default_on.py::test_screen_defaults_on` created in Step 1.)

- [ ] **Step 6: Run + full suite**

Run: `python -m pytest tests/loop/test_screen_default_on.py tests/loop/test_screen_wiring.py -v`
Expected: PASS.

Run: `python -m pytest -q`
Expected: green. Triage by blast radius:
- **Immune** to the default flip: tests that call `build_market_state` / `build_system_prompt` / `build_user_prompt` directly (e.g. `tests/eval/test_us3c_acceptance.py`, `test_us3f_acceptance.py`, `tests/state/*`) — they never construct an `InnerLoop`/`WalkForwardEval`, so `LoopConfig.screen` is irrelevant to them.
- **Exposed** to the flip: tests that build an `InnerLoop` or call `compare_harnesses` without passing an explicit `screen=` (e.g. `test_us2c`, `test_us3a/3d/3e` if they drive the loop). These now run guarded by default.
- For an exposed failure: a compare/stats/inner-loop test that shifts is almost certainly (a) a synthetic candidate genuinely tripping a data veto, or (b) an arm asymmetry — re-check `_guard` wrapping. Because the richer builder makes the synthetic runner read frontside and it trips no data veto, the expectation is these stay green; update only tests whose premise legitimately changed (document each), or pin them to `screen=False` if they are specifically testing the unguarded baseline.

- [ ] **Step 7: Commit**

```bash
git add alpha/loop/inner_loop.py alpha/loop/compare.py tests/loop/test_screen_wiring.py tests/loop/test_screen_default_on.py
git commit -m "richer-state Task 2: screen default-on (regime now reads frontside) + symmetric GuardedPolicy in compare_harnesses"
```

---

## Task 3: Acceptance gate + docs

**Files:** Create `tests/eval/test_richer_state_acceptance.py`; Modify `docs/PROJECT_STATE.md`, `docs/blueprint.md`

- [ ] **Step 1: Write the acceptance test**

Create `tests/eval/test_richer_state_acceptance.py`:

```python
"""Acceptance: with the richer state builder wired + screen default-on, the live walk reads frontside on a
genuine uptrend (so the guard keeps the clean runner) AND still drops a real SSR name (prior-day <= -10%).
This is the production posture: the L4 guard is always live and correct, not over-firing on every uptrend."""
from datetime import date, datetime
from pathlib import Path
import pandas as pd
from alpha.data.source import FakeSource
from alpha.state.builder import build_market_state
from alpha.universe.universe import build_universe
from alpha.regime.classifier import GCycle
from alpha.eval.decision import Candidate, DecisionPackage
from alpha.universe.universe import CandidateUniverse
from alpha.guard.screen import GuardedPolicy

CUR = date(2026, 6, 12)


def _source():
    cal = [date(2026, 6, 11), CUR]
    snap = pd.DataFrame({
        "symbol": ["RUN", "KNIFE"], "name": ["Runner", "Knife"],
        "open": [10.0, 10.0], "high": [12.0, 10.0], "low": [10.0, 8.0],
        "close": [12.0, 9.0], "volume": [1, 1], "prev_close": [10.0, 10.0]})   # RUN +20% gainer; KNIFE flat today
    bars = {"KNIFE": pd.DataFrame({"date": [date(2026, 6, 10), date(2026, 6, 11)],
                                   "open": [10.0, 8.8], "high": [10, 9], "low": [8, 8],
                                   "close": [10.0, 8.8], "volume": [1, 1]})}     # KNIFE -12% on 6/11 -> SSR on 6/12
    return FakeSource(calendar=cal, bars=bars, snapshots={CUR: snap})


class _StubPolicy:
    def decide(self, state, universe):
        return DecisionPackage(date=CUR, candidates=[Candidate(symbol=s, pattern="gap_and_go")
                                                     for s in ("RUN", "KNIFE")])


def test_richer_state_frontside_keeps_runner_but_drops_ssr():
    src = _source()
    uni = build_universe(src, CUR, gainer_pct=10.0, gap_pct=5.0, rvol_window=2)
    state = build_market_state(uni, CUR, as_of=datetime(2026, 6, 12, 16, 0),
                               history=[], prev_gainers=frozenset({"RUN"}))   # RUN persisted -> ft populated
    assert GCycle().read(state).frontside is True                  # frontside, not over-firing backside
    out = GuardedPolicy(_StubPolicy(), src).decide(state, CandidateUniverse.from_stocks([]))
    assert [c.symbol for c in out.candidates] == ["RUN"]           # clean frontside runner kept
    assert any("KNIFE" in r and "SSR" in r for r in out.key_risks) # the real SSR name still vetoed
```

- [ ] **Step 2: Run the acceptance test + full suite**

Run: `python -m pytest tests/eval/test_richer_state_acceptance.py -v && python -m pytest -q`
Expected: acceptance PASS; full suite green; record the exact count for PROJECT_STATE.

- [ ] **Step 3: Update `docs/PROJECT_STATE.md`**

Replace the header `Last updated` line (read it first for the exact current text) to note the richer-state wiring + screen-default-on. Then add a "Richer-state perception wiring" entry after the US-3f paragraph summarizing: the unified `build_market_state` (prebuilt universe + threaded history/prev_gainers), `GCycle` now reads frontside on genuine uptrends, `LoopConfig.screen` **defaults ON** with a symmetric guard in `compare_harnesses` (the L4 guard is always live + correct). Refresh the now-stale "minimal builder / screen opt-in / over-fire" notes (in the US-3b/3e entries' framing and the "Other deferred" list — drop "wiring the richer `features/builder` into the live loop … can default ON" since it is now done). Note the remaining orthogonal item: the live temp=0 verdict run.

- [ ] **Step 4: Reconcile `docs/blueprint.md`**

Grep `minimal builder` / `sentiment_norm` / `screen` / `features/builder` and update any line that frames the live loop as using the minimal builder / `screen` as opt-in to reflect the richer builder wired + `screen` default-on. Keep edits to the relevant lines.

- [ ] **Step 5: Commit**

```bash
git add tests/eval/test_richer_state_acceptance.py docs/PROJECT_STATE.md docs/blueprint.md
git commit -m "richer-state Task 3: acceptance gate (frontside keeps runner, still vetoes SSR) + PROJECT_STATE/blueprint"
```

---

## Self-Review

**1. Spec coverage.** The richer `features/builder` perception is wired into both live drivers via a unified prebuilt-universe builder + threaded `history`/`prev_gainers` (Task 1); `GCycle` consequently reads frontside on genuine uptrends; `LoopConfig.screen` defaults ON with a symmetric `compare_harnesses` guard (Task 2); acceptance proves frontside-keeps-runner + still-vetoes-SSR (Task 3). The two user-asked outcomes ("GCycle reads frontside" + "screen can default ON") are both delivered.

**2. Placeholder scan.** Every step has literal code + a runnable command + expected outcome, except the doc steps (3.3/3.4), which are bounded edits requiring a read-first for exact anchors.

**3. Type/contract consistency.** Unified `build_market_state(universe, day, *, as_of, history=(), prev_gainers=frozenset(), min_samples=DEFAULT_MIN_SAMPLES)`; back-compat defaults reproduce the minimal output (`follow_through_rate=None`, `sentiment_norm=None`) for the fields existing tests assert. `features/builder` shim keeps its `(day, source, history, …)` signature. `GCycle.read`, `follow_through_rate(universe, prev_gainers)`, `raw_sentiment`/`normalize_sentiment`, `runner_echelon(by_status("gainer"))` all reused unchanged. `compare_harnesses` `_guard` wrap returns the policy unchanged when `screen=False`.

**4. Firewall.** The unified builder reads only the prebuilt universe + threaded `history` (no fetch). The drivers still wrap the source in `GuardedSource(AsOfGuard(cursor))` and build the universe through it. `history` is forward-only (`sentiment_raw` from `<= cursor` days). No new firewall edge.

**5. Blast radius / honesty.** Task 1 is low-risk (screen off ⇒ `GCycle` unused in the loop ⇒ only `MarketState` fields + ignored prompt text change). Task 2 is the real change, isolated to its own commit: the richer builder makes the synthetic runner read **frontside**, so `screen`-default-on **keeps** it (no data veto trips on a clean +15%/day runner: SSR no [prior +15%], reverse-split/dilution no [no corp], halt-then-dump no [spike≥15% but close>prev → no dump]) — so the compare/stats/inner-loop apparatus tests stay green, and the only legitimately-changed tests are `test_screen_wiring`'s over-fire/off-by-default cases (now corrected). The honest deferrals stand: `sentiment_norm` needs ≥`min_samples` history (synthetic windows keep it None — correct); real vendor feeds remain deferred; the live temp=0 verdict run is the remaining orthogonal item. Each genuinely-changed test is updated with its rationale, not forced.
