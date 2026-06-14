# US-1f Sizing (L3) + Guard (L4) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the two survival-critical post-decision layers — **L3 sizing/portfolio/correlation** (confidence×regime → size tier, same-narrative = one netted bet, total exposure vs the regime risk-gate) and **L4 guard** (stop-loss signals, hard vetoes, circuit breakers) — that turn the immutable-core risk doctrine into executable enforcement over a set of proposed picks.

**Architecture:** Pure, dependency-light value objects + functions. `sizing/` maps each `Pick(symbol, narrative, confidence)` to a `SizeTier` via `confidence × risk_gate`, groups picks by **narrative** so a multi-ticker narrative counts as **one netted bet**, and caps total exposure at `risk_gate × max_total`. `guard/` produces `StopSignal`s (form/regime/time), `VetoVerdict`s (regime-no-chase + reverse-split + flag-driven dilution/halt/regulatory), and a `Breaker` (single-name / single-day / consecutive-loss / MWCB). These are the executable form of the spec §6 immutable-core rules; US-1g/US-2 wire them into the `DecisionPackage` + inner loop.

**Tech Stack:** Python ≥3.11, pydantic v2 / dataclasses, pytest. No LLM, no network — fully offline.

**Spec:** `docs/superpowers/specs/2026-06-13-us-market-adaptation-design.md` (US-1 "sizing L3 + guard L4"; §4 module layout; §4.1 DecisionPackage; §6 immutable-core doctrine). Sub-plan **US-1f** of US-1 (after 1e regime; before 1g seeds + DecisionPackage). **New layer — designed from spec, not ported from CN** (the CN repo never built sizing/guard modules).

**Scope boundary (US-1f only):** the sizing + guard computation components, operating on lightweight inputs the caller supplies. **Deferred:** wiring these into the `DecisionPackage` (size_tier / fill_feasibility / taboo_check fields) → US-1g; wiring into the inner loop → US-2; the **data-dependent vetoes** (dilution/offering/ATM-shelf, halt-then-dump, going-concern, SSR, MWCB) fire only when their boolean flag is set — **US-3 supplies those flags** from intraday/fundamental data (US-1f builds the mechanism + the regime/reverse-split/stop/breaker rules that DO fire at daily cadence). **Reused:** `RegimeRead` (alpha/regime/classifier.py); narrative tagging is supplied upstream (the agent in US-2 / theme data in US-3) — US-1f tests it with explicit tags.

**Immutable-core rules made executable (spec §6):** respect the regime / no chasing in risk-off → `guard/veto`; same-narrative = one bet → `sizing/correlation` + `sizing/portfolio`; stop discipline → `guard/stops`; position/loss circuit-breakers → `guard/breaker`; don't-fight-SSR + dilution/halt vetoes → flag-driven in `guard/veto` (US-3 data).

**Conventions:** all code/comments English; `from __future__ import annotations` at top of every module; commit after every passing task; run via `python -m pytest`.

**Key invariants (each gets a test):**
1. `size_tier` scales with `confidence × risk_gate`; deep risk-off shrinks every tier toward flat.
2. Same-narrative picks net to **one** bet (portfolio exposure counts a narrative once, at its strongest-conviction weight), so N tickers in one narrative ≠ N× exposure.
3. Total portfolio exposure is capped at `risk_gate × max_total_exposure` (regime gates aggregate risk); over-budget plans are flagged `capped`.
4. The guard can **veto** (override) an entry: deep risk-off, a pending reverse-split, or any set data-flag (dilution/halt/regulatory) → vetoed; stop signals fire on form/regime/time.
5. Circuit breakers trip on single-day loss / consecutive losses / MWCB and halt new entries.

---

### Task 1: Sizing package + position tiers

