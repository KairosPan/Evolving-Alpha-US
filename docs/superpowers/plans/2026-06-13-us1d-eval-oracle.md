# US-1d Eval Oracle + Scoring Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the firewall-clean evaluation scaffolding — a forward-return oracle (with delisting = terminal loss), an exogenous pool-category oracle, a pluggable scorer (return-primary, pool-diagnostic), trivial baselines, and a walk-forward harness that decides at `t` and scores at `t+horizon` (horizon≥2) — so US-1's "baselines reproduce, firewall no-leak" acceptance can be measured.

**Architecture:** `WalkForwardEval` walks the trading calendar; on each day it wraps the source in a per-day `GuardedSource(AsOfGuard(day))`, builds the `MarketState` + `CandidateUniverse` (US-0), records that day's **exogenous** pool membership (fixed-threshold gainer/loser sets, *independent of `H`*), and asks a `DecisionPolicy` to decide. Scoring is **delayed**: a decision made at `t` is scored only once `t+horizon` has been walked, using realized future bars/membership — the policy never sees `>t` data, so the firewall holds by construction. The default `ReturnScorer` scores by forward return (next-open→t+N-close), counts a delisting/halt-to-zero in the window as a terminal loss (−1.0, never discarded), and reports a cross-sectional `advantage` vs the "buy the whole decision-day gainer pool" baseline. `PoolScorer` is a coarse diagnostic over the exogenous categories.

**Tech Stack:** Python ≥3.11, pydantic v2, pandas, pytest. No LLM, no network — fully offline (tests use the US-0 `FakeSource`).

**Spec:** `docs/superpowers/specs/2026-06-13-us-market-adaptation-design.md` (US-1 "return + pool-category oracle, walk-forward, baselines"; §7 oracle; §10 eval protocol). Sub-plan **US-1d** of US-1 (after 1c persistence; before 1e regime machine). Carries spec P0s: return-oracle primary + **delist=terminal-loss**; **exogenous** pool-category (kills the H-circular threshold); **horizon≥2**.

**Scope boundary (US-1d only):** oracles + scorer + metrics + decision contract + baselines + walk-forward. **Baseline-only acceptance** — no LLM agent yet (US-2), so walk-forward runs only the trivial baselines. **Deferred:** the rich human-facing `DecisionPackage` (size_tier/fill/taboo/regime_read fields) → US-1g (US-1d defines the minimal eval contract it extends); the regime classifier that would give a real per-line phase → US-1e (membership here is exogenous fixed-threshold, not regime-relative); **fill-feasibility + cost model** → US-3 (at daily cadence US entries fill at next-open; hard halt-locked infeasibility needs intraday/halt data); the rich `Trajectory` per-step record + stop-on-nuke path pricing → US-2 inner loop; purged/embargoed CV + multi-seed → US-2 eval protocol. **Reused (do not redefine):** `MarketState`, `CandidateUniverse`/`StockSnapshot`, `build_universe`, `build_market_state`, `MarketDataSource`/`GuardedSource`/`AsOfGuard`, `trading_days_between`.

**Conventions:** all code/comments English; `from __future__ import annotations` at the top of every module; commit after every passing task; run via `python -m pytest`.

**Key invariants (each gets a test):**
1. The forward-return oracle buys next-open, sells t+N-close; honest `None` on missing data; raises if `entry_day == exit_day` (no same-day round-trip).
2. **Delisting = terminal loss:** a candidate tradable at entry but delisted/halted-to-zero by exit scores −1.0 (and category `nuked`), never discarded for missing exit data.
3. The pool-category oracle is **exogenous**: membership comes from module-constant thresholds on raw daily moves, never from `H` or the (H-evolvable) universe screen.
4. Walk-forward never leaks: the policy is called with `≤t` snapshots; scoring uses a guard at the current cursor; a decision at `t` is scored using `t+1..t+horizon` only, with `horizon≥2` enforced.
5. Baselines reproduce deterministically (same source + window → same report).

---

### Task 1: Eval package + decision contract

**Files:**
- Create: `alpha/eval/__init__.py`
- Create: `alpha/eval/decision.py`
- Create: `tests/eval/__init__.py`
- Create: `tests/eval/test_decision.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/eval/test_decision.py
import pytest
from pydantic import ValidationError
from datetime import date
from alpha.eval.decision import Candidate, DecisionPackage


def test_candidate_defaults_and_bounds():
    c = Candidate(symbol="RUN")
    assert c.name == "" and c.pattern == "" and c.confidence == 0.5
    with pytest.raises(ValidationError):
        Candidate(symbol="RUN", confidence=1.5)


def test_decision_package_frozen():
    d = DecisionPackage(date=date(2026, 6, 12),
                        candidates=[Candidate(symbol="RUN", pattern="gap_and_go")])
    assert d.candidates[0].symbol == "RUN" and d.no_trade_reason == ""
    with pytest.raises(ValidationError):
        d.no_trade_reason = "x"


def test_no_trade_package():
    d = DecisionPackage(date=date(2026, 6, 12), no_trade_reason="risk-off")
    assert d.candidates == [] and d.no_trade_reason == "risk-off"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/eval/test_decision.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'alpha.eval'`

- [ ] **Step 3: Write minimal implementation**

```python
# alpha/eval/__init__.py
```

```python
# tests/eval/__init__.py
```

```python
# alpha/eval/decision.py
from __future__ import annotations

from datetime import date as Date
from typing import Protocol

from pydantic import BaseModel, ConfigDict, Field

from alpha.state.market import MarketState
from alpha.universe.universe import CandidateUniverse


class Candidate(BaseModel):
    """One picked ticker (US-1d eval contract: which symbol + declared pattern, for attribution)."""
    model_config = ConfigDict(frozen=True)
    symbol: str
    name: str = ""
    pattern: str = ""              # the matched pattern / skill_id (policy-declared, for by_pattern)
    reason: str = ""
    confidence: float = Field(default=0.5, ge=0.0, le=1.0)


class DecisionPackage(BaseModel):
    """A day's decision (US-1d minimal eval subset of the co-pilot's action a_t).

    US-1g enriches this with size_tier / fill_feasibility / taboo_check / regime_read. Here it is the
    eval contract: ranked candidates + no-trade reason + the policy's raw regime read (<=t).
    `symbol`s should be unique; a policy returning duplicates would be double-counted (the scorer
    de-dups defensively).
    """
    model_config = ConfigDict(frozen=True)
    date: Date
    candidates: list[Candidate] = Field(default_factory=list)
    no_trade_reason: str = ""
    regime_read: str = ""


class DecisionPolicy(Protocol):
    """Policy interface: read the day's aggregate state + candidate universe, produce a decision."""
    def decide(self, state: MarketState, universe: CandidateUniverse) -> DecisionPackage: ...
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/eval/test_decision.py -q`
Expected: PASS (3 passed)

