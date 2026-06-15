# US-3b SSR + Reverse-Split + Guard-Veto Wiring Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Give the dormant L4 guard `veto()` (zero production call sites) two computable data flags — **SSR** (Reg SHO Rule 201: a ≥10% prior-day decline restricts the next session) and **reverse_split_pending** (US-0 corp-actions) — and wire it into the live decision path as a **composable, opt-in** guard layer (`GuardedPolicy` + `InnerLoop` `screen` flag), activating the immutable `dont_fight_ssr` doctrine without disturbing the existing eval apparatus.

**Architecture:** `veto(ctx)` stays pure and unchanged (six tests pin its contract). US-3b computes the flags at a new seam and passes them in via `CandidateContext`. Two real obstacles drive the design: (1) `source.corporate_actions(start, end)` filters by **ex_date**, but a *pending* reverse split has a future `ex_date` and `GuardedSource` blocks `end > as_of` — so a new **PIT-by-announce** primitive `corporate_actions_known(as_of)` is added to the source layer; (2) `veto()` requires a structured `RegimeRead` and reads it via `GCycle().read(state)`, whose risk-off/backside arms would over-fire on the **minimal** live `state/builder` (it feeds `GCycle` `sentiment_norm=None`/`follow_through=None` → every day reads backside). Therefore the guard is wired **opt-in, default OFF**: the mechanism + data flags ship and are fully tested, ready to flip on once a later US-3 slice wires the richer `features/builder` so `GCycle` reads frontside correctly. Vetoed candidates are **dropped** (hard override → never entered/scored) with reasons surfaced in `DecisionPackage.key_risks`; the structured `regime` (always `None` on the live path today) is populated as a side win.

**Tech Stack:** Python ≥ 3.11, pydantic v2 (frozen `DecisionPackage`/`Candidate`; `model_copy` to rebuild), stdlib `@dataclass` (`CandidateContext`/`VetoVerdict`), pandas, pytest. Deterministic, offline (`FakeSource`); firewall-clean (`screen_decision` self-wraps in `GuardedSource(AsOfGuard(state.date))`; SSR reads only prior-day bars `end < as_of`; corp reads `announce_date <= as_of`).

---

## Context: the dormant guard and the two obstacles

`alpha/guard/veto.py` is complete and unit-tested but has **zero production call sites**. `veto(ctx: CandidateContext) -> VetoVerdict(vetoed, reasons)` accumulates reasons from: deep risk-off (`risk_gate < 0.2`), backside (`not frontside`), and six boolean flags (`reverse_split_pending`, `dilution`, `halt_then_dump`, `going_concern`, `regulatory`, `ssr`). US-3b makes the **two computable** flags real and calls `veto()` on the live path.

