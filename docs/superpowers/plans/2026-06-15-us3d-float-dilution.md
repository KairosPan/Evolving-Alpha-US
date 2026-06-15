# US-3d Float + Dilution-Veto Activation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a `free_float` field to the daily snapshot (rendered in the agent prompt) and **activate the dormant L4 `dilution` veto flag** by computing it from a PIT-safe corporate-actions dilution-filing signal (ATM / shelf / secondary offering) and wiring it into `screen_decision` — the veto branch already fires; US-3d supplies the data.

**Architecture:** Two orthogonal, firewall-safe additions that mirror the two prior enrichment patterns. (1) **`free_float`** rides the daily-snapshot DataFrame and is filled at the `build_universe` chokepoint into a new `StockSnapshot.free_float` field (the US-3c `short_interest` pattern — a per-symbol enrichment column, `_opt_float` None/NaN-safe). (2) **Dilution** is a corporate-actions *filing* signal (the US-3b `reverse_split` pattern): a new `has_dilution_filing(corp, symbol, as_of)` in `alpha/data/corp_actions.py` reuses the existing `known_corporate_actions` (announce-keyed, PIT-safe) over new `kind` values `{atm, shelf, offering}`, and `screen_decision` computes `dilution=has_dilution_filing(corp, …)` from the corp frame it **already fetches** — a one-line add to the `CandidateContext`. `veto()` already appends `"dilution / offering / ATM-shelf"` when `ctx.dilution` is true, so vetoed candidates are dropped with the reason surfaced in `key_risks`. Enforcement remains **opt-in** (it runs only inside `screen_decision`, reached via `GuardedPolicy`/`LoopConfig.screen`, both default-off), so the existing suite is untouched.

**Tech Stack:** Python ≥ 3.11, pydantic v2 (frozen `StockSnapshot`), pandas, pytest. Deterministic, offline (`FakeSource`); firewall-clean (`free_float` rides the guarded `daily_snapshot`; the dilution filing read reuses `corporate_actions_known(as_of)`, announce-keyed `<= as_of`).

---

## Context: what's dormant and what activates it

- `alpha/guard/veto.py` — `CandidateContext.dilution: bool = False` (comment "ATM/shelf/offering (US-3)") and `veto()` already appends `"dilution / offering / ATM-shelf"` when it is true. **Zero changes to `veto.py`.** The flag is just never set.
- `alpha/guard/screen.py::screen_decision` (US-3b) already builds a `CandidateContext` per candidate with `ssr` + `reverse_split_pending`, dropping vetoed names and recording reasons in `DecisionPackage.key_risks`. It already fetches `corp = guarded.corporate_actions_known(as_of)` once. US-3d adds `dilution=has_dilution_filing(corp, c.symbol, as_of)` — no new fetch.
- `alpha/data/corp_actions.py` — `has_reverse_split_pending` is the PIT-safe precedent (announce `<= as_of`). US-3d adds the sibling `has_dilution_filing`.
- `alpha/universe/stock.py` — the comment reserves `# float / halts -> None until US-3d / US-3e`. US-3d fills the float half (`free_float`).
- The `dilution_pump` failure-detector seed (`status: active`, trigger "low-float runner with ATM/shelf history") is **already active** and needs no change; `free_float` + the dilution veto reason now give it real substance (low-float context + the surfaced veto).

**Naming:** the field is `free_float` (tradeable float in millions of shares), **not** `float` — avoiding shadowing the `float` builtin and matching the "low-float" / short-interest-%-of-float vocabulary.

**Dilution semantics (MVP, honest):** an ATM/shelf is an open-ended dilution overhang once filed, so `has_dilution_filing` reports **any** dilution-kind filing announced by `as_of` (no `ex_date`/withdrawal-lifecycle modeling — deferred to a real EDGAR feed). This is conservative by design (the threat model: a low-float runner with an active ATM can spike-and-dump on a dilution event); over-vetoing a concluded offering is the accepted MVP trade-off.

## US-3 decomposition status