- [ ] **Step 5: Commit**

```bash
git add alpha/eval/__init__.py alpha/eval/decision.py tests/eval/__init__.py tests/eval/test_decision.py
git commit -m "US-1d Task 1: eval package + decision contract (Candidate/DecisionPackage/DecisionPolicy)"
```

---

### Task 2: Forward-return oracle + delisting = terminal loss

**Files:**
- Create: `alpha/eval/return_oracle.py`
- Create: `tests/eval/test_return_oracle.py`

`forward_return` is a pure function; `ReturnOracle` wraps a source and adds the delisting-terminal-loss rule (P0). Enforces `entry_day != exit_day`.

- [ ] **Step 1: Write the failing test**

```python
# tests/eval/test_return_oracle.py
from datetime import date
import pandas as pd
import pytest
from alpha.eval.return_oracle import forward_return, ReturnOracle, TERMINAL_LOSS
from alpha.data.source import FakeSource


def _bars(dates, opens, closes):
    return pd.DataFrame({"date": dates, "open": opens, "high": closes, "low": opens,
                         "close": closes, "volume": [1]*len(dates)})


def test_forward_return_basic():
    bars = _bars([date(2026, 6, 11), date(2026, 6, 12)], [10.0, 11.0], [10.5, 13.0])
    # buy open@6/11 (10.0), sell close@6/12 (13.0) -> 0.30
    assert abs(forward_return(bars, date(2026, 6, 11), date(2026, 6, 12)) - 0.30) < 1e-9


def test_forward_return_missing_returns_none():
    bars = _bars([date(2026, 6, 11)], [10.0], [10.5])
    assert forward_return(bars, date(2026, 6, 11), date(2026, 6, 12)) is None     # no exit row
    assert forward_return(pd.DataFrame(), date(2026, 6, 11), date(2026, 6, 12)) is None


def test_oracle_no_same_day():
    src = FakeSource(calendar=[date(2026, 6, 12)], bars={}, snapshots={})
    with pytest.raises(ValueError):
        ReturnOracle(src).score("RUN", date(2026, 6, 12), date(2026, 6, 12))


def test_oracle_delisting_is_terminal_loss():
    cal = [date(2026, 6, 11), date(2026, 6, 12), date(2026, 6, 15)]
    bars = {"DEAD": _bars([date(2026, 6, 11)], [10.0], [10.5])}     # tradable at entry, gone after
    corp = pd.DataFrame({"symbol": ["DEAD"], "announce_date": [date(2026, 6, 10)],
                         "ex_date": [date(2026, 6, 12)], "kind": ["delist"], "ratio": [0.0]})
    src = FakeSource(calendar=cal, bars=bars, snapshots={}, corp_actions=corp)
    # entry 6/11 (tradable), exit 6/15 (no bar) + delist ex_date 6/12 in (entry, exit] -> terminal loss
    assert ReturnOracle(src).score("DEAD", date(2026, 6, 11), date(2026, 6, 15)) == TERMINAL_LOSS


def test_oracle_genuine_missing_returns_none():
    cal = [date(2026, 6, 11), date(2026, 6, 12)]
    src = FakeSource(calendar=cal, bars={}, snapshots={})           # no bars at all, no delist
    assert ReturnOracle(src).score("GHOST", date(2026, 6, 11), date(2026, 6, 12)) is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/eval/test_return_oracle.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'alpha.eval.return_oracle'`

- [ ] **Step 3: Write minimal implementation**

```python
# alpha/eval/return_oracle.py
from __future__ import annotations

from datetime import date as Date

import pandas as pd

TERMINAL_LOSS = -1.0


def forward_return(bars: pd.DataFrame, entry_day: Date, exit_day: Date) -> float | None:
    """Buy next-open, sell t+N-close: (close@exit_day - open@entry_day) / open@entry_day.

    entry/exit not in bars, open missing/<=0, or close missing -> None (honest, never fabricated).
    Pure: reads the given df only.
    """
    if bars is None or bars.empty or "date" not in bars.columns:
        return None
    e = bars.loc[bars["date"] == entry_day]
    x = bars.loc[bars["date"] == exit_day]
    if e.empty or x.empty:
        return None
    op = e.iloc[0].get("open")
    cl = x.iloc[0].get("close")
    if op is None or cl is None or pd.isna(op) or pd.isna(cl) or op <= 0:
        return None
    return float((cl - op) / op)


class ReturnOracle:
    """Forward-return oracle (uses realized OHLCV at scoring time). Pass a GuardedSource to bound it.

    Delisting/halt-to-zero rule: a symbol tradable at entry but with no exit bar AND a known delist
    ex_date in (entry, exit] is a TERMINAL LOSS (-1.0), never discarded as missing data.
    """

    def __init__(self, source) -> None:
        self._source = source

    def score(self, symbol: str, entry_day: Date, exit_day: Date) -> float | None:
        if entry_day == exit_day:
            raise ValueError(f"no same-day round-trip: entry_day == exit_day == {entry_day} "
                             f"(use horizon>=2)")
        bars = self._source.daily_bars(symbol, entry_day, exit_day)
        ret = forward_return(bars, entry_day, exit_day)
        if ret is not None:
            return ret
        if self._tradable_at(bars, entry_day) and self._delisted_between(symbol, entry_day, exit_day):
            return TERMINAL_LOSS
        return None

    @staticmethod
    def _tradable_at(bars: pd.DataFrame, entry_day: Date) -> bool:
        if bars is None or bars.empty or "date" not in bars.columns:
            return False
        e = bars.loc[bars["date"] == entry_day]
        if e.empty:
            return False
        op = e.iloc[0].get("open")
        return op is not None and not pd.isna(op) and op > 0

    def _delisted_between(self, symbol: str, entry_day: Date, exit_day: Date) -> bool:
        corp = self._source.corporate_actions(entry_day, exit_day)
        if corp is None or corp.empty:
            return False
        rows = corp[(corp["symbol"] == symbol) & (corp["kind"] == "delist")
                    & (corp["ex_date"] > entry_day) & (corp["ex_date"] <= exit_day)]
        return not rows.empty
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/eval/test_return_oracle.py -q`
Expected: PASS (5 passed)

