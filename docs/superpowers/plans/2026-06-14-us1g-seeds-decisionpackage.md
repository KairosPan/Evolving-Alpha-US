# US-1g Seeds v1 + DecisionPackage Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Complete US-1 — enrich the `DecisionPackage` to the full human-facing action `a_t` (§4.1: per-candidate plan + size + fill + taboo + portfolio + regime read) and author the four **defense-heavy** v1 seed packs (runner / swing / event / meme) that load into the harness `H`.

**Architecture:** The full `DecisionPackage` extends the minimal US-1d eval contract in `alpha/eval/decision.py` (US-1d explicitly telegraphed this) — all new fields are optional with defaults, so the US-1d scorer/baselines keep working while the US-2 agent can populate the rich plan. Seeds are authored as JSON matching the US-1a `from_seed` schemas (`skill_id`/`name`/`type`/`family`/`phases`/`trigger`/`entry`/`exit_stop`/`taboo`/`depends_on`/`status` for skills; `lesson_id`/`phases`/`family`/`outcome`/`failure_signature`/`named_analog`/`lesson` for memory; `section`/`regime`/`immutable`/`guidance` for doctrine) and loaded by the existing `load_seeds`.

**Tech Stack:** Python ≥3.11, pydantic v2, pytest. No LLM, no network — fully offline.

**Spec:** `docs/superpowers/specs/2026-06-13-us-market-adaptation-design.md` (US-1 "DecisionPackage schema"; §4.1; §6 four families + defense-heavy bias + immutable-core). Sub-plan **US-1g** of US-1 — the **final** one; after it US-1 is complete and US-2 wires in the LLM agent + Refiner.

**Scope boundary (US-1g only):** the full DecisionPackage schema + v1 seed content + loading them into `H`. **Deferred:** the agent that *produces* a populated DecisionPackage → US-2; the Refiner that edits seeds → US-2; data-dependent seed signals (short-interest / SSR / intraday halts / earnings calendar) → US-3 (US-1g seeds use daily-available triggers + flag-driven taboos); the `state_machine.json` seed — the regime machine ships in code as `default_us_cycle()` (US-1e), so `load_seeds` loads only skills/memory/doctrine. **Reused:** US-1a `Skill`/`Lesson`/`Doctrine`/`load_seeds`/`HarnessState`; US-1f `SizeTier`; US-1e `RegimeRead` concepts.

**Design bias (spec §6):** **defense seeds (failure-detectors + taboos) outnumber offense seeds (entry patterns)** — guardrails clear the capability floor faster and resist the Refiner-over-pruning failure mode; offense skills that need US-3 data (squeezes) ship `incubating`.

**Conventions:** all code/comments/seeds English; `from __future__ import annotations` at top of every module; commit after every passing task; run via `python -m pytest`.

**Key invariants (each gets a test):**
1. The enriched `DecisionPackage` is backward-compatible: US-1d-style construction (symbol/pattern only) still validates; the new fields default.
2. Seeds load via `load_seeds` into a valid `HarnessState`; every family (runner/swing/event/meme) is represented; phases are canonical; doctrine carries the immutable-core red-lines.
3. The seed set is **defense-heavy**: `failure_detector` skills outnumber `pattern` skills.
4. Immutable-core doctrine entries are write-protected after load (the guard holds on seeded immutable entries).

---

### Task 1: DecisionPackage sub-models + enriched Candidate

