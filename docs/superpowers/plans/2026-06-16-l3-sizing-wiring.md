# L3 Sizing → live DecisionPackage Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Wire the already-built L3 sizing layer (`alpha/sizing/`) into the live decision path so every agent-produced `DecisionPackage` carries a per-candidate `size_tier` (confidence × regime `risk_gate`) and a top-level `portfolio` (exposure budget + correlated groups) — completing the §4.1 human-confirmation surface — via a composable `SizingPolicy` decorator mirroring the existing `GuardedPolicy`.

**Architecture:** `alpha/sizing/{position,correlation,portfolio}.py` are fully implemented + tested (US-1f) but have **zero call sites** on the live path: `alpha/agent/parse.py` emits candidates with `size_tier=None` and `portfolio=None`. This plan adds a stateless `SizingPolicy(inner)` decorator (new `alpha/sizing/policy.py`) that runs the inner policy then calls `size_decision(decision, *, state)` — assigning each candidate a `size_tier` and attaching the `Portfolio` plan via `model_copy` on the frozen models, exactly as `GuardedPolicy`/`screen_decision` (L4) does. It composes **outside** `GuardedPolicy` (`SizingPolicy(GuardedPolicy(base))`) so it sizes the **post-veto survivors** and the portfolio reflects only kept names. A new `LoopConfig.size` flag (default ON) drives composition in `InnerLoop._rebind` and symmetrically across all `compare_harnesses` arms.

**Honest scope (verified by the understanding pass).** **Wiring L3 is verdict-NEUTRAL.** The entire scoring/eval/verdict path (`ReturnScorer`, `advantage`, `EvalReport`, the breaker, `apply_credit`, `stats.verdict`, `contribution_split`) is **equal-weighted per candidate and never reads `size_tier`/`portfolio`** — so this slice changes the decision *surface* (and the DAgger record) but does NOT move the HCH-vs-Hexpert numbers. Therefore existing apparatus tests' numeric assertions stay green; only tests that explicitly assert `size_tier is None` / `portfolio is None` on a live decision change. **Deferred (honest):** `fill_feasibility` (no `alpha/eval/fill.py` exists — needs the intraday inference path) and per-candidate `taboo_check` (the L4 guard *drops* vetoed candidates rather than annotating kept ones). Real correlation **netting** is dormant until narrative/theme tagging lands (the deferred per-narrative-line piece): the narrative key is `candidate.family`, which the agent does not set today (`''`), so each name is its own bet and `correlated_groups` is empty — the mechanism is wired and auto-activates when family/narrative is populated (the US-3f `depends_on` pattern).

**Tech Stack:** Python ≥ 3.11, pydantic v2 (frozen models → `model_copy`), pytest. Deterministic, offline (`FakeSource`/`MockLLMClient`); firewall-clean (sizing reads only the in-hand `decision` + `state`; no source fetch).

---

## Context: the exact pieces (from the read-only understanding pass)

- `alpha/sizing/position.py`: `size_tier(confidence: float, risk_gate: float) -> SizeTier` — `score = max(0,confidence) * max(0,risk_gate)`; `flat (<0.15) / probe (<0.35) / core (<0.6) / heavy (>=0.6)`. `SizeTier = Literal["flat","probe","core","heavy"]`. `SizingConfig(max_name_weight=1.0, max_total_exposure=4.0)` (frozen).
- `alpha/sizing/correlation.py`: `Pick(symbol, narrative, confidence)` (frozen). Grouping keys on `narrative` (falls back to `symbol` when `narrative == ""`).
- `alpha/sizing/portfolio.py`: `plan_portfolio(picks: list[Pick], risk_gate: float, config: SizingConfig) -> PortfolioPlan`; `PortfolioPlan(sized, correlated_groups, total_exposure, total_exposure_budget, capped)`; `total_exposure_budget = max(0,risk_gate) * config.max_total_exposure`; same-narrative netted to one bet at the max member weight; total capped at budget.
- `alpha/eval/decision.py`: `Candidate` (frozen) has `size_tier: SizeTier | None = None`, `family: str = ""`, `confidence: float = 0.5`. `DecisionPackage` (frozen) has `portfolio: Portfolio | None = None`, `regime: RegimeRead | None = None`. `Portfolio(total_exposure_budget: float = 0.0, correlated_groups: list[list[str]] = [])`.
- `alpha/guard/screen.py`: the **pattern to mirror** — `GuardedPolicy.__init__(inner, source)`; `decide` = `screen_decision(self._inner.decide(state, universe), source=…, state=state)`; `screen_decision` rebuilds the frozen package via `decision.model_copy(update=…)` and sets `decision.regime = GCycle().read(state)`.
- `alpha/loop/inner_loop.py::_rebind`: `self._agent = GuardedPolicy(base, self._source) if self._cfg.screen else base`. `LoopConfig.screen: bool = True`.
- `alpha/loop/compare.py`: the `_guard(policy)` helper wraps all four non-HCH arms when `cfg.screen` (two Hexpert `wf.walk`, two Hmin `wf.run`).
- **Verdict-neutrality (verified):** `alpha/eval/scorer.py`, `metrics.py`, `stats.py`, `contribution.py`, and the `InnerLoop` breaker read only `symbol`/`pattern`/`advantage` — never `size_tier`/`portfolio`.