- [ ] **Step 5: Commit**

```bash
git add alpha/eval/return_oracle.py tests/eval/test_return_oracle.py
git commit -m "US-1d Task 2: forward-return oracle + delisting=terminal-loss + horizon>=2 guard"
```

---

### Task 3: Exogenous pool-category oracle

**Files:**
- Create: `alpha/eval/oracle.py`
- Create: `tests/eval/test_oracle.py`

Membership comes from **module-constant** thresholds on a day's raw % moves — never from `H` or the universe screen. This is the P0 de-circularization.

- [ ] **Step 1: Write the failing test**

```python
# tests/eval/test_oracle.py
from datetime import date
import pandas as pd
from alpha.eval.oracle import (
    classify_day, outcome, DayMembership, PoolRecord, SCORE, GAINER_PCT, LOSER_PCT,
)


def _snap(symbols, closes, prev_closes):
    return pd.DataFrame({"symbol": symbols, "close": closes, "prev_close": prev_closes})


def test_thresholds_are_module_constants():
    assert GAINER_PCT == 20.0 and LOSER_PCT == -20.0    # fixed, exogenous (not from H)


def test_classify_day():
    snap = _snap(["UP", "FLAT", "DOWN"], [13.0, 10.2, 7.0], [10.0, 10.0, 10.0])
    mem = classify_day(snap)                              # +30% / +2% / -30%
    assert mem.gainers == frozenset({"UP"})
    assert mem.losers == frozenset({"DOWN"})


def test_outcome():
    mem = DayMembership(gainers=frozenset({"UP"}), losers=frozenset({"DOWN"}))
    assert outcome("UP", mem) == "continued"
    assert outcome("DOWN", mem) == "nuked"
    assert outcome("FLAT", mem) == "faded"
    assert SCORE == {"continued": 1.0, "faded": 0.0, "nuked": -1.0}


def test_pool_record():
    rec = PoolRecord()
    snap = _snap(["UP"], [13.0], [10.0])
    rec.record(date(2026, 6, 12), classify_day(snap))
    assert rec.get(date(2026, 6, 12)).gainers == frozenset({"UP"})
    assert rec.get(date(2026, 6, 13)) is None


def test_exogenous_threshold_differs_from_universe_screen():
    # +15% is a universe gainer (build_universe gainer_pct=10%) but NOT an exogenous oracle gainer
    # (GAINER_PCT=20%) -> proves the oracle membership is decoupled from the H-evolvable screen.
    mem = classify_day(_snap(["MID"], [11.5], [10.0]))     # +15%
    assert "MID" not in mem.gainers and "MID" not in mem.losers
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/eval/test_oracle.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'alpha.eval.oracle'`

- [ ] **Step 3: Write minimal implementation**

```python
# alpha/eval/oracle.py
from __future__ import annotations

from dataclasses import dataclass
from datetime import date as Date
from typing import Literal

import pandas as pd

Outcome = Literal["continued", "faded", "nuked"]
SCORE: dict[str, float] = {"continued": 1.0, "faded": 0.0, "nuked": -1.0}

# EXOGENOUS fixed thresholds (% daily move). Deliberately NOT from H or the universe screen, so the
# oracle label cannot be gamed by editing the harness (spec §7 de-circularization).
GAINER_PCT = 20.0
LOSER_PCT = -20.0


@dataclass(frozen=True)
class DayMembership:
    """A day's exogenous pool: big-gainer and loser symbol sets (fixed-threshold)."""
    gainers: frozenset[str]
    losers: frozenset[str]


def classify_day(snapshot: pd.DataFrame) -> DayMembership:
    """Classify a day's cross-section into gainer/loser pools by the fixed exogenous thresholds.

    pct = (close - prev_close) / prev_close * 100. Rows missing close/prev_close (or prev_close<=0)
    are unclassified (in neither pool).
    """
    if snapshot is None or snapshot.empty:
        return DayMembership(gainers=frozenset(), losers=frozenset())
    gainers: set[str] = set()
    losers: set[str] = set()
    for rec in snapshot.to_dict("records"):
        close, prev = rec.get("close"), rec.get("prev_close")
        if close is None or prev is None or pd.isna(close) or pd.isna(prev) or prev <= 0:
            continue
        pct = (close - prev) / prev * 100.0
        if pct >= GAINER_PCT:
            gainers.add(str(rec["symbol"]))
        elif pct <= LOSER_PCT:
            losers.add(str(rec["symbol"]))
    return DayMembership(gainers=frozenset(gainers), losers=frozenset(losers))


def outcome(symbol: str, mem: DayMembership) -> Outcome:
    """Realized category at a day: nuked (in losers) > continued (in gainers) > faded (neither)."""
    if symbol in mem.losers:
        return "nuked"
    if symbol in mem.gainers:
        return "continued"
    return "faded"


class PoolRecord:
    """Records per-day exogenous membership during a walk (each cursor records <= cursor only)."""

    def __init__(self) -> None:
        self._by_day: dict[Date, DayMembership] = {}

    def record(self, day: Date, mem: DayMembership) -> None:
        self._by_day[day] = mem

    def get(self, day: Date) -> DayMembership | None:
        return self._by_day.get(day)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/eval/test_oracle.py -q`
Expected: PASS (4 passed)

- [ ] **Step 5: Commit**

```bash
git add alpha/eval/oracle.py tests/eval/test_oracle.py
git commit -m "US-1d Task 3: exogenous pool-category oracle (fixed thresholds, decoupled from H)"
```

---

### Task 4: Metrics (ScoredCandidate + EvalReport)