**Files:**
- Modify: `alpha/eval/decision.py`
- Create: `tests/eval/test_decision_full.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/eval/test_decision_full.py
import pytest
from datetime import date
from alpha.eval.decision import Candidate, FillFeasibility, TabooCheck, DecisionPackage


def test_minimal_candidate_still_valid_backward_compat():
    c = Candidate(symbol="RUN", pattern="gap_and_go")     # US-1d-style
    assert c.skill_id == "" and c.size_tier is None and c.fill_feasibility is None
    assert c.taboo_check == [] and c.family == ""


def test_full_candidate():
    c = Candidate(symbol="RUN", name="Runner", pattern="gap_and_go", skill_id="gap_and_go",
                  family="runner", entry="buy ORB-high reclaim", exit_stop="lose VWAP",
                  size_tier="core", confidence=0.7,
                  fill_feasibility=FillFeasibility(buyable=True, reason="liquid open"),
                  taboo_check=[TabooCheck(rule="no-chase-risk-off", status="pass")],
                  counterview="if AI line flips backside, drop")
    assert c.size_tier == "core" and c.fill_feasibility.buyable is True
    assert c.taboo_check[0].status == "pass" and c.family == "runner"


def test_size_tier_must_be_valid():
    with pytest.raises(Exception):
        Candidate(symbol="RUN", size_tier="enormous")     # not a SizeTier literal
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/eval/test_decision_full.py -q`
Expected: FAIL — `ImportError: cannot import name 'FillFeasibility'`

- [ ] **Step 3: Edit `alpha/eval/decision.py`**

Add the import and sub-models, and extend `Candidate`. Add near the top imports:

```python
from alpha.sizing.position import SizeTier
```

Add these sub-models (before `Candidate`):

```python
class FillFeasibility(BaseModel):
    """Whether the pick is realistically buyable (inference-path; spec §7). buyable=False de-ranks."""
    model_config = ConfigDict(frozen=True)
    buyable: bool = True
    reason: str = ""


class TabooCheck(BaseModel):
    """A guard taboo evaluated against the pick (from L4 guard)."""
    model_config = ConfigDict(frozen=True)
    rule: str
    status: Literal["pass", "fail"]
```

Change `from typing import Protocol` to `from typing import Literal, Protocol` (Literal is **required** by `TabooCheck` and is not currently imported — with `from __future__ import annotations`, pydantic needs it in the module namespace). Then extend `Candidate` with the §4.1 fields (after `confidence`):

```python
    # ── full DecisionPackage fields (US-1g, §4.1); all optional so US-1d construction still validates
    skill_id: str = ""
    family: str = ""                                  # runner|swing|event|meme (or "")
    entry: str = ""
    exit_stop: str = ""
    size_tier: SizeTier | None = None                # from L3 sizing
    fill_feasibility: FillFeasibility | None = None  # from eval/fill (inference path)
    taboo_check: list[TabooCheck] = Field(default_factory=list)   # from L4 guard
    counterview: str = ""
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/eval/test_decision_full.py -q`
Expected: PASS (3 passed). Also run `python -m pytest tests/eval -q` to confirm US-1d eval tests still pass (backward-compat).

- [ ] **Step 5: Commit**

```bash
git add alpha/eval/decision.py tests/eval/test_decision_full.py
git commit -m "US-1g Task 1: DecisionPackage sub-models + enriched Candidate (§4.1, backward-compatible)"
```

---

### Task 2: Enriched DecisionPackage (portfolio / key_risks / human_confirm)

**Files:**
- Modify: `alpha/eval/decision.py`
- Modify: `tests/eval/test_decision_full.py` (append)

- [ ] **Step 1: Write the failing test (append)**

```python
# append to tests/eval/test_decision_full.py
from alpha.eval.decision import Portfolio


def test_minimal_decision_package_backward_compat():
    d = DecisionPackage(date=date(2026, 6, 12))            # US-1d-style
    assert d.key_risks == [] and d.portfolio is None and d.human_confirm is None
    assert d.as_of is None and d.regime is None           # §4.1 fields default for backward-compat


def test_full_decision_package():
    d = DecisionPackage(date=date(2026, 6, 12),
                        candidates=[Candidate(symbol="RUN", pattern="gap_and_go", family="runner")],
                        no_trade_reason="", regime_read="trend, frontside",
                        key_risks=["AI leader rolls over"],
                        portfolio=Portfolio(total_exposure_budget=0.6, correlated_groups=[["RUN", "AI2"]]),
                        human_confirm=None)
    assert d.portfolio.total_exposure_budget == 0.6
    assert d.portfolio.correlated_groups == [["RUN", "AI2"]]
    assert d.key_risks == ["AI leader rolls over"]


def test_structured_regime_and_as_of_round_trip():
    from datetime import datetime
    from alpha.regime.classifier import RegimeRead
    d = DecisionPackage(date=date(2026, 6, 12), as_of=datetime(2026, 6, 12, 16, 0),
                        regime=RegimeRead(phase="trend", confidence=0.7, frontside=True, risk_gate=0.6))
    again = DecisionPackage.model_validate(d.model_dump())
    assert again.regime.phase == "trend" and again.regime.risk_gate == 0.6
    assert again.as_of == datetime(2026, 6, 12, 16, 0)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/eval/test_decision_full.py -q`