US-3a runner-tier, US-3b SSR/reverse-split guard-veto, US-3c short-interest/short_squeeze — all DONE. **US-3d = THIS PLAN.** Deferred: **3e** intraday / halts / MWCB (the `halt_then_dump` veto flag); **3f** social / options_flow → `gamma_squeeze` / per-narrative. Also deferred (noted, not built here): a real EDGAR/SEC offerings feed (the offline `FakeSource`/`SnapshotSource`/`PITStore` mechanism + schema are in place — only the ingestion is missing); dilution-filing withdrawal/expiry lifecycle; float-based L3 position sizing; the `going_concern`/`regulatory` veto flags; the live temp=0 LLM verdict run.

---

## File Structure

| File | Change | Responsibility |
|---|---|---|
| `alpha/universe/stock.py` | Modify | Add `free_float: float \| None`; refresh the deferral comment. |
| `alpha/data/source.py` | Modify | Extend `_EMPTY_SNAP` with `free_float` (schema-doc consistency). |
| `alpha/universe/universe.py` | Modify | `build_universe` fills `free_float` via the existing `_opt_float(rec.get(...))`. |
| `alpha/agent/prompt.py` | Modify | `build_user_prompt` renders `float=…M` when `free_float` present. |
| `alpha/data/corp_actions.py` | Modify | `DILUTION_KINDS` + `has_dilution_filing(corp, symbol, as_of)` (announce-keyed, PIT-safe). |
| `alpha/guard/screen.py` | Modify | Import `has_dilution_filing`; add `dilution=…` to the `CandidateContext` in `screen_decision`. |
| `tests/universe/test_build_universe.py` | Modify | `free_float` populated / None when absent. |
| `tests/agent/test_prompt.py` | Modify | `build_user_prompt` renders `float=…M` when present, absent otherwise. |
| `tests/data/test_corp_actions.py` | Modify | `has_dilution_filing` (announced → True; PIT + wrong-kind → False). |
| `tests/guard/test_screen.py` | Modify | `screen_decision` drops a dilution candidate + records the reason. |
| `tests/guard/test_us3d_acceptance.py` | Create | End-to-end: `GuardedPolicy` drops a name with an announced ATM/shelf filing, keeps the clean runner, surfaces the reason. |
| `docs/PROJECT_STATE.md`, `docs/blueprint.md` | Modify | US-3d DONE entry + refreshed roadmap; reconcile the float/dilution doc lines. |

**No `veto.py` change** (the flag + reason already exist). **No new `MarketDataSource` method** (dilution reuses `corporate_actions_known`; `free_float` rides `daily_snapshot`). **No seed change.**

**TDD framing.** All three tasks are genuine red→green (new field, new helper, new wiring). The dilution veto runs only inside `screen_decision` (reached via the opt-in `GuardedPolicy`/`LoopConfig.screen`, default-off), so the existing 351-test suite stays green — verified by a full-suite run after every task.

---

## Task 1: `free_float` field + plumbing + prompt render

**Files:** Modify `alpha/universe/stock.py`, `alpha/data/source.py`, `alpha/universe/universe.py`, `alpha/agent/prompt.py`; Test `tests/universe/test_build_universe.py`, `tests/agent/test_prompt.py`

- [ ] **Step 1: Write the failing tests**

Append to `tests/universe/test_build_universe.py`:

```python
def test_build_universe_populates_free_float():
    cal = [date(2026, 6, 11), date(2026, 6, 12)]
    snaps = {date(2026, 6, 12): pd.DataFrame({
        "symbol": ["LO"], "name": ["LowFloat"], "open": [10.0], "high": [13.0], "low": [10.0],
        "close": [12.0], "volume": [5], "prev_close": [10.0], "free_float": [4.5]})}   # 4.5M float
    src = FakeSource(calendar=cal, bars={}, snapshots=snaps)
    s = build_universe(src, date(2026, 6, 12), gainer_pct=10.0, gap_pct=5.0, rvol_window=2).get("LO")
    assert s.free_float == 4.5


def test_build_universe_free_float_absent_is_none(fake_source):
    s = build_universe(fake_source, date(2026, 6, 12), gainer_pct=10.0, gap_pct=5.0, rvol_window=2).get("RUN")
    assert s.free_float is None        # conftest snapshots have no free_float column -> None, never fabricated
```