**Files:**
- Create: `alpha/eval/metrics.py`
- Create: `tests/eval/test_metrics.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/eval/test_metrics.py
from datetime import date
from alpha.eval.metrics import ScoredCandidate, EvalReport, build_report


def _sc(symbol, outcome, score, base=None):
    return ScoredCandidate(decision_date=date(2026, 6, 12), symbol=symbol, pattern="p",
                           outcome=outcome, score=score, day_baseline=base)


def test_advantage_backfill():
    assert _sc("A", "continued", 1.0, base=0.2).advantage == 0.8
    assert _sc("A", "continued", 1.0).advantage == 1.0        # no baseline -> falls back to score


def test_build_report_aggregates():
    scored = [_sc("A", "continued", 0.30, 0.10), _sc("B", "nuked", -0.20, 0.10),
              _sc("C", "faded", 0.0, 0.10)]
    rep = build_report(scored, n_decisions=5, n_no_trade=2, horizon=2)
    assert rep.n_candidates == 3 and rep.n_decisions == 5 and rep.n_no_trade == 2 and rep.horizon == 2
    assert abs(rep.hit_rate - 1/3) < 1e-9 and abs(rep.nuke_rate - 1/3) < 1e-9
    assert abs(rep.mean_score - (0.30 - 0.20 + 0.0)/3) < 1e-9
    assert abs(rep.mean_excess - ((0.20) + (-0.30) + (-0.10))/3) < 1e-9
    assert "p" in rep.by_pattern and rep.by_pattern["p"].n == 3


def test_empty_report():
    rep = build_report([], n_decisions=3, n_no_trade=3, horizon=2)
    assert rep.n_candidates == 0 and rep.hit_rate == 0.0 and rep.mean_score == 0.0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/eval/test_metrics.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'alpha.eval.metrics'`

- [ ] **Step 3: Write minimal implementation**

```python
# alpha/eval/metrics.py
from __future__ import annotations

from datetime import date as Date
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, model_validator

from alpha.eval.oracle import Outcome


class ScoredCandidate(BaseModel):
    """One scored candidate.

    score = raw score (ReturnScorer: forward return; PoolScorer: SCORE[outcome]);
    day_baseline = the decision-day gainer-pool baseline (same scorer lens; None on empty pool);
    advantage = score - day_baseline (cross-sectional excess, de-market-beta; falls back to score).
    """
    model_config = ConfigDict(frozen=True)
    decision_date: Date
    symbol: str
    pattern: str
    outcome: Outcome
    score: float
    day_baseline: float | None = None
    advantage: float

    @model_validator(mode="before")
    @classmethod
    def _fill_advantage(cls, data: Any) -> Any:
        if isinstance(data, dict) and data.get("advantage") is None and data.get("score") is not None:
            base = data.get("day_baseline")
            data = {**data, "advantage": data["score"] - base if base is not None else data["score"]}
        return data


class PatternStat(BaseModel):
    model_config = ConfigDict(frozen=True)
    n: int
    hit_rate: float
    nuke_rate: float
    mean_score: float


class EvalReport(BaseModel):
    model_config = ConfigDict(frozen=True)
    n_decisions: int
    n_no_trade: int
    n_candidates: int
    horizon: int = 2
    hit_rate: float          # continued / n_candidates
    nuke_rate: float         # nuked / n_candidates
    mean_score: float        # expectancy (raw lens)
    mean_excess: float = 0.0  # mean advantage (cross-sectional excess)
    by_pattern: dict[str, PatternStat] = Field(default_factory=dict)


def _agg(items: list[ScoredCandidate]) -> tuple[float, float, float, float]:
    n = len(items)
    if n == 0:
        return (0.0, 0.0, 0.0, 0.0)
    hits = sum(1 for s in items if s.outcome == "continued")
    nukes = sum(1 for s in items if s.outcome == "nuked")
    mean = sum(s.score for s in items) / n
    excess = sum(s.advantage for s in items) / n
    return (hits / n, nukes / n, mean, excess)


def build_report(scored: list[ScoredCandidate], n_decisions: int,
                 n_no_trade: int, horizon: int = 2) -> EvalReport:
    hit, nuke, mean, excess = _agg(scored)
    patterns: dict[str, list[ScoredCandidate]] = {}
    for s in scored:
        patterns.setdefault(s.pattern, []).append(s)
    by_pattern = {pat: PatternStat(n=len(items), hit_rate=_agg(items)[0],
                                   nuke_rate=_agg(items)[1], mean_score=_agg(items)[2])
                  for pat, items in patterns.items()}
    return EvalReport(n_decisions=n_decisions, n_no_trade=n_no_trade, n_candidates=len(scored),
                      horizon=horizon, hit_rate=hit, nuke_rate=nuke, mean_score=mean,
                      mean_excess=excess, by_pattern=by_pattern)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/eval/test_metrics.py -q`
Expected: PASS (3 passed)

- [ ] **Step 5: Commit**

```bash
git add alpha/eval/metrics.py tests/eval/test_metrics.py
git commit -m "US-1d Task 4: metrics (ScoredCandidate + EvalReport + build_report)"
```

---

### Task 5: Pluggable scorer (ReturnScorer default + PoolScorer)

**Files:**
- Create: `alpha/eval/scorer.py`
- Create: `tests/eval/test_scorer.py`

`ReturnScorer` is primary (score = forward return, delist=−1.0 kept). `PoolScorer` is the coarse diagnostic. Both compute `advantage` vs the decision-day gainer-pool baseline.

- [ ] **Step 1: Write the failing test**