Expected: FAIL — `ImportError: cannot import name 'Portfolio'`

- [ ] **Step 3: Edit `alpha/eval/decision.py`**

Add the `Portfolio` sub-model (before `DecisionPackage`):

```python
class Portfolio(BaseModel):
    """Portfolio-level sizing summary (from L3 sizing). Field names match PortfolioPlan / spec §4.1."""
    model_config = ConfigDict(frozen=True)
    total_exposure_budget: float = 0.0
    correlated_groups: list[list[str]] = Field(default_factory=list)
```

Add two imports to `alpha/eval/decision.py`: change `from datetime import date as Date` to
`from datetime import date as Date, datetime`, and add `from alpha.regime.classifier import RegimeRead`
(pydantic v2 holds the frozen `RegimeRead` dataclass as a field and round-trips it — verified).

Extend `DecisionPackage` with the §4.1 top-level fields (after `regime_read`):

```python
    # ── full DecisionPackage fields (US-1g, §4.1); optional so US-1d construction still validates
    as_of: datetime | None = None        # snapshot timestamp; agent sets it on the inference path (US-2)
    regime: RegimeRead | None = None     # structured GLOBAL regime read from G_cycle (§4.1 global_risk_gate
                                         #   + frontside); per-narrative 'lines' -> US-3 (needs theme data).
                                         #   regime_read (str above) stays as the agent's prose read / phase_prior.
    key_risks: list[str] = Field(default_factory=list)
    portfolio: Portfolio | None = None
    human_confirm: str | None = None     # human fills: confirm | reject | modify(+reason) -> DAgger label
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/eval/test_decision_full.py -q`
Expected: PASS (6 passed)

- [ ] **Step 5: Commit**

```bash
git add alpha/eval/decision.py tests/eval/test_decision_full.py
git commit -m "US-1g Task 2: enriched DecisionPackage (portfolio / key_risks / human_confirm)"
```

---

### Task 3: Seed skills (four families, defense-heavy)

**Files:**
- Create: `seeds/skills.json`

Author the v1 skill pack: **10 failure-detectors > 6 patterns** (defense-heavy). Squeeze offense ships `incubating` (needs US-3 short data). Use only valid `from_seed` keys.

- [ ] **Step 1: Create `seeds/skills.json`**