---

## File Structure

| File | Change | Responsibility |
|---|---|---|
| `alpha/sizing/policy.py` | Create | `size_decision(decision, *, state, config=SizingConfig())` + the `SizingPolicy(inner)` decorator. The L3 analog of `guard/screen.py`. |
| `alpha/loop/inner_loop.py` | Modify | `LoopConfig.size: bool = True`; `_rebind` composes `SizingPolicy(GuardedPolicy(base))`. |
| `alpha/loop/compare.py` | Modify | Rename `_guard` → `_wrap`; it now applies `GuardedPolicy` (when `screen`) then `SizingPolicy` (when `size`), symmetrically across all four arms. |
| `tests/sizing/test_policy.py` | Create | Unit: `size_decision` assigns tiers from confidence×risk_gate + attaches the portfolio; `SizingPolicy` decorator; reads `decision.regime` when present, else computes it; sizes the post-guard survivors. |
| `tests/loop/test_sizing_wiring.py` | Create | Wiring: a live `InnerLoop` with default config emits decisions carrying `size_tier` + `portfolio`; `size=False` emits unsized decisions. |
| `tests/eval/test_l3_sizing_acceptance.py` | Create | Acceptance: size-on decisions carry tier+portfolio, size-off do not, AND the per-step advantages are **identical** between the two runs (verdict-neutral). |
| `docs/PROJECT_STATE.md`, `docs/blueprint.md` | Modify | Record L3 wired into the live DecisionPackage (size_tier + portfolio); note verdict-neutrality + the family/narrative + fill/taboo deferrals. |

**No change to `alpha/sizing/{position,correlation,portfolio}.py`** (the layer is done) and **no change to any scorer/eval/stats** (verdict-neutral by design). No `alpha/agent/parse.py` change (narrative stays `candidate.family`, currently `""`).

---

## Task 1: `SizingPolicy` + `size_decision` (the L3 unit)

**Files:** Create `alpha/sizing/policy.py`, `tests/sizing/test_policy.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/sizing/test_policy.py`:

```python
"""L3 sizing decorator: size_decision assigns a per-candidate size_tier (confidence x regime risk_gate)
and attaches the Portfolio plan; SizingPolicy wraps any policy. Verdict-neutral — sizing never touches
scoring (proven in tests/eval/test_l3_sizing_acceptance.py)."""
from datetime import date, datetime
from alpha.eval.decision import Candidate, DecisionPackage
from alpha.regime.classifier import RegimeRead
from alpha.sizing.policy import SizingPolicy, size_decision
from alpha.state.market import MarketState
from alpha.universe.universe import CandidateUniverse

CUR = date(2026, 6, 12)


def _state(**kw):
    return MarketState(date=CUR, gainer_count=1, gap_up_count=0, loser_count=0, failed_breakout_count=0,
                       max_runner_tier=0, echelon=[], breadth_raw=1.0, sentiment_norm=None,
                       as_of=datetime(2026, 6, 12, 16, 0), **kw)


def _pkg(*cands, regime=None):
    return DecisionPackage(date=CUR, candidates=list(cands), regime=regime)


def test_size_decision_assigns_tier_from_confidence_and_risk_gate():
    # risk_gate=0.8, confidence=0.9 -> score 0.72 -> 'heavy'; confidence=0.4 -> 0.32 -> 'probe'
    regime = RegimeRead(phase="trend", confidence=0.7, frontside=True, risk_gate=0.8)
    out = size_decision(_pkg(Candidate(symbol="RUN", confidence=0.9),
                             Candidate(symbol="LAG", confidence=0.4), regime=regime), state=_state())
    tiers = {c.symbol: c.size_tier for c in out.candidates}
    assert tiers == {"RUN": "heavy", "LAG": "probe"}
    assert out.portfolio is not None
    assert out.portfolio.total_exposure_budget == 0.8 * 4.0          # risk_gate x max_total_exposure


def test_size_decision_falls_back_to_gcycle_when_regime_absent():
    # no regime on the package (screen off) -> size_decision computes GCycle().read(state) itself
    out = size_decision(_pkg(Candidate(symbol="RUN", confidence=0.9)), state=_state())
    assert out.candidates[0].size_tier in {"flat", "probe", "core", "heavy"}
    assert out.portfolio is not None


def test_sizing_policy_sizes_inner_decision():
    class _Stub:
        def decide(self, state, universe):
            return _pkg(Candidate(symbol="RUN", confidence=0.9),
                        regime=RegimeRead(phase="trend", confidence=0.7, frontside=True, risk_gate=0.9))
    out = SizingPolicy(_Stub()).decide(_state(), CandidateUniverse.from_stocks([]))
    assert out.candidates[0].size_tier == "heavy"                    # 0.9 x 0.9 = 0.81 -> heavy
```