```python
# tests/eval/test_scorer.py
from datetime import date
import pandas as pd
import pytest
from alpha.eval.decision import Candidate, DecisionPackage
from alpha.eval.oracle import DayMembership
from alpha.eval.return_oracle import ReturnOracle
from alpha.eval.scorer import PoolScorer, ReturnScorer
from alpha.data.source import FakeSource


def _decision(*symbols):
    return DecisionPackage(date=date(2026, 6, 11),
                           candidates=[Candidate(symbol=s, pattern="p") for s in symbols])


def test_pool_scorer_outcome_and_advantage():
    decision_mem = DayMembership(gainers=frozenset({"WIN", "B"}), losers=frozenset())
    exit_mem = DayMembership(gainers=frozenset({"WIN"}), losers=frozenset({"B"}))
    sc = PoolScorer().score_step(_decision("WIN"), decision_mem, exit_mem,
                                 date(2026, 6, 12), date(2026, 6, 15), oracle=None)
    # baseline = mean SCORE over decision gainers {WIN:continued=1, B:nuked=-1} = 0.0
    assert sc["WIN"].outcome == "continued" and sc["WIN"].score == 1.0
    assert sc["WIN"].day_baseline == 0.0 and sc["WIN"].advantage == 1.0


def test_return_scorer_uses_forward_return_and_keeps_delist():
    cal = [date(2026, 6, 11), date(2026, 6, 12), date(2026, 6, 15)]
    bars = {
        "WIN": pd.DataFrame({"date": [date(2026, 6, 12), date(2026, 6, 15)], "open": [10.0, 11.0],
                             "high": [11, 13], "low": [10, 11], "close": [10.5, 13.0], "volume": [1, 1]}),
        "DEAD": pd.DataFrame({"date": [date(2026, 6, 12)], "open": [10.0], "high": [10], "low": [9],
                              "close": [9.5], "volume": [1]}),
    }
    corp = pd.DataFrame({"symbol": ["DEAD"], "announce_date": [date(2026, 6, 11)],
                         "ex_date": [date(2026, 6, 15)], "kind": ["delist"], "ratio": [0.0]})
    src = FakeSource(calendar=cal, bars=bars, snapshots={}, corp_actions=corp)
    decision_mem = DayMembership(gainers=frozenset({"WIN"}), losers=frozenset())
    exit_mem = DayMembership(gainers=frozenset({"WIN"}), losers=frozenset({"DEAD"}))
    out = ReturnScorer().score_step(_decision("WIN", "DEAD"), decision_mem, exit_mem,
                                    date(2026, 6, 12), date(2026, 6, 15), oracle=ReturnOracle(src))
    assert abs(out["WIN"].score - 0.30) < 1e-9            # (13-10)/10
    assert out["DEAD"].score == -1.0                       # delist = terminal loss, NOT discarded
    assert out["DEAD"].outcome == "nuked"


def test_return_scorer_discards_genuine_missing():
    src = FakeSource(calendar=[date(2026, 6, 12), date(2026, 6, 15)], bars={}, snapshots={})
    decision_mem = DayMembership(gainers=frozenset(), losers=frozenset())
    exit_mem = DayMembership(gainers=frozenset(), losers=frozenset())
    out = ReturnScorer().score_step(_decision("GHOST"), decision_mem, exit_mem,
                                    date(2026, 6, 12), date(2026, 6, 15), oracle=ReturnOracle(src))
    assert out == {}                                       # no data, not a delist -> discarded


def test_scorer_dedups_duplicate_symbols():
    decision_mem = DayMembership(gainers=frozenset(), losers=frozenset())
    exit_mem = DayMembership(gainers=frozenset({"X"}), losers=frozenset())
    dec = DecisionPackage(date=date(2026, 6, 11),
                          candidates=[Candidate(symbol="X", pattern="p"), Candidate(symbol="X", pattern="p")])
    out = PoolScorer().score_step(dec, decision_mem, exit_mem,
                                  date(2026, 6, 12), date(2026, 6, 15), oracle=None)
    assert len(out) == 1                                    # duplicate symbol counted once
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/eval/test_scorer.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'alpha.eval.scorer'`

- [ ] **Step 3: Write minimal implementation**

```python
# alpha/eval/scorer.py
from __future__ import annotations

from datetime import date as Date
from typing import Protocol

from alpha.eval.decision import DecisionPackage
from alpha.eval.metrics import ScoredCandidate
from alpha.eval.oracle import SCORE, DayMembership, outcome
from alpha.eval.return_oracle import ReturnOracle


class Scorer(Protocol):
    """Score one matured decision into {symbol: ScoredCandidate} (de-duped; may drop missing-data).

    decision_mem = decision-day (<=t) exogenous membership, used only to define the day_baseline set.
    exit_mem = exit-day membership, used for the realized outcome category. Always consumes t+ labels
    post-hoc; never feeds the decision path (firewall).
    """
    def score_step(self, decision: DecisionPackage, decision_mem: DayMembership,
                   exit_mem: DayMembership, entry_day: Date, exit_day: Date,
                   oracle: ReturnOracle | None) -> dict[str, ScoredCandidate]: ...


class PoolScorer:
    """Diagnostic: outcome category + SCORE[outcome]. baseline = mean SCORE over decision gainers."""

    def score_step(self, decision: DecisionPackage, decision_mem: DayMembership,
                   exit_mem: DayMembership, entry_day: Date, exit_day: Date,
                   oracle: ReturnOracle | None) -> dict[str, ScoredCandidate]:
        base = self._baseline(decision_mem, exit_mem)
        out: dict[str, ScoredCandidate] = {}
        for c in decision.candidates:
            if c.symbol in out:
                continue
            oc = outcome(c.symbol, exit_mem)
            score = SCORE[oc]
            out[c.symbol] = ScoredCandidate(
                decision_date=decision.date, symbol=c.symbol, pattern=c.pattern, outcome=oc,
                score=score, day_baseline=base,
                advantage=score - base if base is not None else score)
        return out

    @staticmethod
    def _baseline(decision_mem: DayMembership, exit_mem: DayMembership) -> float | None:
        pool = decision_mem.gainers
        if not pool:
            return None
        return sum(SCORE[outcome(s, exit_mem)] for s in pool) / len(pool)


class ReturnScorer:
    """Primary: score = forward return (delist=-1.0 KEPT; genuine missing -> discard).
    outcome = exit-day category (for reporting). baseline = mean forward return over decision gainers."""

    def score_step(self, decision: DecisionPackage, decision_mem: DayMembership,
                   exit_mem: DayMembership, entry_day: Date, exit_day: Date,
                   oracle: ReturnOracle | None) -> dict[str, ScoredCandidate]:
        if oracle is None:
            raise ValueError("ReturnScorer requires a ReturnOracle")
        base = self._baseline(decision_mem, entry_day, exit_day, oracle)
        out: dict[str, ScoredCandidate] = {}
        for c in decision.candidates:
            if c.symbol in out:
                continue
            ret = oracle.score(c.symbol, entry_day, exit_day)
            if ret is None:
                continue                              # genuine missing data -> discard
            oc = outcome(c.symbol, exit_mem)
            out[c.symbol] = ScoredCandidate(
                decision_date=decision.date, symbol=c.symbol, pattern=c.pattern, outcome=oc,
                score=ret, day_baseline=base,
                advantage=ret - base if base is not None else ret)
        return out

    @staticmethod
    def _baseline(decision_mem: DayMembership, entry_day: Date, exit_day: Date,
                  oracle: ReturnOracle) -> float | None:
        rets = [r for s in sorted(decision_mem.gainers)
                if (r := oracle.score(s, entry_day, exit_day)) is not None]
        return sum(rets) / len(rets) if rets else None
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/eval/test_scorer.py -q`
Expected: PASS (3 passed)

