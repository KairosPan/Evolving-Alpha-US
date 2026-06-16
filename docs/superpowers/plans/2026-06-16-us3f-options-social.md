# US-3f Options-Flow + Social Sentiment → gamma_squeeze Activation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add `options_flow` and `social_sentiment` to the daily snapshot (rendered in the agent prompt). Adding `options_flow` (a None-default field whose name matches `gamma_squeeze.depends_on`) **auto-activates** the last incubating offense seed, `gamma_squeeze`, through the generic `depends_on` enforcement US-3c already shipped — **no machinery or seed change**. `social_sentiment` is rendered context for the already-active `social_euphoria_top`. This closes the US-3 enrichment arc; per-narrative-line phase tagging is the remaining (deferred) big piece.

**Architecture:** US-3c built a *generic* data-dependency gate: `available_data_signals(universe)` collects optional (None-default) `StockSnapshot` field names that are non-None for ≥1 candidate, and `build_system_prompt` (fed by `decide`) surfaces a skill only when its `depends_on` ⊆ those signals. So a skill is activated purely by adding a snapshot field whose name equals its `depends_on` entry. `gamma_squeeze` declares `depends_on: ["options_flow"]`; adding an `options_flow` field (None default, filled in `build_universe`) makes it a live signal on options-flow days → `gamma_squeeze` surfaces, otherwise stays hidden. `social_euphoria_top` is `active` with **no** `depends_on`, so `social_sentiment` is just a rendered signal (the US-3d `free_float` pattern). Both fields flow via the established `_opt_float(rec.get(...))` path; `gamma_squeeze` **stays `incubating`** (evidence-gated promotion, like `short_squeeze`). Enforcement runs on the live `decide` path (existing); the data is opt-in by presence (absent on existing fixtures → no change).

**Tech Stack:** Python ≥ 3.11, pydantic v2 (frozen `StockSnapshot`), pandas, pytest. Deterministic, offline (`FakeSource`); firewall-clean (both fields ride the already-guarded `daily_snapshot`).

---

## Context: what's dormant, what auto-activates, what's deferred

- `seeds/skills.json` — `gamma_squeeze` (meme, `pattern`, `incubating`, `depends_on: ["options_flow"]`) and `social_euphoria_top` (meme, `failure_detector`, **`active`, no `depends_on`**). **No seed change in US-3f.**
- `alpha/agent/prompt.py` — `available_data_signals` + `_depends_on_satisfied` + the `build_system_prompt` filter (US-3c) are **generic**: they already enforce *any* skill's `depends_on` against the live snapshot fields. Verified: an `options_flow` field with a None default, non-None for a candidate, lands in `available_data_signals` and satisfies `gamma_squeeze.depends_on` → it surfaces. **Zero machinery change.**
- `alpha/universe/stock.py` — `StockSnapshot` carries the US-3a/3c/3d enrichments; `options_flow`/`social_sentiment` not yet added.
- `tests/seeds/test_seed_packs.py::test_squeeze_offense_is_incubating` pins both squeezes `incubating` — US-3f does not change status (only data-gated visibility), so it stays green.