- [ ] **Step 2: Run to verify failure**

Run: `python -m pytest tests/sizing/test_policy.py -q`
Expected: FAIL — `No module named 'alpha.sizing.policy'`.

- [ ] **Step 3: Implement `alpha/sizing/policy.py`**

```python
from __future__ import annotations

from alpha.eval.decision import DecisionPackage, Portfolio
from alpha.regime.classifier import GCycle
from alpha.sizing.correlation import Pick
from alpha.sizing.portfolio import plan_portfolio
from alpha.sizing.position import SizingConfig, size_tier
from alpha.state.market import MarketState

_DEFAULT_CONFIG = SizingConfig()


def size_decision(decision: DecisionPackage, *, state: MarketState,
                  config: SizingConfig = _DEFAULT_CONFIG) -> DecisionPackage:
    """Apply L3 sizing to a (already L4-guarded) DecisionPackage: assign each KEPT candidate a size_tier
    from confidence x regime risk_gate, and attach the portfolio plan (exposure budget + correlated
    groups). VERDICT-NEUTRAL: scoring is equal-weighted and never reads size_tier/portfolio, so this only
    enriches the human-confirmation surface (+ the DAgger record). FIREWALL-CLEAN: reads only the decision
    + state (no source fetch). Frozen models -> rebuilt via model_copy.

    Narrative key for correlation is candidate.family (the agent does not set it yet -> "" -> each name is
    its own bet, correlated_groups empty); netting auto-activates when family/narrative tagging lands.
    DEFERRED (not this slice): fill_feasibility (needs the intraday inference path — no eval/fill module)
    and per-candidate taboo_check (the L4 guard drops vetoed candidates rather than soft-annotating kept ones).
    """
    regime = decision.regime or GCycle().read(state)
    rg = regime.risk_gate
    sized = [c.model_copy(update={"size_tier": size_tier(c.confidence, rg)}) for c in decision.candidates]
    plan = plan_portfolio([Pick(symbol=c.symbol, narrative=c.family, confidence=c.confidence)
                           for c in sized], rg, config)
    portfolio = Portfolio(total_exposure_budget=plan.total_exposure_budget,
                          correlated_groups=plan.correlated_groups)
    return decision.model_copy(update={"candidates": sized, "portfolio": portfolio})


class SizingPolicy:
    """Composable L3 sizing decorator: wraps any DecisionPolicy, runs it, then sizes the result. Compose
    OUTSIDE GuardedPolicy so it sizes the post-veto survivors: SizingPolicy(GuardedPolicy(agent, source))."""

    def __init__(self, inner) -> None:
        self._inner = inner

    def decide(self, state: MarketState, universe) -> DecisionPackage:
        return size_decision(self._inner.decide(state, universe), state=state)
```

- [ ] **Step 4: Run to verify pass**

Run: `python -m pytest tests/sizing/test_policy.py -q`
Expected: PASS (3 tests).

- [ ] **Step 5: Commit**

```bash
git add alpha/sizing/policy.py tests/sizing/test_policy.py
git commit -m "L3 sizing Task 1: SizingPolicy decorator + size_decision (size_tier + portfolio on the DecisionPackage)"
```

