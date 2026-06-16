# US-3e Halt-then-Dump Veto (Daily Proxy) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Activate the dormant L4 `halt_then_dump` veto flag with a **daily-OHLC proxy** — a name that spiked intraday ≥15% above its prior close (a likely LULD halt-up) but round-tripped to close at/below the prior close (the spike failed) — wired into `screen_decision`. The `veto()` branch already fires `"halt-then-dump"`; US-3e supplies the (daily-cadence) signal. Real intraday LULD halts/halt-count, the market-wide circuit breaker (`breaker.set_mwcb`), and intraday fill-feasibility are **honestly deferred** (no intraday feed).

**Architecture:** US-3e is intrinsically intraday, but the engine is daily-cadence with no tick/halt feed — so the one genuinely offline-computable piece is the spike-and-dump daily proxy from OHLC. `open/high/low` are not on `StockSnapshot`, but they are on the daily-snapshot DataFrame, so `screen_decision` fetches the day's snapshot once (guard-safe, `as_of` ≤ `as_of`) and a pure `halt_then_dump_proxy(row)` computes the flag from `prev_close/high/close`. It slots into the per-candidate `CandidateContext` exactly like US-3b `ssr` and US-3d `dilution` — a one-line add; `veto.py` is unchanged. Enforcement stays opt-in via `GuardedPolicy`/`LoopConfig.screen` (default-off), so the existing suite is untouched. Empty-snapshot fixtures (the SSR-style screen tests) yield no rows → the proxy is a no-op there.