**Files:**
- Create: `alpha/sizing/__init__.py`
- Create: `alpha/sizing/position.py`
- Create: `tests/sizing/__init__.py`
- Create: `tests/sizing/test_position.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/sizing/test_position.py
from alpha.sizing.position import size_tier, SIZE_TIER_WEIGHT, SizingConfig


def test_size_tier_scales_with_confidence_and_risk_gate():
    assert size_tier(0.9, 0.9) == "heavy"        # score 0.81
    assert size_tier(0.8, 0.7) == "core"         # score 0.56
    assert size_tier(0.6, 0.4) == "probe"        # score 0.24
    assert size_tier(0.3, 0.3) == "flat"         # score 0.09


def test_risk_off_shrinks_to_flat():
    # high conviction but deep risk-off regime -> flat (regime gates size)
    assert size_tier(0.95, 0.05) == "flat"       # score 0.0475


def test_tier_weights_monotonic():
    w = SIZE_TIER_WEIGHT
    assert w["flat"] == 0.0 < w["probe"] < w["core"] < w["heavy"] == 1.0


def test_config_defaults():
    cfg = SizingConfig()
    assert cfg.max_name_weight > 0 and cfg.max_total_exposure > 0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/sizing/test_position.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'alpha.sizing'`

- [ ] **Step 3: Write minimal implementation**

```python
# alpha/sizing/__init__.py
```

```python
# tests/sizing/__init__.py
```

```python
# alpha/sizing/position.py
from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

SizeTier = Literal["flat", "probe", "core", "heavy"]

# fraction of a single-name unit allocated at each tier
SIZE_TIER_WEIGHT: dict[str, float] = {"flat": 0.0, "probe": 0.25, "core": 0.5, "heavy": 1.0}


@dataclass(frozen=True)
class SizingConfig:
    """Risk budget (in single-name 'units'). Seed initial values — evolvable later."""
    max_name_weight: float = 1.0       # max weight any one name can carry
    max_total_exposure: float = 4.0    # max aggregate netted exposure at full risk-on (risk_gate=1)


def size_tier(confidence: float, risk_gate: float) -> SizeTier:
    """Map conviction x regime appetite to a discrete size tier. score = confidence * risk_gate.

    The regime risk_gate (from G_cycle) gates conviction: a strong pick in a risk-off tape sizes
    small — the executable form of 'respect the regime'.
    """
    score = max(0.0, confidence) * max(0.0, risk_gate)
    if score < 0.15:
        return "flat"
    if score < 0.35:
        return "probe"
    if score < 0.6:
        return "core"
    return "heavy"
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/sizing/test_position.py -q`
Expected: PASS (4 passed)

- [ ] **Step 5: Commit**

```bash
git add alpha/sizing/__init__.py alpha/sizing/position.py tests/sizing/__init__.py tests/sizing/test_position.py
git commit -m "US-1f Task 1: sizing package + position tiers (confidence x risk_gate)"
```

---

### Task 2: Correlation (same-narrative = one bet)

**Files:**
- Create: `alpha/sizing/correlation.py`
- Create: `tests/sizing/test_correlation.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/sizing/test_correlation.py
from alpha.sizing.correlation import Pick, group_by_narrative, correlated_groups


def _picks():
    return [
        Pick(symbol="AI1", narrative="ai", confidence=0.9),
        Pick(symbol="AI2", narrative="ai", confidence=0.6),
        Pick(symbol="NUKE1", narrative="nuclear", confidence=0.7),
        Pick(symbol="SOLO", narrative="", confidence=0.5),   # untagged -> its own bet
    ]


def test_group_by_narrative():
    groups = group_by_narrative(_picks())
    assert {s.symbol for s in groups["ai"]} == {"AI1", "AI2"}
    assert {s.symbol for s in groups["nuclear"]} == {"NUKE1"}
    # untagged narratives are keyed by symbol so they don't merge into one bucket
    assert "SOLO" in groups and len(groups["SOLO"]) == 1


def test_correlated_groups_returns_multi_member_only():
    cg = correlated_groups(_picks())
    assert cg == [["AI1", "AI2"]]            # only the multi-ticker narrative is a correlated group
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/sizing/test_correlation.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'alpha.sizing.correlation'`

- [ ] **Step 3: Write minimal implementation**