```json
[
  {"skill_id": "gap_and_go", "name": "Gap and Go", "type": "pattern", "family": "runner",
   "phases": ["ignition", "trend"], "trigger": "gaps up on a catalyst and holds above the prior close and premarket high",
   "entry": "buy the opening-range-high reclaim that holds VWAP", "exit_stop": "lose VWAP / opening-range low",
   "taboo": ["chase extended far above VWAP", "enter in risk-off or on the backside"], "status": "active"},
  {"skill_id": "first_red_day", "name": "First Red Day", "type": "failure_detector", "family": "runner",
   "phases": ["distribution", "flush"], "trigger": "a multi-day runner prints its first lower close after a green streak",
   "entry": "", "exit_stop": "exit longs / do not add", "taboo": ["buy the first red day of an extended runner"], "status": "active"},
  {"skill_id": "parabolic_blowoff", "name": "Parabolic Blowoff", "type": "failure_detector", "family": "runner",
   "phases": ["trend", "distribution"], "trigger": "exhaustion gap + climactic volume + large upper wick at the highs",
   "entry": "", "exit_stop": "sell into the blowoff / never chase it", "taboo": ["chase the parabolic top"], "status": "active"},
  {"skill_id": "dilution_pump", "name": "Dilution Pump", "type": "failure_detector", "family": "runner",
   "phases": ["trend", "distribution", "flush"], "trigger": "low-float runner with ATM/shelf history spiking on weak catalyst",
   "entry": "", "exit_stop": "fade / do not hold into an offering", "taboo": ["hold a dilution-prone name overnight"], "status": "active"},
  {"skill_id": "reverse_split_pump", "name": "Reverse-Split Pump", "type": "failure_detector", "family": "runner",
   "phases": ["ignition", "trend"], "trigger": "post-reverse-split low-float spike with no real catalyst",
   "entry": "", "exit_stop": "avoid / fade the pop", "taboo": ["chase a reverse-split pump"], "status": "active"},
  {"skill_id": "base_breakout", "name": "Base Breakout", "type": "pattern", "family": "swing",
   "phases": ["ignition", "trend"], "trigger": "breaks a flat/cup base pivot on expanding volume with relative strength",
   "entry": "buy the pivot breakout", "exit_stop": "below the base / undercut of the pivot",
   "taboo": ["buy extended >5% past the pivot", "buy a breakout in a market downtrend"], "status": "active"},
  {"skill_id": "pullback_to_ma", "name": "Pullback to Moving Average", "type": "pattern", "family": "swing",
   "phases": ["trend"], "trigger": "a leader pulls back to the rising 10/20 EMA and holds with a reclaim",
   "entry": "buy the reclaim of the MA", "exit_stop": "decisive loss of the MA",
   "taboo": ["catch a knife below a broken MA"], "status": "active"},
  {"skill_id": "failed_breakout", "name": "Failed Breakout", "type": "failure_detector", "family": "swing",
   "phases": ["distribution"], "trigger": "a breakout undercuts the pivot and closes back inside the base",
   "entry": "", "exit_stop": "exit on the undercut", "taboo": ["hold a failed breakout hoping it recovers"], "status": "active"},
  {"skill_id": "distribution_cluster", "name": "Distribution Day Cluster", "type": "failure_detector", "family": "swing",
   "phases": ["distribution", "flush"], "trigger": "a cluster of high-volume down days in the leaders / index",
   "entry": "", "exit_stop": "reduce exposure / raise stops", "taboo": ["add risk into a distribution cluster"], "status": "active"},
  {"skill_id": "earnings_gap_continuation", "name": "Earnings Gap Continuation", "type": "pattern", "family": "event",
   "phases": ["ignition", "trend"], "trigger": "beat-and-raise earnings gap that holds the gap and the opening range",
   "entry": "buy the gap-and-hold above the opening range", "exit_stop": "lose the gap / fill",
   "taboo": ["chase a gap that is already fading"], "status": "active"},
  {"skill_id": "sell_the_news", "name": "Sell the News", "type": "failure_detector", "family": "event",
   "phases": ["ignition", "trend", "distribution"], "trigger": "good news but the stock closes red / fails to hold the pop",
   "entry": "", "exit_stop": "do not chase into the news; fade strength", "taboo": ["buy the anticipated catalyst at the top"], "status": "active"},
  {"skill_id": "fda_binary_risk", "name": "FDA Binary Risk", "type": "failure_detector", "family": "event",
   "phases": ["ignition", "trend"], "trigger": "an upcoming binary catalyst (PDUFA/data) on a biotech",
   "entry": "", "exit_stop": "size for total loss or avoid; no naked overnight hold", "taboo": ["hold a biotech binary naked over the event"], "status": "active"},
  {"skill_id": "short_squeeze", "name": "Short Squeeze", "type": "pattern", "family": "meme",
   "phases": ["ignition", "trend"], "trigger": "high short interest + catalyst + tape strength reclaiming key levels",
   "entry": "buy the reclaim with strength", "exit_stop": "exit on squeeze exhaustion / loss of the reclaim",
   "taboo": ["chase a parabolic squeeze top"], "depends_on": ["short_interest", "days_to_cover"], "status": "incubating"},
  {"skill_id": "gamma_squeeze", "name": "Gamma Squeeze", "type": "pattern", "family": "meme",
   "phases": ["ignition", "trend"], "trigger": "heavy near-the-money call buying forcing dealer hedging",
   "entry": "buy strength while gamma is positive", "exit_stop": "exit when the options flow reverses",
   "taboo": ["hold through opex unwind"], "depends_on": ["options_flow"], "status": "incubating"},
  {"skill_id": "squeeze_exhaustion", "name": "Squeeze Exhaustion", "type": "failure_detector", "family": "meme",
   "phases": ["distribution", "flush"], "trigger": "a parabolic squeeze with climactic volume and a failed new high",
   "entry": "", "exit_stop": "do not chase; the squeeze is ending", "taboo": ["buy the squeeze top"], "status": "active"},
  {"skill_id": "social_euphoria_top", "name": "Social Euphoria Top", "type": "failure_detector", "family": "meme",
   "phases": ["flush"], "trigger": "peak social-sentiment + parabolic price = late-stage distribution",
   "entry": "", "exit_stop": "distribute / do not initiate", "taboo": ["buy peak euphoria"], "status": "active"}
]
```