Append to `tests/agent/test_prompt.py`:

```python
def test_user_prompt_renders_free_float_when_present():
    state = MarketState(date=date(2026, 6, 12), gainer_count=1, gap_up_count=0, loser_count=0,
                        failed_breakout_count=0, max_runner_tier=1, echelon=[], breadth_raw=1.0,
                        as_of=datetime(2026, 6, 12, 16, 0))
    uni = CandidateUniverse.from_stocks([
        StockSnapshot(symbol="LO", name="Lo", status="gainer", pct_change=20.0, rvol=4.0, free_float=4.0),
        StockSnapshot(symbol="PLAIN", name="Pl", status="gainer", pct_change=12.0, rvol=2.0),
    ])
    up = build_user_prompt(state, uni)
    assert "float=4M" in up                              # low-float name shows the suffix
    plain_line = [ln for ln in up.splitlines() if ln.startswith("- PLAIN")][0]
    assert "float=" not in plain_line                    # no free_float -> no suffix (no noise)
```

- [ ] **Step 2: Run to verify failure**

Run: `python -m pytest tests/universe/test_build_universe.py -k free_float tests/agent/test_prompt.py -k free_float -v`
Expected: FAIL — `StockSnapshot` has no `free_float` field yet (`frozen=True`, pydantic default `extra='ignore'`, so the prompt test's kwarg is silently dropped and `s.free_float` raises `AttributeError`; the universe test asserts a non-existent attribute).

- [ ] **Step 3: Add the field to `alpha/universe/stock.py`**

Replace:

```python
    short_interest: float | None = None    # FINRA short interest as % of float (0-100); US-3c
    days_to_cover: float | None = None      # short shares / avg daily volume; US-3c
    # consecutive_up_days populated by build_universe (US-3a); short_interest/days_to_cover (US-3c);
    # float / halts -> None until US-3d / US-3e
```

with:

```python
    short_interest: float | None = None    # FINRA short interest as % of float (0-100); US-3c
    days_to_cover: float | None = None      # short shares / avg daily volume; US-3c
    free_float: float | None = None         # tradeable float (millions of shares); US-3d
    # consecutive_up_days populated by build_universe (US-3a); short_interest/days_to_cover (US-3c);
    # free_float (US-3d); halts -> None until US-3e
```

- [ ] **Step 4: Extend the snapshot schema in `alpha/data/source.py`**

Replace:

```python
_EMPTY_SNAP = ["symbol", "name", "open", "high", "low", "close", "volume", "prev_close",
               "short_interest", "days_to_cover"]
```

with:

```python
_EMPTY_SNAP = ["symbol", "name", "open", "high", "low", "close", "volume", "prev_close",
               "short_interest", "days_to_cover", "free_float"]
```

- [ ] **Step 5: Populate it in `build_universe`**

In `alpha/universe/universe.py::build_universe`, in the `StockSnapshot(...)` construction, add after `days_to_cover=...`:

```python
            short_interest=_opt_float(rec.get("short_interest")),
            days_to_cover=_opt_float(rec.get("days_to_cover")),
            free_float=_opt_float(rec.get("free_float")),
        )
```

- [ ] **Step 6: Render it in `build_user_prompt`**

In `alpha/agent/prompt.py::build_user_prompt`, extend the per-candidate line block. Change:

```python
        if s.short_interest is not None:                 # squeeze fuel — only shown when data is live
            dtc = f" dtc={s.days_to_cover:.1f}" if s.days_to_cover is not None else ""
            line += f" si={s.short_interest:.0f}%{dtc}"
        lines.append(line)
```

to:

```python
        if s.short_interest is not None:                 # squeeze fuel — only shown when data is live
            dtc = f" dtc={s.days_to_cover:.1f}" if s.days_to_cover is not None else ""
            line += f" si={s.short_interest:.0f}%{dtc}"
        if s.free_float is not None:                      # low-float context (dilution-pump fuel)
            line += f" float={s.free_float:.0f}M"
        lines.append(line)
```

Also in `alpha/agent/prompt.py`, bump the prompt fingerprint (the template changed) — change `PROMPT_FINGERPRINT = "us3c-v1"` to `PROMPT_FINGERPRINT = "us3d-v1"` — and add `free_float` to the `available_data_signals` docstring's example-field list (`... short_interest, days_to_cover, free_float`).

- [ ] **Step 7: Run the tests to verify they pass**

Run: `python -m pytest tests/universe/test_build_universe.py tests/agent/test_prompt.py -v`
Expected: the new tests PASS; existing prompt tests still pass (no `free_float` on their fixtures → no suffix → lines unchanged).

- [ ] **Step 8: Full suite**

Run: `python -m pytest -q`
Expected: 351 + 3 new = 354 green.

- [ ] **Step 9: Commit**

```bash
git add alpha/universe/stock.py alpha/data/source.py alpha/universe/universe.py alpha/agent/prompt.py \
        tests/universe/test_build_universe.py tests/agent/test_prompt.py
git commit -m "US-3d Task 1: free_float on the snapshot + build_universe fill + prompt render"
```

---

## Task 2: `has_dilution_filing` + wire the dilution veto

**Files:** Modify `alpha/data/corp_actions.py`, `alpha/guard/screen.py`; Test `tests/data/test_corp_actions.py`, `tests/guard/test_screen.py`

- [ ] **Step 1: Write the failing tests**

Append to `tests/data/test_corp_actions.py` (it already imports `pd`, `date`, and the corp_actions helpers — mirror the existing `has_reverse_split_pending` test style):

```python
def test_has_dilution_filing_announced_offering():
    from alpha.data.corp_actions import has_dilution_filing
    corp = pd.DataFrame({"symbol": ["DIL"], "announce_date": [date(2026, 6, 9)],
                         "ex_date": [date(2026, 6, 20)], "kind": ["atm"], "ratio": [None]})
    assert has_dilution_filing(corp, "DIL", date(2026, 6, 12)) is True     # announced by as_of -> overhang


def test_has_dilution_filing_pit_and_wrong_kind():
    from alpha.data.corp_actions import has_dilution_filing
    future = pd.DataFrame({"symbol": ["DIL"], "announce_date": [date(2026, 6, 20)],
                           "ex_date": [date(2026, 7, 1)], "kind": ["shelf"], "ratio": [None]})
    assert has_dilution_filing(future, "DIL", date(2026, 6, 12)) is False  # announced AFTER as_of -> unknown
    split = pd.DataFrame({"symbol": ["DIL"], "announce_date": [date(2026, 6, 9)],
                          "ex_date": [date(2026, 6, 20)], "kind": ["reverse_split"], "ratio": [0.1]})
    assert has_dilution_filing(split, "DIL", date(2026, 6, 12)) is False   # not a dilution kind
```

Append to `tests/guard/test_screen.py`:

```python
def test_screen_drops_dilution_candidate_and_records_reason(fake_source):
    # fake_source RUN is a rising gainer (no SSR); attach an announced ATM filing -> dilution veto fires.
    # (pd, date, FakeSource are already imported at module level.)
    snap = fake_source.daily_snapshot(date(2026, 6, 12))
    src = FakeSource(calendar=fake_source.trading_calendar(), bars={},
                     snapshots={date(2026, 6, 12): snap},
                     corp_actions=pd.DataFrame({"symbol": ["RUN"], "announce_date": [date(2026, 6, 9)],
                                                "ex_date": [date(2026, 6, 20)], "kind": ["atm"], "ratio": [None]}))
    out = screen_decision(_pkg("RUN"), source=src, state=_state())
    assert out.candidates == [] and any("RUN" in r and "dilution" in r for r in out.key_risks)
```

- [ ] **Step 2: Run to verify failure**

Run: `python -m pytest tests/data/test_corp_actions.py -k dilution tests/guard/test_screen.py -k dilution -v`
Expected: FAIL — `ImportError: cannot import name 'has_dilution_filing'` / `screen_decision` does not yet set `dilution`.

- [ ] **Step 3: Add `has_dilution_filing` to `alpha/data/corp_actions.py`**

After `has_reverse_split_pending`, add:

```python
DILUTION_KINDS = ("atm", "shelf", "offering")   # ATM program / shelf registration / secondary offering


def has_dilution_filing(corp: pd.DataFrame, symbol: str, as_of: Date) -> bool:
    """True iff a dilution filing (ATM / shelf / secondary offering) for `symbol` is announced by as_of.

    Unlike a reverse split (a scheduled event gated on ex_date), an ATM/shelf is an open-ended dilution
    overhang once filed, so this reports ANY announced dilution-kind filing (withdrawal/expiry lifecycle
    is deferred to a real EDGAR feed). PIT-safe: keyed on announce_date <= as_of via known_corporate_actions."""
    known = known_corporate_actions(corp, as_of)
    if known.empty:
        return False
    dil = known[(known["symbol"] == symbol) & (known["kind"].isin(DILUTION_KINDS))]
    return not dil.empty
```

- [ ] **Step 4: Wire it into `screen_decision`**

In `alpha/guard/screen.py`, extend the import:

```python
from alpha.data.corp_actions import has_dilution_filing, has_reverse_split_pending
```

In `screen_decision`, add the `dilution` flag to the `CandidateContext` (reusing the already-fetched `corp`):

```python
        ctx = CandidateContext(symbol=c.symbol, regime=regime,
                               ssr=ssr_active(guarded, c.symbol, as_of),
                               reverse_split_pending=has_reverse_split_pending(corp, c.symbol, as_of),
                               dilution=has_dilution_filing(corp, c.symbol, as_of))
```

- [ ] **Step 5: Run the tests to verify they pass**

Run: `python -m pytest tests/data/test_corp_actions.py tests/guard/test_screen.py -v`
Expected: all PASS (new dilution tests + the existing reverse-split/SSR/screen contracts unchanged).

- [ ] **Step 6: Full suite**

Run: `python -m pytest -q`
Expected: 354 + 3 new = 357 green.

- [ ] **Step 7: Commit**

```bash
git add alpha/data/corp_actions.py alpha/guard/screen.py tests/data/test_corp_actions.py tests/guard/test_screen.py
git commit -m "US-3d Task 2: has_dilution_filing (ATM/shelf/offering, PIT-by-announce) + wire the dilution veto into screen_decision"
```

---

## Task 3: US-3d acceptance gate + docs

**Files:** Create `tests/guard/test_us3d_acceptance.py`; Modify `docs/PROJECT_STATE.md`, `docs/blueprint.md`

- [ ] **Step 1: Write the acceptance test**

Create `tests/guard/test_us3d_acceptance.py`:

```python
"""US-3d acceptance: the L4 hard veto, wired via GuardedPolicy, enforces the dilution guard on a FRONTSIDE
regime — it drops a name with an announced ATM/shelf offering (open-ended dilution overhang), keeps the
clean low-float runner, surfaces the reason in key_risks, and renders free_float in the agent prompt.
Headline US-3d guarantee: float is live on the snapshot and the dormant dilution veto now fires on real
(PIT-by-announce) offering filings."""
from datetime import date, datetime
import pandas as pd
from alpha.data.source import FakeSource
from alpha.state.market import MarketState
from alpha.eval.decision import Candidate, DecisionPackage
from alpha.universe.universe import build_universe, CandidateUniverse
from alpha.state.builder import build_market_state
from alpha.agent.prompt import build_user_prompt
from alpha.guard.screen import GuardedPolicy

CUR = date(2026, 6, 12)


def _source():
    cal = [date(2026, 6, 11), CUR]
    snap = pd.DataFrame({
        "symbol": ["CLEAN", "DILUTE"], "name": ["Clean", "Diluter"],
        "open": [10.0, 10.0], "high": [13.0, 13.0], "low": [10.0, 10.0],
        "close": [12.0, 12.0], "volume": [5, 5], "prev_close": [10.0, 10.0],
        "free_float": [3.0, 4.0]})                                          # both low-float gainers (+20%)
    corp = pd.DataFrame({"symbol": ["DILUTE"], "announce_date": [date(2026, 6, 9)],
                         "ex_date": [date(2026, 6, 20)], "kind": ["shelf"], "ratio": [None]})
    return FakeSource(calendar=cal, bars={}, snapshots={CUR: snap}, corp_actions=corp)


def _frontside_state():
    return MarketState(date=CUR, gainer_count=2, gap_up_count=0, loser_count=0, failed_breakout_count=0,
                       max_runner_tier=1, echelon=[], breadth_raw=2.0, sentiment_norm=0.7,
                       follow_through_rate=0.5, as_of=datetime(2026, 6, 12, 16, 0))


class _StubPolicy:
    def decide(self, state, universe):
        return DecisionPackage(date=CUR, candidates=[Candidate(symbol=s, pattern="gap_and_go")
                                                     for s in ("CLEAN", "DILUTE")])


def test_guard_enforces_dilution_on_frontside():
    src = _source()
    out = GuardedPolicy(_StubPolicy(), src).decide(_frontside_state(), CandidateUniverse.from_stocks([]))
    assert [c.symbol for c in out.candidates] == ["CLEAN"]                  # the dilution name is dropped
    assert out.regime is not None and out.regime.frontside is True
    assert any("DILUTE" in r and "dilution" in r for r in out.key_risks)   # reason surfaced
    # float is live on the snapshot + rendered in the agent prompt
    uni = build_universe(src, CUR, gainer_pct=10.0, gap_pct=5.0, rvol_window=2)
    assert uni.get("CLEAN").free_float == 3.0
    state = build_market_state(uni, CUR, as_of=datetime(2026, 6, 12, 16, 0))
    assert "float=3M" in build_user_prompt(state, uni)
```

- [ ] **Step 2: Run the acceptance test**

Run: `python -m pytest tests/guard/test_us3d_acceptance.py -v`
Expected: PASS.

- [ ] **Step 3: Full suite**

Run: `python -m pytest -q`
Expected: all green; record the exact count (expected 358 = 351 + 7 new: Task1 +3, Task2 +3, Task3 +1). Use whatever the run reports for the PROJECT_STATE edit.

- [ ] **Step 4: Update `docs/PROJECT_STATE.md`**

Replace the header `Last updated` line (line 4). Old (verbatim):

```markdown
> Last updated: 2026-06-15 (US-0 + US-1 + US-2 complete; US-3a runner-tier + US-3b guard-veto + US-3c short-interest/short_squeeze shipped; US-3d next).
```

New:

```markdown
> Last updated: 2026-06-15 (US-0 + US-1 + US-2 complete; US-3a runner-tier + US-3b guard-veto + US-3c short-interest + US-3d float/dilution-veto shipped; US-3e next).
```

Insert, immediately after the US-3c paragraph (the block ending "Full suite **351 tests green**.") and before the "Next — US-3d → US-3f" paragraph:

```markdown
**US-3d Float + dilution-veto activation — Complete (2026-06-15). The dormant dilution guard is live.**
`StockSnapshot` gains `free_float` (tradeable float, millions of shares), filled at the `build_universe`
chokepoint from the daily snapshot (US-3c data-on-snapshot pattern; real source deferred) and rendered as
`float=…M` in the agent prompt (low-float / dilution-pump context). The L4 `dilution` veto — present in
`veto()` but never set — is **activated**: a new `corp_actions.has_dilution_filing(corp, symbol, as_of)`
(the US-3b reverse-split pattern: PIT-by-announce over `kind ∈ {atm, shelf, offering}`, reusing
`known_corporate_actions`/`corporate_actions_known`) is computed in `screen_decision` from the corp frame it
already fetches, so a candidate with an announced ATM/shelf/offering is dropped with `"dilution / offering /
ATM-shelf"` surfaced in `key_risks`. Conservative MVP: any announced dilution filing vetoes (open-ended
overhang; ex_date/withdrawal lifecycle deferred to a real EDGAR feed). Enforcement stays opt-in via
`GuardedPolicy`/`LoopConfig.screen` (default-off), so the suite is untouched. Acceptance-tested end-to-end on
a frontside regime. Full suite **358 tests green**.