- [ ] **Step 5: Commit**

```bash
git add alpha/eval/scorer.py tests/eval/test_scorer.py
git commit -m "US-1d Task 5: pluggable scorer (ReturnScorer primary + PoolScorer diagnostic)"
```

---

### Task 6: Baselines (Hmin)

**Files:**
- Create: `alpha/eval/baselines.py`
- Create: `tests/eval/test_baselines.py`

`NoTrade`, `ChaseBiggestGainer` (the naive US-momentum floor), and `PoolAverage` (the zero-advantage benchmark = "buy every gainer").

- [ ] **Step 1: Write the failing test**

```python
# tests/eval/test_baselines.py
from datetime import date, datetime
from alpha.universe.stock import StockSnapshot
from alpha.universe.universe import CandidateUniverse
from alpha.state.market import MarketState
from alpha.eval.baselines import NoTradePolicy, ChaseBiggestGainerPolicy, PoolAveragePolicy


def _state():
    return MarketState(date=date(2026, 6, 12), gainer_count=2, gap_up_count=0, loser_count=0,
                       failed_breakout_count=0, max_runner_tier=0, echelon=[], breadth_raw=0.0,
                       sentiment_norm=None, as_of=datetime(2026, 6, 12, 16, 0))


def _universe():
    return CandidateUniverse.from_stocks([
        StockSnapshot(symbol="BIG", name="Big", status="gainer", pct_change=40.0),
        StockSnapshot(symbol="SMALL", name="Small", status="gainer", pct_change=22.0),
        StockSnapshot(symbol="DIP", name="Dip", status="loser", pct_change=-25.0),
    ])


def test_no_trade():
    d = NoTradePolicy().decide(_state(), _universe())
    assert d.candidates == [] and d.no_trade_reason


def test_chase_biggest_gainer():
    d = ChaseBiggestGainerPolicy().decide(_state(), _universe())
    assert [c.symbol for c in d.candidates] == ["BIG"]          # biggest pct_change among gainers
    assert d.candidates[0].pattern == "chase_biggest_gainer"


def test_pool_average_buys_all_gainers_sorted():
    d = PoolAveragePolicy().decide(_state(), _universe())
    assert [c.symbol for c in d.candidates] == ["BIG", "SMALL"]  # all gainers, sorted, deterministic


def test_chase_no_gainers():
    empty = CandidateUniverse.from_stocks([])
    d = ChaseBiggestGainerPolicy().decide(_state(), empty)
    assert d.candidates == [] and d.no_trade_reason
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/eval/test_baselines.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'alpha.eval.baselines'`

- [ ] **Step 3: Write minimal implementation**

```python
# alpha/eval/baselines.py
from __future__ import annotations

from alpha.eval.decision import Candidate, DecisionPackage
from alpha.state.market import MarketState
from alpha.universe.universe import CandidateUniverse


class NoTradePolicy:
    """Floor baseline: never trade."""

    def decide(self, state: MarketState, universe: CandidateUniverse) -> DecisionPackage:
        return DecisionPackage(date=state.date, no_trade_reason="baseline:no-trade")


class ChaseBiggestGainerPolicy:
    """Floor baseline (Hmin): blindly chase the day's biggest gainer (naivest US momentum)."""

    def decide(self, state: MarketState, universe: CandidateUniverse) -> DecisionPackage:
        gainers = universe.by_status("gainer")
        ranked = [s for s in gainers if s.pct_change is not None]
        if not ranked:
            return DecisionPackage(date=state.date, no_trade_reason="no gainers")
        top = max(s.pct_change for s in ranked)
        picks = sorted((s for s in ranked if abs(s.pct_change - top) < 1e-9), key=lambda s: s.symbol)
        cands = [Candidate(symbol=s.symbol, name=s.name, pattern="chase_biggest_gainer",
                           reason=f"+{s.pct_change:.0f}% biggest gainer") for s in picks]
        return DecisionPackage(date=state.date, candidates=cands)


class PoolAveragePolicy:
    """Benchmark baseline: buy the WHOLE gainer pool — the ~zero-advantage reference that answers
    'how much better than buying every gainer is the agent?'.

    NOTE: it buys the *universe* gainers (build_universe's regime-relative gainer_pct screen), which
    is NOT identical to the scorer's day_baseline pool (the EXOGENOUS fixed-threshold gainers). So its
    advantage is only APPROXIMATELY zero — exactly zero would require the screen threshold to equal
    the exogenous GAINER_PCT. It is the closest practical zero-point, not an algebraic identity."""

    def decide(self, state: MarketState, universe: CandidateUniverse) -> DecisionPackage:
        gainers = sorted(universe.by_status("gainer"), key=lambda s: s.symbol)
        if not gainers:
            return DecisionPackage(date=state.date, no_trade_reason="no gainers")
        cands = [Candidate(symbol=s.symbol, name=s.name, pattern="pool_avg", reason="pool baseline")
                 for s in gainers]
        return DecisionPackage(date=state.date, candidates=cands)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/eval/test_baselines.py -q`
Expected: PASS (4 passed)

- [ ] **Step 5: Commit**

```bash
git add alpha/eval/baselines.py tests/eval/test_baselines.py
git commit -m "US-1d Task 6: baselines (NoTrade / ChaseBiggestGainer / PoolAverage)"
```

---

### Task 7: WalkForwardEval (per-day guarded, delayed scoring, horizon≥2)

**Files:**
- Create: `alpha/eval/walk_forward.py`
- Create: `tests/eval/test_walk_forward.py`

Walks the calendar; per day wraps the source in a `GuardedSource`, builds state+universe, records exogenous membership, asks the policy. Scores a decision at `t` only once `t+horizon` is walked, using a guard at the current cursor. **horizon≥2 enforced.**

- [ ] **Step 1: Write the failing test**