---

## Task 2: Wire into `LoopConfig` + `InnerLoop._rebind` + symmetric `compare_harnesses`

**Files:** Modify `alpha/loop/inner_loop.py`, `alpha/loop/compare.py`; Create `tests/loop/test_sizing_wiring.py`

- [ ] **Step 1: Write the failing wiring test**

Create `tests/loop/test_sizing_wiring.py`:

```python
"""L3 sizing is wired into the live loop and ON by default: a frontside runner's pick carries a size_tier
and the decision carries a portfolio (exposure budget). size=False emits unsized decisions."""
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
    snaps, px, closes = {}, 10.0, []
    for d in cal:
        prev = px; px = px * 1.15; closes.append(px)
        snaps[d] = pd.DataFrame({"symbol": ["RUN"], "name": ["RUN"], "open": [prev], "high": [px],
                                 "low": [prev], "close": [px], "volume": [1], "prev_close": [prev]})
    bars = {"RUN": pd.DataFrame({"date": cal, "open": [10.0] + closes[:-1], "high": closes,
                                 "low": [10.0] + closes[:-1], "close": closes, "volume": [1] * n})}
    return FakeSource(calendar=cal, bars=bars, snapshots=snaps)


def _loop(*, size):
    src = _runner_source(6)
    mgr = HarnessManager(load_seeds(SEEDS), SnapshotStore(tempfile.mkdtemp()))
    cfg = LoopConfig(horizon=2, evidence_min=2, refine_every=1, size=size)
    return InnerLoop(mgr, src, src.trading_calendar()[0], src.trading_calendar()[-1],
                     MockLLMClient('{"candidates": [{"symbol": "RUN", "pattern": "gap_and_go"}]}'),
                     MockLLMClient('{"ops": []}'), config=cfg).run()


def test_size_defaults_on():
    assert LoopConfig().size is True


def test_live_decisions_carry_size_tier_and_portfolio():
    lr = _loop(size=True)
    sized = [c for s in lr.trajectory.steps for c in s.decision.candidates if c.size_tier is not None]
    assert sized                                                    # at least one kept pick is sized
    assert all(c.size_tier in {"flat", "probe", "core", "heavy"} for c in sized)
    assert any(s.decision.portfolio is not None for s in lr.trajectory.steps)


def test_size_off_emits_unsized_decisions():
    lr = _loop(size=False)
    assert all(c.size_tier is None for s in lr.trajectory.steps for c in s.decision.candidates)
    assert all(s.decision.portfolio is None for s in lr.trajectory.steps)
```

- [ ] **Step 2: Run to verify failure**

Run: `python -m pytest tests/loop/test_sizing_wiring.py -q`
Expected: `test_size_defaults_on` FAILS (`LoopConfig` has no `size` field → AttributeError / the assertion fails).

- [ ] **Step 3: Add `LoopConfig.size` + compose in `_rebind`**

In `alpha/loop/inner_loop.py`, add the field to `LoopConfig` (right after the `screen` block):

```python
    size: bool = True           # L3 sizing ON by default — assign size_tier (confidence x risk_gate) +
    #   attach the portfolio plan (exposure budget + correlated groups). VERDICT-NEUTRAL: scoring is
    #   equal-weighted and never reads size, so this enriches the decision surface without changing the
    #   HCH-vs-Hexpert numbers. Set size=False to emit unsized decisions.
```

Add the import (with the other policy imports near `from alpha.guard.screen import GuardedPolicy`):

```python
from alpha.sizing.policy import SizingPolicy
```

In `_rebind`, replace the single `self._agent = …` line with the layered composition (size OUTSIDE guard):

```python
        policy = GuardedPolicy(base, self._source) if self._cfg.screen else base
        self._agent = SizingPolicy(policy) if self._cfg.size else policy
```

- [ ] **Step 4: Symmetrize `compare_harnesses` (rename `_guard` → `_wrap`, add sizing)**

In `alpha/loop/compare.py`, add the import (next to `from alpha.guard.screen import GuardedPolicy`):

```python
from alpha.sizing.policy import SizingPolicy
```

Replace the `_guard` helper with `_wrap` (guard inner, size outer — same order as `_rebind`):

```python
    def _wrap(policy):                        # L4 guard (when screen) then L3 sizing (when size) — match HCH
        p = GuardedPolicy(policy, source) if cfg.screen else policy
        return SizingPolicy(p) if cfg.size else p
```