```python
# alpha/sizing/correlation.py
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Pick:
    """A proposed pick. narrative = the correlation key (theme/sympathy); '' = untagged (stands alone).
    The narrative tag is supplied upstream (agent in US-2 / theme data in US-3)."""
    symbol: str
    narrative: str
    confidence: float


def group_by_narrative(picks: list[Pick]) -> dict[str, list[Pick]]:
    """Group picks by narrative. Untagged picks ('') are keyed by symbol so they never merge."""
    groups: dict[str, list[Pick]] = {}
    for p in picks:
        key = p.narrative if p.narrative else p.symbol
        groups.setdefault(key, []).append(p)
    return groups


def correlated_groups(picks: list[Pick]) -> list[list[str]]:
    """Symbol groups (>=2 members) that share a real narrative — each is ONE correlated bet.
    Sorted for determinism."""
    out: list[list[str]] = []
    for key, members in group_by_narrative(picks).items():
        if len(members) >= 2 and any(m.narrative for m in members):
            out.append(sorted(m.symbol for m in members))
    return sorted(out)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/sizing/test_correlation.py -q`
Expected: PASS (2 passed)

- [ ] **Step 5: Commit**

```bash
git add alpha/sizing/correlation.py tests/sizing/test_correlation.py
git commit -m "US-1f Task 2: correlation (same-narrative = one bet)"
```

---

### Task 3: Portfolio plan (size + net + cap by risk-gate)

**Files:**
- Create: `alpha/sizing/portfolio.py`
- Create: `tests/sizing/test_portfolio.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/sizing/test_portfolio.py
from alpha.sizing.correlation import Pick
from alpha.sizing.portfolio import plan_portfolio, PortfolioPlan
from alpha.sizing.position import SizingConfig


def test_per_pick_tier_assigned():
    plan = plan_portfolio([Pick("RUN", "ai", 0.9)], risk_gate=0.9, config=SizingConfig())
    assert isinstance(plan, PortfolioPlan)
    assert plan.sized[0].symbol == "RUN" and plan.sized[0].size_tier == "heavy"


def test_same_narrative_nets_to_one_bet():
    # two AI names, both heavy (weight 1.0 each). Netted = ONE bet at the max weight (1.0), not 2.0.
    plan = plan_portfolio([Pick("AI1", "ai", 0.9), Pick("AI2", "ai", 0.9)],
                          risk_gate=1.0, config=SizingConfig())
    assert plan.correlated_groups == [["AI1", "AI2"]]
    assert plan.total_exposure == 1.0                 # one netted bet, not 2.0


def test_total_exposure_capped_by_risk_gate():
    # 6 independent names: conf 0.9 x risk_gate 0.5 = 0.45 -> core (weight 0.5) -> raw 6*0.5 = 3.0;
    # budget = risk_gate(0.5) * max_total(4) = 2.0 -> capped, total clamped to 2.0
    picks = [Pick(f"N{i}", f"narr{i}", 0.9) for i in range(6)]
    plan = plan_portfolio(picks, risk_gate=0.5, config=SizingConfig())
    assert plan.total_exposure_budget == 2.0
    assert plan.total_exposure == 2.0 and plan.capped is True


def test_no_picks():
    plan = plan_portfolio([], risk_gate=0.8, config=SizingConfig())
    assert plan.sized == [] and plan.total_exposure == 0.0 and plan.capped is False
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/sizing/test_portfolio.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'alpha.sizing.portfolio'`

- [ ] **Step 3: Write minimal implementation**