- **SSR** (Reg SHO Rule 201): a security that closes ≥10% below its prior close triggers a short-sale restriction for the rest of that day **and the next**. For a long-only momentum co-pilot the doctrine reading (`dont_fight_ssr`: "do not fight a one-sided tape") is: **don't chase a name today that cratered ≥10% yesterday.** So at decision day `t`, SSR is active for symbol X iff X's close-to-close move on `t-1` was ≤ −10%. This is the **prior** trading day's move — not today's snapshot (today's `pct_change` would decide SSR for *tomorrow*).
- **reverse_split_pending**: `alpha/data/corp_actions.py::has_reverse_split_pending(corp, symbol, as_of)` already exists and is PIT-correct (announced `<= as_of`, `ex_date > as_of`).

**Obstacle 1 — the corporate_actions firewall trap.** `FakeSource`/`SnapshotSource`/`GuardedSource.corporate_actions(start, end)` filter rows by `ex_date in [start, end]`, and `GuardedSource.corporate_actions(start, end)` calls `guard.check(end)`. A *pending* reverse split has `ex_date > as_of`, so any window with `end <= as_of` silently drops it, and `end > as_of` raises `LookaheadError`. There is **no** PIT-safe window through the ex_date-filtered method that returns pending splits. US-3b adds `corporate_actions_known(as_of)` — filter by `announce_date <= as_of` (the existing `known_corporate_actions(corp, as_of)` semantics), returning all such rows including future `ex_date`s.

**Obstacle 2 — the regime-veto blast radius.** `veto()` requires a non-optional `RegimeRead`; the live path never builds one (`GCycle` is test-only; `DecisionPackage.regime` is always `None` in prod). The seam must call `GCycle().read(state)`. But the live `alpha/state/builder.py::build_market_state` sets `sentiment_norm=None` and `follow_through_rate=None`, so for the synthetic single-gainer fixtures every existing walk/compare/stats/inner-loop test uses, `GCycle.read` computes `proxy≈1.0, ft=0.0 → phase="distribution", frontside=False`. Wiring the veto **on by default** would drop the picked symbol on *every* day and break essentially the whole suite — and would be *premature* (the regime arm can only read frontside once the richer `features/builder`, which computes `follow_through`/`sentiment`, is on the live path — a later US-3 slice). **Resolution: opt-in, default OFF.** The data-flag vetoes (SSR/reverse-split) are exact today; the regime arm rides along when `screen=True` and becomes meaningful when the richer builder lands.

## US-3 decomposition status

US-3a (runner-tier) DONE. **US-3b = THIS PLAN.** Deferred to later slices (flags whose data US-3b does not add, kept `False`): **3c** FINRA short-interest → `short_squeeze`; **3d** float / dilution / EDGAR → the `dilution` veto; **3e** intraday / halts / MWCB (`breaker.set_mwcb`, `halt_then_dump`); **3f** social / options / per-narrative + `going_concern`/`regulatory`. Also deferred: wiring the richer `features/builder` into the live loop (which is what lets `screen=True` become the default), and the live temp=0 LLM verdict run.

---

## File Structure

| File | Change | Responsibility |
|---|---|---|
| `alpha/data/source.py` | Modify | Add `corporate_actions_known(as_of)` to the `MarketDataSource` Protocol + `FakeSource` + `GuardedSource` (guarded). PIT-by-announce primitive. |
| `alpha/data/snapshot_source.py` | Modify | `corporate_actions_known(as_of)` on `SnapshotSource`. |
| `alpha/data/alpaca.py` | Modify | `corporate_actions_known(as_of)` on `AlpacaSource` (smoke-only, announce-filtered). |
| `alpha/guard/screen.py` | Create | `SSR_DROP_PCT`, `_prior_day_pct`, `ssr_active`, `screen_decision`, `GuardedPolicy`. The wiring layer. |
| `alpha/loop/inner_loop.py` | Modify | `LoopConfig.screen: bool = False`; `_rebind` wraps the agent in `GuardedPolicy(self._source)` when on. |
| `seeds/doctrine.json` | Modify | Drop the "(active once US-3 SSR data lands)" parenthetical from `dont_fight_ssr` — now active. |
| `tests/data/test_source.py` | Modify | `corporate_actions_known` tests (pending future-ex split visible; ex_date-filter contrast; guard-safe). |
| `tests/guard/test_screen.py` | Create | `ssr_active` + `screen_decision` + `GuardedPolicy` unit tests (all veto branches, drop+key_risks, regime populated, frozen-safe). |
| `tests/loop/test_screen_wiring.py` | Create | `InnerLoop` `screen` opt-in: on → veto fires (regime backside) → entries dropped; off → unchanged. |
| `tests/guard/test_us3b_acceptance.py` | Create | End-to-end: `GuardedPolicy` over a frontside state drops an SSR name + a reverse-split name, keeps the clean one, surfaces reasons, populates regime. |
| `docs/PROJECT_STATE.md` | Modify | US-3b DONE entry + refreshed roadmap. |

**TDD framing.** Tasks 1–3 are genuine red→green (new primitive + new module). Task 4 wires + activates (the `screen=True` test fails without the flag; `screen=False` is a regression lock). Task 5 is the acceptance gate + docs. The guard is **default-off**, so the existing 322-test suite stays green throughout — verified by a full-suite run after every task.

---

## Task 1: `corporate_actions_known(as_of)` PIT-by-announce primitive

**Files:**
- Modify: `alpha/data/source.py`, `alpha/data/snapshot_source.py`, `alpha/data/alpaca.py`
- Test: `tests/data/test_source.py`

- [ ] **Step 1: Write the failing tests**

Append to `tests/data/test_source.py`:

```python
def test_corporate_actions_known_sees_pending_future_ex_split(fake_source):
    # conftest fake_source: RUN reverse_split announced 6/9, ex 6/20 (pending as of 6/12).
    from datetime import date
    from alpha.data.corp_actions import has_reverse_split_pending
    known = fake_source.corporate_actions_known(date(2026, 6, 12))
    assert list(known["symbol"]) == ["RUN"]                       # announced <= 6/12, future ex kept
    # the ex_date-filtered accessor MISSES it (ex 6/20 not in [6/1, 6/12]) -> the trap this primitive fixes
    assert fake_source.corporate_actions(date(2026, 6, 1), date(2026, 6, 12)).empty
    assert has_reverse_split_pending(known, "RUN", date(2026, 6, 12)) is True


def test_corporate_actions_known_is_guard_safe(fake_source):
    from datetime import date
    from alpha.data.firewall import AsOfGuard, LookaheadError
    from alpha.data.source import GuardedSource
    import pytest
    gs = GuardedSource(fake_source, AsOfGuard(date(2026, 6, 12)))
    assert list(gs.corporate_actions_known(date(2026, 6, 12))["symbol"]) == ["RUN"]   # as_of == cursor ok
    with pytest.raises(LookaheadError):
        gs.corporate_actions_known(date(2026, 6, 13))                                 # future as_of blocked


def test_snapshot_source_corporate_actions_known(tmp_path):
    # SnapshotSource is the production OFFLINE source (PITStore-backed) — lock the new primitive there too.
    from datetime import date
    import pandas as pd
    from alpha.data.pit_store import PITStore
    from alpha.data.snapshot_source import SnapshotSource
    from alpha.data.corp_actions import has_reverse_split_pending
    store = PITStore(tmp_path)
    store.put_corp_actions(pd.DataFrame({"symbol": ["RS"], "announce_date": [date(2026, 6, 9)],
                                         "ex_date": [date(2026, 6, 20)], "kind": ["reverse_split"],
                                         "ratio": [0.1]}))
    known = SnapshotSource(store).corporate_actions_known(date(2026, 6, 12))
    assert has_reverse_split_pending(known, "RS", date(2026, 6, 12)) is True   # announced 6/9, ex 6/20 future
```

- [ ] **Step 2: Run to verify failure**

Run: `python -m pytest tests/data/test_source.py -k corporate_actions_known -v`
Expected: FAIL — `AttributeError: 'FakeSource' object has no attribute 'corporate_actions_known'`.

- [ ] **Step 3: Add to `alpha/data/source.py`**

Add the import near the top (after `from alpha.data.firewall import AsOfGuard`):

```python
from alpha.data.corp_actions import known_corporate_actions
```

(No cycle: `corp_actions` imports only pandas/datetime.)

Add to the `MarketDataSource` Protocol (after the `corporate_actions` line):

```python
    def corporate_actions_known(self, as_of: Date) -> pd.DataFrame: ...
```

Add to `FakeSource` (after its `corporate_actions` method):

```python
    def corporate_actions_known(self, as_of: Date) -> pd.DataFrame:
        """Corp actions ANNOUNCED by as_of (PIT-by-announcement), incl. future ex_dates (pending)."""
        return known_corporate_actions(self._corp, as_of)
```

Add to `GuardedSource` (after its `corporate_actions` method):

```python
    def corporate_actions_known(self, as_of: Date) -> pd.DataFrame:
        self._guard.check(as_of)
        return self._inner.corporate_actions_known(as_of)
```

- [ ] **Step 4: Add to `alpha/data/snapshot_source.py`**

Add the import (after `from alpha.data.pit_store import PITStore`):

```python
from alpha.data.corp_actions import known_corporate_actions
```

Add the method (after `corporate_actions`):

```python
    def corporate_actions_known(self, as_of: Date) -> pd.DataFrame:
        return known_corporate_actions(self._store.get_corp_actions(), as_of)
```

- [ ] **Step 5: Add to `alpha/data/alpaca.py`**

Add the method (after `corporate_actions`). It must NOT route through the ex_date-filtered `corporate_actions` — that would drop exactly the pending future-ex splits this primitive exists to surface (and the raw Alpaca `.df` isn't `announce_date`-normalized, so `known_corporate_actions` would `KeyError`). Mark it an explicit smoke-stub (mirrors the existing `daily_snapshot` `NotImplementedError`), so the contradiction can never masquerade as a working path:

```python
    def corporate_actions_known(self, as_of: Date) -> pd.DataFrame:
        # smoke-only: the announce-keyed query (NOT the ex_date-filtered corporate_actions, which drops
        # pending future-ex splits) is refined during smoke against real payloads. Never return a
        # silently pending-blind frame.
        raise NotImplementedError("AlpacaSource.corporate_actions_known: announce-window fetch refined during smoke")
```

(No new import needed in `alpaca.py`.)

- [ ] **Step 6: Run the tests to verify they pass**

Run: `python -m pytest tests/data/test_source.py -k corporate_actions_known -v`
Expected: all three PASS (FakeSource pending-split + guard-safe + SnapshotSource).

- [ ] **Step 7: Full suite**

Run: `python -m pytest -q`
Expected: 322 + 3 new = 325 green (additive method, no existing behavior changed).

- [ ] **Step 8: Commit**

```bash
git add alpha/data/source.py alpha/data/snapshot_source.py alpha/data/alpaca.py tests/data/test_source.py
git commit -m "US-3b Task 1: corporate_actions_known(as_of) PIT-by-announce primitive (fixes the pending-reverse-split firewall trap)"
```

---

## Task 2: `ssr_active` (Reg SHO Rule 201 prior-day computation)

**Files:**
- Create: `alpha/guard/screen.py`
- Test: `tests/guard/test_screen.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/guard/test_screen.py`:

```python
from datetime import date, datetime
import pandas as pd
import pytest
from alpha.data.source import FakeSource
from alpha.data.firewall import AsOfGuard
from alpha.data.source import GuardedSource
from alpha.guard.screen import ssr_active


def _src(sym_closes):
    """sym_closes: {symbol: [close_6/10, close_6/11, close_6/12]}."""
    cal = [date(2026, 6, 10), date(2026, 6, 11), date(2026, 6, 12)]
    bars = {s: pd.DataFrame({"date": cal, "open": c, "high": c, "low": c, "close": c,
                             "volume": [1, 1, 1]}) for s, c in sym_closes.items()}
    return FakeSource(calendar=cal, bars=bars, snapshots={})


def test_ssr_active_when_prior_day_dropped_10pct():
    src = _src({"KNIFE": [10.0, 8.8, 9.0]})            # 6/11 close 8.8 = -12% vs 6/10 -> SSR on 6/12
    assert ssr_active(src, "KNIFE", date(2026, 6, 12)) is True


def test_ssr_inactive_when_prior_day_drop_below_threshold():
    src = _src({"MILD": [10.0, 9.2, 9.5]})             # -8% prior day -> no SSR
    assert ssr_active(src, "MILD", date(2026, 6, 12)) is False


def test_ssr_inactive_when_bars_missing():
    src = _src({"OTHER": [10.0, 9.0, 8.0]})
    assert ssr_active(src, "ABSENT", date(2026, 6, 12)) is False    # no bars -> never fabricate


def test_ssr_inactive_on_first_day():
    src = _src({"KNIFE": [10.0, 8.8, 9.0]})
    assert ssr_active(src, "KNIFE", date(2026, 6, 10)) is False     # no prior trading day


def test_ssr_is_guard_safe():
    src = _src({"KNIFE": [10.0, 8.8, 9.0]})
    gs = GuardedSource(src, AsOfGuard(date(2026, 6, 12)))           # reads only prior-day bars (< as_of)
    assert ssr_active(gs, "KNIFE", date(2026, 6, 12)) is True
```

- [ ] **Step 2: Run to verify failure**

Run: `python -m pytest tests/guard/test_screen.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'alpha.guard.screen'`.

- [ ] **Step 3: Create `alpha/guard/screen.py` with the SSR computation**

```python
from __future__ import annotations

from datetime import date as Date

import pandas as pd

from alpha.data.calendar import prev_trading_day

SSR_DROP_PCT = -10.0   # Reg SHO Rule 201: a >=10% prior-day decline restricts short sales the next session


def _prior_day_pct(source, symbol: str, prev: Date) -> float | None:
    """Close-to-close % change for `symbol` ENDING at `prev` (the trading day before the decision day).
    Missing/short data -> None (never fabricate). Reads only bars dated <= prev (firewall-safe)."""
    cal = source.trading_calendar()
    le = [d for d in cal if d <= prev]
    if len(le) < 2:
        return None
    bars = source.daily_bars(symbol, le[-2], prev)
    if bars is None or bars.empty or "date" not in bars.columns:
        return None
    df = bars.copy()
    df["date"] = pd.to_datetime(df["date"]).dt.date
    closes = list(pd.to_numeric(df[df["date"] <= prev].sort_values("date")["close"], errors="coerce").dropna())
    if len(closes) < 2 or closes[-2] == 0:
        return None
    return (closes[-1] - closes[-2]) / closes[-2] * 100.0


def ssr_active(source, symbol: str, as_of: Date) -> bool:
    """Reg SHO Rule 201: True iff `symbol` fell >= 10% (close-to-close) on the PRIOR trading day, so a
    short-sale restriction is in effect on `as_of` (don't chase a one-sided tape). Missing data -> False."""
    prev = prev_trading_day(source.trading_calendar(), as_of)
    if prev is None:
        return False
    pct = _prior_day_pct(source, symbol, prev)
    return pct is not None and pct <= SSR_DROP_PCT
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `python -m pytest tests/guard/test_screen.py -v`
Expected: all five PASS.

- [ ] **Step 5: Commit**

```bash
git add alpha/guard/screen.py tests/guard/test_screen.py
git commit -m "US-3b Task 2: ssr_active (Reg SHO Rule 201 prior-day >=10% decline, firewall-safe)"
```

---

## Task 3: `screen_decision` + `GuardedPolicy` (the veto wiring layer)

**Files:**
- Modify: `alpha/guard/screen.py`
- Test: `tests/guard/test_screen.py`

- [ ] **Step 1: Write the failing tests**

Append to `tests/guard/test_screen.py`:

```python
from alpha.state.market import MarketState
from alpha.eval.decision import Candidate, DecisionPackage
from alpha.universe.universe import CandidateUniverse
from alpha.regime.classifier import RegimeRead
from alpha.guard.screen import screen_decision, GuardedPolicy


def _state(d=date(2026, 6, 12), *, sn=0.7, ft=0.5, gainers=2, losers=0, fb=0):
    return MarketState(date=d, gainer_count=gainers, gap_up_count=0, loser_count=losers,
                       failed_breakout_count=fb, max_runner_tier=1, echelon=[], breadth_raw=1.0,
                       sentiment_norm=sn, follow_through_rate=ft,
                       as_of=datetime(d.year, d.month, d.day, 16, 0))


def _pkg(*symbols):
    return DecisionPackage(date=date(2026, 6, 12),
                           candidates=[Candidate(symbol=s, pattern="gap_and_go") for s in symbols])


def test_screen_keeps_clean_candidate_and_populates_regime():
    src = _src({"CLEAN": [10.0, 11.0, 12.0]})                       # rising -> no SSR
    out = screen_decision(_pkg("CLEAN"), source=src, state=_state())   # sn=0.7, ft=0.5 -> trend/frontside
    assert [c.symbol for c in out.candidates] == ["CLEAN"]
    assert out.regime is not None and out.regime.frontside is True
    assert out.key_risks == []


def test_screen_drops_ssr_candidate_and_records_reason():
    src = _src({"KNIFE": [10.0, 8.8, 9.0]})                         # prior-day -12% -> SSR
    out = screen_decision(_pkg("KNIFE"), source=src, state=_state())
    assert out.candidates == []
    assert any("KNIFE" in r and "SSR" in r for r in out.key_risks)
    assert out.no_trade_reason                                       # all vetoed -> no-trade reason set


def test_screen_drops_reverse_split_candidate(fake_source):
    # conftest fake_source: RUN has a pending reverse split (announced 6/9, ex 6/20); RUN rising -> no SSR
    out = screen_decision(_pkg("RUN"), source=fake_source, state=_state())
    assert out.candidates == [] and any("reverse split" in r for r in out.key_risks)


def test_screen_drops_all_in_risk_off_regime():
    src = _src({"CLEAN": [10.0, 11.0, 12.0]})
    out = screen_decision(_pkg("CLEAN"), source=src, state=_state(sn=0.1))   # proxy 0.1 -> washout, risk_gate 0.1
    assert out.candidates == [] and any("risk-off" in r for r in out.key_risks)


def test_screen_is_frozen_safe():
    src = _src({"CLEAN": [10.0, 11.0, 12.0]})
    pkg = _pkg("CLEAN", "CLEAN2")
    out = screen_decision(pkg, source=src, state=_state())
    assert len(pkg.candidates) == 2                                 # original untouched (frozen rebuild)
    assert out is not pkg


def test_guarded_policy_screens_inner_decision():
    src = _src({"KNIFE": [10.0, 8.8, 9.0]})
    class _Stub:
        def decide(self, state, universe):
            return _pkg("KNIFE")
    gp = GuardedPolicy(_Stub(), src)
    out = gp.decide(_state(), CandidateUniverse.from_stocks([]))
    assert out.candidates == [] and any("SSR" in r for r in out.key_risks)
```

- [ ] **Step 2: Run to verify failure**

Run: `python -m pytest tests/guard/test_screen.py -k "screen or guarded" -v`
Expected: FAIL — `ImportError: cannot import name 'screen_decision'`.

- [ ] **Step 3: Add `screen_decision` + `GuardedPolicy` to `alpha/guard/screen.py`**

Add imports at the top of `alpha/guard/screen.py` (below the existing `prev_trading_day` import):

```python
from alpha.data.corp_actions import has_reverse_split_pending
from alpha.data.firewall import AsOfGuard
from alpha.data.source import GuardedSource
from alpha.eval.decision import DecisionPackage
from alpha.guard.veto import CandidateContext, veto
from alpha.regime.classifier import GCycle
from alpha.state.market import MarketState
```

Append:

```python
def screen_decision(decision: DecisionPackage, *, source, state: MarketState) -> DecisionPackage:
    """Apply the L4 hard veto to a freshly-produced DecisionPackage: DROP candidates the immutable-core
    guard blocks (SSR / reverse-split-pending / risk-off / backside regime), record dropped reasons in
    key_risks, and populate the structured regime. Frozen models -> rebuilt via model_copy.

    PIT-safe: all data reads go through a fresh GuardedSource(AsOfGuard(state.date)); SSR reads only
    prior-day bars (< as_of) and corp actions are announce-keyed (<= as_of). Vetoed candidates are
    dropped (never entered/scored) rather than annotated — a kept-but-failed candidate would still be
    scored as an entry by the drivers, defeating the hard veto."""
    as_of = state.date
    guarded = GuardedSource(source, AsOfGuard(as_of))
    regime = GCycle().read(state)
    corp = guarded.corporate_actions_known(as_of)
    kept, notes = [], []
    for c in decision.candidates:
        ctx = CandidateContext(symbol=c.symbol, regime=regime,
                               ssr=ssr_active(guarded, c.symbol, as_of),
                               reverse_split_pending=has_reverse_split_pending(corp, c.symbol, as_of))
        v = veto(ctx)
        if v.vetoed:
            notes.append(f"vetoed {c.symbol}: {'; '.join(v.reasons)}")
        else:
            kept.append(c)
    update = {"candidates": kept, "regime": regime, "key_risks": list(decision.key_risks) + notes}
    if not kept and decision.candidates:
        update["no_trade_reason"] = decision.no_trade_reason or "all candidates vetoed by L4 guard"
    return decision.model_copy(update=update)


class GuardedPolicy:
    """Composable L4 guard: wraps any DecisionPolicy; runs it, then applies screen_decision so the
    immutable-core hard veto overrides the agent. Works in any driver that calls policy.decide()."""

    def __init__(self, inner, source) -> None:
        self._inner = inner
        self._source = source

    def decide(self, state: MarketState, universe) -> DecisionPackage:
        decision = self._inner.decide(state, universe)
        return screen_decision(decision, source=self._source, state=state)
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `python -m pytest tests/guard/test_screen.py -v`
Expected: all PASS (Task 2 + Task 3 tests).

- [ ] **Step 5: Full suite**

Run: `python -m pytest -q`
Expected: green (new module, nothing else wired yet).

- [ ] **Step 6: Commit**

```bash
git add alpha/guard/screen.py tests/guard/test_screen.py
git commit -m "US-3b Task 3: screen_decision (drop vetoed + record key_risks + populate regime) + GuardedPolicy"
```

---

## Task 4: Wire `screen` into `InnerLoop` (opt-in) + activate the `dont_fight_ssr` doctrine

**Files:**
- Modify: `alpha/loop/inner_loop.py`
- Modify: `seeds/doctrine.json`
- Test: `tests/loop/test_screen_wiring.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/loop/test_screen_wiring.py`:

```python
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


def _source(n=6):
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


def _loop(src, *, screen):
    mgr = HarnessManager(load_seeds(SEEDS), SnapshotStore(tempfile.mkdtemp()))
    cfg = LoopConfig(horizon=2, evidence_min=2, refine_every=1, screen=screen)
    return InnerLoop(mgr, src, src.trading_calendar()[0], src.trading_calendar()[-1],
                     MockLLMClient('{"candidates": [{"symbol": "RUN", "pattern": "gap_and_go"}]}'),
                     MockLLMClient('{"ops": []}'), config=cfg)


def test_screen_off_by_default_keeps_entries():
    lr = _loop(_source(6), screen=False).run()
    assert any(s.entries for s in lr.trajectory.steps)             # RUN enters normally (apparatus unchanged)


def test_screen_on_vetoes_backside_entries():
    # the minimal state builder feeds GCycle sentiment_norm=None/ft=0 -> single-gainer reads backside,
    # so the wired veto drops every RUN pick (entries empty) and records reasons. This demonstrates the
    # opt-in wiring; the SSR/reverse-split discrimination is unit-tested in tests/guard/test_screen.py.
    lr = _loop(_source(6), screen=True).run()
    assert all(not s.entries for s in lr.trajectory.steps)         # all vetoed -> no entries
    assert any(s.decision.key_risks for s in lr.trajectory.steps)  # veto reasons surfaced
    assert any(s.decision.regime is not None for s in lr.trajectory.steps)  # structured regime populated
```

- [ ] **Step 2: Run to verify failure**

Run: `python -m pytest tests/loop/test_screen_wiring.py -v`
Expected: FAIL — `test_screen_on_vetoes_backside_entries` fails with an **AssertionError**, not a ValidationError: `LoopConfig` is a plain pydantic v2 model (no `extra="forbid"`), so `LoopConfig(..., screen=True)` **silently ignores** the unknown kwarg and `cfg.screen` is absent → the loop runs unscreened → RUN still enters → `all(not s.entries)` fails. `test_screen_off_by_default_keeps_entries` already passes.

- [ ] **Step 3: Add the `screen` flag to `LoopConfig` and wrap the agent in `_rebind`**

In `alpha/loop/inner_loop.py`, add to `LoopConfig` (after `enable_refine`):

```python
    screen: bool = False        # US-3b: when True, wrap the agent in GuardedPolicy (L4 hard veto). OFF by
    #   default — the regime arm over-fires on the minimal state builder until the richer features/builder
    #   (follow_through/sentiment) is on the live path (a later US-3 slice). SSR/reverse-split flags are exact.
```

Add the import (with the other `alpha.guard`-adjacent imports, e.g. after the `from alpha.loop.floor_breaker import ...` line):

```python
from alpha.guard.screen import GuardedPolicy
```

In `_rebind`, wrap the agent when `screen` is on. Change:

```python
        h = self._mgr.harness
        self._agent = self._agent_factory(h) if self._agent_factory is not None \
            else LLMAgentPolicy(h, self._agent_llm)
        self._refiner = Refiner(h, self._refiner_llm, self._mgr.tools, self._refiner_cfg)
```

to:

```python
        h = self._mgr.harness
        base = self._agent_factory(h) if self._agent_factory is not None \
            else LLMAgentPolicy(h, self._agent_llm)
        self._agent = GuardedPolicy(base, self._source) if self._cfg.screen else base
        self._refiner = Refiner(h, self._refiner_llm, self._mgr.tools, self._refiner_cfg)
```

(`GuardedPolicy` gets the raw `self._source`; `screen_decision` self-wraps in `GuardedSource(AsOfGuard(state.date))`, so PIT is enforced regardless.)

- [ ] **Step 4: Run the tests to verify they pass**

Run: `python -m pytest tests/loop/test_screen_wiring.py -v`
Expected: both PASS.

- [ ] **Step 5: Activate the `dont_fight_ssr` doctrine seed**

First confirm no test pins the old guidance text:

Run: `grep -rn "active once US-3" .`
Expected: only `seeds/doctrine.json` (and this plan / PROJECT_STATE prose). If a test asserts the old string, update it.

In `seeds/doctrine.json`, change the `dont_fight_ssr` entry guidance from:

```json
   "guidance": "Respect short-sale restriction and halts; do not fight a one-sided tape (active once US-3 SSR data lands)."}
```

to:

```json
   "guidance": "Respect short-sale restriction and halts; do not fight a one-sided tape."}
```

- [ ] **Step 6: Full suite**

Run: `python -m pytest -q`
Expected: green (screen defaults off everywhere; seed text change has no asserting test).

- [ ] **Step 7: Commit**

```bash
git add alpha/loop/inner_loop.py seeds/doctrine.json tests/loop/test_screen_wiring.py
git commit -m "US-3b Task 4: opt-in screen wiring in InnerLoop (GuardedPolicy) + activate dont_fight_ssr doctrine"
```

---

## Task 5: US-3b acceptance gate + PROJECT_STATE

**Files:**
- Create: `tests/guard/test_us3b_acceptance.py`
- Modify: `docs/PROJECT_STATE.md`

- [ ] **Step 1: Write the acceptance test**

Create `tests/guard/test_us3b_acceptance.py`:

```python
"""US-3b acceptance: the L4 hard veto, wired via GuardedPolicy, enforces the immutable dont_fight_ssr +
reverse-split doctrine on a FRONTSIDE regime — it drops an SSR name (prior-day -12%) and a reverse-split
name, keeps the clean runner, surfaces the reasons in key_risks, and populates the structured regime.
This is the headline US-3b guarantee: the dormant guard now fires on real, PIT-computed data flags."""
from datetime import date, datetime
import pandas as pd
from alpha.data.source import FakeSource
from alpha.state.market import MarketState
from alpha.eval.decision import Candidate, DecisionPackage
from alpha.universe.universe import CandidateUniverse
from alpha.guard.screen import GuardedPolicy

CUR = date(2026, 6, 12)


def _source():
    cal = [date(2026, 6, 10), date(2026, 6, 11), CUR]
    bars = {
        "CLEAN": pd.DataFrame({"date": cal, "open": [10, 11, 12.0], "high": [11, 12, 13],
                               "low": [10, 11, 12], "close": [10.0, 11.0, 12.0], "volume": [1, 1, 1]}),
        "KNIFE": pd.DataFrame({"date": cal, "open": [10, 8.8, 9.0], "high": [10, 9, 10],
                               "low": [8, 8, 8], "close": [10.0, 8.8, 9.0], "volume": [1, 1, 1]}),  # -12% on 6/11
        "RSPLIT": pd.DataFrame({"date": cal, "open": [10, 11, 12.0], "high": [11, 12, 13],
                                "low": [10, 11, 12], "close": [10.0, 11.0, 12.0], "volume": [1, 1, 1]}),
    }
    corp = pd.DataFrame({"symbol": ["RSPLIT"], "announce_date": [date(2026, 6, 9)],
                         "ex_date": [date(2026, 6, 20)], "kind": ["reverse_split"], "ratio": [0.1]})
    return FakeSource(calendar=cal, bars=bars, snapshots={}, corp_actions=corp)


def _frontside_state():
    # sentiment_norm=0.7 + follow_through=0.5 + fb_rate 0 -> GCycle reads trend/frontside, risk_gate 0.7
    return MarketState(date=CUR, gainer_count=3, gap_up_count=0, loser_count=0, failed_breakout_count=0,
                       max_runner_tier=1, echelon=[], breadth_raw=3.0, sentiment_norm=0.7,
                       follow_through_rate=0.5, as_of=datetime(2026, 6, 12, 16, 0))


class _StubPolicy:
    def decide(self, state, universe):
        return DecisionPackage(date=CUR, candidates=[Candidate(symbol=s, pattern="gap_and_go")
                                                     for s in ("CLEAN", "KNIFE", "RSPLIT")])


def test_guard_enforces_ssr_and_reverse_split_on_frontside():
    out = GuardedPolicy(_StubPolicy(), _source()).decide(_frontside_state(), CandidateUniverse.from_stocks([]))
    assert [c.symbol for c in out.candidates] == ["CLEAN"]              # only the clean runner survives
    assert out.regime is not None and out.regime.frontside is True      # structured regime populated
    assert any("KNIFE" in r and "SSR" in r for r in out.key_risks)      # SSR veto surfaced
    assert any("RSPLIT" in r and "reverse split" in r for r in out.key_risks)   # reverse-split veto surfaced
```

- [ ] **Step 2: Run the acceptance test**

Run: `python -m pytest tests/guard/test_us3b_acceptance.py -v`
Expected: PASS.

- [ ] **Step 3: Full suite**

Run: `python -m pytest -q`
Expected: all green; **339 total** (322 baseline + 17 new: Task1 +3, Task2 +5, Task3 +6, Task4 +2, Task5 +1). Record the exact count for the PROJECT_STATE edit (use whatever the run reports).

- [ ] **Step 4: Reconcile `docs/blueprint.md` (SSR semantic)**

`docs/blueprint.md` (the SSR row) frames Reg SHO Rule 201 as "affects short/squeeze logic only". For this long-only co-pilot US-3b reads SSR as a no-chase veto (`dont_fight_ssr`: don't chase a one-sided/exhaustion tape), using a daily proxy. Reconcile the doc so the set is self-consistent — change the SSR row's final cell from:

```
| SSR-flag (US-3); affects short/squeeze logic only |
```

to:

```
| SSR-flag = prior-day close-to-close ≤ −10% (daily proxy of the intraday Rule 201 trigger); for this long-only co-pilot, read as a no-chase veto on a one-sided/exhaustion tape (`dont_fight_ssr`), not short-side logic (wired US-3b) |
```

- [ ] **Step 5: Update `docs/PROJECT_STATE.md`**

Replace the header `Last updated` line (line 4). Old (verbatim):

```markdown
> Last updated: 2026-06-15 (US-0 + US-1 + US-2 complete; US-3a runner-tier enrichment live on the walk path; US-3b next).
```

New:

```markdown
> Last updated: 2026-06-15 (US-0 + US-1 + US-2 complete; US-3a runner-tier + US-3b SSR/reverse-split guard-veto (opt-in) shipped; US-3c next).
```

Then, immediately after the **US-3a** paragraph (the block ending "Full suite **322 tests green**.") and before the **"Next — US-3b → US-3f"** paragraph, insert:

```markdown
**US-3b SSR + reverse-split + guard-veto wiring — Complete (2026-06-15). The dormant L4 veto is live (opt-in).**
The guard `veto()` (zero production call sites until now) is wired via a composable `GuardedPolicy` decorator +
`alpha/guard/screen.py::screen_decision`, fed two PIT-computed flags: **SSR** (`ssr_active` — Reg SHO Rule 201:
a ≥10% prior-day close-to-close decline restricts chasing the name today) and **reverse_split_pending**
(`has_reverse_split_pending`). Resolved the corporate-actions firewall trap with a new PIT-by-announce source
primitive `corporate_actions_known(as_of)` (the ex_date-filtered accessor silently dropped pending future-ex
splits). `screen_decision` drops vetoed candidates (hard override → never entered/scored), surfaces reasons in
`DecisionPackage.key_risks`, and finally populates the structured `regime` (previously always `None` on the live
path). The immutable `dont_fight_ssr` doctrine is activated (seed parenthetical dropped). **Wired OPT-IN, default
OFF** (`LoopConfig.screen`): the regime risk-off/backside arm over-fires on the *minimal* `state/builder` (it
feeds `GCycle` `sentiment_norm=None`/`follow_through=None` → every synthetic day reads backside), so global
default-on enforcement waits on wiring the richer `features/builder` into the live loop (a later US-3 slice). The
SSR/reverse-split data-flag vetoes are exact today and unit-tested; the full opt-in path is acceptance-tested
end-to-end on a frontside regime. The other four veto flags (`dilution`/`halt_then_dump`/`going_concern`/
`regulatory`) stay wired in `veto()` and default `False` via `CandidateContext` — US-3b adds no data for them
(3d/3e/3f do). Known limitation: `screen` reaches only the HCH `InnerLoop` arm; `compare_harnesses` builds the
Hexpert/Hmin arms outside `InnerLoop`, so before `screen` can drive a verdict those arms must be wrapped in
`GuardedPolicy` symmetrically — deferred with the screen-default-ON slice. Full suite **339 tests green** (use
the exact count from Step 3).
```

Then update the **"Next — US-3b → US-3f"** paragraph. Replace the verbatim opening substring (stops exactly before `FINRA`):

```
**Next — US-3b → US-3f (deferred roadmap):** **3b** SSR + reverse-split + guard-veto wiring
(`alpha/guard/veto.py` has zero production call sites; SSR = prior-day close ≤ −10%; reverse-split via
`corp_actions.has_reverse_split_pending`; activates the `dont_fight_ssr` immutable doctrine). **3c** FINRA
```

with:

```
**Next — US-3c → US-3f (deferred roadmap):** **3c** FINRA
```

Finally, in the "Other deferred" sentence of that paragraph, add: *wiring the richer `features/builder` into the live loop so `GCycle` reads frontside and `LoopConfig.screen` (+ symmetric `GuardedPolicy` on all `compare_harnesses` arms) can default ON.*

- [ ] **Step 6: Commit**

```bash
git add tests/guard/test_us3b_acceptance.py docs/blueprint.md docs/PROJECT_STATE.md
git commit -m "US-3b Task 5: acceptance gate (SSR + reverse-split veto on a frontside regime) + blueprint/PROJECT_STATE"
```

---

## Self-Review

**1. Spec coverage.** Two named flags delivered (SSR via `ssr_active` Task 2; reverse_split via the Task 1 primitive + existing `has_reverse_split_pending`). Veto wired into the live path via `GuardedPolicy` (a plain `decide()` decorator) + the opt-in `InnerLoop.screen` (Task 4); `GuardedPolicy` is also usable by `WalkForwardEval.walk(policy)` with **no** code change (so no `screen` flag is needed there — the composability is real but US-3b only wires the `InnerLoop` arm). `dont_fight_ssr` activated (Task 4). Deferred flags (`dilution`/`halt_then_dump`/`going_concern`/`regulatory`) stay wired in `veto()` and default `False` — no data in US-3b.

**2. Placeholder scan.** Every step has literal code + a runnable command + expected outcome. No TBD/TODO.

**3. Type/contract consistency.** `veto(ctx)`/`CandidateContext`/`VetoVerdict` are untouched (the six `tests/guard/test_veto.py` contracts hold). `corporate_actions_known(self, as_of: Date) -> pd.DataFrame` matches across Protocol + 4 impls. `screen_decision(decision, *, source, state) -> DecisionPackage` and `GuardedPolicy.decide(state, universe)` match `DecisionPolicy`. `model_copy(update=...)` respects the frozen models. `GCycle().read(state) -> RegimeRead`, `prev_trading_day`, `has_reverse_split_pending` signatures all verified against source.

**4. Firewall.** `screen_decision` self-wraps in `GuardedSource(AsOfGuard(state.date))`; SSR reads only prior-day bars (`end = prev < as_of`); corp via `corporate_actions_known(as_of)` (announce ≤ as_of, guard checks `as_of`). New guard-safe tests assert a future `as_of` raises `LookaheadError`. No `> as_of` read introduced.

**5. Blast radius / honesty.** The guard is **default OFF**, so all existing tests (322 + Task-1's 3 = 325 after Task 1) stay green; only `screen=True` paths and the new modules add behavior. The default-off choice is not a hedge — it is forced by a real dependency (the regime arm needs the richer state builder to read frontside) and documented in code (`LoopConfig.screen` comment), the plan, and PROJECT_STATE. Vetoed candidates are **dropped** (not annotated) because the drivers score every `decision.candidate`; a kept-but-failed candidate would be entered, defeating the hard veto — `key_risks` is the audit channel instead. `AlpacaSource.corporate_actions_known` is a documented `NotImplementedError` smoke-stub (routing through the ex_date-filtered `corporate_actions` would drop pending splits and `KeyError` on the un-normalized payload), not a silently-wrong path; it is not exercised offline. Known limitation: `screen` reaches only the HCH `InnerLoop` arm — `compare_harnesses` builds Hexpert/Hmin outside `InnerLoop`, so a future verdict run must wrap all arms in `GuardedPolicy` symmetrically before flipping the default ON (documented in PROJECT_STATE).