Replace all four `_guard(...)` call sites with `_wrap(...)` (the two Hexpert `wf.walk` sites and the two Hmin `wf.run` sites). Grep `_guard(` inside the function to confirm none remain.

- [ ] **Step 5: Run the wiring tests**

Run: `python -m pytest tests/loop/test_sizing_wiring.py -q`
Expected: PASS (3 tests).

- [ ] **Step 6: Full suite + blast-radius triage**

Run: `python -m pytest -q`
Expected: green, with **no existing test changes needed** (the adversarial review confirmed this independently: the backward-compat tests in `tests/eval/test_decision_full.py` / `test_us1g_acceptance.py` construct packages **directly** — no `SizingPolicy` — so their `size_tier is None` / `portfolio is None` assertions still hold; round-trip tests use explicit values and pydantic handles the optional fields; and no `tests/loop/` test inspects `size_tier`/`portfolio`). `size` defaults ON, so live `InnerLoop` / `compare_harnesses` decisions now carry `size_tier` + `portfolio`, but sizing is **verdict-neutral** (no scorer/breaker/stats/contribution reads it) so numeric assertions stay green. Triage guard (expected to surface nothing on live decisions): `grep -rn "size_tier is None\|portfolio is None" tests/ | grep -vE "test_sizing|test_l3|test_decision_full|test_us1g"` — if anything DOES turn up on a loop/compare-produced decision, either update it to the now-populated value or pin that test to `size=False` if it is specifically an unsized baseline (document each). Pure-`screen` tests (`test_screen_*`) are unaffected (sizing doesn't change `entries`/`regime`/scores).

- [ ] **Step 7: Commit**

```bash
git add alpha/loop/inner_loop.py alpha/loop/compare.py tests/loop/test_sizing_wiring.py
git commit -m "L3 sizing Task 2: LoopConfig.size default-on + SizingPolicy in _rebind + symmetric compare_harnesses (_wrap)"
```

---

## Task 3: Acceptance (verdict-neutral) + docs

**Files:** Create `tests/eval/test_l3_sizing_acceptance.py`; Modify `docs/PROJECT_STATE.md`, `docs/blueprint.md`

- [ ] **Step 1: Write the acceptance test**

Create `tests/eval/test_l3_sizing_acceptance.py`:

```python
"""Acceptance: wiring L3 sizing into the live loop enriches the DecisionPackage (size_tier + portfolio)
but is VERDICT-NEUTRAL — the per-step advantages are identical with sizing on vs off (scoring is
equal-weighted and never reads size). This is the production posture: a complete decision surface that
does not bias the HCH-vs-Hexpert comparison."""
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


def _src(n=6):
    cal = [date(2026, 6, d) for d in range(1, 1 + n)]
    snaps, px, closes = {}, 10.0, []
    for d in cal:
        prev = px; px = px * 1.15; closes.append(px)
        snaps[d] = pd.DataFrame({"symbol": ["RUN"], "name": ["RUN"], "open": [prev], "high": [px],
                                 "low": [prev], "close": [px], "volume": [1], "prev_close": [prev]})
    bars = {"RUN": pd.DataFrame({"date": cal, "open": [10.0] + closes[:-1], "high": closes,
                                 "low": [10.0] + closes[:-1], "close": closes, "volume": [1] * n})}
    return FakeSource(calendar=cal, bars=bars, snapshots=snaps)


def _run(size):
    # fresh src + mgr + MockLLMClients per call (MockLLMClient is stateful — its response cursor must not
    # carry across the two runs); the ONLY difference between the two runs is the size flag.
    src = _src()
    mgr = HarnessManager(load_seeds(SEEDS), SnapshotStore(tempfile.mkdtemp()))
    cfg = LoopConfig(horizon=2, evidence_min=2, refine_every=1, size=size)
    return InnerLoop(mgr, src, src.trading_calendar()[0], src.trading_calendar()[-1],
                     MockLLMClient('{"candidates": [{"symbol": "RUN", "pattern": "gap_and_go"}]}'),
                     MockLLMClient('{"ops": []}'), config=cfg).run()


def _advantages(lr):
    return [round(c.advantage, 8) for s in lr.trajectory.scored_steps()
            for c in sorted(s.outcomes.values(), key=lambda x: x.symbol)]


def test_l3_sizing_is_verdict_neutral_but_enriches_surface():
    on, off = _run(True), _run(False)
    # surface enriched with sizing on, absent with sizing off
    assert any(c.size_tier is not None for s in on.trajectory.steps for c in s.decision.candidates)
    assert all(c.size_tier is None for s in off.trajectory.steps for c in s.decision.candidates)
    # verdict-neutral: the scored advantages are identical on vs off
    assert _advantages(on) == _advantages(off) and _advantages(on)   # non-empty + equal
```

- [ ] **Step 2: Run the acceptance test + full suite**

Run: `python -m pytest tests/eval/test_l3_sizing_acceptance.py -q && python -m pytest -q`
Expected: acceptance PASS; full suite green; record the exact count for PROJECT_STATE.

- [ ] **Step 3: Update `docs/PROJECT_STATE.md`**

Read the header `Last updated` line first; update it to note L3 sizing wired into the live DecisionPackage. Add an "L3 sizing → live DecisionPackage" entry after the verdict-runner paragraph: the `SizingPolicy` decorator (mirrors `GuardedPolicy`), composed `SizingPolicy(GuardedPolicy(base))` to size post-veto survivors; `LoopConfig.size` default ON + symmetric `compare_harnesses`; **verdict-neutral** (scoring is equal-weighted, never reads size — the decision surface is now §4.1-complete without biasing the verdict); honest deferrals (`fill_feasibility` needs the intraday inference path; per-candidate `taboo_check` needs a soft-annotate guard mode; correlation **netting** is dormant until narrative/family tagging supplies the key — the mechanism is wired). Move "wire L3 sizing / L4 guard into the agent's DecisionPackage" out of the "Other deferred" list (L4 was done in US-3b; L3 is now done).

- [ ] **Step 4: Reconcile `docs/blueprint.md`**

Grep `size_tier` / `L3` / `sizing` / `DecisionPackage` / `portfolio` and update any line that frames L3 sizing as built-but-unwired to reflect it is now on the live path (size_tier + portfolio populated; verdict-neutral). Keep edits to the relevant lines.

- [ ] **Step 5: Commit**

```bash
git add tests/eval/test_l3_sizing_acceptance.py docs/PROJECT_STATE.md docs/blueprint.md
git commit -m "L3 sizing Task 3: acceptance (verdict-neutral surface enrichment) + PROJECT_STATE/blueprint"
```

---

## Self-Review

**1. Spec coverage.** The built-but-unwired L3 layer is now on the live path: every agent decision carries `size_tier` per candidate (confidence × regime `risk_gate`) and a top-level `portfolio` (exposure budget + correlated groups), via a `SizingPolicy` decorator mirroring `GuardedPolicy` (Task 1), wired ON by default in `InnerLoop` + symmetric across `compare_harnesses` arms (Task 2), proven verdict-neutral (Task 3). The §4.1 human-confirmation surface is now complete for sizing.

**2. Placeholder scan.** Every code step has literal code + a runnable command + expected outcome. The acceptance `_run` helper carries an explicit note to write it cleanly (fresh per-run objects) rather than the illustrative inline form.

**3. Type/contract consistency.** `size_decision(decision, *, state, config=SizingConfig())` and `SizingPolicy(inner)` mirror `screen_decision`/`GuardedPolicy`. `size_tier(confidence, risk_gate)`, `plan_portfolio(picks, risk_gate, config)`, `Pick(symbol, narrative, confidence)`, `Portfolio(total_exposure_budget, correlated_groups)` all match the verified signatures. Composition order `SizingPolicy(GuardedPolicy(base))` is identical in `_rebind` and `_wrap`.

**4. Firewall.** `size_decision` reads only the in-hand `decision` + `state` (no source fetch); `state`/`universe` are already `AsOfGuard`-built by the drivers. No new firewall edge. `regime = decision.regime or GCycle().read(state)` is deterministic and as-of-clean.

**5. Blast radius / honesty.** Verdict-neutral by construction (verified: no scorer/breaker/stats/contribution reads size) — so apparatus tests' numeric assertions stay green; only `size_tier is None`/`portfolio is None` assertions on live decisions change, triaged in Task 2 Step 6. Honest deferrals stated: `fill_feasibility` (no `eval/fill` module), per-candidate `taboo_check` (guard drops, doesn't annotate), correlation netting (dormant until narrative/family tagging — `candidate.family` is `""` today, so each name is its own bet and `correlated_groups` is empty; the mechanism is wired and auto-activates).