```python
# alpha/sizing/portfolio.py
from __future__ import annotations

from dataclasses import dataclass

from alpha.sizing.correlation import Pick, correlated_groups, group_by_narrative
from alpha.sizing.position import SIZE_TIER_WEIGHT, SizeTier, SizingConfig, size_tier


@dataclass(frozen=True)
class SizedPick:
    symbol: str
    narrative: str
    size_tier: SizeTier


@dataclass(frozen=True)
class PortfolioPlan:
    sized: list[SizedPick]                 # per-pick size tier (what the human sees per name)
    correlated_groups: list[list[str]]     # multi-ticker narratives = one bet each
    total_exposure: float                  # sum of per-narrative netted weights (post-cap)
    total_exposure_budget: float           # risk_gate * max_total_exposure (matches DecisionPackage §4.1)
    capped: bool                           # raw netted exposure exceeded the budget


def plan_portfolio(picks: list[Pick], risk_gate: float, config: SizingConfig) -> PortfolioPlan:
    """Assign size tiers, net same-narrative picks to one bet, cap aggregate exposure by risk_gate."""
    sized = [SizedPick(symbol=p.symbol, narrative=p.narrative,
                       size_tier=size_tier(p.confidence, risk_gate)) for p in picks]
    tier_by_symbol = {s.symbol: s.size_tier for s in sized}
    # each narrative group counts ONCE, at its strongest-conviction member's weight (one bet)
    raw_exposure = 0.0
    for members in group_by_narrative(picks).values():
        raw_exposure += max(SIZE_TIER_WEIGHT[tier_by_symbol[m.symbol]] for m in members) \
            * config.max_name_weight
    budget = max(0.0, risk_gate) * config.max_total_exposure
    capped = raw_exposure > budget
    total = min(raw_exposure, budget)
    return PortfolioPlan(sized=sized, correlated_groups=correlated_groups(picks),
                         total_exposure=total, total_exposure_budget=budget, capped=capped)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/sizing/test_portfolio.py -q`
Expected: PASS (4 passed)

- [ ] **Step 5: Commit**

```bash
git add alpha/sizing/portfolio.py tests/sizing/test_portfolio.py
git commit -m "US-1f Task 3: portfolio plan (size + narrative-net + risk-gate cap)"
```

---

### Task 4: Guard package + stop-loss signals

**Files:**
- Create: `alpha/guard/__init__.py`
- Create: `alpha/guard/stops.py`
- Create: `tests/guard/__init__.py`
- Create: `tests/guard/test_stops.py`

Stop signals are **form** (price ≤ stop), **regime** (tape flipped to backside/flush), and **time** (held past the plan).

- [ ] **Step 1: Write the failing test**

```python
# tests/guard/test_stops.py
from alpha.regime.classifier import RegimeRead
from alpha.guard.stops import Position, stop_signals


def _pos(**kw):
    base = dict(symbol="RUN", entry_price=10.0, current_price=11.0, stop_price=9.0,
               days_held=1, narrative="ai")
    base.update(kw)
    return Position(**base)


_TREND = RegimeRead(phase="trend", confidence=0.7, frontside=True, risk_gate=0.7)
_FLUSH = RegimeRead(phase="flush", confidence=0.6, frontside=False, risk_gate=0.2)


def test_no_stop_when_healthy():
    assert stop_signals(_pos(), _TREND, max_hold_days=5) == []


def test_form_stop_when_below_stop_price():
    sigs = stop_signals(_pos(current_price=8.5), _TREND, max_hold_days=5)
    assert [s.kind for s in sigs] == ["form"]


def test_regime_stop_on_backside():
    sigs = stop_signals(_pos(), _FLUSH, max_hold_days=5)
    assert "regime" in [s.kind for s in sigs]


def test_time_stop_when_held_too_long():
    sigs = stop_signals(_pos(days_held=6), _TREND, max_hold_days=5)
    assert "time" in [s.kind for s in sigs]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/guard/test_stops.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'alpha.guard'`

- [ ] **Step 3: Write minimal implementation**

```python
# alpha/guard/__init__.py
```

```python
# tests/guard/__init__.py
```

```python
# alpha/guard/stops.py
from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from alpha.regime.classifier import RegimeRead

StopKind = Literal["form", "regime", "time"]


@dataclass(frozen=True)
class Position:
    symbol: str
    entry_price: float
    current_price: float
    stop_price: float
    days_held: int
    narrative: str = ""


@dataclass(frozen=True)
class StopSignal:
    symbol: str
    kind: StopKind
    reason: str


def stop_signals(position: Position, regime: RegimeRead, max_hold_days: int) -> list[StopSignal]:
    """Stop discipline: form (price <= stop), regime (tape turned backside), time (held past plan)."""
    out: list[StopSignal] = []
    if position.current_price <= position.stop_price:
        out.append(StopSignal(position.symbol, "form",
                              f"price {position.current_price} <= stop {position.stop_price}"))
    if not regime.frontside:
        out.append(StopSignal(position.symbol, "regime",
                              f"regime backside ({regime.phase}); exit / no add"))
    if position.days_held > max_hold_days:
        out.append(StopSignal(position.symbol, "time",
                              f"held {position.days_held} > max {max_hold_days} days"))
    return out
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/guard/test_stops.py -q`
Expected: PASS (4 passed)

