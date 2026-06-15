# US-3a Runner-Tier Enrichment Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Populate `StockSnapshot.consecutive_up_days` at the single chokepoint (`build_universe`) so the entire dormant multi-day-runner cascade lights up on the *live* walk — `MarketState.max_runner_tier`/`echelon`, the `chased_blowoff`/`weak_laggard_nuke` failure-signature taxonomy, and the agent prompt's `up_days` line — turning forward-plumbed dead code live with one well-tested change.

**Architecture:** `build_universe` already fetches per-symbol daily bars (for trailing RVOL). US-3a reuses **one** trailing-bar fetch per up-side symbol (gainer/gap_up) to drive *both* RVOL and a `day`-anchored runner count delegating to the already-built-and-unit-tested `alpha.features.runner.consecutive_up_days` — no second round-trip. The runner count is **anchored at `day`**: if the fetched bars lack a row dated `day` (the snapshot store and the bar store are independent — a symbol can be screened from the day's snapshot yet lack a current-day bar under capture lag), it reports `None` ("tier unknown") rather than a stale-positive count ending one day early, mirroring how `_trailing_rvol` returns `None` on a missing current-day bar. Losers are down-on-day so their trailing up-count is `0` by construction (no probe). Every downstream consumer already *reads* `consecutive_up_days` / `max_runner_tier` — they were forward-plumbed in US-1e/US-2b and have been inert only because `build_universe` never filled the field. No consumer logic changes; US-3a fills the source field and locks the cascade with integration tests.

**Tech Stack:** Python ≥ 3.11, pydantic v2 (frozen `StockSnapshot`), pandas ≥ 2.0, pytest. Deterministic, fully offline (`FakeSource`); firewall-clean (bars fetched with `end == day <= as_of`, exactly as the existing RVOL probe).

---

## Context: why this is the right first US-3 slice

The runner-tier machinery is **written, unit-tested, and forward-plumbed but inert on real walks**:

- `alpha/features/runner.py` — `consecutive_up_days(bars, day)` and `runner_echelon(snapshots)` exist and are unit-tested (`tests/features/test_runner.py`).
- `alpha/state/builder.py::build_market_state` (a **live-path** builder used by `WalkForwardEval.walk` **and** `alpha/loop/inner_loop.py`) already computes `max_runner_tier`/`echelon` from `s.consecutive_up_days` — but the universe snapshots carry `None`, so it always yields `max_runner_tier=0`, empty `echelon`.
- `alpha/refine/signatures.py::extract_signatures` reads `step.entries[sym].consecutive_up_days` + `step.market.max_runner_tier` to split nukes into `chased_blowoff` vs `weak_laggard_nuke` — both branches are dead on live walks (everything collapses to `generic_nuke`), as its own NOTE admits.
- `alpha/agent/prompt.py::build_user_prompt` renders `up_days={cud}` — currently always `?` on live walks.

**Three production call sites of `build_universe`** therefore all light up at once when the field is filled: `alpha/eval/walk_forward.py::WalkForwardEval.walk`, `alpha/loop/inner_loop.py` (the US-2c InnerLoop — same `build_universe → build_market_state → agent.decide → entries` chain), and the richer `alpha/features/builder.py::build_market_state` (off-walk; used by `tests/features/test_builder.py` + US-1e acceptance). The **single root cause** is that `build_universe` (`alpha/universe/universe.py`) never populates `consecutive_up_days`. (The richer `features/builder.py` *does* enrich it — but onto a throwaway local list via `model_copy`, so it never reaches the universe snapshots that become `step.entries`.) Filling the field at the chokepoint lights up the whole chain at once. Lowest risk, highest leverage, computable from data already on hand → correct first slice.

## US-3 decomposition (this plan = US-3a; the rest is the deferred roadmap)

- **US-3a — Runner-tier enrichment (THIS PLAN).** Populate `consecutive_up_days`; activate `max_runner_tier`/`echelon` + the nuke taxonomy + agent-prompt `up_days` on the live walk.
- **US-3b — SSR + reverse-split + guard-veto wiring.** `alpha/guard/veto.py::veto()` and `CandidateContext` have **zero production call sites**; wire them into the decision path, compute SSR (prior-day close ≤ −10% → next-day short-sale restriction) and reverse-split-pending (already computable via `alpha/data/corp_actions.py::has_reverse_split_pending`). Activates the `dont_fight_ssr` immutable doctrine.
- **US-3c — FINRA short-interest → activate `short_squeeze`.** Add `short_interest` to snapshots; flip the incubating `short_squeeze` seed live.
- **US-3d — Float / dilution / EDGAR.** `float` field + dilution flags (ATM/shelf) for the guard's `dilution` veto.
- **US-3e — Intraday / halts / MWCB.** LULD halts (涨停 analog) + intraday bars + market-wide circuit-breaker wiring (`alpha/guard/breaker.py::set_mwcb` has no caller); enables fill-feasibility + halt-locked infeasibility.
- **US-3f — Social / options / per-narrative.** Social sentiment, options flow (gamma squeeze), per-narrative-line phase tagging.

Each later slice is its own plan + adversarial review + execution, exactly like US-2a→US-2e.

---

## File Structure

| File | Change | Responsibility |
|---|---|---|
| `alpha/universe/universe.py` | Modify | `RUNNER_LOOKBACK` const; `_trailing_bars` (one wide fetch); `_runner_up_days(bars, day)` (day-anchored count, `None` on missing day bar); `_trailing_rvol` gains an optional pre-fetched-`bars` param; `build_universe` populates `consecutive_up_days` from the single fetch (loser=0). The one real production change. |
| `alpha/universe/stock.py` | Modify (comment) | Refresh the "until US-3 enrichment" comment for `consecutive_up_days` (now populated). |
| `alpha/state/builder.py` | Modify (docstring) | Refresh the stale docstring that claims `build_universe` does not populate `consecutive_up_days`. No logic change. |
| `alpha/refine/signatures.py` | Modify (docstring) | Refresh the stale docstring that claims nukes always degrade to `generic_nuke` on live walks. No logic change. |
| `alpha/features/builder.py` | Modify (DRY) | Read `consecutive_up_days` from the now-populated universe instead of re-fetching + `model_copy`; drop the now-unused `_lookback_start` and `consecutive_up_days` import. Behavior-identical for runs < 30 up-days (all fixtures); a strict correctness improvement at the ≥30 boundary (see Task 3). |
| `tests/universe/test_build_universe.py` | Modify | Unit tests: gainer cud populated; loser cud=0; missing-day-bar cud `None`; guard-safe. |
| `tests/eval/test_runner_cascade.py` | Create | Integration locks: live walk surfaces `max_runner_tier`/`echelon`/`entries.cud` (incl. the InnerLoop-shaped chain); signature taxonomy discriminates **both** `chased_blowoff` and `weak_laggard_nuke` on genuinely-populated fields. |
| `tests/agent/test_prompt_up_days.py` | Create | Lock: `build_user_prompt` renders a real `up_days` (not `?`) over a populated universe. |
| `tests/eval/test_us3a_acceptance.py` | Create | US-3a acceptance gate: the runner-tier cascade renders end-to-end on a seeded-harness walk. |
| `docs/PROJECT_STATE.md` | Modify | Header `Last updated` line + replace the "Next — US-3" block with the US-3a-DONE entry + the US-3b–f deferred roadmap. |

**Note on TDD framing:** Task 1 is a genuine red→green (the field is `None` until implemented). Tasks 2–3 add **integration / cascade locks** — tests that assert behavior *enabled by* Task 1's chokepoint fill; they would fail without Task 1 (asserting `max_runner_tier == 0` / `up_days=?` / `generic_nuke`) and pass once it lands. They are honest regression locks for Task 1's reach across modules (`walk_forward`, `inner_loop`, `signatures`, `prompt`), not red→green for new production logic. This is called out at each step.

---

## Task 1: `build_universe` populates `consecutive_up_days` (single-fetch, day-anchored)

**Files:**
- Modify: `alpha/universe/universe.py` (`RUNNER_LOOKBACK`; `_trailing_bars`; `_runner_up_days`; `_trailing_rvol` optional bars; wire into `build_universe`)
- Modify: `alpha/universe/stock.py:24` (refresh comment)
- Test: `tests/universe/test_build_universe.py`

- [ ] **Step 1: Write the failing tests**

Append to `tests/universe/test_build_universe.py` (the file already imports `from datetime import date` and `from alpha.universe.universe import build_universe`; add the `pandas`/`FakeSource` imports the loser/missing-bar tests need):

```python
import pandas as pd
from alpha.data.source import FakeSource


def test_build_universe_populates_consecutive_up_days(fake_source):
    # RUN closes 11 -> 14 -> 17 over 6/10..6/12 -> 2 consecutive up-days ending 6/12.
    u = build_universe(fake_source, date(2026, 6, 12), gainer_pct=10.0, gap_pct=5.0, rvol_window=2)
    assert u.get("RUN").consecutive_up_days == 2


def test_build_universe_runner_tier_is_guard_safe(fake_source):
    # cud bars are fetched with end == day <= as_of, so the firewall does not trip.
    from alpha.data.firewall import AsOfGuard
    from alpha.data.source import GuardedSource
    gs = GuardedSource(fake_source, AsOfGuard(date(2026, 6, 12)))
    u = build_universe(gs, date(2026, 6, 12), gainer_pct=10.0, gap_pct=5.0, rvol_window=2)
    assert u.get("RUN").consecutive_up_days == 2


def test_build_universe_loser_consecutive_up_days_zero():
    # A loser is down on the day -> its trailing up-count ending today is 0 by construction (no probe).
    cal = [date(2026, 6, 11), date(2026, 6, 12)]
    snaps = {date(2026, 6, 12): pd.DataFrame({
        "symbol": ["DROP"], "name": ["d"], "open": [10.0], "high": [10.0],
        "low": [8.0], "close": [8.0], "volume": [1], "prev_close": [10.0]})}   # -20% loser
    src = FakeSource(calendar=cal, bars={}, snapshots=snaps)
    u = build_universe(src, date(2026, 6, 12), gainer_pct=10.0, gap_pct=5.0, rvol_window=2)
    assert u.get("DROP").status == "loser" and u.get("DROP").consecutive_up_days == 0


def test_build_universe_missing_day_bar_runner_tier_unknown():
    # A gainer present in the day snapshot but whose bars lack the day row (capture lag) -> tier UNKNOWN
    # (None), not a stale-positive count ending one day early.
    cal = [date(2026, 6, 10), date(2026, 6, 11), date(2026, 6, 12)]
    snaps = {date(2026, 6, 12): pd.DataFrame({
        "symbol": ["LAG"], "name": ["l"], "open": [13.0], "high": [18.0],
        "low": [13.0], "close": [17.0], "volume": [1], "prev_close": [14.0]})}   # +21% gainer on 6/12
    bars = {"LAG": pd.DataFrame({"date": [date(2026, 6, 10), date(2026, 6, 11)],   # NO 6/12 row
                                 "open": [10.0, 12.5], "high": [12, 15], "low": [9.5, 12],
                                 "close": [11.0, 14.0], "volume": [1, 1]})}
    src = FakeSource(calendar=cal, bars=bars, snapshots=snaps)
    u = build_universe(src, date(2026, 6, 12), gainer_pct=10.0, gap_pct=5.0, rvol_window=2)
    assert u.get("LAG").status == "gainer" and u.get("LAG").consecutive_up_days is None
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python -m pytest tests/universe/test_build_universe.py -v`
Expected: the four new tests FAIL — `consecutive_up_days` is `None` for RUN (assert `None == 2`); loser is `None`, not `0`; the missing-bar gainer is `None` only by coincidence of the field default (it must remain `None` *after* implementation — that test will re-confirm once the probe exists and could otherwise return a stale count).

- [ ] **Step 3: Add the constant + helpers in `alpha/universe/universe.py`**

Add the import next to the other late imports (after `from alpha.data.calendar import trading_days_between`):

```python
from alpha.features.runner import consecutive_up_days
```

(No import cycle: `universe.universe` → `features.runner` → `{state.market, universe.stock}`, both leaves; verified against the current import graph.)

Add the module constant and two helpers just above `build_universe`:

```python
RUNNER_LOOKBACK = 30   # max consecutive-up-days probed (a run of n up-days needs n+1 closes)


def _trailing_bars(source, symbol: str, day: Date, lookback: int):
    """One trailing daily-bar fetch ending at `day` (guard-safe: end == day <= as_of), wide enough to
    feed BOTH the RVOL window and the runner-depth count from a single round-trip per symbol."""
    cal = [d for d in source.trading_calendar() if d <= day]
    if not cal:
        return None
    start = cal[-(lookback + 1)] if len(cal) > lookback else cal[0]
    return source.daily_bars(symbol, start, day)


def _runner_up_days(bars, day: Date, max_lookback: int = RUNNER_LOOKBACK) -> int | None:
    """Trailing consecutive up-closes ANCHORED at `day` (multi-day-runner tier).

    Returns None when `bars` has no row dated `day` — the snapshot store and the bar store are
    independent, so a symbol can be screened from the day's snapshot yet lack a current-day bar
    (capture lag). We report tier 'unknown' rather than a stale-positive count ending one day early,
    matching the missing-current-day posture of `_trailing_rvol`. Otherwise delegates the count to
    alpha.features.runner.consecutive_up_days (capped at max_lookback)."""
    if bars is None or getattr(bars, "empty", True) or "date" not in bars.columns:
        return None
    if day not in set(pd.to_datetime(bars["date"]).dt.date):
        return None
    return consecutive_up_days(bars, day, max_lookback=max_lookback)
```

- [ ] **Step 4: Let `_trailing_rvol` reuse a pre-fetched frame (no second round-trip)**

Change the `_trailing_rvol` signature and its single fetch line. Replace:

```python
def _trailing_rvol(source, symbol: str, day: Date, window: int) -> float | None:
    """today_volume / mean(volume over the `window` trading days strictly BEFORE `day`)."""
    cal = source.trading_calendar()
    prior = [d for d in cal if d < day]
    if len(prior) < window:
        return None
    win = sorted(prior)[-window:]
    bars = source.daily_bars(symbol, win[0], day)        # end=day is legal (<=as_of)
```

with:

```python
def _trailing_rvol(source, symbol: str, day: Date, window: int, *, bars=None) -> float | None:
    """today_volume / mean(volume over the `window` trading days strictly BEFORE `day`).
    Optionally reuse a pre-fetched (wider) bar frame to avoid a second round-trip per symbol;
    the internal date masks slice the RVOL window out of any wider frame."""
    cal = source.trading_calendar()
    prior = [d for d in cal if d < day]
    if len(prior) < window:
        return None
    win = sorted(prior)[-window:]
    if bars is None:
        bars = source.daily_bars(symbol, win[0], day)    # end=day is legal (<=as_of)
```

(The rest of `_trailing_rvol` is unchanged: its `today`/`trailing` date masks already filter a wider frame down to the RVOL window, so passing a 31-day frame yields the identical RVOL.)

- [ ] **Step 5: Wire it into `build_universe`**

In `alpha/universe/universe.py::build_universe`, replace the `stocks[symbol] = StockSnapshot(...)` construction block with this — one fetch per up-side symbol feeds both RVOL and the runner count; losers skip the probe:

```python
        if status == "loser":                      # down on the day -> not a runner; cud 0, RVOL only
            rvol = _trailing_rvol(source, symbol, day, rvol_window)
            cud: int | None = 0
        else:                                      # gainer / gap_up: ONE fetch feeds RVOL + runner depth
            bars = _trailing_bars(source, symbol, day, max(rvol_window, RUNNER_LOOKBACK))
            rvol = _trailing_rvol(source, symbol, day, rvol_window, bars=bars)
            cud = _runner_up_days(bars, day)
        stocks[symbol] = StockSnapshot(
            symbol=symbol, name=str(rec.get("name", "")), status=status,
            close=(float(close) if close is not None else None),
            prev_close=(float(prev) if prev is not None else None),
            pct_change=pct, gap_pct=gap,
            volume=(float(rec["volume"]) if rec.get("volume") is not None else None),
            rvol=rvol, consecutive_up_days=cud,
        )
```

Note: only `status == "loser"` takes the cud=0 fast path. A gap_up that opened up but *closed red* is classified `gap_up` (not `loser`), so it still probes — and naturally returns 0 because today's lower close terminates the run. The dichotomy is "loser status → 0 without probe" vs "gainer/gap_up → probe", not "down-on-day → 0".

- [ ] **Step 6: Refresh the stock.py comment**

In `alpha/universe/stock.py`, line 24, replace:

```python
    # float / short_interest / halts -> None until US-3 enrichment
```

with:

```python
    # consecutive_up_days populated by build_universe (US-3a; None = current-day bar absent);
    # float / short_interest / halts -> None until US-3b+
```

- [ ] **Step 7: Run the tests to verify they pass**

Run: `python -m pytest tests/universe/test_build_universe.py -v`
Expected: all tests PASS (the original 3 + the new 4). The missing-bar test now exercises the real probe and confirms it returns `None` (anchored), not a stale `1`.

- [ ] **Step 8: Run the full suite (guard against regressions in the chokepoint)**

Run: `python -m pytest -q`
Expected: all previously-green tests still pass (314) + the new universe tests. This gate explicitly covers the three `build_universe` consumers — `tests/eval/` (walk_forward), `tests/loop/` (US-2c InnerLoop, US-2d compare, US-2e stats), `tests/features/test_builder.py` + `tests/regime/test_us1e_acceptance.py`. All their fixtures provide bars covering `day`, so the fill is behavior-preserving for them.

- [ ] **Step 9: Commit**

```bash
git add alpha/universe/universe.py alpha/universe/stock.py tests/universe/test_build_universe.py
git commit -m "US-3a Task 1: build_universe populates day-anchored consecutive_up_days from a single per-symbol fetch (loser=0)"
```

---

## Task 2: Cascade lock — live walk surfaces runner tier + signature taxonomy discriminates both branches

**Files:**
- Create: `tests/eval/test_runner_cascade.py`
- Modify: `alpha/state/builder.py` (refresh docstring only)
- Modify: `alpha/refine/signatures.py` (refresh docstring only)

This task adds **integration locks** for Task 1's cross-module reach. No production logic changes — `state/builder.py` and `signatures.py` already read the fields; we lock that they are now genuinely populated end-to-end, and refresh the stale docstrings.

- [ ] **Step 1: Write the cascade-lock tests**

Create `tests/eval/test_runner_cascade.py`:

```python
"""US-3a cascade locks: once build_universe fills consecutive_up_days, the live walk surfaces
max_runner_tier / echelon / entries.cud, and the failure-signature taxonomy discriminates
chased_blowoff vs weak_laggard_nuke on genuinely-populated runner fields (was generic_nuke)."""
from datetime import date, datetime
from pathlib import Path
import pandas as pd
from alpha.data.source import FakeSource
from alpha.harness.loader import load_seeds
from alpha.llm.client import MockLLMClient
from alpha.agent.agent import LLMAgentPolicy
from alpha.eval.walk_forward import WalkForwardEval
from alpha.universe.universe import build_universe
from alpha.state.builder import build_market_state
from alpha.eval.decision import Candidate, DecisionPackage
from alpha.eval.metrics import ScoredCandidate
from alpha.eval.trajectory import TrajectoryStep, Trajectory
from alpha.refine.signatures import extract_signatures

SEEDS = Path(__file__).resolve().parents[2] / "seeds"


def _runner_source(n=8):
    """Single symbol RUN rising +15%/day -> consecutive_up_days climbs 0,1,2,...,7 over the window."""
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


def _two_runner_source(n=8):
    """RUN rises every day (top tier); LAG is flat then +10% only on the last day (a genuine laggard)."""
    cal = [date(2026, 6, d) for d in range(1, 1 + n)]
    last = cal[-1]
    run = [10.0 * (1.15 ** k) for k in range(1, 1 + n)]      # strictly rising -> cud n-1
    lag = [10.0] * (n - 1) + [11.0]                          # flat then +10% today -> cud 1
    snaps = {last: pd.DataFrame({
        "symbol": ["RUN", "LAG"], "name": ["RUN", "LAG"],
        "open": [run[-2], 10.0], "high": [run[-1], 11.0], "low": [run[-2], 10.0],
        "close": [run[-1], 11.0], "volume": [1, 1], "prev_close": [run[-2], 10.0]})}
    bars = {"RUN": pd.DataFrame({"date": cal, "open": run, "high": run, "low": run, "close": run, "volume": [1] * n}),
            "LAG": pd.DataFrame({"date": cal, "open": lag, "high": lag, "low": lag, "close": lag, "volume": [1] * n})}
    return FakeSource(calendar=cal, bars=bars, snapshots=snaps)


def test_live_walk_surfaces_runner_tier():
    src = _runner_source(8)
    agent = LLMAgentPolicy(load_seeds(SEEDS),
                           MockLLMClient('{"candidates": [{"symbol": "RUN", "pattern": "gap_and_go"}]}'))
    traj = WalkForwardEval(src, src.trading_calendar()[0], src.trading_calendar()[-1], horizon=2).walk(agent)
    tiers = [s.market.max_runner_tier for s in traj.steps]
    assert max(tiers) >= 2                                       # the live state now surfaces a runner tier
    cud = [st.entries["RUN"].consecutive_up_days for st in traj.steps if "RUN" in st.entries]
    assert cud and all(c is not None for c in cud) and max(cud) >= 2   # entries carry real cud (not None)


def test_signatures_discriminate_on_populated_runner_tier():
    src = _two_runner_source(8)
    day = src.trading_calendar()[-1]
    uni = build_universe(src, day)
    state = build_market_state(uni, day, as_of=datetime(day.year, day.month, day.day, 16, 0))
    assert state.max_runner_tier >= 2
    assert uni.get("RUN").consecutive_up_days == state.max_runner_tier   # RUN is the top runner
    assert uni.get("LAG").consecutive_up_days == 1                        # a genuine laggard
    nuke = lambda sym: ScoredCandidate(decision_date=day, symbol=sym, pattern="gap_and_go",
                                       outcome="nuked", score=-0.5, day_baseline=0.0)
    dec = DecisionPackage(date=day, candidates=[Candidate(symbol="RUN", pattern="gap_and_go"),
                                                Candidate(symbol="LAG", pattern="gap_and_go")])
    step = TrajectoryStep(date=day, market=state, decision=dec,
                          entries={"RUN": uni.get("RUN"), "LAG": uni.get("LAG")},
                          outcomes={"RUN": nuke("RUN"), "LAG": nuke("LAG")}, scored=True)
    kinds = {s.symbol: s.kind for s in extract_signatures(Trajectory(steps=[step]), load_seeds(SEEDS))}
    assert kinds == {"RUN": "chased_blowoff", "LAG": "weak_laggard_nuke"}   # both branches locked
```

- [ ] **Step 2: Run the cascade-lock tests**

Run: `python -m pytest tests/eval/test_runner_cascade.py -v`
Expected: both PASS — confirming Task 1's chokepoint fill reaches `MarketState`, `entries`, and *both* signature-taxonomy branches. Had Task 1 not landed, `max(tiers) == 0` and every nuke would be `generic_nuke` — the regression these locks guard.

- [ ] **Step 3: Refresh the stale docstring in `alpha/state/builder.py`**

Replace the **entire** `build_market_state` docstring (the triple-quoted block, currently lines 10–16, beginning `"""Minimal MarketState ...` through `... regime-relative normalization is US-1).`) with:

```python
    """Minimal MarketState from the day's universe: breadth counts + runner echelon.

    The runner echelon / max_runner_tier are driven by StockSnapshot.consecutive_up_days, which
    build_universe populates as of US-3a (gainers/gap_ups by a day-anchored trailing-bar probe; losers
    0; None when a current-day bar is absent). So over a built universe the echelon is now live on the
    walk path. sentiment_norm stays None here — the regime-relative normalization lives in the richer
    alpha/features/builder.py build (wired into the eval loop in a later US-3 slice).
    """
```

- [ ] **Step 4: Refresh the stale docstring in `alpha/refine/signatures.py`**

Replace the **entire** `extract_signatures` docstring (the triple-quoted block, currently lines 28–33, beginning `"""Per non-continued scored pick ...` through `... see plan Task 4 note)."""`) with:

```python
    """Per non-continued scored pick, classify the failure. Continued (win) -> no signature.
    nuked split by entry context: chased a top-tier extended runner vs took a laggard.

    As of US-3a build_universe populates consecutive_up_days, so on real walks step.entries carry a
    runner tier and step.market.max_runner_tier is non-zero -> the chased_blowoff / weak_laggard_nuke
    discrimination is live (it degrades to generic_nuke only when a pick's tier is genuinely unknown)."""
```

- [ ] **Step 5: Run the full suite**

Run: `python -m pytest -q`
Expected: all green (signatures/state unit tests unchanged; new cascade locks pass).

- [ ] **Step 6: Commit**

```bash
git add tests/eval/test_runner_cascade.py alpha/state/builder.py alpha/refine/signatures.py
git commit -m "US-3a Task 2: cascade locks (live walk surfaces runner tier; nuke taxonomy discriminates both branches) + refresh stale docstrings"
```

---

## Task 3: Agent-prompt `up_days` lock + `features/builder.py` DRY cleanup

**Files:**
- Create: `tests/agent/test_prompt_up_days.py`
- Modify: `alpha/features/builder.py` (read cud from the populated universe; drop redundant fetch + `_lookback_start`)

- [ ] **Step 1: Write the prompt lock test**

Create `tests/agent/test_prompt_up_days.py`:

```python
"""US-3a lock: build_user_prompt renders a real up_days from the now-populated universe (was '?')."""
from datetime import date, datetime
from alpha.universe.universe import build_universe
from alpha.state.builder import build_market_state
from alpha.agent.prompt import build_user_prompt


def test_user_prompt_renders_runner_up_days(fake_source):
    day = date(2026, 6, 12)
    uni = build_universe(fake_source, day, rvol_window=2)         # RUN -> 2 trailing up-days
    state = build_market_state(uni, day, as_of=datetime(2026, 6, 12, 16, 0))
    text = build_user_prompt(state, uni)
    # FLOP's -8.3% day is inside the +/-10% band and its gap is 0%, so the only universe line is RUN
    # -> "no up_days=?" is a real assertion about RUN's rendered tier, not a vacuous empty-universe pass.
    assert "up_days=2" in text and "up_days=?" not in text
```

- [ ] **Step 2: Run it (lock confirmation)**

Run: `python -m pytest tests/agent/test_prompt_up_days.py -v`
Expected: PASS (RUN's `consecutive_up_days == 2` from Task 1 renders as `up_days=2`; the only universe line is RUN, so no `up_days=?`). Pre-Task-1 this would render `up_days=?` and fail.

- [ ] **Step 3: Simplify `alpha/features/builder.py` to read cud from the populated universe**

Replace the body of `build_market_state` from the `universe = build_universe(source, day)` line through the `echelon = runner_echelon(...)` line. Change:

```python
    universe = build_universe(source, day)
    # enrich gainers with strictly-trailing consecutive_up_days
    start = _lookback_start(source, day)
    enriched = []
    for s in universe.by_status("gainer"):
        bars = source.daily_bars(s.symbol, start, day)
        enriched.append(s.model_copy(update={"consecutive_up_days": consecutive_up_days(bars, day)}))
    g, gu, lo = counts(universe)
    ft = follow_through_rate(universe, prev_gainers)
    fb = failed_breakout_count(universe)
    echelon = runner_echelon(enriched)
```

to:

```python
    universe = build_universe(source, day)            # snapshots already carry consecutive_up_days (US-3a)
    g, gu, lo = counts(universe)
    ft = follow_through_rate(universe, prev_gainers)
    fb = failed_breakout_count(universe)
    echelon = runner_echelon(universe.by_status("gainer"))   # same gainer set, now read (not re-fetched)
```

Then delete the now-unused `_lookback_start` function (the whole `def _lookback_start(...): ...` block at the bottom of the file) and drop `consecutive_up_days` from the `from alpha.features.runner import ...` line (keep `runner_echelon`):

```python
from alpha.features.runner import runner_echelon
```

**Behavior note (honest, not byte-identical):** this builder still echelons only `by_status("gainer")` — the same gainer set as before — so its `MarketState.echelon`/`max_runner_tier` are unchanged for every test fixture. Two precise caveats: (a) `build_universe` now also fills cud for *gap_ups*, which this builder does not echelon (that gap_up cud is consumed by the live `state/builder.py`, which tiers over *all* stocks — the two builders deliberately tier from different status sets); and (b) the old path fetched a 30-close window (`_lookback_start(window=30)`), capping the count at 29, while the unified probe fetches 31 closes and caps at `RUNNER_LOOKBACK=30`. They are therefore identical for any run **< 30** up-days (all fixtures are ≤ 8 bars); for a genuine run of exactly 30 the new value is one higher (30 vs the old window-truncated 29) — a strict correctness improvement, unreachable by the suite, not a regression.

- [ ] **Step 4: Verify the enriched-builder tests are behavior-preserving**

Run: `python -m pytest tests/features/test_builder.py tests/regime/test_us1e_acceptance.py -v`
Expected: PASS — `test_build_market_state_enriched` still sees `max_runner_tier == 2`, `echelon[0].tier == 2`, `representatives == ["RUN"]`; US-1e acceptance still green.

- [ ] **Step 5: Run the full suite**

Run: `python -m pytest -q`
Expected: all green.

- [ ] **Step 6: Commit**

```bash
git add tests/agent/test_prompt_up_days.py alpha/features/builder.py
git commit -m "US-3a Task 3: agent-prompt up_days lock + DRY features/builder (read cud from populated universe)"
```

---

## Task 4: US-3a acceptance gate + PROJECT_STATE

**Files:**
- Create: `tests/eval/test_us3a_acceptance.py`
- Modify: `docs/PROJECT_STATE.md`

- [ ] **Step 1: Write the acceptance test**

Create `tests/eval/test_us3a_acceptance.py`:

```python
"""US-3a acceptance: the runner-tier cascade renders end-to-end on a seeded-harness walk — a live
multi-day runner surfaces a MarketState tier, its universe snapshot carries the tier, and the agent
prompt the policy builds shows a real up_days (not '?'). This is the headline US-3a guarantee:
forward-plumbed runner machinery is now live on the walk path, driven by build_universe."""
from datetime import date
from pathlib import Path
import pandas as pd
from alpha.data.source import FakeSource
from alpha.harness.loader import load_seeds
from alpha.llm.client import MockLLMClient
from alpha.agent.agent import LLMAgentPolicy
from alpha.eval.walk_forward import WalkForwardEval
from alpha.universe.universe import build_universe
from alpha.agent.prompt import build_user_prompt

SEEDS = Path(__file__).resolve().parents[2] / "seeds"


def _runner_source(n=8):
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


def test_runner_tier_cascade_renders_end_to_end():
    src = _runner_source(8)
    agent = LLMAgentPolicy(load_seeds(SEEDS),
                           MockLLMClient('{"candidates": [{"symbol": "RUN", "pattern": "gap_and_go"}]}'))
    traj = WalkForwardEval(src, src.trading_calendar()[0], src.trading_calendar()[-1], horizon=2).walk(agent)
    # pick a step where the runner tier has surfaced (>=2 trailing up-days; RUN's cud climbs toward 7)
    hot = [s for s in traj.steps if s.market.max_runner_tier >= 2 and "RUN" in s.entries]
    assert hot, "expected at least one step where the multi-day runner surfaced a tier"
    step = hot[0]
    assert step.entries["RUN"].consecutive_up_days >= 2          # universe snapshot carries the tier
    text = build_user_prompt(step.market, build_universe(src, step.date))
    assert "up_days=?" not in text and f"max_runner_tier={step.market.max_runner_tier}" in text
```

- [ ] **Step 2: Run the acceptance test**

Run: `python -m pytest tests/eval/test_us3a_acceptance.py -v`
Expected: PASS.

- [ ] **Step 3: Run the full suite one final time**

Run: `python -m pytest -q`
Expected: all green (314 baseline + 8 new = 322 tests).

- [ ] **Step 4: Update `docs/PROJECT_STATE.md`**

First, replace the header `Last updated` line (line 4). Old (verbatim):

```markdown
> Last updated: 2026-06-15 (US-0 + US-1 + US-2 complete: agent/refiner/inner-loop/compare + statistical-acceptance procedure built; empirical verdict awaits a live temp=0 run; US-3 next).
```

New:

```markdown
> Last updated: 2026-06-15 (US-0 + US-1 + US-2 complete; US-3a runner-tier enrichment live on the walk path; US-3b next).
```

Then replace the entire **"Next — US-3 (data enrichment) ..."** paragraph (the block starting `**Next — US-3 (data enrichment) and/or a live-LLM smoke run:**` through `... keep-last-K checkpoint pruning.`) with:

```markdown
## US-3 Data enrichment (sub-plans 3a → 3f)

**US-3a Runner-tier enrichment — Complete (2026-06-15). The runner machinery is live on the walk.**
`build_universe` (`alpha/universe/universe.py`) now populates `StockSnapshot.consecutive_up_days` at the
single chokepoint — gainers/gap_ups via a **day-anchored** trailing-bar probe (reusing the one RVOL fetch
per symbol; delegates to the already-tested `alpha/features/runner.py::consecutive_up_days`; returns `None`
when the current-day bar is absent rather than a stale-positive count); losers `0` by construction. This
lights up the whole forward-plumbed cascade on the **live walk** (all three `build_universe` consumers —
`walk_forward`, the US-2c `inner_loop`, and the richer `features/builder`): `MarketState.max_runner_tier`/
`echelon` (the minimal `state/builder.py`), the `chased_blowoff` / `weak_laggard_nuke` failure-signature
taxonomy (`refine/signatures.py` — was always `generic_nuke` on real walks), and the agent prompt's
`up_days` line (`agent/prompt.py` — was always `?`). DRY: the richer `features/builder.py` now reads cud
from the populated universe (dropped the throwaway `model_copy` enrichment + `_lookback_start`). Cascade +
acceptance locks prove it end-to-end (both nuke branches discriminated on populated data) on a seeded-harness
walk; stale "until US-3 enrichment" docstrings refreshed. Full suite **322 tests green**.

**Next — US-3b → US-3f (deferred roadmap):** **3b** SSR + reverse-split + guard-veto wiring
(`alpha/guard/veto.py` has zero production call sites; SSR = prior-day close ≤ −10%; reverse-split via
`corp_actions.has_reverse_split_pending`; activates the `dont_fight_ssr` immutable doctrine). **3c** FINRA
short-interest → activate the incubating `short_squeeze` seed. **3d** float / dilution / EDGAR → the guard's
`dilution` veto. **3e** intraday / halts / MWCB (LULD halts = 涨停 analog; `breaker.set_mwcb` has no caller;
enables fill-feasibility + halt-locked infeasibility). **3f** social / options (gamma squeeze) / per-narrative
phase tagging. Plus, **orthogonal to US-3**: a live temp=0 Claude/DeepSeek run on captured Alpaca windows is
what renders the actual HCH-vs-Hexpert verdict via the US-2e procedure (the offline suite validates the
apparatus; MockLLM ignores prompts; honest expectation = parity). **Deferred §10 methodology** (gate-non-blocking):
purged & embargoed CV; regime-stratified eval. **Other deferred:** Hcredit (C4) ablation arm; wire L3 sizing /
L4 guard into the agent's `DecisionPackage`; master-dispatch G sub-agents (keeps the `G`-pass a reserved
no-op); keep-last-K checkpoint pruning.
```

- [ ] **Step 5: Commit**

```bash
git add tests/eval/test_us3a_acceptance.py docs/PROJECT_STATE.md
git commit -m "US-3a Task 4: acceptance gate (runner-tier cascade renders end-to-end) + PROJECT_STATE"
```

---

## Self-Review

**1. Spec coverage.** The goal — populate `consecutive_up_days` so the live walk surfaces runner tiers — is implemented in Task 1 (the only production-logic change) and locked across every consumer: `MarketState` (Task 2), the signature taxonomy *both branches* (Task 2), the agent prompt (Task 3), end-to-end acceptance (Task 4). All three `build_universe` call sites (`walk_forward`, `inner_loop`, `features/builder`) are named and covered by the Task-1 Step-8 full-suite gate. Stale comments/docstrings in `stock.py` / `state/builder.py` / `signatures.py` are all refreshed. US-3b–f are laid out as the deferred roadmap.

**2. Placeholder scan.** No TBD/TODO/"add error handling"/"similar to" — every step has the literal code or the literal command + expected outcome.

**3. Type consistency.** `_trailing_bars(source, symbol, day, lookback)` → frame|None; `_runner_up_days(bars, day, max_lookback=RUNNER_LOOKBACK) -> int | None` (None when no `day` row); `_trailing_rvol(source, symbol, day, window, *, bars=None) -> float | None`. `StockSnapshot.consecutive_up_days` is `int | None`; Task 1 writes `int` (gainer/gap_up probe), `None` (gainer/gap_up with no current-day bar), or `0` (loser) — all valid, and every consumer already treats `None`/`<1` as "no tier". `build_user_prompt(state, universe)`, `build_market_state(universe, day, *, as_of)`, `extract_signatures(traj, h)`, `LLMAgentPolicy(h, llm)`, `WalkForwardEval(source, start, end, horizon=...).walk(policy)`, `ScoredCandidate(decision_date, symbol, pattern, outcome, score, day_baseline)` signatures all match current code.

**4. Firewall.** The (single) per-symbol bar fetch uses `end == day`, identical to the existing `_trailing_rvol` probe already proven guard-safe (`test_build_universe_is_guard_safe`), and Task 1 Step 1 adds an explicit guard-safe assertion. No `> day` read is introduced. The day-anchored `None` posture is strictly *more* conservative than the old (would-be) stale count.

**5. Risk / cost / behavior-preservation.** Task 1 **eliminates** the double-`daily_bars` fetch the naive approach would add: one wider fetch per up-side symbol now feeds both RVOL and the runner count, so per-symbol round-trips on the real Alpaca source stay at one (losers unchanged: RVOL fetch only). `_trailing_rvol` change is additive (`bars=None` default preserves byte-for-byte behavior; its date masks slice any wider frame). The only behavioral change to existing code is `features/builder.py` (Task 3): behavior-identical for runs < 30 up-days (all fixtures), a strict improvement at the ≥30 edge (documented, unreachable by the suite); note also that the two `build_market_state` functions deliberately tier from different status sets (live `state/builder.py`: all snapshots incl. gap_ups; `features/builder.py`: gainers only), so the cascade is single-*sourced* (one cud fill) but not single-*pathed*. Every other change either fills a previously-`None` field (additive) or edits a docstring/comment.