**Tech Stack:** Python ≥ 3.11, pydantic v2, pandas, pytest. Deterministic, offline (`FakeSource`); firewall-clean (the proxy reads only the day's own snapshot, `as_of` ≤ `as_of`, known at the decision-day close).

---

## Context: what's dormant, what's computable, what's deferred

- `alpha/guard/veto.py` — `CandidateContext.halt_then_dump: bool = False` (comment "(US-3 intraday)") and `veto()` already appends `"halt-then-dump"` when it is true. **Zero changes to `veto.py`.** The flag is just never set.
- `alpha/guard/screen.py::screen_decision` (US-3b/3d) builds a `CandidateContext` per candidate with `ssr` + `reverse_split_pending` + `dilution`, dropping vetoed names and recording reasons in `key_risks`. US-3e adds `halt_then_dump=…` (one line) + one daily-snapshot fetch.
- `alpha/universe/stock.py` — `StockSnapshot` carries `close`/`prev_close`/`pct_change`/`gap_pct` but **not** `open`/`high`/`low`; those live on the daily-snapshot DataFrame (`_EMPTY_SNAP` includes `open,high,low`) and `daily_bars`. The proxy therefore reads the snapshot row, not the `StockSnapshot`.

**What US-3e ships (offline-computable):** the `halt_then_dump` daily proxy + its wiring. **What it honestly defers (needs intraday / new architecture):**
- **Real LULD halts / halt-count / halt-resume** — intraday tick + halt-event data; the daily proxy is a noisy stop-gap.
- **MWCB (`breaker.set_mwcb`)** — the portfolio `Breaker` (`alpha/guard/breaker.py`) has **zero production callers**; it is a portfolio-level loss circuit-breaker (not a per-candidate veto) and would need a portfolio P&L state machine + an index-crash monitor (and an index data feed) to drive `set_mwcb`. That is a separate medium-size architecture slice; US-3e leaves `Breaker` as-is and documents the dependency. (A market-wide risk-off is already covered by the regime arm of `veto()` via `GCycle`.)
- **Fill-feasibility (hard halt-locked infeasibility)** — needs intraday size-at-offer/depth; `DecisionPackage.FillFeasibility` stays on the inference path (deferred since US-1d).

## US-3 decomposition status

US-3a runner-tier, US-3b SSR/reverse-split guard-veto, US-3c short-interest/short_squeeze, US-3d float/dilution-veto — all DONE. **US-3e = THIS PLAN (the `halt_then_dump` daily-proxy veto).** Deferred within US-3e: real LULD halts/halt-count, MWCB/`Breaker` portfolio wiring, intraday fill-feasibility. Remaining roadmap: **3f** social / options_flow → `gamma_squeeze` / per-narrative. Orthogonal (still open): wiring the richer `features/builder` into the live loop (unlocks `LoopConfig.screen` default-on + symmetric `GuardedPolicy` on `compare_harnesses` arms); the live temp=0 LLM verdict run.

---

## File Structure

| File | Change | Responsibility |
|---|---|---|
| `alpha/guard/screen.py` | Modify | `HALT_SPIKE_PCT` + `_num` helper + pure `halt_then_dump_proxy(row)`; fetch the day's snapshot once in `screen_decision` and add `halt_then_dump=…` to the `CandidateContext`. |
| `tests/guard/test_screen.py` | Modify | `halt_then_dump_proxy` unit cases + `screen_decision` drops a halt-then-dump candidate + records the reason. |
| `tests/guard/test_us3e_acceptance.py` | Create | End-to-end: `GuardedPolicy` drops a name that spiked-and-dumped, keeps the clean runner, surfaces the reason. |
| `docs/PROJECT_STATE.md`, `docs/blueprint.md` | Modify | US-3e DONE entry (with the honest deferrals) + refreshed roadmap; reconcile the halt/LULD/MWCB doc lines. |

**No `veto.py` change** (flag + reason already exist). **No `StockSnapshot`/`build_universe`/source change** (the proxy reads the day's snapshot row in the guard layer). **No new data source.**

**TDD framing.** Both tasks are genuine red→green. The proxy runs only inside `screen_decision` (reached via the opt-in `GuardedPolicy`/`LoopConfig.screen`, default-off), so the existing 358-test suite stays green — verified by a full-suite run after every task.

---

## Task 1: `halt_then_dump` daily proxy + wire the veto

**Files:** Modify `alpha/guard/screen.py`; Test `tests/guard/test_screen.py`

- [ ] **Step 1: Write the failing tests**

Append to `tests/guard/test_screen.py` (the module already imports `pd`, `date`, `FakeSource`, `screen_decision`, `_pkg`, `_state`):

```python
def test_halt_then_dump_proxy():
    from alpha.guard.screen import halt_then_dump_proxy
    assert halt_then_dump_proxy({"prev_close": 10.0, "high": 13.0, "close": 9.5}) is True    # +30% spike, closed red
    assert halt_then_dump_proxy({"prev_close": 10.0, "high": 13.0, "close": 12.0}) is False  # spiked but held green
    assert halt_then_dump_proxy({"prev_close": 10.0, "high": 10.5, "close": 9.0}) is False   # no >=15% intraday spike
    assert halt_then_dump_proxy(None) is False                                               # missing -> never fabricate
    assert halt_then_dump_proxy({"prev_close": None, "high": 13.0, "close": 9.0}) is False   # missing prev_close


def test_screen_drops_halt_then_dump_candidate_and_records_reason():
    # SPIKE spiked >=15% intraday (high 13 vs prev 10) then round-tripped to close red (9.5) -> halt-then-dump.
    cal = [date(2026, 6, 11), date(2026, 6, 12)]
    snap = pd.DataFrame({"symbol": ["SPIKE"], "name": ["Spiker"], "open": [10.0], "high": [13.0],
                         "low": [9.0], "close": [9.5], "volume": [9], "prev_close": [10.0]})
    src = FakeSource(calendar=cal, bars={}, snapshots={date(2026, 6, 12): snap})
    out = screen_decision(_pkg("SPIKE"), source=src, state=_state())
    assert out.candidates == [] and any("SPIKE" in r and "halt-then-dump" in r for r in out.key_risks)
```

- [ ] **Step 2: Run to verify failure**

Run: `python -m pytest tests/guard/test_screen.py -k "halt_then_dump" -v`
Expected: FAIL — `ImportError: cannot import name 'halt_then_dump_proxy'`; the screen test's candidate is not dropped (flag never set).

- [ ] **Step 3: Add the proxy to `alpha/guard/screen.py`**

After the `SSR_DROP_PCT` constant (and near `ssr_active`), add:

```python
HALT_SPIKE_PCT = 0.15   # an intraday high >=15% above prior close ~ a LULD halt-up (Tier-1 band) event


def _num(value) -> float | None:
    """None-and-NaN-safe scalar float (snapshot rows can carry NaN)."""
    return None if value is None or pd.isna(value) else float(value)


def halt_then_dump_proxy(row) -> bool:
    """Daily-OHLC proxy for a halt-then-dump: the name spiked intraday >= HALT_SPIKE_PCT above its prior
    close (a likely LULD halt-up) but round-tripped to close at/below the prior close — a failed spike, do
    not chase it long. `row` is a daily-snapshot record (dict) or None. Real intraday LULD halts/halt-count
    need a tick feed (deferred); this is the daily-cadence proxy. Missing data -> False (never fabricated).

    Distinct from failed_breakout (gap-up at the OPEN that closes red): this keys on the intraday HIGH
    spike (the halt-up signature), so it also catches names that opened flat, spiked, and dumped."""
    if row is None:
        return False
    prev, high, close = _num(row.get("prev_close")), _num(row.get("high")), _num(row.get("close"))
    if prev is None or high is None or close is None or prev <= 0:
        return False
    spiked = (high - prev) / prev >= HALT_SPIKE_PCT
    dumped = close <= prev
    return spiked and dumped
```

- [ ] **Step 4: Fetch the day's snapshot once + wire the flag in `screen_decision`**

In `screen_decision`, after `corp = guarded.corporate_actions_known(as_of)`, add the snapshot fetch + row lookup:

```python
    corp = guarded.corporate_actions_known(as_of)
    snap = guarded.daily_snapshot(as_of)               # day's OHLC for the halt-then-dump proxy (guard-safe)
    rows = ({str(r["symbol"]): r for r in snap.to_dict("records")}
            if snap is not None and not snap.empty else {})
```

Then add `halt_then_dump=…` to the `CandidateContext` (after `dilution=…`):

```python
        ctx = CandidateContext(symbol=c.symbol, regime=regime,
                               ssr=ssr_active(guarded, c.symbol, as_of),
                               reverse_split_pending=has_reverse_split_pending(corp, c.symbol, as_of),
                               dilution=has_dilution_filing(corp, c.symbol, as_of),
                               halt_then_dump=halt_then_dump_proxy(rows.get(c.symbol)))
```

- [ ] **Step 5: Run the tests to verify they pass**

Run: `python -m pytest tests/guard/test_screen.py -v`
Expected: all PASS — the new halt tests + the existing SSR/reverse-split/dilution/screen contracts. (The existing screen tests use `_src(...)` sources with `snapshots={}` → `daily_snapshot` is empty → `rows={}` → `halt_then_dump_proxy(None)` → False, so they are unaffected.)

- [ ] **Step 6: Full suite**

Run: `python -m pytest -q`
Expected: 358 + 2 new = 360 green. The new `daily_snapshot` fetch in `screen_decision` is no-op for empty-snapshot fixtures and benign for populated ones (US-3b/3d acceptance names spiked but closed green → `halt_then_dump` False, no interference).

- [ ] **Step 7: Commit**

```bash
git add alpha/guard/screen.py tests/guard/test_screen.py
git commit -m "US-3e Task 1: halt_then_dump daily-OHLC proxy (spike >=15% then close <= prior) + wire the veto into screen_decision"
```

---

## Task 2: US-3e acceptance gate + docs

**Files:** Create `tests/guard/test_us3e_acceptance.py`; Modify `docs/PROJECT_STATE.md`, `docs/blueprint.md`

- [ ] **Step 1: Write the acceptance test**

Create `tests/guard/test_us3e_acceptance.py`:

```python
"""US-3e acceptance: the L4 hard veto, wired via GuardedPolicy, enforces the halt-then-dump guard on a
FRONTSIDE regime — it drops a name that spiked >=15% intraday (a likely LULD halt-up) then round-tripped to
close red, keeps the clean runner that held its spike, and surfaces the reason in key_risks. Headline US-3e
guarantee: the dormant halt_then_dump veto now fires on a daily-OHLC proxy (real intraday LULD/MWCB/
fill-feasibility are deferred — no intraday feed)."""
from datetime import date, datetime
import pandas as pd
from alpha.data.source import FakeSource
from alpha.state.market import MarketState
from alpha.eval.decision import Candidate, DecisionPackage
from alpha.universe.universe import CandidateUniverse
from alpha.guard.screen import GuardedPolicy

CUR = date(2026, 6, 12)


def _source():
    cal = [date(2026, 6, 11), CUR]
    snap = pd.DataFrame({
        "symbol": ["CLEAN", "SPIKE"], "name": ["Clean", "Spiker"],
        "open": [10.0, 10.0], "high": [12.0, 14.0], "low": [10.0, 9.0],
        "close": [12.0, 9.5], "volume": [5, 9], "prev_close": [10.0, 10.0]})
    # CLEAN: +20% intraday high but CLOSED green (12) -> not a halt-then-dump.
    # SPIKE: +40% intraday high (likely halt-up) but CLOSED red (9.5 <= 10) -> halt-then-dump.
    return FakeSource(calendar=cal, bars={}, snapshots={CUR: snap})


def _frontside_state():
    return MarketState(date=CUR, gainer_count=2, gap_up_count=0, loser_count=0, failed_breakout_count=0,
                       max_runner_tier=1, echelon=[], breadth_raw=2.0, sentiment_norm=0.7,
                       follow_through_rate=0.5, as_of=datetime(2026, 6, 12, 16, 0))


class _StubPolicy:
    def decide(self, state, universe):
        return DecisionPackage(date=CUR, candidates=[Candidate(symbol=s, pattern="gap_and_go")
                                                     for s in ("CLEAN", "SPIKE")])


def test_guard_enforces_halt_then_dump_on_frontside():
    out = GuardedPolicy(_StubPolicy(), _source()).decide(_frontside_state(), CandidateUniverse.from_stocks([]))
    assert [c.symbol for c in out.candidates] == ["CLEAN"]                       # the spiked-and-dumped name is dropped
    assert out.regime is not None and out.regime.frontside is True
    assert any("SPIKE" in r and "halt-then-dump" in r for r in out.key_risks)   # reason surfaced
```

- [ ] **Step 2: Run the acceptance test**

Run: `python -m pytest tests/guard/test_us3e_acceptance.py -v`
Expected: PASS.

- [ ] **Step 3: Full suite**

Run: `python -m pytest -q`
Expected: all green; record the exact count (expected 361 = 358 + 3 new: Task1 +2, Task2 +1). Use whatever the run reports for the PROJECT_STATE edit.

- [ ] **Step 4: Update `docs/PROJECT_STATE.md`**

Replace the header `Last updated` line (line 4). Old (verbatim):

```markdown
> Last updated: 2026-06-15 (US-0 + US-1 + US-2 complete; US-3a runner-tier + US-3b guard-veto + US-3c short-interest + US-3d float/dilution-veto shipped; US-3e next).
```

New:

```markdown
> Last updated: 2026-06-15 (US-0 + US-1 + US-2 complete; US-3a–US-3e shipped (runner-tier, guard-veto, short-interest, dilution, halt-then-dump); US-3f next).
```

Insert, immediately after the US-3d paragraph (the block ending "Full suite **358 tests green**.") and before the "Next — US-3e → US-3f" paragraph:

```markdown
**US-3e Halt-then-dump veto (daily proxy) — Complete (2026-06-15). The last daily-cadence guard flag is live.**
The dormant L4 `halt_then_dump` veto is activated with a **daily-OHLC proxy** (`alpha/guard/screen.py::halt_then_dump_proxy`):
a name whose intraday high spiked ≥15% above its prior close (a likely LULD halt-up) but round-tripped to
close at/below the prior close is a failed spike → vetoed. `screen_decision` fetches the day's snapshot once
(guard-safe) and slots `halt_then_dump=…` into the `CandidateContext` — the US-3b/3d one-line pattern; `veto()`
already fires `"halt-then-dump"`. Distinct from `failed_breakout` (gap-at-open): this keys on the intraday HIGH
spike. Opt-in via `GuardedPolicy`/`LoopConfig.screen` (default-off); suite untouched. **Honestly deferred (need
an intraday feed / new architecture):** real LULD halts + halt-count (tick data); the **MWCB** market-wide
circuit breaker (`alpha/guard/breaker.py::Breaker.set_mwcb` has zero production callers — a portfolio-level loss
breaker needing a P&L state machine + index-crash monitor, not a per-candidate veto; market-wide risk-off is
already covered by the regime arm of `veto()`); and intraday **fill-feasibility**. Acceptance-tested end-to-end
on a frontside regime. Full suite **361 tests green**.

**Next — US-3f (deferred roadmap):**
```

(That last line replaces the start of the existing `**Next — US-3e → US-3f (deferred roadmap):** **3e** intraday / halts / MWCB (...). **3f** social / options (gamma squeeze) / per-narrative` sentence — drop the `**3e** …` clause, keeping `**3f** social / options (gamma squeeze) / per-narrative phase tagging.` onward. Verify the exact current wording before the edit and stop precisely before `**3f**`.)

Finally, in the "Other deferred" sentence, append: *real LULD halts / halt-count (intraday tick feed); MWCB / `Breaker` portfolio wiring (P&L state machine + index-crash monitor); intraday fill-feasibility (size-at-offer).*

- [ ] **Step 5: Reconcile `docs/blueprint.md`**

Grep `halt` / `LULD` / `MWCB` / `fill_feasibility` in `docs/blueprint.md`. Update the runner-family row's "Halt-resumption / … / halt count → **US-3 intraday**" framing (and any halt/MWCB cell) to note the **halt-then-dump daily proxy is wired in US-3e**, while real LULD halts / halt-count / MWCB / intraday fill-feasibility remain **US-3 intraday-feed deferred**. Keep the edit to the one or two relevant cells; do not rewrite unrelated content.

- [ ] **Step 6: Commit**

```bash
git add tests/guard/test_us3e_acceptance.py docs/PROJECT_STATE.md docs/blueprint.md
git commit -m "US-3e Task 2: acceptance gate (halt-then-dump veto fires on a spike-and-dump) + PROJECT_STATE/blueprint"
```

---

## Self-Review

**1. Spec coverage.** The `halt_then_dump` veto is activated via a daily-OHLC proxy (Task 1) + acceptance-tested end-to-end (Task 2). The intraday-only parts of "intraday / halts / MWCB / fill-feasibility" (real LULD halts/halt-count, `Breaker`/MWCB portfolio wiring, fill-feasibility) are explicitly deferred with the dependency named — no overclaim.

**2. Placeholder scan.** Every step has literal code + a runnable command + expected outcome, except Task 2 Step 5 (blueprint), a bounded grep-then-edit of the halt/MWCB cell(s).

**3. Type/contract consistency.** `halt_then_dump_proxy(row) -> bool` is pure (dict|None → bool), None/NaN-safe via `_num`. `screen_decision` reuses the existing fetch pattern (adds one `daily_snapshot` read + a row dict). `CandidateContext.halt_then_dump` and the `veto()` reason already exist (no `veto.py` change). Mirrors the US-3b `ssr` / US-3d `dilution` wiring exactly.

**4. Firewall.** The proxy reads only the day's own snapshot via `guarded.daily_snapshot(as_of)` (`AsOfGuard` checks `as_of` ≤ `as_of`) — the day-D OHLC is point-in-time known at the day-D close, when `screen_decision` runs (once per day). No prior/forward read; no new firewall edge.

**5. Blast radius / honesty.** The proxy runs only inside `screen_decision` (opt-in `GuardedPolicy`/`LoopConfig.screen`, default-off), so the 358-test suite stays green; the new `daily_snapshot` fetch is a no-op on the `snapshots={}` screen fixtures and benign on the US-3b/3d acceptance fixtures (they spiked but closed green → flag False). The deferrals are honest and named (intraday feed for LULD/halt-count/fill-feasibility; a portfolio P&L state machine + index feed for MWCB/`Breaker`) — consistent with US-3a–3d activating mechanisms without overclaiming. The 15% spike threshold is a documented tuning knob (a future Refiner/eval concern).