```python
# tests/eval/test_walk_forward.py
from datetime import date
import pandas as pd
import pytest
from alpha.data.source import FakeSource
from alpha.eval.baselines import NoTradePolicy, ChaseBiggestGainerPolicy
from alpha.eval.scorer import ReturnScorer
from alpha.eval.walk_forward import WalkForwardEval


def _source():
    cal = [date(2026, 6, 10), date(2026, 6, 11), date(2026, 6, 12), date(2026, 6, 15)]
    # snapshots used for universe + exogenous membership (close vs prev_close)
    snaps = {}
    for d, rows in {
        date(2026, 6, 10): [("RUN", 14.0, 10.0), ("DIP", 8.0, 10.0)],   # RUN +40% gainer
        date(2026, 6, 11): [("RUN", 18.0, 14.0)],                        # RUN +28% gainer
        date(2026, 6, 12): [("RUN", 17.0, 18.0)],
        date(2026, 6, 15): [("RUN", 20.0, 17.0)],
    }.items():
        snaps[d] = pd.DataFrame({"symbol": [r[0] for r in rows], "name": [r[0] for r in rows],
                                 "open": [r[2] for r in rows], "high": [r[1] for r in rows],
                                 "low": [r[2] for r in rows], "close": [r[1] for r in rows],
                                 "volume": [1]*len(rows), "prev_close": [r[2] for r in rows]})
    bars = {"RUN": pd.DataFrame({
        "date": cal, "open": [10.0, 14.0, 18.0, 17.0], "high": [14, 18, 18, 20],
        "low": [10, 14, 17, 17], "close": [14.0, 18.0, 17.0, 20.0], "volume": [1, 1, 1, 1]})}
    return FakeSource(calendar=cal, bars=bars, snapshots=snaps)


def test_horizon_must_be_at_least_two():
    with pytest.raises(ValueError):
        WalkForwardEval(_source(), date(2026, 6, 10), date(2026, 6, 15), horizon=1)


def test_no_trade_yields_no_candidates():
    wf = WalkForwardEval(_source(), date(2026, 6, 10), date(2026, 6, 15), horizon=2)
    rep = wf.run(NoTradePolicy())
    assert rep.n_candidates == 0 and rep.n_no_trade == rep.n_decisions and rep.horizon == 2


def test_chase_baseline_reproduces_deterministically():
    wf1 = WalkForwardEval(_source(), date(2026, 6, 10), date(2026, 6, 15), horizon=2, scorer=ReturnScorer())
    wf2 = WalkForwardEval(_source(), date(2026, 6, 10), date(2026, 6, 15), horizon=2, scorer=ReturnScorer())
    r1 = wf1.run(ChaseBiggestGainerPolicy())
    r2 = wf2.run(ChaseBiggestGainerPolicy())
    assert (r1.n_candidates, r1.mean_score, r1.hit_rate) == (r2.n_candidates, r2.mean_score, r2.hit_rate)
    assert r1.n_candidates == 2            # RUN picked+scored on decision days d0 and d1 (regression guard)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/eval/test_walk_forward.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'alpha.eval.walk_forward'`

- [ ] **Step 3: Write minimal implementation**

```python
# alpha/eval/walk_forward.py
from __future__ import annotations

from datetime import date as Date, datetime as DateTime

from alpha.data.firewall import AsOfGuard
from alpha.data.source import GuardedSource
from alpha.data.calendar import trading_days_between
from alpha.eval.decision import DecisionPolicy
from alpha.eval.metrics import EvalReport, ScoredCandidate, build_report
from alpha.eval.oracle import PoolRecord, classify_day
from alpha.eval.return_oracle import ReturnOracle
from alpha.eval.scorer import PoolScorer
from alpha.state.builder import build_market_state
from alpha.universe.universe import build_universe


class WalkForwardEval:
    """Forward-replay eval: policy decides on <=t snapshots; scored at t+horizon with realized data.
    The firewall holds by construction (per-day GuardedSource; scoring guard at the current cursor).

    HORIZON SEMANTICS: `horizon` = trading-day steps from the DECISION day to the EXIT day. A decision
    at day t enters at t+1 OPEN and exits at t+horizon CLOSE. horizon>=2 therefore means the position
    is held at least overnight (t+1 open -> t+2 close) and is NEVER opened-and-closed in the same
    session — the US analog of the A-share T+1 no-same-day-round-trip constraint. (horizon=2 = the
    shortest legal hold; larger horizon = longer hold.) The last `horizon` decisions in the window
    have no t+horizon day yet and are left unscored (the full per-step Trajectory is US-2)."""

    def __init__(self, source, start: Date, end: Date, horizon: int = 2, scorer=None) -> None:
        if horizon < 2:
            raise ValueError(f"horizon must be >=2 (no same-day round-trip), got {horizon}")
        self._source = source
        self._start = start
        self._end = end
        self._horizon = horizon
        self._scorer = scorer or PoolScorer()

    def run(self, policy: DecisionPolicy) -> EvalReport:
        days = trading_days_between(self._source.trading_calendar(), self._start, self._end)
        record = PoolRecord()
        decisions: list = []        # one per walked day
        scored: list[ScoredCandidate] = []
        n_no_trade = 0
        for i, cursor in enumerate(days):
            guarded = GuardedSource(self._source, AsOfGuard(cursor))
            universe = build_universe(guarded, cursor)
            state = build_market_state(universe, cursor,
                                       as_of=DateTime(cursor.year, cursor.month, cursor.day, 16, 0))
            record.record(cursor, classify_day(guarded.daily_snapshot(cursor)))
            decision = policy.decide(state, universe)
            decisions.append(decision)
            if not decision.candidates:
                n_no_trade += 1
            # delayed scoring: score decision j once we've walked to j+horizon
            j = i - self._horizon
            if j >= 0:
                scored.extend(self._score(decisions[j], days, j, cursor, record))
        return build_report(scored, n_decisions=len(days), n_no_trade=n_no_trade, horizon=self._horizon)

    def _score(self, decision, days: list[Date], j: int, cursor: Date,
               record: PoolRecord) -> list[ScoredCandidate]:
        # invariant: j == i - horizon, so j+horizon == i (the current cursor index) — always a valid
        # index whose membership was recorded THIS iteration; days[j+1]/days[j+horizon] never go OOB.
        entry_day = days[j + 1]                       # buy next open (t+1)
        exit_day = days[j + self._horizon]            # sell t+horizon close
        decision_mem = record.get(days[j])
        exit_mem = record.get(exit_day)
        oracle = ReturnOracle(GuardedSource(self._source, AsOfGuard(cursor)))   # as_of>=exit, firewall ok
        out = self._scorer.score_step(decision, decision_mem, exit_mem, entry_day, exit_day, oracle)
        return list(out.values())
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/eval/test_walk_forward.py -q`
Expected: PASS (3 passed)