- [ ] **Step 5: Commit**

```bash
git add alpha/guard/__init__.py alpha/guard/stops.py tests/guard/__init__.py tests/guard/test_stops.py
git commit -m "US-1f Task 4: guard package + stop-loss signals (form/regime/time)"
```

---

### Task 5: Hard veto layer

**Files:**
- Create: `alpha/guard/veto.py`
- Create: `tests/guard/test_veto.py`

The veto **overrides** an entry. Rules that fire at daily cadence: deep risk-off (no-chase) + pending reverse-split. Data-flag rules (dilution / halt-then-dump / going-concern / regulatory / SSR) fire when their flag is set — **US-3 supplies the flags**.

- [ ] **Step 1: Write the failing test**

```python
# tests/guard/test_veto.py
from alpha.regime.classifier import RegimeRead
from alpha.guard.veto import CandidateContext, veto


_RISK_ON = RegimeRead(phase="trend", confidence=0.7, frontside=True, risk_gate=0.7)
_RISK_OFF = RegimeRead(phase="washout", confidence=0.5, frontside=False, risk_gate=0.1)


def test_clean_entry_not_vetoed():
    v = veto(CandidateContext(symbol="RUN", regime=_RISK_ON))
    assert v.vetoed is False and v.reasons == []


def test_deep_risk_off_vetoes_new_entry():
    v = veto(CandidateContext(symbol="RUN", regime=_RISK_OFF))
    assert v.vetoed is True and any("risk-off" in r for r in v.reasons)


def test_backside_distribution_vetoes_new_entry():
    # distribution: backside (frontside=False) but risk_gate above the deep-risk-off threshold
    distribution = RegimeRead(phase="distribution", confidence=0.6, frontside=False, risk_gate=0.4)
    v = veto(CandidateContext(symbol="RUN", regime=distribution))
    assert v.vetoed is True and any("backside" in r for r in v.reasons)


def test_reverse_split_pending_vetoes():
    v = veto(CandidateContext(symbol="RUN", regime=_RISK_ON, reverse_split_pending=True))
    assert v.vetoed is True and any("reverse split" in r for r in v.reasons)


def test_data_flags_veto_when_set():
    for flag in ("dilution", "halt_then_dump", "going_concern", "regulatory", "ssr"):
        v = veto(CandidateContext(symbol="RUN", regime=_RISK_ON, **{flag: True}))
        assert v.vetoed is True


def test_multiple_reasons_accumulate():
    v = veto(CandidateContext(symbol="RUN", regime=_RISK_OFF, reverse_split_pending=True))
    assert v.vetoed is True and len(v.reasons) >= 2
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/guard/test_veto.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'alpha.guard.veto'`

- [ ] **Step 3: Write minimal implementation**