- [ ] **Step 2: Validate the JSON loads as skills**

Run: `python -c "import json; from alpha.harness.skill import Skill; d=json.load(open('seeds/skills.json')); ss=[Skill.from_seed(x) for x in d]; print(len(ss),'skills;', sum(s.type=='failure_detector' for s in ss),'detectors >', sum(s.type=='pattern' for s in ss),'patterns')"`
Expected: `16 skills; 10 detectors > 6 patterns`

- [ ] **Step 3: Commit**

```bash
git add seeds/skills.json
git commit -m "US-1g Task 3: seed skills v1 (4 families, defense-heavy: 10 detectors > 6 patterns)"
```

---

### Task 4: Seed memory + doctrine

**Files:**
- Create: `seeds/memory.json`
- Create: `seeds/doctrine.json`

- [ ] **Step 1: Create `seeds/memory.json`**

```json
[
  {"lesson_id": "no_chase_extended", "phases": ["trend"], "family": "runner", "outcome": "principle",
   "failure_signature": "chased a runner far above VWAP into resistance",
   "named_analog": "", "lesson": "Do not chase an extended runner into resistance; wait for a pullback or reclaim."},
  {"lesson_id": "blowoff_is_the_exit", "phases": ["distribution", "flush"], "family": "runner", "outcome": "loss",
   "failure_signature": "bought the climactic blowoff bar", "named_analog": "",
   "lesson": "Climactic volume + a large upper wick at the highs is the exit, not the entry."},
  {"lesson_id": "respect_the_base", "phases": ["distribution"], "family": "swing", "outcome": "principle",
   "failure_signature": "held a breakout that undercut its pivot", "named_analog": "",
   "lesson": "A breakout that closes back inside the base has failed; exit on the undercut."},
  {"lesson_id": "binary_size_for_total_loss", "phases": ["ignition", "trend"], "family": "event", "outcome": "principle",
   "failure_signature": "held a biotech binary naked over the event", "named_analog": "",
   "lesson": "Binary catalysts can gap to near zero; size any naked hold for a total loss, or avoid."},
  {"lesson_id": "sell_the_news_lesson", "phases": ["ignition", "trend"], "family": "event", "outcome": "loss",
   "failure_signature": "bought the anticipated catalyst at the top", "named_analog": "",
   "lesson": "When good news prints and the stock cannot hold the pop, it is a fade, not a chase."},
  {"lesson_id": "squeeze_top_max_pain", "phases": ["flush"], "family": "meme", "outcome": "loss",
   "failure_signature": "chased a parabolic squeeze into its top", "named_analog": "",
   "lesson": "The parabolic top of a squeeze is maximum pain for late chasers; let it come back."},
  {"lesson_id": "no_chase_risk_off", "phases": ["washout", "distribution", "flush"], "family": null, "outcome": "principle",
   "failure_signature": "initiated new longs in a risk-off / backside tape", "named_analog": "",
   "lesson": "Do not chase new longs in risk-off or on the backside; cash is a position."},
  {"lesson_id": "one_narrative_one_bet", "phases": [], "family": null, "outcome": "principle",
   "failure_signature": "sized N tickers in one narrative as N independent bets", "named_analog": "",
   "lesson": "Tickers in the same narrative move together; size the whole narrative as one bet."}
]
```