**Next — US-3e → US-3f (deferred roadmap):** **3e** intraday / halts / MWCB
```

(That last line replaces the start of the existing `**Next — US-3d → US-3f (deferred roadmap):** **3d** float / dilution / EDGAR → the guard's \`dilution\` veto. **3e** intraday / halts / MWCB` sentence — drop the `**3d** …` clause, stopping exactly before `**3e**`.)

Finally, in the "Other deferred" sentence of that paragraph, add: *a real EDGAR/SEC offerings feed (the offline corp-actions dilution mechanism + schema are in place) and the dilution-filing withdrawal/expiry lifecycle; float-based L3 sizing.*

- [ ] **Step 5: Reconcile `docs/blueprint.md`**

Find the float / dilution / offering lines in `docs/blueprint.md` (grep `dilution` / `float` / `offering` / `ATM`). Update any "(US-3)" / deferred framing for float and the dilution flag to note they are wired in US-3d (`free_float` on the snapshot; the `dilution` veto fires on PIT-by-announce ATM/shelf/offering corp-action filings; real EDGAR feed deferred). Keep the edit to the one or two stale cells/lines; do not rewrite unrelated content.

- [ ] **Step 6: Commit**

```bash
git add tests/guard/test_us3d_acceptance.py docs/PROJECT_STATE.md docs/blueprint.md
git commit -m "US-3d Task 3: acceptance gate (dilution veto fires on announced ATM/shelf) + PROJECT_STATE/blueprint"
```