```python
# alpha/guard/veto.py
from __future__ import annotations

from dataclasses import dataclass

from alpha.regime.classifier import RegimeRead

RISK_OFF_THRESHOLD = 0.2     # below this risk_gate, do not chase new longs (immutable-core)


@dataclass(frozen=True)
class CandidateContext:
    """Inputs the guard needs to clear a NEW entry. Data flags default False; US-3 sets them from
    intraday/fundamental sources (the mechanism is here; the data is later)."""
    symbol: str
    regime: RegimeRead
    reverse_split_pending: bool = False     # from US-0 corp_actions (PIT by announcement)
    dilution: bool = False                  # ATM/shelf/offering (US-3)
    halt_then_dump: bool = False            # (US-3 intraday)
    going_concern: bool = False             # (US-3 fundamental)
    regulatory: bool = False                # SEC/exchange action (US-3)
    ssr: bool = False                       # short-sale restriction active (US-3)


@dataclass(frozen=True)
class VetoVerdict:
    vetoed: bool
    reasons: list[str]


def veto(ctx: CandidateContext) -> VetoVerdict:
    """Hard veto on a new entry (overrides the agent). Accumulates all firing reasons."""
    reasons: list[str] = []
    # no chasing in risk-off OR on the backside (new entries only on the frontside) — mirrors the
    # regime stop in stops.py (stops exit on backside; veto blocks new entries on backside).
    if ctx.regime.risk_gate < RISK_OFF_THRESHOLD:
        reasons.append(f"risk-off regime (risk_gate {ctx.regime.risk_gate:.2f} < {RISK_OFF_THRESHOLD}): no chasing")
    elif not ctx.regime.frontside:
        reasons.append(f"backside regime ({ctx.regime.phase}): no new entries")
    if ctx.reverse_split_pending:
        reasons.append("reverse split pending")
    if ctx.dilution:
        reasons.append("dilution / offering / ATM-shelf")
    if ctx.halt_then_dump:
        reasons.append("halt-then-dump")
    if ctx.going_concern:
        reasons.append("going-concern risk")
    if ctx.regulatory:
        reasons.append("regulatory / SEC action")
    if ctx.ssr:
        reasons.append("short-sale restriction active (SSR): don't fight it")
    return VetoVerdict(vetoed=bool(reasons), reasons=reasons)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/guard/test_veto.py -q`
Expected: PASS (5 passed)

- [ ] **Step 5: Commit**

```bash
git add alpha/guard/veto.py tests/guard/test_veto.py
git commit -m "US-1f Task 5: hard veto layer (regime no-chase + reverse-split + data-flag vetoes)"
```

---

### Task 6: Circuit breaker

**Files:**
- Create: `alpha/guard/breaker.py`
- Create: `tests/guard/test_breaker.py`

Trips on single-day loss, consecutive losses, or a market-wide circuit-breaker (MWCB) event — halting new entries.

- [ ] **Step 1: Write the failing test**

```python
# tests/guard/test_breaker.py
from alpha.guard.breaker import Breaker, BreakerConfig


def test_no_trip_when_healthy():
    b = Breaker(BreakerConfig())
    b.record_day_pnl(-0.01)                  # small loss
    tripped, reasons = b.check()
    assert tripped is False and reasons == []


def test_single_day_loss_trips():
    b = Breaker(BreakerConfig(max_single_day_loss=0.05))
    b.record_day_pnl(-0.08)
    tripped, reasons = b.check()
    assert tripped is True and any("single-day" in r for r in reasons)


def test_consecutive_losses_trip():
    b = Breaker(BreakerConfig(max_consecutive_losses=3))
    for _ in range(3):
        b.record_day_pnl(-0.01)
    tripped, reasons = b.check()
    assert tripped is True and any("consecutive" in r for r in reasons)


def test_a_win_resets_consecutive_losses():
    b = Breaker(BreakerConfig(max_consecutive_losses=3))
    b.record_day_pnl(-0.01)
    b.record_day_pnl(-0.01)
    b.record_day_pnl(0.02)                   # win resets the streak
    b.record_day_pnl(-0.01)
    assert b.check()[0] is False


def test_mwcb_halts_new_entries():
    b = Breaker(BreakerConfig())
    b.set_mwcb(True)
    tripped, reasons = b.check()
    assert tripped is True and any("MWCB" in r for r in reasons)


def test_single_name_loss_trips():
    b = Breaker(BreakerConfig(max_single_name_loss=0.15))
    b.record_name_pnl("RUN", -0.10)
    b.record_name_pnl("RUN", -0.08)              # cumulative -18% <= -15%
    assert b.check_name("RUN")[0] is True
    assert b.check_name("OTHER")[0] is False     # untouched name is fine


def test_winning_name_not_tripped():
    b = Breaker(BreakerConfig(max_single_name_loss=0.15))
    b.record_name_pnl("WIN", -0.10)
    b.record_name_pnl("WIN", 0.30)               # net +20%
    assert b.check_name("WIN")[0] is False
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/guard/test_breaker.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'alpha.guard.breaker'`