- [ ] **Step 2: Create `seeds/doctrine.json`**

```json
[
  {"section": "stop_discipline", "regime": "all", "immutable": true,
   "guidance": "Always honor the predefined stop. Never average down past a stop. The stop is the plan."},
  {"section": "no_chase_risk_off", "regime": "all", "immutable": true,
   "guidance": "No new longs in risk-off or on the backside (frontside=False). Enter only on the frontside."},
  {"section": "one_correlated_bet", "regime": "all", "immutable": true,
   "guidance": "Tickers in the same narrative/sympathy group are one correlated bet; net their exposure, never stack."},
  {"section": "loss_circuit_breaker", "regime": "all", "immutable": true,
   "guidance": "Halt new entries when the single-day, consecutive-loss, single-name, or market-wide breaker trips."},
  {"section": "survivorship_pit", "regime": "all", "immutable": true,
   "guidance": "Use only point-in-time data. A delisting/halt-to-zero in the hold is a terminal loss, never dropped."},
  {"section": "fill_feasibility", "regime": "all", "immutable": true,
   "guidance": "Do not rank an unbuyable pick ahead of a buyable one; model the realistic entry, not a fantasy fill."},
  {"section": "dont_fight_ssr", "regime": "all", "immutable": true,
   "guidance": "Respect short-sale restriction and halts; do not fight a one-sided tape (active once US-3 SSR data lands)."},
  {"section": "trend_play", "regime": "trend", "immutable": false,
   "guidance": "Ride the lead runner and first sympathy; add on reclaims; trim into blowoffs; honor the first distribution day."},
  {"section": "ignition_play", "regime": "ignition", "immutable": false,
   "guidance": "Enter the lead runner and the first sympathy ticker on the follow-through day, not the fifth laggard."},
  {"section": "recovery_play", "regime": "recovery", "immutable": false,
   "guidance": "Probe size only, on the first clean gap-and-go survivors and a confirmed day-2 continuation."},
  {"section": "distribution_play", "regime": "distribution", "immutable": false,
   "guidance": "Reduce exposure, raise stops, stop chasing laggards; a leader breakdown on volume means get smaller."},
  {"section": "washout_play", "regime": "washout", "immutable": false,
   "guidance": "Cash is a position. Wait for gappers to hold and a leader to emerge before risking capital."}
]
```

- [ ] **Step 3: Validate both load**

Run: `python -c "import json; from alpha.harness.memory import Lesson; from alpha.harness.doctrine import Doctrine; m=[Lesson.from_seed(x) for x in json.load(open('seeds/memory.json'))]; doc=Doctrine.from_seed_list(json.load(open('seeds/doctrine.json'))); print(len(m),'lessons;', len(doc.immutable_core()),'immutable of', len(doc.entries),'doctrine')"`
Expected: `8 lessons; 7 immutable of 12 doctrine`

- [ ] **Step 4: Commit**

```bash
git add seeds/memory.json seeds/doctrine.json
git commit -m "US-1g Task 4: seed memory (8 lessons) + doctrine (12 entries, 7 immutable red-lines)"
```

---

### Task 5: Seed load + validation test

**Files:**
- Create: `tests/seeds/__init__.py`
- Create: `tests/seeds/test_seed_packs.py`

Loads the real `seeds/` directory into a `HarnessState` and asserts the spec §6 properties (all families present, defense-heavy, canonical phases, immutable red-lines write-protected after load).

