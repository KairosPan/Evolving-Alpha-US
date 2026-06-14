# US-1e Regime Machine + Features Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the L1 perception layer — US-momentum feature modules (sentiment, breadth, runner) that enrich `MarketState`, the 6-state US momentum cycle as a state-machine container, and a read-only `G_cycle` classifier that reads `MarketState` and emits a global regime read (phase + confidence + frontside/backside + risk-gate).

**Architecture:** Pure feature functions compute breadth/runner/sentiment scalars from the US-0 `CandidateUniverse` + trailing daily bars; a full `build_market_state` composes them into an enriched `MarketState` (adds `sentiment_raw`, `follow_through_rate`, `gap_and_go_count`; populates `consecutive_up_days` runner echelon; regime-relative `sentiment_norm`). `regime/cycle.py` holds the canonical 6-state US momentum `StateMachine` (states + transition signals). `regime/classifier.py`'s `G_cycle` is the read-only sub-agent of `H.G`: it maps a `MarketState` to a `RegimeRead` using objective, oracle-auditable rules — **SSOT: it never writes the phase back into `H`** (it produces an `s_t`-side label).

**Tech Stack:** Python ≥3.11, pydantic v2, pandas, pytest. No LLM, no network — fully offline (US-0 `FakeSource`).

**Spec:** `docs/superpowers/specs/2026-06-13-us-market-adaptation-design.md` (US-1 "regime classifier + state machine"; §5 regime machine; §4 SSOT principle). Sub-plan **US-1e** of US-1 (after 1d eval; before 1f sizing/guard).

**Scope boundary (US-1e only):** features + state machine + GLOBAL regime classifier. **Deferred:** **per-narrative-line phases** (washout/trend per theme) → US-3 (need theme/catalyst tagging absent at daily cadence; US-1e classifies the *global mother-state* phase + a global frontside/backside proxy); the LLM Refiner that calibrates the classifier judges against the oracle → US-2; wiring the full builder into `WalkForwardEval` → US-2 (US-1e ships the full builder standalone + tested; the eval loop keeps the US-0 minimal builder until the agent needs the rich state). **Reused (do not redefine):** `CandidateUniverse`/`StockSnapshot`, `build_universe`, `MarketState`/`RunnerRung`, `MarketDataSource`/`GuardedSource`, `trading_days_between`/`prev_trading_day`, the canonical phase vocabulary `CANONICAL_PHASES` from `alpha/harness/regime.py`.

**Conventions:** all code/comments English; `from __future__ import annotations` at top of every module; commit after every passing task; run via `python -m pytest`.

**Key invariants (each gets a test):**
1. `sentiment_norm` is regime-relative (trailing percentile, `≤`-day history only); `None` when samples insufficient (never an absolute threshold).
2. Runner `consecutive_up_days` is computed from **strictly trailing** bars (no future leakage); the echelon groups by tier descending.
3. The full builder produces an enriched `MarketState` from `≤t` data only; backward-compatible MarketState (new fields default, so US-0/1d constructions still validate).
4. `G_cycle` is **read-only / SSOT**: it returns a `RegimeRead` and has no method that mutates a harness; phase ∈ the canonical 6 US states; `risk_gate ∈ [0,1]`.
5. The classifier maps representative market states to the intended phase deterministically (objective, oracle-auditable rules), and degrades to low confidence when `sentiment_norm` is `None`.

---

### Task 1: Features package + sentiment (raw + regime-relative normalization)

**Files:**
- Create: `alpha/features/__init__.py`
- Create: `alpha/features/sentiment.py`
- Create: `tests/features/__init__.py`
- Create: `tests/features/test_sentiment.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/features/test_sentiment.py
from alpha.features.sentiment import raw_sentiment, normalize_sentiment


def test_raw_sentiment_directionality():
    strong = raw_sentiment(gainer_count=40, max_runner_tier=5, follow_through=0.8,
                           failed_breakout_rate=0.1, loser_count=2)
    weak = raw_sentiment(gainer_count=3, max_runner_tier=1, follow_through=0.1,
                         failed_breakout_rate=0.7, loser_count=40)
    assert strong > weak                       # more gainers/runners/follow-through -> higher


def test_normalize_percentile():
    hist = [0.0, 1.0, 2.0, 3.0, 4.0]
    assert normalize_sentiment(2.0, hist, min_samples=3) == 3 / 5     # <=2.0 are {0,1,2}
    assert normalize_sentiment(5.0, hist, min_samples=3) == 1.0


def test_normalize_insufficient_samples_is_none():
    assert normalize_sentiment(2.0, [0.0, 1.0], min_samples=3) is None
    assert normalize_sentiment(2.0, None, min_samples=3) is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/features/test_sentiment.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'alpha.features'`

- [ ] **Step 3: Write minimal implementation**

```python
# alpha/features/__init__.py
```

```python
# tests/features/__init__.py
```