- [ ] **Step 3: Write minimal implementation**

```python
# alpha/guard/breaker.py
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class BreakerConfig:
    """Loss circuit-breaker thresholds (fractions). Seed initial values — evolvable later."""
    max_single_day_loss: float = 0.06       # day P&L worse than -6% -> halt
    max_consecutive_losses: int = 4         # N losing days in a row -> halt
    max_single_name_loss: float = 0.15      # cumulative single-name loss worse than -15% -> halt adds to it


class Breaker:
    """Portfolio loss circuit-breaker. record_day_pnl per closed day; check() before new entries."""

    def __init__(self, config: BreakerConfig | None = None) -> None:
        self._config = config or BreakerConfig()
        self._last_day_pnl: float = 0.0
        self._consecutive_losses: int = 0
        self._mwcb: bool = False
        self._name_pnl: dict[str, float] = {}

    def record_day_pnl(self, pnl: float) -> None:
        self._last_day_pnl = pnl
        if pnl < 0:
            self._consecutive_losses += 1
        else:
            self._consecutive_losses = 0

    def record_name_pnl(self, symbol: str, pnl: float) -> None:
        """Accumulate per-name P&L (fraction) so a single name's drawdown can halt adds to it."""
        self._name_pnl[symbol] = self._name_pnl.get(symbol, 0.0) + pnl

    def check_name(self, symbol: str) -> tuple[bool, list[str]]:
        """Single-name circuit breaker: True if cumulative loss for `symbol` breaches the limit."""
        loss = self._name_pnl.get(symbol, 0.0)
        if loss <= -self._config.max_single_name_loss:
            return (True, [f"single-name {symbol} loss {loss:.2%} <= -{self._config.max_single_name_loss:.0%}"])
        return (False, [])

    def set_mwcb(self, active: bool) -> None:
        """Market-wide circuit breaker event (US-3 index data sets this)."""
        self._mwcb = active

    def check(self) -> tuple[bool, list[str]]:
        reasons: list[str] = []
        if self._last_day_pnl <= -self._config.max_single_day_loss:
            reasons.append(f"single-day loss {self._last_day_pnl:.2%} <= -{self._config.max_single_day_loss:.0%}")
        if self._consecutive_losses >= self._config.max_consecutive_losses:
            reasons.append(f"{self._consecutive_losses} consecutive losing days")
        if self._mwcb:
            reasons.append("MWCB market-wide halt active")
        return (bool(reasons), reasons)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/guard/test_breaker.py -q`
Expected: PASS (5 passed)

- [ ] **Step 5: Commit**

```bash
git add alpha/guard/breaker.py tests/guard/test_breaker.py
git commit -m "US-1f Task 6: circuit breaker (single-day / consecutive-loss / MWCB)"
```

---

### Task 7: US-1f acceptance gate + docs update

**Files:**
- Create: `tests/guard/test_us1f_acceptance.py`
- Modify: `docs/PROJECT_STATE.md` (mark US-1f done)

- [ ] **Step 1: Write the acceptance test**