- [ ] **Step 1: Write the failing test**

```python
# tests/seeds/__init__.py
```

```python
# tests/seeds/test_seed_packs.py
from pathlib import Path
import pytest
from alpha.harness.loader import load_seeds
from alpha.harness.regime import FAMILIES, CANONICAL_PHASES
from alpha.harness.errors import ImmutableDoctrineError

SEEDS = Path(__file__).resolve().parents[2] / "seeds"


def _h():
    return load_seeds(SEEDS)


def test_seeds_load_into_harness():
    h = _h()
    assert len(h.skills) == 16 and len(h.memory) == 8 and len(h.doctrine.entries) == 12


def test_all_families_represented_in_skills():
    h = _h()
    for fam in FAMILIES:
        assert h.skills.by_family(fam), f"no seed skills for family {fam}"


def test_defense_heavy():
    h = _h()
    detectors = len(h.skills.by_type("failure_detector"))
    patterns = len(h.skills.by_type("pattern"))
    assert detectors > patterns, f"not defense-heavy: {detectors} detectors vs {patterns} patterns"


def test_phases_are_canonical():
    h = _h()
    for s in h.skills.all():
        for p in s.phases:
            assert p in CANONICAL_PHASES, f"{s.skill_id} has non-canonical phase {p}"


def test_immutable_core_present_and_protected():
    h = _h()
    core = h.doctrine.immutable_core()
    assert len(core) == 7
    sections = {e.section for e in core}
    assert {"stop_discipline", "no_chase_risk_off", "one_correlated_bet", "loss_circuit_breaker"} <= sections
    with pytest.raises(ImmutableDoctrineError):           # write-protected after load
        core[0].guidance = "loosen"


def test_squeeze_offense_is_incubating():
    h = _h()
    # offense that needs US-3 data ships incubating (not minted active)
    assert h.skills.get("short_squeeze").status == "incubating"
    assert h.skills.get("gamma_squeeze").status == "incubating"
```

- [ ] **Step 2: Run test to verify it fails, then passes**

Run: `python -m pytest tests/seeds/test_seed_packs.py -q`
Expected: PASS (6 passed) — the seeds exist (Tasks 3-4) and `load_seeds` exists (US-1a). If any assertion FAILS, fix the seed JSON (not the loader) to satisfy the spec §6 properties.

- [ ] **Step 3: Commit**

```bash
git add tests/seeds/__init__.py tests/seeds/test_seed_packs.py
git commit -m "US-1g Task 5: seed-pack validation (families / defense-heavy / canonical / immutable-core)"
```

---

### Task 6: US-1g acceptance gate + docs (US-1 complete)

**Files:**
- Create: `tests/eval/test_us1g_acceptance.py`
- Modify: `docs/PROJECT_STATE.md` (mark US-1g done + US-1 complete)

- [ ] **Step 1: Write the acceptance test**

```python
# tests/eval/test_us1g_acceptance.py
"""US-1g acceptance: a full §4.1 DecisionPackage is constructible (the human-facing action a_t), and
the v1 seed packs load into a harness H that is queryable by family — the substrate US-2's agent
will read (H) and produce (DecisionPackage)."""
from pathlib import Path
from datetime import date
from alpha.eval.decision import (
    Candidate, FillFeasibility, TabooCheck, Portfolio, DecisionPackage,
)
from alpha.harness.loader import load_seeds

SEEDS = Path(__file__).resolve().parents[2] / "seeds"


def test_full_decision_package_round_trips_through_dict():
    dp = DecisionPackage(
        date=date(2026, 6, 12), regime_read="trend; AI frontside",
        candidates=[Candidate(symbol="AI1", name="Alpha AI", pattern="gap_and_go",
                              skill_id="gap_and_go", family="runner", entry="ORB reclaim",
                              exit_stop="lose VWAP", size_tier="core", confidence=0.7,
                              fill_feasibility=FillFeasibility(buyable=True),
                              taboo_check=[TabooCheck(rule="no-chase-risk-off", status="pass")],
                              counterview="drop if AI flips backside")],
        key_risks=["AI leader rolls over"],
        portfolio=Portfolio(total_exposure_budget=0.6, correlated_groups=[["AI1", "AI2"]]),
        human_confirm=None)
    again = DecisionPackage.model_validate(dp.model_dump())   # frozen + serializable round-trip
    assert again.candidates[0].size_tier == "core"
    assert again.portfolio.correlated_groups == [["AI1", "AI2"]]


def test_agent_substrate_ready():
    # the agent (US-2) reads this H and emits a DecisionPackage like the one above
    h = load_seeds(SEEDS)
    runner_skills = h.skills.by_family("runner")
    assert any(s.skill_id == "gap_and_go" for s in runner_skills)
    assert h.doctrine.immutable_core()                      # discipline red-lines present for the agent
```