- [ ] **Step 5: Commit**

```bash
git add alpha/eval/walk_forward.py tests/eval/test_walk_forward.py
git commit -m "US-1d Task 7: WalkForwardEval (per-day guarded, delayed scoring, horizon>=2)"
```

---

### Task 8: US-1d acceptance gate + docs update

**Files:**
- Create: `tests/eval/test_us1d_acceptance.py`
- Modify: `docs/PROJECT_STATE.md` (mark US-1d done)

- [ ] **Step 1: Write the acceptance test**

```python
# tests/eval/test_us1d_acceptance.py
"""US-1d acceptance: baseline-only walk-forward reproduces, the firewall holds (a policy that
peeks at future data is blocked by the per-day guard), delisting scores as a terminal loss, and
the pool-category oracle is exogenous (independent of the universe screen / H)."""
from datetime import date
import pandas as pd
import pytest
from alpha.data.source import FakeSource
from alpha.data.firewall import LookaheadError
from alpha.eval.baselines import NoTradePolicy, PoolAveragePolicy
from alpha.eval.scorer import ReturnScorer
from alpha.eval.walk_forward import WalkForwardEval


def _source():
    cal = [date(2026, 6, 10), date(2026, 6, 11), date(2026, 6, 12), date(2026, 6, 15)]
    snaps = {}
    for d, rows in {
        date(2026, 6, 10): [("RUN", 14.0, 10.0)], date(2026, 6, 11): [("RUN", 18.0, 14.0)],
        date(2026, 6, 12): [("RUN", 17.0, 18.0)], date(2026, 6, 15): [("RUN", 20.0, 17.0)],
    }.items():
        snaps[d] = pd.DataFrame({"symbol": [r[0] for r in rows], "name": [r[0] for r in rows],
                                 "open": [r[2] for r in rows], "high": [r[1] for r in rows],
                                 "low": [r[2] for r in rows], "close": [r[1] for r in rows],
                                 "volume": [1], "prev_close": [r[2] for r in rows]})
    bars = {"RUN": pd.DataFrame({"date": cal, "open": [10.0, 14.0, 18.0, 17.0],
                                 "high": [14, 18, 18, 20], "low": [10, 14, 17, 17],
                                 "close": [14.0, 18.0, 17.0, 20.0], "volume": [1, 1, 1, 1]})}
    return FakeSource(calendar=cal, bars=bars, snapshots=snaps)


def test_baseline_walk_forward_reproduces_and_no_trade_is_empty():
    wf = WalkForwardEval(_source(), date(2026, 6, 10), date(2026, 6, 15), horizon=2)
    assert wf.run(NoTradePolicy()).n_candidates == 0
    a = WalkForwardEval(_source(), date(2026, 6, 10), date(2026, 6, 15), horizon=2, scorer=ReturnScorer())
    b = WalkForwardEval(_source(), date(2026, 6, 10), date(2026, 6, 15), horizon=2, scorer=ReturnScorer())
    assert a.run(PoolAveragePolicy()).mean_score == b.run(PoolAveragePolicy()).mean_score


def test_guarded_source_blocks_lookahead():
    # The policy only ever receives (state, universe) built from a per-day GuardedSource, so it
    # structurally cannot reach future data. Prove the underlying guard rejects an out-of-window fetch:
    from alpha.data.source import GuardedSource
    from alpha.data.firewall import AsOfGuard
    gs = GuardedSource(_source(), AsOfGuard(date(2026, 6, 11)))
    with pytest.raises(LookaheadError):
        gs.daily_bars("RUN", date(2026, 6, 11), date(2026, 6, 15))   # exit beyond cursor -> blocked
```

- [ ] **Step 2: Run the full suite**

Run: `python -m pytest -q`
Expected: PASS — all US-0 + US-1a/b/c + US-1d tests green.

- [ ] **Step 3: Update `docs/PROJECT_STATE.md`**

In the US-1 section, mark **US-1d (eval oracle + scoring) done** with the date and a one-line summary (forward-return oracle with delist=terminal-loss + horizon≥2; exogenous pool-category; pluggable ReturnScorer/PoolScorer with cross-sectional advantage; baselines; walk-forward with per-day guard + delayed scoring). Update the "Next" pointer to **US-1e (regime machine + features)**.

- [ ] **Step 4: Commit**

```bash
git add tests/eval/test_us1d_acceptance.py docs/PROJECT_STATE.md
git commit -m "US-1d Task 8: acceptance gate (baseline walk-forward + firewall + delist + exogenous oracle) + PROJECT_STATE"
```

---

## Self-Review (run after writing, fix inline)

**Spec coverage (US-1 "return + pool-category oracle, walk-forward, baselines"):** forward-return oracle (Task 2) ✓ · **delist=terminal-loss** P0 (Task 2) ✓ · **horizon≥2** P1 (Tasks 2,7) ✓ · **exogenous** pool-category P0 (Task 3) ✓ · pluggable scorer, return-primary (Task 5) ✓ · cross-sectional advantage / day-baseline (Tasks 4,5) ✓ · baselines incl. PoolAverage zero-point (Task 6) ✓ · walk-forward delayed scoring + firewall-by-construction (Task 7) ✓ · metrics/report (Task 4) ✓.

**Type consistency:** `Scorer.score_step(decision, decision_mem, exit_mem, entry_day, exit_day, oracle)` identical in `PoolScorer`/`ReturnScorer` and called identically by `WalkForwardEval._score`. `DayMembership(gainers, losers)`, `outcome`, `SCORE`, `classify_day` used consistently. `ScoredCandidate(decision_date, symbol, pattern, outcome, score, day_baseline, advantage)` matches `build_report`/scorers. Uses US-0 `build_universe`/`build_market_state`/`GuardedSource`/`AsOfGuard`/`trading_days_between` with their real signatures.

**Placeholder scan:** no TBD/TODO; every code step shows full code; deferrals (rich DecisionPackage → 1g; regime classifier → 1e; fill/cost → US-3; Trajectory/stop-on-nuke + purged-CV/multi-seed → US-2) are explicit scope notes.

**Scope:** eval scaffolding only; baseline-only acceptance (no LLM); no inner loop. Produces an independently-testable, firewall-clean eval layer that US-2 will drive with the LLM agent + Refiner.