```python
# tests/guard/test_us1f_acceptance.py
"""US-1f acceptance: sizing nets same-narrative picks to one risk-gated bet, and the guard layer
vetoes / stops / breaks as the immutable-core rules require — over a small end-to-end scenario."""
from alpha.regime.classifier import RegimeRead
from alpha.sizing.correlation import Pick
from alpha.sizing.portfolio import plan_portfolio
from alpha.sizing.position import SizingConfig
from alpha.guard.veto import CandidateContext, veto
from alpha.guard.stops import Position, stop_signals
from alpha.guard.breaker import Breaker, BreakerConfig


def test_sizing_and_guard_end_to_end():
    regime = RegimeRead(phase="trend", confidence=0.7, frontside=True, risk_gate=0.6)
    picks = [Pick("AI1", "ai", 0.9), Pick("AI2", "ai", 0.8), Pick("NUKE", "nuclear", 0.7)]
    plan = plan_portfolio(picks, risk_gate=regime.risk_gate, config=SizingConfig())
    # two AI names net to one bet; nuclear is a second bet -> two correlated/independent bets
    assert plan.correlated_groups == [["AI1", "AI2"]]
    assert plan.total_exposure <= plan.total_exposure_budget

    # guard clears a clean name but vetoes one with a pending reverse split
    assert veto(CandidateContext("AI1", regime)).vetoed is False
    assert veto(CandidateContext("AI2", regime, reverse_split_pending=True)).vetoed is True

    # a position that lost its stop on a backside flip gets form + regime stops
    flush = RegimeRead(phase="flush", confidence=0.6, frontside=False, risk_gate=0.15)
    sigs = stop_signals(Position("AI1", 10.0, 8.0, 9.0, 2, "ai"), flush, max_hold_days=5)
    assert {s.kind for s in sigs} == {"form", "regime"}

    # consecutive losses trip the portfolio breaker; a single name's drawdown halts adds to it
    b = Breaker(BreakerConfig(max_consecutive_losses=2, max_single_name_loss=0.15))
    b.record_day_pnl(-0.01)
    b.record_day_pnl(-0.01)
    assert b.check()[0] is True
    b.record_name_pnl("AI2", -0.20)
    assert b.check_name("AI2")[0] is True
```

- [ ] **Step 2: Run the full suite**

Run: `python -m pytest -q`
Expected: PASS — all US-0 + US-1a..e + US-1f tests green.

- [ ] **Step 3: Update `docs/PROJECT_STATE.md`**

In the US-1 section, mark **US-1f (sizing L3 + guard L4) done** with the date and a one-line summary (sizing: confidence×risk_gate size tiers + same-narrative netting + risk-gate exposure cap; guard: form/regime/time stops + hard veto (regime no-chase, reverse-split, data-flag dilution/halt/regulatory) + single-day/consecutive-loss/MWCB circuit breaker; the immutable-core rules made executable). Update the "Next" pointer to **US-1g (seeds v1 + DecisionPackage schema)** — the final US-1 sub-plan.

- [ ] **Step 4: Commit**

```bash
git add tests/guard/test_us1f_acceptance.py docs/PROJECT_STATE.md
git commit -m "US-1f Task 7: acceptance gate (sizing + guard end-to-end) + PROJECT_STATE"
```

---

## Self-Review (run after writing, fix inline)

**Spec coverage (US-1 "sizing L3 + guard L4"; §4/§6):** size tiers confidence×risk_gate (Task 1) ✓ · same-narrative = one bet (Tasks 2-3) ✓ · total exposure capped by regime risk-gate (Task 3) ✓ · stop discipline form/regime/time (Task 4) ✓ · hard veto regime-no-chase + **backside** + reverse-split + data-flags incl. SSR (Task 5) ✓ · circuit breakers single-name/single-day/consecutive/MWCB (Task 6) ✓ · immutable-core rules made executable (all) ✓. **Deferred & documented:** DecisionPackage wiring → US-1g; inner-loop wiring → US-2; data-flag sources (dilution/SSR/halt/MWCB) → US-3; narrative tagging supplied upstream (agent US-2 / theme data US-3).

**Type consistency:** `Pick(symbol, narrative, confidence)` used identically in correlation + portfolio. `SizeTier`/`SIZE_TIER_WEIGHT`/`SizingConfig`/`size_tier` consistent across position + portfolio. `RegimeRead` (from alpha/regime/classifier) consumed by stops + veto with its real fields (phase/confidence/frontside/risk_gate). `Position`/`StopSignal`, `CandidateContext`/`VetoVerdict`, `Breaker`/`BreakerConfig` self-consistent and used in the acceptance test.

**Placeholder scan:** no TBD/TODO; every code step shows full code; deferrals are explicit scope notes.

**Scope:** sizing + guard computation only; no LLM, no DecisionPackage, no loop wiring. Produces independently-testable L3/L4 components that US-1g/US-2 compose.