- [ ] **Step 2: Run the full suite**

Run: `python -m pytest -q`
Expected: PASS — all US-0 + US-1a..f + US-1g tests green.

- [ ] **Step 3: Update `docs/PROJECT_STATE.md`**

Mark **US-1g (seeds v1 + DecisionPackage) done** and **US-1 COMPLETE** with the date and a summary: the full non-LLM substrate is in place — data → PIT/firewall → harness `H=(p,K,M)` + meta-tools + persistence/rollback → eval oracle (return + delist-terminal-loss + exogenous pool) → L1 regime/features → L3 sizing + L4 guard → full DecisionPackage + four defense-heavy seed packs. Set the "Next" pointer to **US-2 (LLM agent + Refiner inner loop)**: per-role LLM clients (Claude/cheap), the agent that reads `H` + state + universe and emits a populated DecisionPackage, the Refiner 4-pass CRUD + credit + retire-discipline, the inner loop with scorer-aware floor-breaker + checkpoint/rollback, and the HCH/Hexpert/Hmin three-way compare to validate on real Alpaca data.

- [ ] **Step 4: Commit**

```bash
git add tests/eval/test_us1g_acceptance.py docs/PROJECT_STATE.md
git commit -m "US-1g Task 6: acceptance gate (full DecisionPackage + seeds into H) + PROJECT_STATE (US-1 complete)"
```

---

## Self-Review (run after writing, fix inline)

**Spec coverage (US-1 "DecisionPackage schema"; §4.1; §6):** full DecisionPackage — per-candidate skill_id/entry/exit_stop/size_tier/fill_feasibility/taboo_check/counterview/family (Task 1) + regime_read/key_risks/portfolio/human_confirm (Task 2) ✓ · four family seed packs (Task 3) ✓ · defense-heavy bias (Tasks 3,5) ✓ · memory + immutable-core doctrine (Task 4) ✓ · load into H + validation (Task 5) ✓ · backward-compatible with US-1d eval (Tasks 1,2) ✓. **Deferred & documented:** agent producing/Refiner editing → US-2; data-dependent seed signals (short/SSR/intraday/earnings) → US-3 (squeezes incubating); state_machine seed → code (`default_us_cycle`).

**Type consistency:** `Candidate`/`DecisionPackage` extended in place (US-1d fields unchanged, new fields optional). `FillFeasibility`/`TabooCheck`/`Portfolio` frozen sub-models. `SizeTier` reused from `alpha.sizing.position`. Seed JSON keys match US-1a `from_seed` (skills: skill_id/name/type/family/phases/trigger/entry/exit_stop/taboo/depends_on/status; memory: lesson_id/phases/family/outcome/failure_signature/named_analog/lesson; doctrine: section/regime/immutable/guidance) — no `extra` keys (extra=forbid). `load_seeds` (US-1a) loads them unchanged. Counts asserted in Task 5 match the authored content (16/8/12, 7 immutable, 10 detectors > 6 patterns).

**Placeholder scan:** no TBD/TODO; every code/seed step shows full content; deferrals are explicit scope notes.

**Scope:** schema + seed content only; no LLM, no agent, no loop. Completes US-1: the full non-LLM substrate US-2 will drive.