**What US-3f ships:** the `options_flow` field (auto-activates `gamma_squeeze`) + the `social_sentiment` field (rendered context) + their prompt render. **What it honestly defers:**
- **Per-narrative-line phase tagging** — a separate big architecture piece: narrative classification of candidates (the `narrative` field on `Pick`/`SizedPick` is supplied upstream, not derived), a per-narrative `RegimeRead`, and narrative-aware phase clustering in `GCycle` (today's `GCycle.read` returns one GLOBAL phase). Not built; deferred to a later slice.
- **Real options-flow / social feeds** — the offline `FakeSource`/`SnapshotSource`/`PITStore` mechanism + schema are in place; real ingestion (an options-flow vendor, a social-sentiment source) is deferred, exactly as the FINRA short-interest feed was for US-3c.

## US-3 decomposition status

US-3a runner-tier, US-3b SSR/reverse-split guard-veto, US-3c short-interest/short_squeeze, US-3d float/dilution-veto, US-3e halt-then-dump — all DONE. **US-3f = THIS PLAN** — options_flow → `gamma_squeeze` + social_sentiment. With it, **the US-3 daily-cadence enrichment arc is complete** (every seed offense skill is now data-backed; the four guard-veto data flags + runner-tier + squeeze pair are live). Remaining (orthogonal / deferred): per-narrative phase tagging; the richer `features/builder` live-loop wiring (unlocks `LoopConfig.screen` default-on + symmetric `GuardedPolicy` on `compare_harnesses` arms); the live temp=0 LLM verdict run; the various intraday/EDGAR/FINRA real feeds.

---

## File Structure

| File | Change | Responsibility |
|---|---|---|
| `alpha/universe/stock.py` | Modify | Add `options_flow: float \| None` + `social_sentiment: float \| None`; refresh the deferral comment. |
| `alpha/data/source.py` | Modify | Extend `_EMPTY_SNAP` with `options_flow`, `social_sentiment` (schema doc). |
| `alpha/universe/universe.py` | Modify | `build_universe` fills both via `_opt_float(rec.get(...))`. |
| `alpha/agent/prompt.py` | Modify | `build_user_prompt` renders `optflow=…`/`social=…` when present; bump `PROMPT_FINGERPRINT` → `us3f-v1`; add the two fields to the `available_data_signals` docstring list. |
| `tests/universe/test_build_universe.py` | Modify | `options_flow`/`social_sentiment` populated / None when absent. |
| `tests/agent/test_prompt.py` | Modify | `build_user_prompt` renders `optflow=`/`social=` when present; **lock** that `gamma_squeeze` surfaces when `options_flow` ∈ signals (and is hidden without). |
| `tests/eval/test_us3f_acceptance.py` | Create | End-to-end: a universe carrying `options_flow` surfaces `gamma_squeeze` (depends_on satisfied), `short_squeeze` stays hidden (no short data); an absent-options universe hides `gamma_squeeze`. |
| `docs/PROJECT_STATE.md`, `docs/blueprint.md` | Modify | US-3f DONE entry + "US-3 enrichment arc complete"; refreshed roadmap; reconcile the options/social/squeeze doc lines. |

**No `seeds/skills.json` change** (`gamma_squeeze` already has the right `depends_on` + `incubating`). **No depends_on-machinery change** (US-3c's `available_data_signals`/`_depends_on_satisfied`/`build_system_prompt`/`decide` are generic and reused as-is). **No `veto.py`/`screen.py` change** (US-3f is offense-skill activation, not a guard veto).

**TDD framing.** Task 1 is genuine red→green (new fields). Task 2 is mostly **activation locks** (tests that assert the *automatic* `depends_on` activation now reaches `gamma_squeeze`) + acceptance + docs — no new production logic (the machinery already activates it once the field exists). The data is absent on existing fixtures, so the 361-test suite stays green — verified by a full-suite run after every task.

---

## Task 1: `options_flow` + `social_sentiment` fields + plumbing + prompt render

**Files:** Modify `alpha/universe/stock.py`, `alpha/data/source.py`, `alpha/universe/universe.py`, `alpha/agent/prompt.py`; Test `tests/universe/test_build_universe.py`, `tests/agent/test_prompt.py`

- [ ] **Step 1: Write the failing tests**

Append to `tests/universe/test_build_universe.py`:

```python
def test_build_universe_populates_options_flow_and_social():
    cal = [date(2026, 6, 11), date(2026, 6, 12)]
    snaps = {date(2026, 6, 12): pd.DataFrame({
        "symbol": ["MEME"], "name": ["Memer"], "open": [10.0], "high": [13.0], "low": [10.0],
        "close": [12.0], "volume": [5], "prev_close": [10.0],
        "options_flow": [3.5], "social_sentiment": [0.8]})}                 # +20% gainer w/ heavy call flow
    src = FakeSource(calendar=cal, bars={}, snapshots=snaps)
    s = build_universe(src, date(2026, 6, 12), gainer_pct=10.0, gap_pct=5.0, rvol_window=2).get("MEME")
    assert s.options_flow == 3.5 and s.social_sentiment == 0.8


def test_build_universe_options_flow_absent_is_none(fake_source):
    s = build_universe(fake_source, date(2026, 6, 12), gainer_pct=10.0, gap_pct=5.0, rvol_window=2).get("RUN")
    assert s.options_flow is None and s.social_sentiment is None   # conftest snapshots lack the columns -> None
```

Append to `tests/agent/test_prompt.py`:

```python
def test_user_prompt_renders_options_flow_and_social_when_present():
    state = MarketState(date=date(2026, 6, 12), gainer_count=1, gap_up_count=0, loser_count=0,
                        failed_breakout_count=0, max_runner_tier=1, echelon=[], breadth_raw=1.0,
                        as_of=datetime(2026, 6, 12, 16, 0))
    uni = CandidateUniverse.from_stocks([
        StockSnapshot(symbol="MEME", name="Me", status="gainer", pct_change=20.0, rvol=4.0,
                      options_flow=3.5, social_sentiment=0.8),
        StockSnapshot(symbol="PLAIN", name="Pl", status="gainer", pct_change=12.0, rvol=2.0),
    ])
    up = build_user_prompt(state, uni)
    assert "optflow=3.5" in up and "social=0.8" in up      # meme name shows the suffixes
    plain_line = [ln for ln in up.splitlines() if ln.startswith("- PLAIN")][0]
    assert "optflow=" not in plain_line and "social=" not in plain_line   # no data -> no suffix (no noise)
```

- [ ] **Step 2: Run to verify failure**

Run: `python -m pytest tests/universe/test_build_universe.py -k "options_flow" tests/agent/test_prompt.py -k "options_flow" -v`
Expected: FAIL — `StockSnapshot` has no `options_flow`/`social_sentiment` fields yet (`frozen=True`, pydantic default `extra='ignore'` → the prompt test's kwargs are silently dropped and `s.options_flow` raises `AttributeError`; the universe test asserts a non-existent attribute).

- [ ] **Step 3: Add the fields to `alpha/universe/stock.py`**

Replace:

```python
    free_float: float | None = None         # tradeable float (millions of shares); US-3d
    # consecutive_up_days populated by build_universe (US-3a); short_interest/days_to_cover (US-3c);
    # free_float (US-3d); halts -> None until US-3e
```

with:

```python
    free_float: float | None = None         # tradeable float (millions of shares); US-3d
    options_flow: float | None = None       # net near-the-money call-flow score (gamma fuel); US-3f
    social_sentiment: float | None = None   # social-sentiment score; US-3f
    # consecutive_up_days populated by build_universe (US-3a); short_interest/days_to_cover (US-3c);
    # free_float (US-3d); options_flow/social_sentiment (US-3f); intraday halts -> None until a tick feed
```

- [ ] **Step 4: Extend the snapshot schema in `alpha/data/source.py`**

Replace:

```python
_EMPTY_SNAP = ["symbol", "name", "open", "high", "low", "close", "volume", "prev_close",
               "short_interest", "days_to_cover", "free_float"]
```

with:

```python
_EMPTY_SNAP = ["symbol", "name", "open", "high", "low", "close", "volume", "prev_close",
               "short_interest", "days_to_cover", "free_float", "options_flow", "social_sentiment"]
```

- [ ] **Step 5: Populate the fields in `build_universe`**

In `alpha/universe/universe.py::build_universe`, in the `StockSnapshot(...)` construction, add after `free_float=...`:

```python
            short_interest=_opt_float(rec.get("short_interest")),
            days_to_cover=_opt_float(rec.get("days_to_cover")),
            free_float=_opt_float(rec.get("free_float")),
            options_flow=_opt_float(rec.get("options_flow")),
            social_sentiment=_opt_float(rec.get("social_sentiment")),
        )
```

- [ ] **Step 6: Render the fields + bump fingerprint + docstring in `alpha/agent/prompt.py`**

In `build_user_prompt`, extend the per-candidate line block. Change:

```python
        if s.free_float is not None:                      # low-float context (dilution-pump fuel)
            line += f" float={s.free_float:.0f}M"
        lines.append(line)
```

to:

```python
        if s.free_float is not None:                      # low-float context (dilution-pump fuel)
            line += f" float={s.free_float:.0f}M"
        if s.options_flow is not None:                    # gamma fuel (near-the-money call flow)
            line += f" optflow={s.options_flow:.1f}"
        if s.social_sentiment is not None:                # social-euphoria context
            line += f" social={s.social_sentiment:.1f}"
        lines.append(line)
```

Bump the fingerprint: change `PROMPT_FINGERPRINT = "us3d-v1"` to `PROMPT_FINGERPRINT = "us3f-v1"`. And add the two fields to the `available_data_signals` docstring's example list (`... free_float, options_flow, social_sentiment`).

- [ ] **Step 7: Run the tests to verify they pass**

Run: `python -m pytest tests/universe/test_build_universe.py tests/agent/test_prompt.py -v`
Expected: the new tests PASS; existing prompt tests still pass (no `options_flow`/`social_sentiment` on their fixtures → no suffix → lines unchanged).

- [ ] **Step 8: Full suite**

Run: `python -m pytest -q`
Expected: 361 + 3 new = 364 green (additive fields; conditional suffixes).

- [ ] **Step 9: Commit**

```bash
git add alpha/universe/stock.py alpha/data/source.py alpha/universe/universe.py alpha/agent/prompt.py \
        tests/universe/test_build_universe.py tests/agent/test_prompt.py
git commit -m "US-3f Task 1: options_flow + social_sentiment on the snapshot + build_universe fill + prompt render"
```

---

## Task 2: lock the `gamma_squeeze` auto-activation + acceptance + docs

**Files:** Modify `tests/agent/test_prompt.py`; Create `tests/eval/test_us3f_acceptance.py`; Modify `docs/PROJECT_STATE.md`, `docs/blueprint.md`

No production code here — `gamma_squeeze` is activated automatically by the US-3c machinery once Task 1's `options_flow` field exists. Task 2 *locks* that behavior and documents it.

- [ ] **Step 1: Write the gamma_squeeze activation lock test**

Append to `tests/agent/test_prompt.py` (the `_h_squeeze()` helper from US-3c builds a harness with `short_squeeze` + `gamma_squeeze`; reuse it):

```python
def test_depends_on_enforced_shows_gamma_squeeze_with_options_flow():
    sp = build_system_prompt(_h_squeeze(), phase_prior="trend", injection="full",
                             available_signals=frozenset({"options_flow"}))
    assert "gamma_squeeze" in sp                          # options_flow live -> gamma_squeeze surfaces
    assert "short_squeeze" not in sp                      # short_interest/days_to_cover absent -> hidden
```

- [ ] **Step 2: Run it (lock confirmation)**

Run: `python -m pytest tests/agent/test_prompt.py -k "gamma_squeeze" -v`
Expected: PASS (Task 1 added no new machinery, but `_h_squeeze`'s `gamma_squeeze` declares `depends_on=["options_flow"]`, so the existing filter surfaces it once `options_flow` is in the signal set). Had `gamma_squeeze.depends_on` not been satisfiable this would fail.

- [ ] **Step 3: Write the acceptance test**

Create `tests/eval/test_us3f_acceptance.py`:

```python
"""US-3f acceptance: options-flow data activates the dormant gamma_squeeze seed (the last incubating offense
skill). On a universe carrying options_flow, build_universe fills the field, the agent's user prompt shows
optflow=, and the system prompt SURFACES gamma_squeeze (its depends_on is now satisfied) while short_squeeze
stays hidden (no short-interest data). On a universe WITHOUT options_flow, gamma_squeeze is hidden. This
closes the US-3 enrichment arc: every incubating offense seed is now data-backed (activation via the generic
depends_on machinery; promotion to active stays evidence-gated)."""
from datetime import date, datetime
from pathlib import Path
import pandas as pd
from alpha.data.source import FakeSource
from alpha.harness.loader import load_seeds
from alpha.universe.universe import build_universe
from alpha.state.builder import build_market_state
from alpha.agent.prompt import build_system_prompt, build_user_prompt, available_data_signals

SEEDS = Path(__file__).resolve().parents[2] / "seeds"
CUR = date(2026, 6, 12)


def _source(*, with_options: bool):
    cal = [date(2026, 6, 11), CUR]
    cols = {"symbol": ["MEME"], "name": ["Memer"], "open": [10.0], "high": [13.0], "low": [10.0],
            "close": [12.0], "volume": [5], "prev_close": [10.0]}                      # +20% gainer
    if with_options:
        cols |= {"options_flow": [4.0], "social_sentiment": [0.9]}
    return FakeSource(calendar=cal, bars={}, snapshots={CUR: pd.DataFrame(cols)})


def _sys_prompt_for(src):
    uni = build_universe(src, CUR, gainer_pct=10.0, gap_pct=5.0, rvol_window=2)
    return build_system_prompt(load_seeds(SEEDS), phase_prior="ignition",
                               available_signals=available_data_signals(uni)), uni


def test_options_flow_activates_gamma_squeeze_end_to_end():
    sp, uni = _sys_prompt_for(_source(with_options=True))
    assert uni.get("MEME").options_flow == 4.0 and uni.get("MEME").social_sentiment == 0.9
    assert "gamma_squeeze" in sp                          # depends_on=[options_flow] satisfied -> surfaced
    assert "short_squeeze" not in sp                      # short-interest absent -> still hidden
    state = build_market_state(uni, CUR, as_of=datetime(2026, 6, 12, 16, 0))
    assert "optflow=4.0" in build_user_prompt(state, uni)   # the agent sees the gamma fuel


def test_without_options_flow_gamma_squeeze_stays_dormant():
    sp, uni = _sys_prompt_for(_source(with_options=False))
    assert uni.get("MEME").options_flow is None
    assert "gamma_squeeze" not in sp                      # no data -> depends_on unsatisfied -> hidden
```

- [ ] **Step 4: Run the acceptance test + full suite**

Run: `python -m pytest tests/eval/test_us3f_acceptance.py -v && python -m pytest -q`
Expected: acceptance PASSES; full suite all green; record the exact count (expected 367 = 361 + 6 new: Task1 +3, Task2 +3). Use whatever the run reports for the PROJECT_STATE edit.

- [ ] **Step 5: Update `docs/PROJECT_STATE.md`**

Replace the header `Last updated` line (line 4). Old (verbatim):

```markdown
> Last updated: 2026-06-15 (US-0 + US-1 + US-2 complete; US-3a–US-3e shipped (runner-tier, guard-veto, short-interest, dilution, halt-then-dump); US-3f next).
```

New:

```markdown
> Last updated: 2026-06-16 (US-0 + US-1 + US-2 complete; US-3a–US-3f shipped — the US-3 daily-cadence enrichment arc is complete; next: per-narrative + the live temp=0 verdict run).
```

Insert, immediately after the US-3e paragraph (the block ending "Full suite **361 tests green**.") and before the "Next — US-3f" paragraph:

```markdown
**US-3f Options-flow + social → gamma_squeeze activation — Complete (2026-06-16). The US-3 enrichment arc is closed.**
`StockSnapshot` gains `options_flow` (near-the-money call-flow score) + `social_sentiment`, filled at the
`build_universe` chokepoint from the daily snapshot (US-3c data-on-snapshot pattern; real feeds deferred) and
rendered as `optflow=…`/`social=…` in the agent prompt. Adding `options_flow` (a None-default field whose name
matches `gamma_squeeze.depends_on`) **auto-activates** the last incubating offense seed, `gamma_squeeze`,
through the **generic** `depends_on` enforcement built in US-3c (`available_data_signals` + `_depends_on_satisfied`
+ the `build_system_prompt` filter, fed by `decide`) — **no machinery or seed change**: on an options-flow day
`gamma_squeeze` surfaces to the agent; otherwise it stays hidden (as does `short_squeeze` without short data).
`social_euphoria_top` is `active`/no-`depends_on`, so `social_sentiment` is rendered context (US-3d `free_float`
pattern). `gamma_squeeze` **stays `incubating`** — promotion to `active` is evidence-gated (lifecycle discipline;
`test_squeeze_offense_is_incubating` pins it). With this, **every US-3 daily-cadence enrichment is live**:
runner-tier (3a), the four guard-veto data flags — SSR/reverse-split (3b), dilution (3d), halt-then-dump (3e) —
short_squeeze (3c) and gamma_squeeze (3f). Full suite **367 tests green**. **Honestly deferred:** real
options-flow / social feeds (offline mechanism + schema in place); per-narrative-line phase tagging (a separate
architecture piece — narrative clustering + a per-line regime read; today's `GCycle` returns one global phase).
```

(The inserted block ends at "...one global phase)." — it does NOT add a new "Next" line.)

Then, as a SEPARATE clean edit, rewrite the lead of the existing "Next" paragraph. Find the verbatim substring (read the file first to confirm exact wording):

```
**Next — US-3f (deferred roadmap):** **3f** social / options (gamma squeeze) / per-narrative phase tagging. Plus, **orthogonal to US-3**:
```

and replace it with (keeping everything from the live-temp=0/verdict sentence onward unchanged):

```
**Next (orthogonal to the enrichment arc):**
```

(Net effect: the now-done `**3f**` clause is dropped and the paragraph opens directly with the orthogonal live-LLM-verdict sentence; per-narrative is already captured in the US-3f deferral note above.)

Finally, in the "Other deferred" sentence, append: *real options-flow / social-sentiment feeds; per-narrative-line phase tagging (narrative clustering + per-line regime read).*

- [ ] **Step 6: Reconcile `docs/blueprint.md`**

Grep `gamma` / `options` / `social` / `squeeze` / `per-narrative` / `narrative` in `docs/blueprint.md`. Update the meme/squeeze family row (US-3c updated the short_squeeze cell) to note **gamma_squeeze is data-backed/activated in US-3f** (options_flow on the snapshot → `depends_on`-gated, incubating pending evidence) and **social_sentiment is live**, with **per-narrative-line phase tagging** the remaining deferred piece. Keep the edit to the one or two relevant cells; do not rewrite unrelated content.

- [ ] **Step 7: Commit**

```bash
git add tests/agent/test_prompt.py tests/eval/test_us3f_acceptance.py docs/PROJECT_STATE.md docs/blueprint.md
git commit -m "US-3f Task 2: lock gamma_squeeze auto-activation + acceptance gate + PROJECT_STATE/blueprint (US-3 arc complete)"
```

---

## Self-Review

**1. Spec coverage.** `options_flow` (auto-activates `gamma_squeeze` via the existing generic `depends_on` machinery — verified the field-name match and that `decide`→`available_data_signals`→`build_system_prompt` surfaces it) + `social_sentiment` (rendered context for the active `social_euphoria_top`) delivered (Task 1), with the activation locked (Task 2 prompt test) + acceptance-tested end-to-end. Per-narrative-line phase tagging + real feeds correctly deferred with the dependency named.

**2. Placeholder scan.** Every step has literal code + a runnable command + expected outcome, except Task 2 Step 6 (blueprint), a bounded grep-then-edit of the meme/squeeze cell(s).

**3. Type/contract consistency.** `options_flow`/`social_sentiment: float | None` match the `short_interest`/`free_float` pattern (frozen model, None default, `_opt_float` None/NaN-safe). `options_flow` name == `gamma_squeeze.depends_on` entry (the activation hinge). No `Skill`/`depends_on`-machinery/`veto`/`screen` change. `build_system_prompt(..., available_signals=…)`, `available_data_signals(universe)`, `_depends_on_satisfied(skill, signals)` all reused unchanged.

**4. Firewall.** Both fields ride the already-guarded `daily_snapshot`; no new fetch or firewall edge. `gamma_squeeze` visibility is computed per-decision from the live universe (no lookahead).

**5. Blast radius / honesty.** The two fields are absent on every existing fixture → `available_data_signals` is unchanged there → `gamma_squeeze` stays hidden on the live `decide` path exactly as before (MockLLM ignores the prompt anyway), so the 361-test suite stays green; `test_squeeze_offense_is_incubating` still holds (status unchanged). `_EMPTY_SNAP` extension matches the US-3c/3d precedent (additive). The honest framing — **activation = the field + the generic depends_on machinery; promotion to `active` stays evidence-gated; per-narrative + real feeds deferred** — is carried in code comments, the plan, and PROJECT_STATE, and US-3f explicitly marks the **US-3 enrichment arc complete** without overclaiming the deferred intraday/feed/narrative work.