```python
# alpha/features/sentiment.py
from __future__ import annotations


def raw_sentiment(gainer_count: int, max_runner_tier: int, follow_through: float,
                  failed_breakout_rate: float, loser_count: int) -> float:
    """Raw US-momentum sentiment composite (dimensionless; only for cross-day relative comparison).

    Positive: gainer breadth, runner depth, follow-through; negative: failed-breakout rate, losers.
    Weights are prior initial values — later evolvable skill params (blueprint §6.1 analog).
    """
    return (
        0.1 * gainer_count
        + 2.0 * max_runner_tier
        + 3.0 * follow_through
        - 5.0 * failed_breakout_rate
        - 0.2 * loser_count
    )


def normalize_sentiment(value: float, history: list[float] | None, min_samples: int) -> float | None:
    """Regime-relative normalization: percentile of `value` within history (<= current day) in [0,1].

    Returns None when samples insufficient (never fabricate an absolute threshold).
    """
    if history is None or len(history) < min_samples:
        return None
    le = sum(1 for h in history if h <= value)
    return le / len(history)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/features/test_sentiment.py -q`
Expected: PASS (3 passed)

- [ ] **Step 5: Commit**

```bash
git add alpha/features/__init__.py alpha/features/sentiment.py tests/features/__init__.py tests/features/test_sentiment.py
git commit -m "US-1e Task 1: features package + sentiment (raw + regime-relative normalization)"
```

---

### Task 2: Breadth features (counts, follow-through, failed-breakout, gap-and-go)

**Files:**
- Create: `alpha/features/breadth.py`
- Create: `tests/features/test_breadth.py`