---

## Self-Review

**1. Spec coverage.** Float delivered (`free_float` on the snapshot, filled in `build_universe`, rendered in the prompt). Dilution veto activated (Task 2): `has_dilution_filing` (PIT-by-announce) + the one-line `screen_decision` wiring; the `veto()` branch already fires. Acceptance-tested end-to-end (Task 3). Deferred items (real EDGAR feed, withdrawal lifecycle, `going_concern`/`regulatory`, float-based sizing, `halt_then_dump` → US-3e) correctly out of scope.

**2. Placeholder scan.** Every step has literal code + a runnable command + expected outcome, except Task 3 Step 5 (blueprint), a bounded grep-then-edit of the float/dilution cell(s).

**3. Type/contract consistency.** `free_float: float | None` matches the `short_interest`/`days_to_cover` pattern (frozen model, None default, `_opt_float` None/NaN-safe). `has_dilution_filing(corp, symbol, as_of) -> bool` mirrors `has_reverse_split_pending`. `screen_decision` reuses the already-fetched `corp` frame (no extra fetch); `CandidateContext.dilution` and the `veto()` reason already exist (no `veto.py` change). Field named `free_float`, not `float` (no builtin shadowing).

**4. Firewall.** `free_float` rides the already-guarded `daily_snapshot`; the dilution read reuses `corporate_actions_known(as_of)` (announce-keyed `<= as_of`, `GuardedSource`-checked) — the Task-2 PIT test asserts a filing announced *after* `as_of` does not fire. No new fetch, no new firewall edge.

**5. Blast radius / honesty.** The dilution veto runs only inside `screen_decision` (reached via the opt-in `GuardedPolicy`/`LoopConfig.screen`, default-off), so the 351-test suite stays green. The `_EMPTY_SNAP` extension matches US-3c precedent (additive, no test broke). The honest framing — **activation = data + PIT filing signal + the already-present veto branch; real EDGAR ingestion + withdrawal lifecycle deferred; conservative any-announced-filing MVP** — is carried in code comments, the plan, and PROJECT_STATE, consistent with US-3a/3b/3c activating mechanisms without overclaiming.
