# US-3c Short-Interest Enrichment + short_squeeze Activation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Supply FINRA short-interest data (`short_interest` % of float + `days_to_cover`) onto the daily snapshot/universe, render it in the agent prompt, and **activate** the dormant `short_squeeze` seed by enforcing its currently-decorative `depends_on` gate — so the skill surfaces to the agent exactly when its data is live, while promotion to `active` status stays evidence-gated.

**Architecture:** Two computable per-symbol attributes ride on the daily snapshot DataFrame (the US-3a pattern — a field on the snapshot, not a separate PIT method like US-3b's corp-actions, because short interest is slowly-changing dimensional data, not a dual-dated event). They are filled at the single `build_universe` chokepoint into new `StockSnapshot` fields. The "activation" is enforcing `Skill.depends_on` (today loaded but never checked): a skill is rendered to the agent only when every name in its `depends_on` is a data signal present in the day's universe. `short_squeeze.depends_on = ["short_interest", "days_to_cover"]`, so it appears precisely on days with short-interest data; `gamma_squeeze.depends_on = ["options_flow"]` stays correctly hidden until US-3f. Enforcement is wired on the live `decide()` path (which always supplies the available-signals set) and is back-compatible elsewhere (default `None` = no enforcement), so the existing suite is untouched. `short_squeeze` **stays `incubating`** — promotion to `active` is earned via Refiner evidence on a live run, not declared (the project's lifecycle discipline; `test_squeeze_offense_is_incubating` pins this).

**Tech Stack:** Python ≥ 3.11, pydantic v2 (frozen `StockSnapshot`), pandas, pytest. Deterministic, offline (`FakeSource`); firewall-clean (short interest rides on the already-guarded `daily_snapshot`).

---

## Context: what's dormant and why this activates it

- `StockSnapshot` (`alpha/universe/stock.py`) has a comment reserving `float / short_interest / halts` for US-3b+. US-3a added `consecutive_up_days` via `build_universe`; US-3c adds `short_interest` + `days_to_cover` the same way.
- `seeds/skills.json` ships `short_squeeze` (meme, `pattern`, `incubating`) with `depends_on: ["short_interest", "days_to_cover"]` and `gamma_squeeze` (`incubating`, `depends_on: ["options_flow"]`). The defense-heavy seed pack deliberately kept squeezes incubating "pending US-3 short data".
- `Skill.depends_on` (`alpha/harness/skill.py:63`) is **loaded but never enforced** — purely decorative today. Both squeeze skills are therefore surfaced to the agent every day (in the INCUBATING trial slots) even though their data is absent. US-3c makes `depends_on` real.
- `GateSpec` (machine-readable threshold gate) exists but its match semantics deliberately "live in the consumer (eval/rule_policy)", which is **not yet wired** (a deterministic `HarnessRulePolicy` is a separate later concern). **US-3c does NOT extend GateSpec or add a `gate` to `short_squeeze`** — that would add machinery with no live consumer. The `depends_on` switch is the activation; threshold gating is deferred with the rule-policy slice.

**The activation, precisely:** before US-3c, `short_interest` is always `None`, `depends_on` is unenforced, and `short_squeeze` is dormant-but-always-shown text. After US-3c, short interest flows to the snapshot + prompt, `depends_on` is enforced on the decide path, and `short_squeeze` surfaces to the agent exactly on days with short-interest data (and the agent can see per-name `si=`/`dtc=` to match it). That is the seed's activation; status promotion stays evidence-gated.

## US-3 decomposition status

US-3a (runner-tier) DONE. US-3b (SSR + reverse-split + guard-veto, opt-in) DONE. **US-3c = THIS PLAN.** Deferred: **3d** float / dilution / EDGAR; **3e** intraday / halts / MWCB; **3f** social / **options_flow → `gamma_squeeze`** / per-narrative. Also deferred (noted, not built here): GateSpec threshold gating + a deterministic `HarnessRulePolicy` consumer; real FINRA feed ingestion via `capture_window`/`AlpacaSource` (the offline `FakeSource`/`SnapshotSource` mechanism + schema are in place); evidence-gated promotion of `short_squeeze` to `active` on a live temp=0 run.

---

## File Structure

| File | Change | Responsibility |
|---|---|---|
| `alpha/universe/stock.py` | Modify | Add `short_interest: float \| None` + `days_to_cover: float \| None`; refresh the deferral comment. |
| `alpha/data/source.py` | Modify | Extend `_EMPTY_SNAP` with the two columns (schema doc; the empty-snapshot fallback). |
| `alpha/universe/universe.py` | Modify | `build_universe` extracts `short_interest`/`days_to_cover` from each snapshot record (None-safe). |
| `alpha/agent/prompt.py` | Modify | `build_user_prompt` renders `si=…% dtc=…` when present; add `available_data_signals(universe)` + `_depends_on_satisfied(skill, signals)`; `build_system_prompt` gains `available_signals` and filters skills/trials by `depends_on`. |
| `alpha/agent/agent.py` | Modify | `decide` computes `available_data_signals(universe)` and passes it to `build_system_prompt`. |
| `tests/universe/test_build_universe.py` | Modify | si/dtc populated from the snapshot record; None when absent. |
| `tests/agent/test_prompt.py` | Modify | `build_user_prompt` si/dtc rendering; `build_system_prompt` `depends_on` filtering (hide/show short_squeeze; gamma_squeeze stays hidden; None = back-compat). |
| `tests/eval/test_us3c_acceptance.py` | Create | End-to-end on the seeded harness: a high-SI universe surfaces `short_squeeze` + renders `si=`; a no-SI universe hides it. |
| `docs/PROJECT_STATE.md`, `docs/blueprint.md` | Modify | US-3c DONE entry + refreshed roadmap; reconcile the snapshot/short-interest doc lines. |

**No seed edit:** `short_squeeze` already has the right `depends_on` and `incubating` status. **No `alpha/data/alpaca.py` change:** real FINRA ingestion (the `_SNAP_COLS`/`_normalize_snapshot`/`capture_window` join) is deferred smoke-work; the offline path reads the columns via `rec.get(...)`/parquet, which tolerates their absence.

**TDD framing.** All three tasks are genuine red→green (new fields, new helper, new behavior). The `depends_on` filter is wired on the live `decide` path but defaults to no-op (`available_signals=None`) for every other caller, so the existing 340-test suite stays green — verified by a full-suite run after every task.

---

## Task 1: short_interest / days_to_cover data + prompt rendering

**Files:**
- Modify: `alpha/universe/stock.py`, `alpha/data/source.py`, `alpha/universe/universe.py`, `alpha/agent/prompt.py`
- Test: `tests/universe/test_build_universe.py`, `tests/agent/test_prompt.py`

- [ ] **Step 1: Write the failing tests**

Append to `tests/universe/test_build_universe.py`:

```python
def test_build_universe_populates_short_interest():
    cal = [date(2026, 6, 11), date(2026, 6, 12)]
    snaps = {date(2026, 6, 12): pd.DataFrame({
        "symbol": ["SQZ"], "name": ["Squeezer"], "open": [10.0], "high": [13.0], "low": [10.0],
        "close": [12.0], "volume": [5], "prev_close": [10.0],
        "short_interest": [30.0], "days_to_cover": [6.0]})}                 # +20% gainer w/ high SI
    src = FakeSource(calendar=cal, bars={}, snapshots=snaps)
    s = build_universe(src, date(2026, 6, 12), gainer_pct=10.0, gap_pct=5.0, rvol_window=2).get("SQZ")
    assert s.short_interest == 30.0 and s.days_to_cover == 6.0


def test_build_universe_short_interest_absent_is_none(fake_source):
    # conftest fake_source snapshots have no short_interest columns -> fields stay None (never fabricated)
    s = build_universe(fake_source, date(2026, 6, 12), gainer_pct=10.0, gap_pct=5.0, rvol_window=2).get("RUN")
    assert s.short_interest is None and s.days_to_cover is None
```

Append to `tests/agent/test_prompt.py`:

```python
def test_user_prompt_renders_short_interest_when_present():
    state = MarketState(date=date(2026, 6, 12), gainer_count=1, gap_up_count=0, loser_count=0,
                        failed_breakout_count=0, max_runner_tier=1, echelon=[], breadth_raw=1.0,
                        as_of=datetime(2026, 6, 12, 16, 0))
    uni = CandidateUniverse.from_stocks([
        StockSnapshot(symbol="SQZ", name="Sq", status="gainer", pct_change=20.0, rvol=4.0,
                      short_interest=30.0, days_to_cover=6.0),
        StockSnapshot(symbol="PLAIN", name="Pl", status="gainer", pct_change=12.0, rvol=2.0),
    ])
    up = build_user_prompt(state, uni)
    assert "si=30%" in up and "dtc=6.0" in up           # high-SI name shows the suffix
    plain_line = [ln for ln in up.splitlines() if ln.startswith("- PLAIN")][0]
    assert "si=" not in plain_line                       # no short interest -> no suffix (no noise)
```

- [ ] **Step 2: Run to verify failure**

Run: `python -m pytest tests/universe/test_build_universe.py -k short_interest tests/agent/test_prompt.py -k short_interest -v`
Expected: FAIL — `StockSnapshot` has no `short_interest`/`days_to_cover` fields yet. The model sets only `frozen=True` (pydantic default `extra='ignore'`), so the prompt test's unknown kwargs are silently dropped at construction and then `s.short_interest` raises `AttributeError` in `build_user_prompt`; the universe test asserts a non-existent attribute. (No `extra='forbid'` needed; `frozen=True` is sufficient — no ConfigDict change.)

- [ ] **Step 3: Add the fields to `alpha/universe/stock.py`**

Replace:

```python
    consecutive_up_days: int | None = None
    # consecutive_up_days populated by build_universe (US-3a; None = current-day bar absent);
    # float / short_interest / halts -> None until US-3b+
```

with:

```python
    consecutive_up_days: int | None = None
    short_interest: float | None = None    # FINRA short interest as % of float (0-100); US-3c
    days_to_cover: float | None = None      # short shares / avg daily volume; US-3c
    # consecutive_up_days populated by build_universe (US-3a); short_interest/days_to_cover (US-3c);
    # float / halts -> None until US-3d / US-3e
```

- [ ] **Step 4: Extend the snapshot schema in `alpha/data/source.py`**

Replace:

```python
_EMPTY_SNAP = ["symbol", "name", "open", "high", "low", "close", "volume", "prev_close"]
```

with:

```python
_EMPTY_SNAP = ["symbol", "name", "open", "high", "low", "close", "volume", "prev_close",
               "short_interest", "days_to_cover"]
```

- [ ] **Step 5: Populate the fields in `build_universe`**

In `alpha/universe/universe.py::build_universe`, in the `StockSnapshot(...)` construction, add the two fields after `consecutive_up_days=cud,`:

```python
            rvol=rvol, consecutive_up_days=cud,
            short_interest=(float(rec["short_interest"]) if rec.get("short_interest") is not None else None),
            days_to_cover=(float(rec["days_to_cover"]) if rec.get("days_to_cover") is not None else None),
        )
```

(`rec.get(...)` tolerates snapshots that lack the columns — the offline `FakeSource`/`SnapshotSource` path needs no further change; real FINRA ingestion via `capture_window`/`AlpacaSource` is deferred.)

- [ ] **Step 6: Render si/dtc in `build_user_prompt`**

In `alpha/agent/prompt.py::build_user_prompt`, replace the per-candidate line construction:

```python
        cud = s.consecutive_up_days if s.consecutive_up_days is not None else "?"
        lines.append(f"- {s.symbol} ({s.name}) [{s.status}] pct={pct} rvol={rvol} up_days={cud}")
```

with:

```python
        cud = s.consecutive_up_days if s.consecutive_up_days is not None else "?"
        line = f"- {s.symbol} ({s.name}) [{s.status}] pct={pct} rvol={rvol} up_days={cud}"
        if s.short_interest is not None:                 # squeeze fuel — only shown when data is live
            dtc = f" dtc={s.days_to_cover:.1f}" if s.days_to_cover is not None else ""
            line += f" si={s.short_interest:.0f}%{dtc}"
        lines.append(line)
```

- [ ] **Step 7: Run the tests to verify they pass**

Run: `python -m pytest tests/universe/test_build_universe.py tests/agent/test_prompt.py -v`
Expected: the new tests PASS; the existing `test_user_prompt_renders_state_and_universe` still passes (its universe has no short_interest → no suffix → line unchanged).

- [ ] **Step 8: Full suite**

Run: `python -m pytest -q`
Expected: 340 + 3 new = 343 green (additive fields; conditional suffix; no behavior change for existing fixtures).

- [ ] **Step 9: Commit**

```bash
git add alpha/universe/stock.py alpha/data/source.py alpha/universe/universe.py alpha/agent/prompt.py \
        tests/universe/test_build_universe.py tests/agent/test_prompt.py
git commit -m "US-3c Task 1: short_interest/days_to_cover on the snapshot + build_universe fill + prompt render"
```

---

## Task 2: enforce `depends_on` — the short_squeeze activation switch

**Files:**
- Modify: `alpha/agent/prompt.py` (helpers + `build_system_prompt` filter)
- Modify: `alpha/agent/agent.py` (`decide` passes the signals)
- Test: `tests/agent/test_prompt.py`

- [ ] **Step 1: Write the failing tests**

Append to `tests/agent/test_prompt.py`:

```python
from alpha.agent.prompt import available_data_signals


def _h_squeeze():
    skills = SkillRegistry.from_skills([
        Skill(skill_id="gap_and_go", name="Gap and Go", type="pattern", family="runner",
              phases=["trend"], trigger="t", entry="e", exit_stop="x", status="active"),
        Skill(skill_id="short_squeeze", name="Short Squeeze", type="pattern", family="meme",
              phases=["ignition", "trend"], trigger="high SI", entry="e", exit_stop="x",
              depends_on=["short_interest", "days_to_cover"], status="incubating"),
        Skill(skill_id="gamma_squeeze", name="Gamma Squeeze", type="pattern", family="meme",
              phases=["ignition", "trend"], trigger="gamma", entry="e", exit_stop="x",
              depends_on=["options_flow"], status="incubating"),
    ])
    doctrine = Doctrine.from_seed_list([{"section": "core", "regime": "all", "immutable": True,
                                         "guidance": "respect the stop"}])
    return HarnessState(doctrine=doctrine, skills=skills, memory=MemoryStore.from_lessons([]))


def test_available_data_signals_collects_non_none_fields():
    uni = CandidateUniverse.from_stocks([
        StockSnapshot(symbol="SQZ", name="Sq", status="gainer", short_interest=30.0, days_to_cover=6.0),
        StockSnapshot(symbol="PLAIN", name="Pl", status="gainer"),
    ])
    sigs = available_data_signals(uni)
    assert "short_interest" in sigs and "days_to_cover" in sigs and "options_flow" not in sigs


def test_depends_on_enforced_hides_squeeze_without_data():
    sp = build_system_prompt(_h_squeeze(), phase_prior="trend", injection="full",
                             available_signals=frozenset({"symbol", "status"}))
    assert "short_squeeze" not in sp and "gamma_squeeze" not in sp      # depends_on unsatisfied -> hidden
    assert "gap_and_go" in sp                                           # no depends_on -> always shown


def test_depends_on_enforced_shows_squeeze_with_data():
    sigs = frozenset({"short_interest", "days_to_cover"})
    sp = build_system_prompt(_h_squeeze(), phase_prior="trend", injection="full", available_signals=sigs)
    assert "short_squeeze" in sp                                        # short-interest data live -> surfaced
    assert "gamma_squeeze" not in sp                                    # options_flow still absent -> hidden


def test_depends_on_default_none_is_backcompat():
    sp = build_system_prompt(_h_squeeze(), phase_prior="trend", injection="full")   # no available_signals
    assert "short_squeeze" in sp and "gamma_squeeze" in sp              # None = no enforcement (unchanged)


def test_depends_on_enforced_on_retrieval_path():
    # the filter applies after select_for_prompt too (retrieval injection), not just the 'full' path
    sigs = frozenset({"short_interest", "days_to_cover"})
    sp = build_system_prompt(_h_squeeze(), phase_prior="trend", injection="retrieval", available_signals=sigs)
    assert "short_squeeze" in sp and "gamma_squeeze" not in sp
    sp0 = build_system_prompt(_h_squeeze(), phase_prior="trend", injection="retrieval",
                              available_signals=frozenset())
    assert "short_squeeze" not in sp0                                   # no data signal -> hidden in retrieval too
```

- [ ] **Step 2: Run to verify failure**

Run: `python -m pytest tests/agent/test_prompt.py -k "depends_on or available_data_signals" -v`
Expected: FAIL — `available_data_signals` does not exist (ImportError); `build_system_prompt` has no `available_signals` kwarg.

- [ ] **Step 3: Add the helpers to `alpha/agent/prompt.py`**

Add after the imports (the module already imports `Skill`, `HarnessState`, `CandidateUniverse`):

```python
def available_data_signals(universe: CandidateUniverse) -> frozenset[str]:
    """Live OPTIONAL data signals: StockSnapshot enrichment fields (those defaulting to None — rvol,
    consecutive_up_days, short_interest, days_to_cover, ...) that are non-None for at least one
    candidate today. Required structural fields (symbol/name/status) are excluded so a skill's
    depends_on names a true data dependency, never an always-present field. A skill is surfaced only
    when its depends_on is a subset of these signals."""
    sigs: set[str] = set()
    for snap in universe.all():
        for field, info in snap.__class__.model_fields.items():
            if info.default is None and getattr(snap, field) is not None:   # optional enrichment, present
                sigs.add(field)
    return frozenset(sigs)


def _depends_on_satisfied(skill: Skill, signals: frozenset[str]) -> bool:
    """A skill is eligible to be surfaced iff every data dependency it declares is a live signal.
    Empty depends_on (the common case) is always satisfied. Enforces the previously-decorative
    Skill.depends_on (e.g. short_squeeze needs short_interest+days_to_cover; gamma_squeeze needs
    options_flow)."""
    return set(skill.depends_on) <= signals
```

- [ ] **Step 4: Add the filter to `build_system_prompt`**

Change the signature to add the parameter (keep all existing params):

```python
def build_system_prompt(h: HarnessState, *, injection: str = "full", phase_prior: str | None = None,
                        skill_budget: int = DEFAULT_SKILL_BUDGET,
                        memory_budget: int = DEFAULT_MEMORY_BUDGET,
                        trial_slots: int = DEFAULT_TRIAL_SLOTS,
                        available_signals: frozenset[str] | None = None) -> str:
```

Immediately after the `if injection == "retrieval": ... else: ...` block that assigns `skills`, `trials`, `lessons`, insert:

```python
    if available_signals is not None:                    # US-3c: enforce Skill.depends_on (None = off)
        skills = [s for s in skills if _depends_on_satisfied(s, available_signals)]
        # filtering runs after select_for_prompt's trial-slot budget, so it may leave fewer trials than
        # trial_slots — acceptable (a data-less trial skill carries no signal worth a slot anyway).
        trials = [s for s in trials if _depends_on_satisfied(s, available_signals)]
```

- [ ] **Step 5: Wire it into `decide` (`alpha/agent/agent.py`)**

Add the import:

```python
from alpha.agent.prompt import available_data_signals, build_system_prompt, build_user_prompt
```

(extend the existing `from alpha.agent.prompt import ...` line). In `decide`, compute the signals and pass them:

```python
    def decide(self, state: MarketState, universe: CandidateUniverse) -> DecisionPackage:
        system = build_system_prompt(self._harness, injection=self._injection,
                                     phase_prior=self._phase_prior, skill_budget=self._skill_budget,
                                     memory_budget=self._memory_budget, trial_slots=self._trial_slots,
                                     available_signals=available_data_signals(universe))
        user = build_user_prompt(state, universe)
```

- [ ] **Step 6: Run the tests to verify they pass**

Run: `python -m pytest tests/agent/test_prompt.py -v`
Expected: all PASS (new depends_on tests + the existing `test_system_prompt_contains_skill_doctrine_contract`, which calls `build_system_prompt` with no `available_signals` → None → unchanged).

- [ ] **Step 7: Full suite**

Run: `python -m pytest -q`
Expected: green. The live `decide` path now passes `available_signals`, so on the existing no-short-interest fixtures `short_squeeze`/`gamma_squeeze` are hidden from the rendered prompt — but `MockLLMClient` ignores the prompt, so no decision/score changes, and no existing test inspects a decide-path prompt for squeeze skills (only `test_seed_packs` asserts they stay `incubating`, which is unchanged). 343 + 5 new = 348.

- [ ] **Step 8: Commit**

```bash
git add alpha/agent/prompt.py alpha/agent/agent.py tests/agent/test_prompt.py
git commit -m "US-3c Task 2: enforce Skill.depends_on (short_squeeze surfaces only when short-interest data is live)"
```

---

## Task 3: US-3c acceptance gate + docs

**Files:**
- Create: `tests/eval/test_us3c_acceptance.py`
- Modify: `docs/PROJECT_STATE.md`, `docs/blueprint.md`

- [ ] **Step 1: Write the acceptance test**

Create `tests/eval/test_us3c_acceptance.py`:

```python
"""US-3c acceptance: short-interest data activates the dormant short_squeeze seed. On a universe carrying
short_interest/days_to_cover, build_universe fills the fields, the agent's user prompt shows si=/dtc=, and
the system prompt SURFACES short_squeeze (its depends_on is now satisfied) while gamma_squeeze stays hidden
(options_flow absent). On a universe WITHOUT short interest, short_squeeze is hidden. This is the headline
US-3c guarantee: depends_on is enforced and short_squeeze is live exactly when its data is."""
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


def _source(*, with_si: bool):
    cal = [date(2026, 6, 11), CUR]
    cols = {"symbol": ["SQZ"], "name": ["Squeezer"], "open": [10.0], "high": [13.0], "low": [10.0],
            "close": [12.0], "volume": [5], "prev_close": [10.0]}                      # +20% gainer
    if with_si:
        cols |= {"short_interest": [35.0], "days_to_cover": [7.0]}
    return FakeSource(calendar=cal, bars={}, snapshots={CUR: pd.DataFrame(cols)})


def _sys_prompt_for(src):
    uni = build_universe(src, CUR, gainer_pct=10.0, gap_pct=5.0, rvol_window=2)
    h = load_seeds(SEEDS)
    return build_system_prompt(h, phase_prior="ignition", available_signals=available_data_signals(uni)), uni


def test_short_interest_activates_short_squeeze_end_to_end():
    sp, uni = _sys_prompt_for(_source(with_si=True))
    assert uni.get("SQZ").short_interest == 35.0 and uni.get("SQZ").days_to_cover == 7.0
    assert "short_squeeze" in sp                                    # depends_on satisfied -> surfaced
    assert "gamma_squeeze" not in sp                                # options_flow absent -> still hidden
    state = build_market_state(uni, CUR, as_of=datetime(2026, 6, 12, 16, 0))
    assert "si=35%" in build_user_prompt(state, uni)               # the agent sees the squeeze fuel


def test_without_short_interest_short_squeeze_stays_dormant():
    sp, uni = _sys_prompt_for(_source(with_si=False))
    assert uni.get("SQZ").short_interest is None
    assert "short_squeeze" not in sp                                # no data -> depends_on unsatisfied -> hidden
```

- [ ] **Step 2: Run the acceptance test**

Run: `python -m pytest tests/eval/test_us3c_acceptance.py -v`
Expected: both PASS.

- [ ] **Step 3: Full suite**

Run: `python -m pytest -q`
Expected: all green; record the exact count (expected 350 = 340 + 10 new: Task1 +3, Task2 +5, Task3 +2). Use whatever the run reports for the PROJECT_STATE edit.

- [ ] **Step 4: Update `docs/PROJECT_STATE.md`**

Replace the header `Last updated` line (line 4). Old (verbatim):

```markdown
> Last updated: 2026-06-15 (US-0 + US-1 + US-2 complete; US-3a runner-tier + US-3b SSR/reverse-split guard-veto (opt-in) shipped; US-3c next).
```

New:

```markdown
> Last updated: 2026-06-15 (US-0 + US-1 + US-2 complete; US-3a runner-tier + US-3b guard-veto + US-3c short-interest/short_squeeze shipped; US-3d next).
```

Insert, immediately after the US-3b paragraph (the block ending "Full suite **339 tests green**.") and before the "Next — US-3c → US-3f" paragraph:

```markdown
**US-3c Short-interest + short_squeeze activation — Complete (2026-06-15). The dormant squeeze seed is live.**
`StockSnapshot` gains `short_interest` (% of float) + `days_to_cover`, filled at the `build_universe` chokepoint
from the daily snapshot (the US-3a data-on-snapshot pattern; real FINRA ingestion via capture/Alpaca deferred —
the offline `FakeSource`/`SnapshotSource` mechanism + schema are in place). `build_user_prompt` renders
`si=…% dtc=…` per candidate when present. The activation makes the previously-**decorative** `Skill.depends_on`
**enforced**: `build_system_prompt` (on the live `decide` path, which now supplies `available_data_signals(universe)`)
surfaces a skill only when every name in its `depends_on` is a live data signal. So `short_squeeze`
(`depends_on=[short_interest, days_to_cover]`) appears to the agent exactly on short-interest days, and
`gamma_squeeze` (`depends_on=[options_flow]`) stays correctly hidden until US-3f. Enforcement defaults OFF
(`available_signals=None`) for non-decide callers, so the suite is untouched. `short_squeeze` **stays
`incubating`** — promotion to `active` is evidence-gated (Refiner on a live run), not declared (lifecycle
discipline; `test_squeeze_offense_is_incubating` pins it). GateSpec threshold gating + a deterministic
`HarnessRulePolicy` consumer are deferred (no live consumer yet). Full suite **350 tests green**.

```

Then update the **"Next — US-3c → US-3f"** paragraph. Replace the verbatim opening substring (stops exactly before `float / dilution`):

```
**Next — US-3c → US-3f (deferred roadmap):** **3c** FINRA
short-interest → activate the incubating `short_squeeze` seed. **3d** float / dilution
```

with:

```
**Next — US-3d → US-3f (deferred roadmap):** **3d** float / dilution
```

- [ ] **Step 5: Reconcile `docs/blueprint.md`**

Find the short-interest / squeeze line(s) in `docs/blueprint.md` (grep `short interest` / `short_squeeze` / `FINRA`). Update any "(US-3)" / "deferred" framing for short interest to note it is wired in US-3c (data on the snapshot + `depends_on`-gated `short_squeeze`, incubating pending evidence). Keep the edit to the one or two stale cells/lines; do not rewrite unrelated content.

- [ ] **Step 6: Commit**

```bash
git add tests/eval/test_us3c_acceptance.py docs/PROJECT_STATE.md docs/blueprint.md
git commit -m "US-3c Task 3: acceptance gate (short interest activates short_squeeze end-to-end) + PROJECT_STATE/blueprint"
```

---

## Self-Review

**1. Spec coverage.** FINRA short-interest data delivered (`short_interest` + `days_to_cover` on the snapshot, filled in `build_universe`, rendered in the prompt). `short_squeeze` activated by enforcing its `depends_on` (Task 2) — it surfaces to the agent exactly when short-interest data is live; acceptance-tested end-to-end (Task 3). `gamma_squeeze` correctly stays hidden (options_flow → US-3f). No GateSpec/seed change (deferred deterministic gating has no live consumer).

**2. Placeholder scan.** Every step has literal code + a runnable command + expected outcome, except Task 3 Step 5 (blueprint) which is a grep-then-edit because the exact stale line is discovered at execution — bounded to "the short-interest/squeeze cell(s)".

**3. Type/contract consistency.** `short_interest`/`days_to_cover: float | None` match the `rvol`/`consecutive_up_days` pattern (frozen model, None default). `available_data_signals(universe) -> frozenset[str]`; `_depends_on_satisfied(skill, signals) -> bool`; `build_system_prompt(..., available_signals: frozenset[str] | None = None)`; `decide` passes it. `Skill.depends_on` is read-only here (no Skill mutation). `model_fields` is the pydantic v2 class attribute (`snap.__class__.model_fields`).

**4. Firewall.** Short interest rides on `daily_snapshot`, already routed through `GuardedSource`/`AsOfGuard` in the live drivers — no new fetch surface, no new firewall edge.

**5. Blast radius / honesty.** `depends_on` enforcement is live on the `decide` path but defaults to no-op (`None`) everywhere else, so the 340-test suite stays green; the decide-path prompt now hides data-less squeeze skills, but `MockLLMClient` ignores the prompt and no test asserts squeeze skills in a decide-path prompt (verified: only `test_prompt`/`test_retrieval` reference them, via hand-built empty-`depends_on` harnesses, and `test_seed_packs` only asserts they stay `incubating` — which they do). The honest framing — **activation = data + enforced depends_on + surfacing; promotion to `active` stays evidence-gated** — is carried in code comments, the plan, and PROJECT_STATE, consistent with US-3a/US-3b activating mechanisms without claiming efficacy. Deferred-but-noted: GateSpec threshold gating + `HarnessRulePolicy`, real FINRA ingestion, `gamma_squeeze`/options_flow (US-3f), float/dilution (US-3d).