Pure functions over a `CandidateUniverse` (+ the prior day's gainer set for follow-through).

- [ ] **Step 1: Write the failing test**

```python
# tests/features/test_breadth.py
from alpha.universe.stock import StockSnapshot
from alpha.universe.universe import CandidateUniverse
from alpha.features.breadth import (
    counts, failed_breakout_count, follow_through_rate, gap_and_go_count,
)


def _u():
    return CandidateUniverse.from_stocks([
        StockSnapshot(symbol="RUN", status="gainer", name="r", pct_change=30.0, gap_pct=8.0,
                      close=13.0, prev_close=10.0),
        StockSnapshot(symbol="GAP", status="gap_up", name="g", pct_change=-2.0, gap_pct=9.0,
                      close=9.8, prev_close=10.0),         # gapped up, closed red -> failed breakout
        StockSnapshot(symbol="DIP", status="loser", name="d", pct_change=-25.0,
                      close=7.5, prev_close=10.0),
    ])


def test_counts():
    g, gu, lo = counts(_u())
    assert (g, gu, lo) == (1, 1, 1)


def test_failed_breakout():
    assert failed_breakout_count(_u()) == 1            # GAP gapped up (gap_pct>0) and closed red


def test_gap_and_go():
    assert gap_and_go_count(_u()) == 1                 # RUN is a gainer that gapped up and held


def test_follow_through_rate():
    # of yesterday's gainers {RUN, OLD}, RUN is a gainer again today -> 1/2
    assert follow_through_rate(_u(), frozenset({"RUN", "OLD"})) == 0.5
    assert follow_through_rate(_u(), frozenset()) is None     # no prior gainers -> undefined
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/features/test_breadth.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'alpha.features.breadth'`

- [ ] **Step 3: Write minimal implementation**

```python
# alpha/features/breadth.py
from __future__ import annotations

from alpha.universe.universe import CandidateUniverse


def counts(universe: CandidateUniverse) -> tuple[int, int, int]:
    """(gainer_count, gap_up_count, loser_count) by snapshot status."""
    return (len(universe.by_status("gainer")), len(universe.by_status("gap_up")),
            len(universe.by_status("loser")))


def failed_breakout_count(universe: CandidateUniverse) -> int:
    """Gapped up (gap_pct>0) but closed red (close < prev_close) — the 炸板 analog."""
    n = 0
    for s in universe.all():
        if (s.gap_pct is not None and s.gap_pct > 0 and s.close is not None
                and s.prev_close is not None and s.close < s.prev_close):
            n += 1
    return n


def gap_and_go_count(universe: CandidateUniverse) -> int:
    """Gainers that gapped up and held (status gainer with gap_pct>0) — the 弱转强 daily proxy."""
    return sum(1 for s in universe.by_status("gainer") if s.gap_pct is not None and s.gap_pct > 0)


def follow_through_rate(universe: CandidateUniverse, prev_gainers: frozenset[str]) -> float | None:
    """Fraction of yesterday's gainers that are gainers again today (risk-on/off effect).
    None when there were no prior gainers (undefined)."""
    if not prev_gainers:
        return None
    today = {s.symbol for s in universe.by_status("gainer")}
    return len(today & prev_gainers) / len(prev_gainers)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/features/test_breadth.py -q`
Expected: PASS (4 passed)

- [ ] **Step 5: Commit**

```bash
git add alpha/features/breadth.py tests/features/test_breadth.py
git commit -m "US-1e Task 2: breadth features (counts / failed-breakout / gap-and-go / follow-through)"
```

---

### Task 3: Runner features (consecutive up-days + echelon)

**Files:**
- Create: `alpha/features/runner.py`
- Create: `tests/features/test_runner.py`

`consecutive_up_days` is computed from **strictly trailing** bars (≤ day). `runner_echelon` groups snapshots (whose `consecutive_up_days` is already populated) into `RunnerRung`s.

- [ ] **Step 1: Write the failing test**

```python
# tests/features/test_runner.py
from datetime import date
import pandas as pd
from alpha.universe.stock import StockSnapshot
from alpha.features.runner import consecutive_up_days, runner_echelon


def _bars(dates, closes):
    return pd.DataFrame({"date": dates, "open": closes, "high": closes, "low": closes,
                         "close": closes, "volume": [1]*len(dates)})


def test_consecutive_up_days():
    # closes 10,11,12,13 over 4 days -> at the last day, 3 consecutive up-closes
    bars = _bars([date(2026, 6, 9), date(2026, 6, 10), date(2026, 6, 11), date(2026, 6, 12)],
                 [10.0, 11.0, 12.0, 13.0])
    assert consecutive_up_days(bars, date(2026, 6, 12)) == 3
    # a down day resets the count
    bars2 = _bars([date(2026, 6, 10), date(2026, 6, 11), date(2026, 6, 12)], [12.0, 11.0, 13.0])
    assert consecutive_up_days(bars2, date(2026, 6, 12)) == 1


def test_consecutive_up_days_missing():
    assert consecutive_up_days(pd.DataFrame(), date(2026, 6, 12)) == 0
    one = _bars([date(2026, 6, 12)], [10.0])
    assert consecutive_up_days(one, date(2026, 6, 12)) == 0      # single bar -> no prior to compare


def test_runner_echelon_groups_by_tier_descending():
    snaps = [
        StockSnapshot(symbol="A", status="gainer", name="a", consecutive_up_days=3),
        StockSnapshot(symbol="B", status="gainer", name="b", consecutive_up_days=3),
        StockSnapshot(symbol="C", status="gainer", name="c", consecutive_up_days=1),
        StockSnapshot(symbol="D", status="gainer", name="d", consecutive_up_days=0),  # not a runner
    ]
    rungs = runner_echelon(snaps)
    assert [(r.tier, r.count) for r in rungs] == [(3, 2), (1, 1)]
    assert rungs[0].representatives == ["A", "B"]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/features/test_runner.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'alpha.features.runner'`

- [ ] **Step 3: Write minimal implementation**

```python
# alpha/features/runner.py
from __future__ import annotations

from datetime import date as Date

import pandas as pd

from alpha.state.market import RunnerRung
from alpha.universe.stock import StockSnapshot


def consecutive_up_days(bars: pd.DataFrame, day: Date, max_lookback: int = 30) -> int:
    """Count of consecutive up-closes ending at `day` (close[t] > close[t-1]), strictly trailing.

    Uses only bars with date <= day. A non-up day stops the count. Missing/short data -> 0.
    """
    if bars is None or bars.empty or "date" not in bars.columns:
        return 0
    df = bars.copy()
    df["date"] = pd.to_datetime(df["date"]).dt.date          # robust to date or datetime64 dtypes
    df = df[df["date"] <= day].sort_values("date")
    closes = list(pd.to_numeric(df["close"], errors="coerce").dropna())
    if len(closes) < 2:
        return 0
    n = 0
    for i in range(len(closes) - 1, 0, -1):
        if closes[i] > closes[i - 1]:
            n += 1
            if n >= max_lookback:
                break
        else:
            break
    return n


def runner_echelon(snapshots: list[StockSnapshot], top_reps: int = 3) -> list[RunnerRung]:
    """Group snapshots by consecutive_up_days tier (>=1), tier descending; reps = first `top_reps`."""
    by_tier: dict[int, list[str]] = {}
    for s in snapshots:
        t = s.consecutive_up_days
        if t is not None and t >= 1:
            by_tier.setdefault(t, []).append(s.symbol)
    return [RunnerRung(tier=t, count=len(syms), representatives=sorted(syms)[:top_reps])
            for t, syms in sorted(by_tier.items(), reverse=True)]
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/features/test_runner.py -q`
Expected: PASS (3 passed)

- [ ] **Step 5: Commit**

```bash
git add alpha/features/runner.py tests/features/test_runner.py
git commit -m "US-1e Task 3: runner features (consecutive up-days trailing + echelon)"
```

---

### Task 4: Extend MarketState with the L1 feature fields

**Files:**
- Modify: `alpha/state/market.py` (add 3 optional fields)
- Create: `tests/state/test_market_l1_fields.py`

Backward-compatible: new fields default, so all US-0/1d constructions still validate.

- [ ] **Step 1: Write the failing test**

```python
# tests/state/test_market_l1_fields.py
from datetime import date, datetime
from alpha.state.market import MarketState


def _ms(**kw):
    base = dict(date=date(2026, 6, 12), gainer_count=0, gap_up_count=0, loser_count=0,
               failed_breakout_count=0, max_runner_tier=0, echelon=[], breadth_raw=0.0,
               sentiment_norm=None, as_of=datetime(2026, 6, 12, 16, 0))
    base.update(kw)
    return MarketState(**base)


def test_new_fields_default_backward_compatible():
    ms = _ms()                                      # US-0/1d-style construction (no new fields)
    assert ms.sentiment_raw == 0.0
    assert ms.follow_through_rate is None
    assert ms.gap_and_go_count == 0


def test_new_fields_settable():
    ms = _ms(sentiment_raw=4.2, follow_through_rate=0.6, gap_and_go_count=5)
    assert ms.sentiment_raw == 4.2 and ms.follow_through_rate == 0.6 and ms.gap_and_go_count == 5
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/state/test_market_l1_fields.py -q`
Expected: FAIL — `AttributeError`/`ValidationError` (fields don't exist yet)

- [ ] **Step 3: Add the fields to `alpha/state/market.py`**

Add these three fields to the `MarketState` model (place after `sentiment_norm`):

```python
    # ── L1 perception features (US-1e) ──
    sentiment_raw: float = 0.0                        # raw composite (normalized into sentiment_norm)
    follow_through_rate: float | None = None          # fraction of prior-day gainers still gainers today
    gap_and_go_count: int = 0                         # gainers that gapped up and held
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/state/test_market_l1_fields.py -q`
Expected: PASS (2 passed). Also run `python -m pytest tests/eval/test_baselines.py -q` to confirm the US-1d MarketState construction still validates (backward-compat).

- [ ] **Step 5: Commit**

```bash
git add alpha/state/market.py tests/state/test_market_l1_fields.py
git commit -m "US-1e Task 4: extend MarketState with L1 feature fields (sentiment_raw/follow_through_rate/gap_and_go_count)"
```

---

### Task 5: Full L1 builder (compose features into an enriched MarketState)

**Files:**
- Create: `alpha/features/builder.py`
- Create: `tests/features/test_builder.py`

`build_market_state(day, source, history, as_of, prev_gainers)` builds the universe, enriches gainers with `consecutive_up_days` from trailing bars, computes all features, and returns the enriched `MarketState`. (The US-0 `alpha/state/builder.py` minimal builder stays for US-1d's `WalkForwardEval`; US-2 migrates the loop to this full builder.)

- [ ] **Step 1: Write the failing test**

```python
# tests/features/test_builder.py
from datetime import date, datetime
import pandas as pd
from alpha.data.source import FakeSource
from alpha.features.builder import build_market_state


def _source():
    cal = [date(2026, 6, 10), date(2026, 6, 11), date(2026, 6, 12)]
    snaps = {date(2026, 6, 12): pd.DataFrame({
        "symbol": ["RUN", "DIP"], "name": ["r", "d"],
        "open": [12.0, 9.0], "high": [14, 9], "low": [12, 7], "close": [14.0, 7.0],
        "volume": [1, 1], "prev_close": [10.0, 10.0]})}                  # RUN +40%, DIP -30%
    bars = {"RUN": pd.DataFrame({"date": cal, "open": [10, 11, 12.0], "high": [11, 12, 14],
                                 "low": [10, 11, 12], "close": [10.0, 11.0, 14.0], "volume": [1, 1, 1]})}
    return FakeSource(calendar=cal, bars=bars, snapshots=snaps)


def test_build_market_state_enriched():
    ms = build_market_state(date(2026, 6, 12), _source(), history=[], 
                            as_of=datetime(2026, 6, 12, 16, 0), prev_gainers=frozenset({"RUN"}))
    assert ms.gainer_count == 1 and ms.loser_count == 1
    assert ms.gap_and_go_count == 1                          # RUN gapped (12 vs 10) and is a gainer
    assert ms.follow_through_rate == 1.0                     # RUN was a prior gainer and still is
    assert ms.max_runner_tier == 2                           # RUN: 10<11<14 -> 2 consecutive up-days
    assert ms.echelon and ms.echelon[0].tier == 2 and ms.echelon[0].representatives == ["RUN"]
    assert ms.sentiment_norm is None                         # empty history -> insufficient samples


def test_sentiment_norm_with_history():
    ms = build_market_state(date(2026, 6, 12), _source(), history=[-100.0, -50.0, 0.0],
                            as_of=datetime(2026, 6, 12, 16, 0), prev_gainers=frozenset(),
                            min_samples=3)
    assert ms.sentiment_norm == 1.0                          # today's strong raw > all history
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/features/test_builder.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'alpha.features.builder'`

- [ ] **Step 3: Write minimal implementation**

```python
# alpha/features/builder.py
from __future__ import annotations

from datetime import date as Date, datetime as DateTime

from alpha.data.source import MarketDataSource
from alpha.features.breadth import counts, failed_breakout_count, follow_through_rate, gap_and_go_count
from alpha.features.runner import consecutive_up_days, runner_echelon
from alpha.features.sentiment import normalize_sentiment, raw_sentiment
from alpha.state.market import MarketState
from alpha.universe.universe import build_universe

DEFAULT_MIN_SAMPLES = 60


def build_market_state(day: Date, source: MarketDataSource, history: list[float], as_of: DateTime,
                       prev_gainers: frozenset[str] = frozenset(),
                       min_samples: int = DEFAULT_MIN_SAMPLES) -> MarketState:
    """Full L1 perception build: enrich the day's universe with trailing runner depth + features.

    history = prior sentiment_raw values (<= day only); prev_gainers = the previous day's gainer set
    (the caller/loop threads it for follow-through). Reads only <= day data.

    FIREWALL CONTRACT: in production the caller (US-2 loop) MUST pass a GuardedSource(AsOfGuard(day))
    so any accidental >day fetch raises. This function reads <= day by construction (window ends at
    day; calendar filtered <= day) but does not itself install the guard.
    """
    universe = build_universe(source, day)
    # enrich gainers with strictly-trailing consecutive_up_days
    enriched = []
    start = _lookback_start(source, day)
    for s in universe.by_status("gainer"):
        bars = source.daily_bars(s.symbol, start, day)
        enriched.append(s.model_copy(update={"consecutive_up_days": consecutive_up_days(bars, day)}))
    g, gu, lo = counts(universe)
    ft = follow_through_rate(universe, prev_gainers)
    fb = failed_breakout_count(universe)
    echelon = runner_echelon(enriched)
    max_tier = echelon[0].tier if echelon else 0
    raw = raw_sentiment(gainer_count=g, max_runner_tier=max_tier, follow_through=(ft or 0.0),
                        failed_breakout_rate=(fb / g if g else 0.0), loser_count=lo)
    return MarketState(
        date=day, gainer_count=g, gap_up_count=gu, loser_count=lo,
        failed_breakout_count=fb, max_runner_tier=max_tier, echelon=echelon,
        breadth_raw=float(g - lo), sentiment_raw=raw,
        sentiment_norm=normalize_sentiment(raw, history, min_samples),
        follow_through_rate=ft, gap_and_go_count=gap_and_go_count(universe), as_of=as_of)


def _lookback_start(source, day: Date, window: int = 30) -> Date:
    """First trading day of the trailing window ending at `day` (for consecutive-up-days bars)."""
    cal = [d for d in source.trading_calendar() if d <= day]
    return cal[-window] if len(cal) >= window else (cal[0] if cal else day)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/features/test_builder.py -q`
Expected: PASS (2 passed)

- [ ] **Step 5: Commit**

```bash
git add alpha/features/builder.py tests/features/test_builder.py
git commit -m "US-1e Task 5: full L1 builder (compose features into enriched MarketState)"
```

---

### Task 6: US momentum state machine

**Files:**
- Create: `alpha/regime/__init__.py`
- Create: `alpha/regime/cycle.py`
- Create: `tests/regime/__init__.py`
- Create: `tests/regime/test_cycle.py`

The 6-state US momentum cycle as a `StateMachine` container (states + transition signals), with a canonical default. Phase names align with `CANONICAL_PHASES` (`alpha/harness/regime.py`).

- [ ] **Step 1: Write the failing test**

```python
# tests/regime/test_cycle.py
import pytest
from alpha.regime.cycle import StateMachine, EmotionPhase, default_us_cycle
from alpha.harness.regime import CANONICAL_PHASES


def test_default_cycle_has_six_canonical_phases():
    sm = default_us_cycle()
    assert sm.phase_names() == CANONICAL_PHASES        # washout..flush, in order


def test_transitions_point_to_known_phases():
    sm = default_us_cycle()
    known = set(sm.phase_names())
    for name in sm.phase_names():
        for to, _signal in sm.next_signals(name):
            assert to in known                          # no dangling transitions


def test_from_seed_list_rejects_duplicate_phase():
    with pytest.raises(ValueError):
        StateMachine.from_seed_list([{"phase": "trend"}, {"phase": "trend"}])


def test_get_and_signals():
    sm = default_us_cycle()
    assert sm.get("trend") is not None
    assert sm.get("nonexistent") is None
    assert isinstance(sm.next_signals("washout"), list)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/regime/test_cycle.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'alpha.regime'`

- [ ] **Step 3: Write minimal implementation**

```python
# alpha/regime/__init__.py
```

```python
# tests/regime/__init__.py
```

```python
# alpha/regime/cycle.py
from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from alpha.harness.regime import CANONICAL_PHASES


class Transition(BaseModel):
    model_config = ConfigDict(extra="forbid")
    to: str
    signal: str


class EmotionPhase(BaseModel):
    model_config = ConfigDict(extra="forbid")
    phase: str
    you_see: list[str] = Field(default_factory=list)
    transitions: list[Transition] = Field(default_factory=list)


class StateMachine(BaseModel):
    """US momentum cycle state machine (G_cycle seed; read-only structure — no inference here)."""
    phases: list[EmotionPhase] = Field(default_factory=list)

    def get(self, phase: str) -> EmotionPhase | None:
        return next((p for p in self.phases if p.phase == phase), None)

    def next_signals(self, phase: str) -> list[tuple[str, str]]:
        p = self.get(phase)
        return [(t.to, t.signal) for t in p.transitions] if p else []

    def phase_names(self) -> list[str]:
        return [p.phase for p in self.phases]

    @classmethod
    def from_seed_list(cls, items: list[dict]) -> "StateMachine":
        phases = [EmotionPhase(**d) for d in items]
        seen: set[str] = set()
        for p in phases:
            if p.phase in seen:
                raise ValueError(f"duplicate phase: {p.phase}")
            seen.add(p.phase)
        return cls(phases=phases)


def default_us_cycle() -> StateMachine:
    """The canonical 6-state US momentum cycle (blueprint §6). Transition signals are seed prose;
    US-1g/US-2 refine them. Frontside = recovery/ignition/trend; backside = distribution/flush."""
    return StateMachine.from_seed_list([
        {"phase": "washout", "you_see": ["few big gainers", "runners failing", "IWM downtrend",
                                          "new-lows high", "no follow-through"],
         "transitions": [{"to": "recovery", "signal": "first clean gap-and-go survivors + a day-2 continuation"},
                         {"to": "washout", "signal": "every pop sold; breadth stays dead"}]},
        {"phase": "recovery", "you_see": ["first first-green-day survivors", "breadth ticking up"],
         "transitions": [{"to": "ignition", "signal": "a narrative gets multiple movers same day"},
                         {"to": "washout", "signal": "the early leaders fail; follow-through collapses"}]},
        {"phase": "ignition", "you_see": ["a narrative ignites (many tickers up big)", "index follow-through day", "RVOL spikes"],
         "transitions": [{"to": "trend", "signal": "clear lead runner + sympathy basket extends"},
                         {"to": "distribution", "signal": "ignition fails to extend; leaders churn"}]},
        {"phase": "trend", "you_see": ["lead runner makes new highs daily", "sympathy runs", "low failed-breakout rate"],
         "transitions": [{"to": "distribution", "signal": "first big distribution day on the leader + no next-day recovery"}]},
        {"phase": "distribution", "you_see": ["choppy", "laggards run while leaders churn", "failed-breakout rate climbing"],
         "transitions": [{"to": "flush", "signal": "leader breaks down on volume / parabolic blowoff"},
                         {"to": "trend", "signal": "leaders reclaim; risk-on resumes"}]},
        {"phase": "flush", "you_see": ["leaders + sympathy co-flush", "the hot ticker dumped", "SSR broad"],
         "transitions": [{"to": "washout", "signal": "breadth collapses; old leaders stop falling, new narrative stirs"}]},
    ])
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/regime/test_cycle.py -q`
Expected: PASS (4 passed)

- [ ] **Step 5: Commit**

```bash
git add alpha/regime/__init__.py alpha/regime/cycle.py tests/regime/__init__.py tests/regime/test_cycle.py
git commit -m "US-1e Task 6: US momentum state machine (6-state canonical cycle)"
```

---

### Task 7: G_cycle classifier (read-only / SSOT)

**Files:**
- Create: `alpha/regime/classifier.py`
- Create: `tests/regime/test_classifier.py`

`G_cycle` reads a `MarketState` and returns a `RegimeRead` (global phase + confidence + frontside + risk-gate). **Read-only / SSOT** — it does not, and cannot, write the phase into a harness.

- [ ] **Step 1: Write the failing test**

```python
# tests/regime/test_classifier.py
from datetime import date, datetime
from alpha.state.market import MarketState
from alpha.regime.classifier import GCycle, RegimeRead
from alpha.harness.regime import CANONICAL_PHASES


def _ms(**kw):
    base = dict(date=date(2026, 6, 12), gainer_count=0, gap_up_count=0, loser_count=0,
               failed_breakout_count=0, max_runner_tier=0, echelon=[], breadth_raw=0.0,
               sentiment_raw=0.0, sentiment_norm=None, follow_through_rate=None,
               gap_and_go_count=0, as_of=datetime(2026, 6, 12, 16, 0))
    base.update(kw)
    return MarketState(**base)


def test_read_is_in_canonical_vocab_and_bounded():
    r = GCycle().read(_ms(sentiment_norm=0.7, gainer_count=30, max_runner_tier=4,
                          follow_through_rate=0.8, failed_breakout_count=1))
    assert isinstance(r, RegimeRead)
    assert r.phase in CANONICAL_PHASES
    assert 0.0 <= r.risk_gate <= 1.0 and 0.0 <= r.confidence <= 1.0


def test_strong_tape_is_trend_frontside():
    r = GCycle().read(_ms(sentiment_norm=0.85, gainer_count=40, max_runner_tier=5,
                          follow_through_rate=0.85, failed_breakout_count=1, loser_count=2))
    assert r.phase == "trend" and r.frontside is True and r.risk_gate > 0.6


def test_weak_tape_is_washout():
    r = GCycle().read(_ms(sentiment_norm=0.1, gainer_count=2, max_runner_tier=0,
                          follow_through_rate=0.05, failed_breakout_count=8, loser_count=40))
    assert r.phase == "washout" and r.frontside is False and r.risk_gate < 0.3


def test_distribution_is_backside():
    r = GCycle().read(_ms(sentiment_norm=0.6, gainer_count=20, max_runner_tier=3,
                          follow_through_rate=0.3, failed_breakout_count=12, loser_count=10))
    assert r.phase in ("distribution", "flush") and r.frontside is False


def test_none_sentiment_degrades_confidence():
    r = GCycle().read(_ms(sentiment_norm=None, gainer_count=5))
    assert r.phase in CANONICAL_PHASES and r.confidence <= 0.5      # uncertain without normalization
    assert r.risk_gate <= 0.5                                       # size multiplier capped when uncertain


def test_classifier_is_read_only_ssot():
    # SSOT (the hardest-won P0): G_cycle reads only — it must expose NO public method beyond read()
    # and hold no harness reference (constructs with no harness arg). Enumerated structurally so a
    # future write/update method can't slip past a hardcoded name list.
    import inspect
    GCycle()                                                        # constructs with no harness
    public = [m for m, _ in inspect.getmembers(GCycle(), predicate=inspect.ismethod)
              if not m.startswith("_")]
    assert public == ["read"], f"GCycle exposes non-read public methods: {public}"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/regime/test_classifier.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'alpha.regime.classifier'`

- [ ] **Step 3: Write minimal implementation**

```python
# alpha/regime/classifier.py
from __future__ import annotations

from dataclasses import dataclass

from alpha.state.market import MarketState


@dataclass(frozen=True)
class RegimeRead:
    """G_cycle output (an s_t-side label, NOT written back into H — SSOT)."""
    phase: str            # one of the canonical 6 US phases
    confidence: float     # [0,1]
    frontside: bool       # global frontside (risk-on) vs backside (every pop sold)
    risk_gate: float      # [0,1] speculative risk appetite / size multiplier


_FRONTSIDE = {"recovery", "ignition", "trend"}


class GCycle:
    """Read-only regime classifier (the G_cycle sub-agent). Deterministic, oracle-auditable rules.

    SSOT: read() returns a RegimeRead; this class has NO method that writes a phase into a harness.
    The LLM Refiner calibrates these thresholds against the realized-future oracle in US-2; per-
    narrative-line phases are US-3 (need theme tagging). Here it reads the GLOBAL mother-state.
    """

    def read(self, state: MarketState) -> RegimeRead:
        sn = state.sentiment_norm
        ft = state.follow_through_rate if state.follow_through_rate is not None else 0.0
        fb_rate = state.failed_breakout_count / state.gainer_count if state.gainer_count else (
            1.0 if state.failed_breakout_count else 0.0)
        # risk-gate: sentiment percentile when available, else a coarse breadth proxy in [0,1]
        if sn is not None:
            proxy = sn
            confidence = 0.7
        else:
            denom = state.gainer_count + state.loser_count
            proxy = (state.gainer_count / denom) if denom else 0.0
            confidence = 0.4                       # no regime-relative normalization yet

        # phase rules (objective; ordered by tape strength). fb_rate / follow-through split
        # frontside trend from backside distribution at similar strength.
        if proxy < 0.2:
            phase = "washout"
        elif proxy < 0.4:
            phase = "recovery"
        elif proxy < 0.6:
            phase = "ignition" if fb_rate < 0.4 else "distribution"
        else:  # strong tape
            if fb_rate >= 0.4 or ft < 0.4:
                phase = "flush" if (state.loser_count > state.gainer_count) else "distribution"
            else:
                phase = "trend"

        # Without regime context (sentiment_norm None) we can't be confidently risk-on, so cap the
        # size-multiplier output at neutral (phase banding still uses the raw proxy above).
        risk_gate = proxy if sn is not None else min(proxy, 0.5)
        return RegimeRead(phase=phase, confidence=confidence,
                          frontside=phase in _FRONTSIDE, risk_gate=risk_gate)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/regime/test_classifier.py -q`
Expected: PASS (6 passed)

- [ ] **Step 5: Commit**

```bash
git add alpha/regime/classifier.py tests/regime/test_classifier.py
git commit -m "US-1e Task 7: G_cycle classifier (read-only/SSOT global regime read)"
```

---

### Task 8: US-1e acceptance gate + docs update

**Files:**
- Create: `tests/regime/test_us1e_acceptance.py`
- Modify: `docs/PROJECT_STATE.md` (mark US-1e done)

- [ ] **Step 1: Write the acceptance test**

```python
# tests/regime/test_us1e_acceptance.py
"""US-1e acceptance: the full L1 builder turns <=t data into an enriched MarketState, and the
read-only G_cycle maps it to a canonical-vocabulary regime read whose phase is a transition target
in the state machine."""
from datetime import date, datetime
import pandas as pd
from alpha.data.source import FakeSource
from alpha.features.builder import build_market_state
from alpha.regime.classifier import GCycle
from alpha.regime.cycle import default_us_cycle


def _source():
    cal = [date(2026, 6, 10), date(2026, 6, 11), date(2026, 6, 12)]
    snaps = {date(2026, 6, 12): pd.DataFrame({
        "symbol": ["RUN"], "name": ["r"], "open": [12.0], "high": [14], "low": [12],
        "close": [14.0], "volume": [1], "prev_close": [10.0]})}
    bars = {"RUN": pd.DataFrame({"date": cal, "open": [10, 11, 12.0], "high": [11, 12, 14],
                                 "low": [10, 11, 12], "close": [10.0, 11.0, 14.0], "volume": [1, 1, 1]})}
    return FakeSource(calendar=cal, bars=bars, snapshots=snaps)


def test_perception_to_regime_read():
    ms = build_market_state(date(2026, 6, 12), _source(), history=[-5.0, -3.0, -1.0],
                            as_of=datetime(2026, 6, 12, 16, 0), prev_gainers=frozenset({"RUN"}),
                            min_samples=3)
    read = GCycle().read(ms)
    sm = default_us_cycle()
    assert read.phase in sm.phase_names()                # phase is a known state
    assert 0.0 <= read.risk_gate <= 1.0
    # the read's phase is reachable in the cycle (either a start state or a transition target)
    targets = {read.phase} | {to for p in sm.phase_names() for to, _ in sm.next_signals(p)}
    assert read.phase in targets
```

- [ ] **Step 2: Run the full suite**

Run: `python -m pytest -q`
Expected: PASS — all US-0 + US-1a/b/c/d + US-1e tests green.

- [ ] **Step 3: Update `docs/PROJECT_STATE.md`**

In the US-1 section, mark **US-1e (regime machine + features) done** with the date and a one-line summary (L1 feature modules — sentiment/breadth/runner; full builder enriching MarketState with trailing runner depth + regime-relative sentiment_norm; 6-state US momentum StateMachine; read-only/SSOT G_cycle global regime classifier). Update the "Next" pointer to **US-1f (sizing L3 + guard L4)**.

- [ ] **Step 4: Commit**

```bash
git add tests/regime/test_us1e_acceptance.py docs/PROJECT_STATE.md
git commit -m "US-1e Task 8: acceptance gate (perception -> regime read) + PROJECT_STATE"
```

---

## Self-Review (run after writing, fix inline)

**Spec coverage (US-1 "regime classifier + state machine"; §5):** feature modules sentiment/breadth/runner (Tasks 1-3) ✓ · enriched MarketState + full builder (Tasks 4-5) ✓ · regime-relative sentiment_norm, no absolute thresholds (Tasks 1,5) ✓ · 6-state US momentum machine (Task 6) ✓ · read-only/SSOT G_cycle global classifier with frontside/backside + risk-gate (Task 7) ✓ · trailing-only runner computation, firewall-safe (Tasks 3,5) ✓. **Deferred & documented:** per-narrative-line phases → US-3; LLM calibration of judges → US-2; full-builder wiring into WalkForwardEval → US-2.

**Type consistency:** `raw_sentiment`/`normalize_sentiment` signatures used identically in sentiment tests and the builder. `RunnerRung(tier, count, representatives)` matches US-0's schema. `build_market_state(day, source, history, as_of, prev_gainers, min_samples)` consistent across Task 5 + acceptance. `MarketState` new fields used in builder + classifier match Task 4. `StateMachine`/`EmotionPhase`/`Transition` + `default_us_cycle` consistent across Task 6 + classifier acceptance. `GCycle.read(state) -> RegimeRead` consistent. Phase vocabulary sourced from `alpha/harness/regime.py::CANONICAL_PHASES` (single source).

**Placeholder scan:** no TBD/TODO; every code step shows full code.

**Scope:** L1 perception + regime only; no LLM, no sizing/guard, no agent. Produces an independently-testable perception layer that US-2's agent consumes (rich MarketState + regime read).
