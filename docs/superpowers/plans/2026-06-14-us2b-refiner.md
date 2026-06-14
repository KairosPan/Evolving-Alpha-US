# US-2b Refiner + Evidence Substrate Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the **Refiner** — the component that CRUD-edits the harness `H=(p,K,M)` via the 9 meta-tools, driven by credit assignment from realized eval outcomes, with retire/promote-discipline — plus the **evidence substrate** it consumes (a per-day `Trajectory`, `apply_credit`, failure `signatures`).

**Architecture:** Three new pieces on top of the US-1/US-2a substrate. (1) **Trajectory** (`alpha/eval/trajectory.py`): `WalkForwardEval.walk()` now also captures, per decision day, the `MarketState`, the `DecisionPackage`, the picked symbols' entry snapshots, and (filled at t+horizon) the scored outcomes; `run()` is unchanged behaviorally (delegates to `walk()` + `report_from_trajectory`). (2) **Credit + signatures** (`alpha/refine/credit.py`, `alpha/refine/signatures.py`): `apply_credit` walks the trajectory's scored steps and mutates each matched skill's `SkillStats` **in place** (the observation channel — NOT a meta-tool edit, NOT logged), populating `expectancy = mean advantage` (de-market-beta) and `expectancy_raw = mean raw score`; `extract_signatures` derives US-native "where it lost" tags. (3) **The Refiner** (`alpha/refine/{ops,refiner_prompt,refiner}.py`): a 4-pass (`p`→`G`→`K`→`M`) driver that, per non-empty pass, makes ONE LLM call scoped to that container's tool whitelist, parses ops, and applies each through `MetaTools` behind discipline gates (evidence-gated retire/promote, edit caps, required rationale, reject-don't-crash), returning an audited `RefineReport`.

**Tech Stack:** Python ≥3.11, pydantic v2, pytest. Reuses US-1 harness (`MetaTools`/`HarnessManager`/`SkillStats`), US-1d eval (`ScoredCandidate`/`Scorer`/`WalkForwardEval`/`oracle`), US-2a LLM layer (`LLMClient`/`extract_json_object`/`make_client`). Offline tests use `MockLLMClient`; no network.

**Spec:** `docs/superpowers/specs/2026-06-13-us-market-adaptation-design.md` (§4 inner loop, §6 immutable doctrine, §7 eval/advantage). CN reference (algorithm source, to be reframed US-native): `reference/cn/youzi/refine/{refiner,credit,refiner_prompt,ops,signatures}.py`.

**Scope — US-2 decomposition (refined after mapping the CN structure; supersedes the coarse US-2a note):**
- **US-2a (done):** LLM clients + agent (the "act" half-loop).
- **US-2b (THIS plan):** Refiner + evidence substrate — `Trajectory`/`walk()`, `apply_credit`, `signatures`, the 4-pass `Refiner` with discipline. Produces a Refiner that, given a trajectory's credit + signatures, edits `H` via `MetaTools` with discipline. **Editing happens in place; this slice does NOT checkpoint or roll back.**
- **US-2c (next):** the **InnerLoop** — interleaved walk + online `apply_credit` + checkpoint-before-refine + the **scorer-aware capability-floor breaker** (rolling daily advantage vs early baseline) + rollback-and-rebind / freeze. (CN `loop/inner_loop.py`.) This is where checkpoint/rollback enter.
- **US-2d:** the three-way **HCH/Hexpert/Hmin** compare + the honest statistical bar (HCH ≥ Hexpert OOS, multi-seed, temp=0). (CN `loop/compare.py`.)
- **Later:** wire L3 sizing / L4 guard into the agent's `DecisionPackage` (size_tier/fill_feasibility/taboo_check); master-dispatch G sub-agents (the `G`-pass is a reserved no-op until then).

**Why this slice boundary:** the dependency chain is trajectory → credit/signatures → refiner → loop → compare; each is independently testable; CN itself shipped these as separate phases (1b-1, 1b-2, 1b-3a/b/d). Bundling the loop+breaker+rollback would double the plan and mis-layer the design (the CN Refiner explicitly does NOT checkpoint/rollback).

**Conventions:** all code/comments English; `from __future__ import annotations` atop every module; commit after each passing task; run via `python -m pytest`.

**Key invariants (each gets a test):**
1. `walk()` returns a `Trajectory` whose scored steps carry the realized `ScoredCandidate` outcomes; `run()` is behaviorally unchanged (the full pre-existing suite stays green).
2. `apply_credit` mutates matched skills' `SkillStats` **in place** — `expectancy` is mean **advantage**, `expectancy_raw` is mean raw score, `nukes` counts `outcome=="nuked"`, EWMA winrate via `record()`; unmatched patterns go to an `__unattributed__` bucket (evidence never silently dropped). It is **cumulative** (called once per trajectory).
3. The Refiner edits `H` **only** through `MetaTools`; an op naming a tool outside its pass, with an empty rationale, or failing the evidence gate is a `RejectedEdit` that leaves `H` unchanged and logs nothing.
4. **Retire-discipline:** `retire_skill` is rejected when `skill.stats.n < min_retire_samples`. **Promote-discipline:** `promote_skill` is rejected when `n < min_promote_samples` or `expectancy <= 0`. Both gates only READ stats.
5. The 4-pass driver runs `('p','G','K','M')` in order; `G` is a reserved **no-op** (no LLM call, a note); a refine makes exactly **3** live LLM calls (p/K/M). Edit caps (per-pass / per-refine) and the `_recent_reports` edit-history feedback hold.

---

### Task 1: Trajectory primitives

**Files:**
- Create: `alpha/eval/trajectory.py`
- Create: `tests/eval/test_trajectory.py`

`TrajectoryStep` records one decision day; `Trajectory` collects them; `report_from_trajectory` rebuilds the existing `EvalReport`. It lives in `trajectory.py` (not `metrics.py`) because it consumes `Trajectory` — putting it in `metrics.py` would force a `metrics → trajectory` import, the direction that *would* create a cycle (`trajectory.py` already imports `build_report`/`EvalReport` from `metrics.py`).

- [ ] **Step 1: Write the failing test**

```python
# tests/eval/test_trajectory.py
from datetime import date, datetime
from alpha.state.market import MarketState
from alpha.universe.stock import StockSnapshot
from alpha.eval.decision import Candidate, DecisionPackage
from alpha.eval.metrics import ScoredCandidate
from alpha.eval.trajectory import TrajectoryStep, Trajectory, report_from_trajectory


def _state(d=date(2026, 6, 12)):
    return MarketState(date=d, gainer_count=1, gap_up_count=0, loser_count=0,
                       failed_breakout_count=0, max_runner_tier=2, echelon=[], breadth_raw=1.0,
                       as_of=datetime(d.year, d.month, d.day, 16, 0))


def _step(d, scored, sym="RUN", outcome="continued"):
    dec = DecisionPackage(date=d, candidates=[Candidate(symbol=sym, pattern="gap_and_go")])
    entries = {sym: StockSnapshot(symbol=sym, name="Runner", status="gainer", consecutive_up_days=3)}
    outcomes = ({sym: ScoredCandidate(decision_date=d, symbol=sym, pattern="gap_and_go",
                                      outcome=outcome, score=0.3, day_baseline=0.1)} if scored else {})
    return TrajectoryStep(date=d, market=_state(d), decision=dec, entries=entries,
                          outcomes=outcomes, scored=scored)


def test_scored_steps_filters():
    traj = Trajectory(steps=[_step(date(2026, 6, 10), True), _step(date(2026, 6, 12), False)])
    assert [s.date for s in traj.scored_steps()] == [date(2026, 6, 10)]
    assert len(traj.all_scored()) == 1 and traj.all_scored()[0].advantage == 0.3 - 0.1


def test_report_from_trajectory_counts():
    traj = Trajectory(steps=[
        _step(date(2026, 6, 10), True),
        TrajectoryStep(date=date(2026, 6, 11), market=_state(date(2026, 6, 11)),
                       decision=DecisionPackage(date=date(2026, 6, 11)), scored=True),   # no-trade, scored
        _step(date(2026, 6, 12), False),                                                  # unscored tail
    ])
    rep = report_from_trajectory(traj, horizon=2)
    assert rep.n_decisions == 3 and rep.n_no_trade == 1 and rep.n_candidates == 1
    assert rep.hit_rate == 1.0


def test_step_is_frozen():
    import pytest
    s = _step(date(2026, 6, 10), True)
    with pytest.raises(Exception):
        s.scored = False
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/eval/test_trajectory.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'alpha.eval.trajectory'`

- [ ] **Step 3: Write minimal implementation**

```python
# alpha/eval/trajectory.py
from __future__ import annotations

from datetime import date as Date

from pydantic import BaseModel, ConfigDict, Field

from alpha.eval.decision import DecisionPackage
from alpha.eval.metrics import ScoredCandidate, build_report, EvalReport
from alpha.state.market import MarketState
from alpha.universe.stock import StockSnapshot


class TrajectoryStep(BaseModel):
    """One decision day's full record. `outcomes` is empty until the decision is scored at t+horizon;
    `scored` marks that the step reached its exit day (the last `horizon` steps never do)."""
    model_config = ConfigDict(frozen=True)
    date: Date
    market: MarketState
    decision: DecisionPackage
    entries: dict[str, StockSnapshot] = Field(default_factory=dict)     # picked symbol -> decision-day snapshot
    outcomes: dict[str, ScoredCandidate] = Field(default_factory=dict)  # symbol -> realized scored outcome
    scored: bool = False


class Trajectory(BaseModel):
    """The ordered per-day record of one walk. Read-only evidence the Refiner consumes."""
    model_config = ConfigDict(frozen=True)
    steps: list[TrajectoryStep] = Field(default_factory=list)

    def scored_steps(self) -> list[TrajectoryStep]:
        return [s for s in self.steps if s.scored]

    def all_scored(self) -> list[ScoredCandidate]:
        return [sc for s in self.scored_steps() for sc in s.outcomes.values()]


def report_from_trajectory(traj: Trajectory, horizon: int = 2) -> EvalReport:
    """Aggregate a Trajectory into the same EvalReport WalkForwardEval.run() always produced:
    n_decisions over all steps, n_no_trade over decisions with no candidates, scored over scored steps."""
    scored = traj.all_scored()
    n_no_trade = sum(1 for s in traj.steps if not s.decision.candidates)
    return build_report(scored, n_decisions=len(traj.steps), n_no_trade=n_no_trade, horizon=horizon)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/eval/test_trajectory.py -q`
Expected: PASS (3 passed)

- [ ] **Step 5: Commit**

```bash
git add alpha/eval/trajectory.py tests/eval/test_trajectory.py
git commit -m "US-2b Task 1: Trajectory primitives (TrajectoryStep/Trajectory/report_from_trajectory)"
```

---

### Task 2: `WalkForwardEval.walk()` + `run()` delegates

**Files:**
- Modify: `alpha/eval/walk_forward.py`
- Create: `tests/eval/test_walk_trajectory.py`

Add `walk(policy) -> Trajectory` capturing per-step structure; make `run()` delegate so existing behavior (and the whole suite) is preserved.

- [ ] **Step 1: Write the failing test**

```python
# tests/eval/test_walk_trajectory.py
from datetime import date
import pandas as pd
from alpha.data.source import FakeSource
from alpha.eval.walk_forward import WalkForwardEval
from alpha.eval.scorer import ReturnScorer
from alpha.eval.baselines import ChaseBiggestGainerPolicy
from alpha.eval.trajectory import Trajectory, report_from_trajectory


def _source():
    cal = [date(2026, 6, 10), date(2026, 6, 11), date(2026, 6, 12), date(2026, 6, 15)]
    rows = {date(2026, 6, 10): [("RUN", 14.0, 10.0)], date(2026, 6, 11): [("RUN", 18.0, 14.0)],
            date(2026, 6, 12): [("RUN", 17.0, 18.0)], date(2026, 6, 15): [("RUN", 20.0, 17.0)]}
    snaps = {d: pd.DataFrame({"symbol": ["RUN"], "name": ["RUN"], "open": [r[2] for r in v],
                              "high": [r[1] for r in v], "low": [r[2] for r in v], "close": [r[1] for r in v],
                              "volume": [1], "prev_close": [r[2] for r in v]}) for d, v in rows.items()}
    bars = {"RUN": pd.DataFrame({"date": cal, "open": [10.0, 14.0, 18.0, 17.0], "high": [14, 18, 18, 20],
                                 "low": [10, 14, 17, 17], "close": [14.0, 18.0, 17.0, 20.0], "volume": [1, 1, 1, 1]})}
    return FakeSource(calendar=cal, bars=bars, snapshots=snaps)


def test_walk_returns_trajectory_with_scored_outcomes():
    wf = WalkForwardEval(_source(), date(2026, 6, 10), date(2026, 6, 15), horizon=2, scorer=ReturnScorer())
    traj = wf.walk(ChaseBiggestGainerPolicy())
    assert isinstance(traj, Trajectory) and len(traj.steps) == 4
    # horizon=2 over 4 days -> decisions 0,1 scored; last 2 unscored
    assert [s.scored for s in traj.steps] == [True, True, False, False]
    assert traj.scored_steps()[0].outcomes                      # day-0 decision has a realized outcome


def test_run_equals_report_from_walk():
    wf = WalkForwardEval(_source(), date(2026, 6, 10), date(2026, 6, 15), horizon=2, scorer=ReturnScorer())
    pol = ChaseBiggestGainerPolicy()
    report = wf.run(pol)
    traj = wf.walk(pol)
    rebuilt = report_from_trajectory(traj, horizon=2)
    assert (report.n_decisions, report.n_candidates, report.n_no_trade) == \
           (rebuilt.n_decisions, rebuilt.n_candidates, rebuilt.n_no_trade)
    assert report.mean_score == rebuilt.mean_score and report.hit_rate == rebuilt.hit_rate
    assert report.n_decisions == 4 and report.n_candidates == 2          # absolute pin (not just self-consistency)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/eval/test_walk_trajectory.py -q`
Expected: FAIL — `AttributeError: 'WalkForwardEval' object has no attribute 'walk'`

- [ ] **Step 3: Write the implementation**

Replace the `run` method in `alpha/eval/walk_forward.py` with `walk` + a delegating `run`. New imports at top (add to the existing import block):

```python
from alpha.eval.trajectory import Trajectory, TrajectoryStep, report_from_trajectory
```

Replace the existing `def run(self, policy):` method body with:

```python
    def walk(self, policy: DecisionPolicy) -> Trajectory:
        """Forward-replay capturing the full per-day record (the Refiner's evidence). Same scoring as
        run(): decision j enters days[j+1] open, exits days[j+horizon] close; last `horizon` unscored."""
        days = trading_days_between(self._source.trading_calendar(), self._start, self._end)
        record = PoolRecord()
        decisions: list = []
        markets: list = []
        universes: list = []
        scored_by_day: dict = {}
        for i, cursor in enumerate(days):
            guarded = GuardedSource(self._source, AsOfGuard(cursor))
            universe = build_universe(guarded, cursor)
            state = build_market_state(universe, cursor,
                                       as_of=DateTime(cursor.year, cursor.month, cursor.day, 16, 0))
            record.record(cursor, classify_day(guarded.daily_snapshot(cursor)))
            decision = policy.decide(state, universe)
            decisions.append(decision); markets.append(state); universes.append(universe)
            j = i - self._horizon
            if j >= 0:
                sc_list = self._score(decisions[j], days, j, cursor, record)
                scored_by_day[days[j]] = {sc.symbol: sc for sc in sc_list}
        n = len(days)
        steps: list[TrajectoryStep] = []
        for i, cursor in enumerate(days):
            uni = universes[i]
            entries = {c.symbol: snap for c in decisions[i].candidates
                       if (snap := uni.get(c.symbol)) is not None}
            steps.append(TrajectoryStep(date=cursor, market=markets[i], decision=decisions[i],
                                        entries=entries, outcomes=scored_by_day.get(cursor, {}),
                                        scored=(i <= n - 1 - self._horizon)))
        return Trajectory(steps=steps)

    def run(self, policy: DecisionPolicy) -> EvalReport:
        return report_from_trajectory(self.walk(policy), horizon=self._horizon)
```

(`EvalReport`/`build_report`/`ScoredCandidate` are already imported in this module; `DateTime` and `_score` already exist.)

- [ ] **Step 4: Run the focused test + the full eval suite (equivalence)**

Run: `python -m pytest tests/eval/test_walk_trajectory.py tests/eval -q`
Expected: PASS — new tests pass AND all pre-existing eval/walk-forward tests stay green (run() unchanged behaviorally).

- [ ] **Step 5: Commit**

```bash
git add alpha/eval/walk_forward.py tests/eval/test_walk_trajectory.py
git commit -m "US-2b Task 2: WalkForwardEval.walk() -> Trajectory; run() delegates (behavior preserved)"
```

---

### Task 3: Credit assignment

**Files:**
- Create: `alpha/refine/__init__.py`
- Create: `alpha/refine/credit.py`
- Create: `tests/refine/__init__.py`
- Create: `tests/refine/test_credit.py`

`apply_credit` mutates matched skills' `SkillStats` in place (cumulative) and returns an incremental `CreditReport`; `merge_credit_reports` merges window increments read-only; `resolve_skill` maps a free-text pattern to a skill.

- [ ] **Step 1: Write the failing test**

```python
# tests/refine/__init__.py
```

```python
# tests/refine/test_credit.py
from datetime import date, datetime
from alpha.harness.skill import Skill, SkillStats
from alpha.harness.doctrine import Doctrine
from alpha.harness.registry import SkillRegistry, MemoryStore
from alpha.harness.state import HarnessState
from alpha.state.market import MarketState
from alpha.eval.decision import Candidate, DecisionPackage
from alpha.eval.metrics import ScoredCandidate
from alpha.eval.trajectory import TrajectoryStep, Trajectory
from alpha.refine.credit import apply_credit, merge_credit_reports, resolve_skill, UNATTRIBUTED


def _h():
    skills = SkillRegistry.from_skills([
        Skill(skill_id="gap_and_go", name="Gap and Go", type="pattern", status="active"),
    ])
    return HarnessState(doctrine=Doctrine(), skills=skills, memory=MemoryStore.from_lessons([]))


def _mkt(d):
    return MarketState(date=d, gainer_count=1, gap_up_count=0, loser_count=0, failed_breakout_count=0,
                       max_runner_tier=1, echelon=[], breadth_raw=1.0, as_of=datetime(d.year, d.month, d.day, 16, 0))


def _step(d, pattern, outcome, score, baseline):
    sc = ScoredCandidate(decision_date=d, symbol="RUN", pattern=pattern, outcome=outcome,
                         score=score, day_baseline=baseline)
    dec = DecisionPackage(date=d, candidates=[Candidate(symbol="RUN", pattern=pattern)])
    return TrajectoryStep(date=d, market=_mkt(d), decision=dec, outcomes={"RUN": sc}, scored=True)


def test_resolve_skill_cascade():
    h = _h()
    assert resolve_skill("gap_and_go", h).skill_id == "gap_and_go"      # exact id
    assert resolve_skill("  GAP_AND_GO ", h).skill_id == "gap_and_go"   # normalized
    assert resolve_skill("Gap and Go", h).skill_id == "gap_and_go"      # by name
    assert resolve_skill("ghost", h) is None and resolve_skill("", h) is None


def test_apply_credit_mutates_stats_in_place():
    h = _h()
    traj = Trajectory(steps=[
        _step(date(2026, 6, 10), "gap_and_go", "continued", 0.30, 0.10),   # win, advantage 0.20
        _step(date(2026, 6, 11), "gap_and_go", "nuked", -0.50, 0.10),      # loss+nuke, advantage -0.60
    ])
    rep = apply_credit(traj, h)
    st = h.skills.get("gap_and_go").stats
    assert st.n == 2 and st.wins == 1 and st.losses == 1 and st.nukes == 1
    assert abs(st.expectancy - (-0.20)) < 1e-9          # mean advantage = (0.20 + -0.60)/2
    assert abs(st.expectancy_raw - (-0.10)) < 1e-9      # mean raw score = (0.30 + -0.50)/2
    assert st.ewma_winrate is not None
    assert rep.per_skill["gap_and_go"].n == 2 and rep.n_scored == 2
    assert rep.per_skill["gap_and_go"].nuke_rate == 0.5


def test_unattributed_bucket():
    h = _h()
    traj = Trajectory(steps=[_step(date(2026, 6, 10), "hallucinated", "faded", 0.0, 0.0)])
    rep = apply_credit(traj, h)
    assert rep.per_skill == {} and rep.unattributed is not None
    assert rep.unattributed.skill_id == UNATTRIBUTED and rep.unattributed.n == 1


def test_merge_is_readonly_and_additive():
    h = _h()
    r1 = apply_credit(Trajectory(steps=[_step(date(2026, 6, 10), "gap_and_go", "continued", 0.4, 0.1)]), h)
    n_after_first = h.skills.get("gap_and_go").stats.n
    merged = merge_credit_reports([r1, r1])                 # merge does NOT touch H stats
    assert h.skills.get("gap_and_go").stats.n == n_after_first   # unchanged by merge
    assert merged.per_skill["gap_and_go"].n == 2 and merged.n_scored == 2
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/refine/test_credit.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'alpha.refine'`

- [ ] **Step 3: Write minimal implementation**

```python
# alpha/refine/__init__.py
```

```python
# alpha/refine/credit.py
from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from alpha.eval.trajectory import Trajectory
from alpha.harness.skill import Skill
from alpha.harness.state import HarnessState

UNATTRIBUTED = "__unattributed__"


def resolve_skill(pattern: str, h: HarnessState) -> Skill | None:
    """Map a policy-declared (free-text) pattern to a skill: exact id, then normalized id, then name."""
    if not pattern:
        return None
    direct = h.skills.get(pattern)
    if direct is not None:
        return direct
    key = pattern.strip().casefold()
    if not key:
        return None
    for s in h.skills.all():
        if s.skill_id.strip().casefold() == key or s.name.strip().casefold() == key:
            return s
    return None


class SkillCredit(BaseModel):
    """Per-skill incremental credit for one window (read-only; H stats are the cumulative truth)."""
    model_config = ConfigDict(frozen=True)
    skill_id: str
    n: int = 0
    wins: int = 0
    losses: int = 0
    nukes: int = 0
    hit_rate: float = 0.0
    nuke_rate: float = 0.0
    expectancy: float = 0.0       # mean advantage (de-market-beta excess)
    expectancy_raw: float = 0.0   # mean raw score


class CreditReport(BaseModel):
    model_config = ConfigDict(frozen=True)
    per_skill: dict[str, SkillCredit] = Field(default_factory=dict)
    unattributed: SkillCredit | None = None
    n_scored: int = 0


class _Acc:
    __slots__ = ("skill_id", "n", "wins", "losses", "nukes", "adv_sum", "score_sum")

    def __init__(self, skill_id: str) -> None:
        self.skill_id = skill_id
        self.n = self.wins = self.losses = self.nukes = 0
        self.adv_sum = 0.0
        self.score_sum = 0.0

    def add(self, win: bool, nuked: bool, advantage: float, score: float) -> None:
        self.n += 1
        self.wins += int(win)
        self.losses += int(not win)
        self.nukes += int(nuked)
        self.adv_sum += advantage
        self.score_sum += score

    def absorb(self, c: SkillCredit) -> None:
        self.n += c.n
        self.wins += c.wins
        self.losses += c.losses
        self.nukes += c.nukes
        self.adv_sum += c.expectancy * c.n
        self.score_sum += c.expectancy_raw * c.n

    def to_credit(self) -> SkillCredit:
        d = self.n or 1
        return SkillCredit(skill_id=self.skill_id, n=self.n, wins=self.wins, losses=self.losses,
                           nukes=self.nukes, hit_rate=self.wins / d, nuke_rate=self.nukes / d,
                           expectancy=self.adv_sum / d, expectancy_raw=self.score_sum / d)


def apply_credit(traj: Trajectory, h: HarnessState, decay: float = 0.1) -> CreditReport:
    """Walk the scored steps and update each matched skill's SkillStats IN PLACE (observation channel,
    NOT a meta-tool edit, NOT logged). CONTRACT: call once per trajectory; re-calling on the SAME
    trajectory double-counts. Calling on successive DISJOINT trajectories is the intended cumulative
    online path (US-2c) and keeps the running mean correct (n and the means co-evolve).
    expectancy = running mean ADVANTAGE; expectancy_raw = running mean raw score."""
    accs: dict[str, _Acc] = {}
    unattr = _Acc(UNATTRIBUTED)
    n_scored = 0
    for step in traj.scored_steps():
        for sc in step.outcomes.values():
            n_scored += 1
            win = sc.outcome == "continued"
            nuked = sc.outcome == "nuked"
            skill = resolve_skill(sc.pattern, h)
            if skill is None:
                unattr.add(win, nuked, sc.advantage, sc.score)
                continue
            st = skill.stats
            st.record(win, decay)                       # n/wins/losses/ewma_winrate
            nn = st.n
            prev_e = st.expectancy or 0.0
            prev_er = st.expectancy_raw or 0.0
            st.expectancy = prev_e + (sc.advantage - prev_e) / nn      # Welford running mean (advantage)
            st.expectancy_raw = prev_er + (sc.score - prev_er) / nn    # Welford running mean (raw)
            if nuked:
                st.nukes += 1
            accs.setdefault(skill.skill_id, _Acc(skill.skill_id)).add(win, nuked, sc.advantage, sc.score)
    return CreditReport(per_skill={sid: a.to_credit() for sid, a in accs.items()},
                        unattributed=(unattr.to_credit() if unattr.n else None), n_scored=n_scored)


def merge_credit_reports(reports: list[CreditReport]) -> CreditReport:
    """Read-only merge of incremental reports for a refine window. Does NOT touch H stats."""
    accs: dict[str, _Acc] = {}
    unattr = _Acc(UNATTRIBUTED)
    n_scored = 0
    for r in reports:
        n_scored += r.n_scored
        for sid, c in r.per_skill.items():
            accs.setdefault(sid, _Acc(sid)).absorb(c)
        if r.unattributed:
            unattr.absorb(r.unattributed)
    return CreditReport(per_skill={sid: a.to_credit() for sid, a in accs.items()},
                        unattributed=(unattr.to_credit() if unattr.n else None), n_scored=n_scored)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/refine/test_credit.py -q`
Expected: PASS (4 passed)

- [ ] **Step 5: Commit**

```bash
git add alpha/refine/__init__.py alpha/refine/credit.py tests/refine/__init__.py tests/refine/test_credit.py
git commit -m "US-2b Task 3: credit assignment (apply_credit in-place Welford on advantage; merge; resolve_skill)"
```

---

### Task 4: Failure signatures

**Files:**
- Create: `alpha/refine/signatures.py`
- Create: `tests/refine/test_signatures.py`

US-native failure tags (no CN 连板 vocabulary): `faded_miss` (idle, not a loss), and for nukes — `chased_blowoff` (chased a top-tier extended runner), `weak_laggard_nuke` (took a non-leader), `generic_nuke` (entry tier unknown). Continued outcomes produce NO signature.

**Known limitation (documented, not a bug — no silent cap):** on real US-2b walks the entry snapshots come from `build_universe`, which does not yet populate `consecutive_up_days`, and `build_market_state` over that universe yields `max_runner_tier=0` (see the `state/builder.py` NOTE — multi-day-runner detection is a later enrichment). So on live trajectories every nuke currently resolves to `generic_nuke`; the `chased_blowoff`/`weak_laggard_nuke` discrimination is implemented and unit-tested with hand-built snapshots and goes live once runner-tier enrichment threads `consecutive_up_days`/`max_runner_tier` into the trajectory (US-2c/US-3). It degrades to a coarser-but-correct label, never a wrong one.

- [ ] **Step 1: Write the failing test**

```python
# tests/refine/test_signatures.py
from datetime import date, datetime
from alpha.harness.skill import Skill
from alpha.harness.doctrine import Doctrine
from alpha.harness.registry import SkillRegistry, MemoryStore
from alpha.harness.state import HarnessState
from alpha.state.market import MarketState
from alpha.universe.stock import StockSnapshot
from alpha.eval.decision import Candidate, DecisionPackage
from alpha.eval.metrics import ScoredCandidate
from alpha.eval.trajectory import TrajectoryStep, Trajectory
from alpha.refine.signatures import extract_signatures


def _h():
    skills = SkillRegistry.from_skills([Skill(skill_id="gap_and_go", name="Gap and Go", type="pattern")])
    return HarnessState(doctrine=Doctrine(), skills=skills, memory=MemoryStore.from_lessons([]))


def _step(d, outcome, cud, max_tier):
    sc = ScoredCandidate(decision_date=d, symbol="RUN", pattern="gap_and_go", outcome=outcome,
                         score=(-0.5 if outcome == "nuked" else 0.0), day_baseline=0.0)
    snap = StockSnapshot(symbol="RUN", name="Runner", status="gainer", consecutive_up_days=cud)
    mkt = MarketState(date=d, gainer_count=1, gap_up_count=0, loser_count=0, failed_breakout_count=0,
                      max_runner_tier=max_tier, echelon=[], breadth_raw=1.0,
                      as_of=datetime(d.year, d.month, d.day, 16, 0))
    dec = DecisionPackage(date=d, candidates=[Candidate(symbol="RUN", pattern="gap_and_go")])
    return TrajectoryStep(date=d, market=mkt, decision=dec, entries={"RUN": snap},
                          outcomes={"RUN": sc}, scored=True)


def _kinds(steps):
    return [s.kind for s in extract_signatures(Trajectory(steps=steps), _h())]


def test_continued_produces_no_signature():
    assert _kinds([_step(date(2026, 6, 10), "continued", 3, 3)]) == []


def test_faded_is_idle_miss():
    sigs = extract_signatures(Trajectory(steps=[_step(date(2026, 6, 10), "faded", 1, 3)]), _h())
    assert [s.kind for s in sigs] == ["faded_miss"] and sigs[0].skill_id == "gap_and_go"


def test_nuke_taxonomy():
    assert _kinds([_step(date(2026, 6, 10), "nuked", 3, 3)]) == ["chased_blowoff"]      # cud >= max_tier
    assert _kinds([_step(date(2026, 6, 11), "nuked", 1, 3)]) == ["weak_laggard_nuke"]   # cud < max_tier
    assert _kinds([_step(date(2026, 6, 12), "nuked", None, 3)]) == ["generic_nuke"]     # tier unknown
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/refine/test_signatures.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'alpha.refine.signatures'`

- [ ] **Step 3: Write minimal implementation**

```python
# alpha/refine/signatures.py
from __future__ import annotations

from datetime import date as Date
from typing import Literal

from pydantic import BaseModel, ConfigDict

from alpha.eval.trajectory import Trajectory
from alpha.harness.state import HarnessState
from alpha.refine.credit import resolve_skill

FailureKind = Literal["chased_blowoff", "weak_laggard_nuke", "generic_nuke", "faded_miss"]


class FailureSignature(BaseModel):
    """Deterministic, read-only 'where it lost' tag for one non-continued scored pick."""
    model_config = ConfigDict(frozen=True)
    date: Date
    symbol: str
    pattern: str
    skill_id: str | None
    kind: FailureKind
    score: float
    evidence: str


def extract_signatures(traj: Trajectory, h: HarnessState) -> list[FailureSignature]:
    """Per non-continued scored pick, classify the failure. Continued (win) -> no signature.
    nuked split by entry context: chased a top-tier extended runner vs took a laggard."""
    sigs: list[FailureSignature] = []
    for step in traj.scored_steps():
        max_tier = step.market.max_runner_tier
        for sym, sc in step.outcomes.items():
            if sc.outcome == "continued":
                continue
            skill = resolve_skill(sc.pattern, h)
            skill_id = skill.skill_id if skill is not None else None
            if sc.outcome == "faded":
                kind: FailureKind = "faded_miss"
                ev = "no follow-through (idle, score 0 — not a loss)"
            else:  # nuked
                snap = step.entries.get(sym)
                cud = snap.consecutive_up_days if snap is not None else None
                if cud is None or max_tier <= 0:
                    kind, ev = "generic_nuke", "nuked; entry runner-tier unknown"
                elif cud >= max_tier:
                    kind, ev = "chased_blowoff", f"chased a top runner (up_days {cud} >= max_tier {max_tier}) into a nuke"
                else:
                    kind, ev = "weak_laggard_nuke", f"took a laggard (up_days {cud} < max_tier {max_tier}); dumped"
            sigs.append(FailureSignature(date=step.date, symbol=sym, pattern=sc.pattern,
                                         skill_id=skill_id, kind=kind, score=sc.score, evidence=ev))
    return sigs
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/refine/test_signatures.py -q`
Expected: PASS (3 passed)

- [ ] **Step 5: Commit**

```bash
git add alpha/refine/signatures.py tests/refine/test_signatures.py
git commit -m "US-2b Task 4: failure signatures (US-native: faded_miss / chased_blowoff / weak_laggard_nuke / generic_nuke)"
```

---

### Task 5: Refine ops (passes + parser)

**Files:**
- Create: `alpha/refine/ops.py`
- Create: `tests/refine/test_ops.py`

The 4-pass taxonomy + per-pass tool whitelist + robust op parsing (reusing the US-2a `extract_json_object`).

- [ ] **Step 1: Write the failing test**

```python
# tests/refine/test_ops.py
from alpha.refine.ops import PASS_ORDER, PASS_TOOLS, RefineOp, parse_ops


def test_pass_structure():
    assert PASS_ORDER == ("p", "G", "K", "M")
    assert PASS_TOOLS["G"] == frozenset()                        # G is a reserved no-op
    assert PASS_TOOLS["p"] == frozenset({"rewrite_doctrine"})
    assert "promote_skill" in PASS_TOOLS["K"] and "retire_skill" in PASS_TOOLS["K"]
    assert PASS_TOOLS["M"] == frozenset({"process_memory", "update_memory", "demote_memory"})
    # every non-G tool is a real MetaTools method
    from alpha.harness.metatools import MetaTools
    for tools in PASS_TOOLS.values():
        for t in tools:
            assert hasattr(MetaTools, t)


def test_parse_ops_valid():
    raw = ('prose {"ops": [{"tool": "retire_skill", "args": {"skill_id": "x"}, "rationale": "decayed"}, '
           '{"tool": "promote_skill", "args": {"skill_id": "y"}}]} tail')
    ops = parse_ops(raw)
    assert [o.tool for o in ops] == ["retire_skill", "promote_skill"]
    assert ops[0].args == {"skill_id": "x"} and ops[0].rationale == "decayed"
    assert ops[1].rationale == ""                                # missing rationale defaults to ''


def test_parse_ops_robust():
    assert parse_ops("no json") == []
    assert parse_ops('{"ops": "notalist"}') == []
    assert parse_ops('{"ops": 5}') == []          # non-iterable ops must not crash (reject-don't-crash)
    # drops malformed items (non-dict, missing/blank tool, non-dict args) but keeps the good one
    raw = '{"ops": [1, {"args": {}}, {"tool": ""}, {"tool": "x", "args": 5}, {"tool": "promote_skill"}]}'
    assert [o.tool for o in parse_ops(raw)] == ["promote_skill"]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/refine/test_ops.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'alpha.refine.ops'`

- [ ] **Step 3: Write minimal implementation**

```python
# alpha/refine/ops.py
from __future__ import annotations

import json
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from alpha.llm.extract import extract_json_object

PassKind = Literal["p", "G", "K", "M"]
PASS_ORDER: tuple[PassKind, ...] = ("p", "G", "K", "M")

# Per-pass tool whitelist. G is a RESERVED no-op (no tools, no LLM call) until G sub-agents exist.
PASS_TOOLS: dict[PassKind, frozenset[str]] = {
    "p": frozenset({"rewrite_doctrine"}),
    "G": frozenset(),
    "K": frozenset({"write_skill", "patch_skill", "retire_skill", "revive_skill", "promote_skill"}),
    "M": frozenset({"process_memory", "update_memory", "demote_memory"}),
}


class RefineOp(BaseModel):
    """One proposed edit from the Refiner LLM (validated/applied later, behind discipline gates)."""
    model_config = ConfigDict(frozen=True)
    tool: str
    args: dict = Field(default_factory=dict)
    rationale: str = ""


def parse_ops(raw: str) -> list[RefineOp]:
    """Pull {"ops": [...]} from prose/fenced/thinking-prefixed LLM text; drop malformed items.
    Any structural failure yields []. Empty rationale is kept as '' (rejected later at apply time)."""
    extracted = extract_json_object(raw)
    if extracted is None:
        return []
    try:
        data = json.loads(extracted)
    except (json.JSONDecodeError, ValueError):
        return []
    if not isinstance(data, dict):
        return []
    raw_ops = data.get("ops")
    if not isinstance(raw_ops, list):       # non-list ops (5, "x", {}) -> no edits (reject-don't-crash)
        return []
    ops: list[RefineOp] = []
    for item in raw_ops:
        if not isinstance(item, dict):
            continue
        tool = item.get("tool")
        if not isinstance(tool, str) or not tool.strip():
            continue
        args = item.get("args")
        if args is None:
            args = {}
        elif not isinstance(args, dict):
            continue
        rationale = item.get("rationale")
        if not isinstance(rationale, str):
            rationale = ""
        ops.append(RefineOp(tool=tool, args=args, rationale=rationale))
    return ops
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/refine/test_ops.py -q`
Expected: PASS (3 passed)

- [ ] **Step 5: Commit**

```bash
git add alpha/refine/ops.py tests/refine/test_ops.py
git commit -m "US-2b Task 5: refine ops (4-pass taxonomy + whitelist + robust parse_ops)"
```

---

### Task 6: Refiner prompts

**Files:**
- Create: `alpha/refine/refiner_prompt.py`
- Create: `tests/refine/test_refiner_prompt.py`

`build_refiner_system_prompt(h, pass_kind, ...)` — per-pass role + tool schema + discipline + current-H slice + immutable red-lines + strict-JSON output contract. `build_refiner_user_prompt(traj, credit, signatures, ...)` — shared evidence + the edit-history feedback block.

- [ ] **Step 1: Write the failing test**

```python
# tests/refine/test_refiner_prompt.py
from datetime import date, datetime
from alpha.harness.skill import Skill, SkillStats
from alpha.harness.doctrine import Doctrine
from alpha.harness.registry import SkillRegistry, MemoryStore
from alpha.harness.state import HarnessState
from alpha.state.market import MarketState
from alpha.eval.decision import Candidate, DecisionPackage
from alpha.eval.metrics import ScoredCandidate
from alpha.eval.trajectory import TrajectoryStep, Trajectory
from alpha.refine.credit import apply_credit
from alpha.refine.signatures import extract_signatures
from alpha.refine.refiner_prompt import build_refiner_system_prompt, build_refiner_user_prompt


def _h():
    skills = SkillRegistry.from_skills([
        Skill(skill_id="gap_and_go", name="Gap and Go", type="pattern", status="active"),
    ])
    doctrine = Doctrine.from_seed_list([
        {"section": "stop_discipline", "regime": "all", "immutable": True, "guidance": "honor the stop"},
        {"section": "trend_play", "regime": "trend", "immutable": False, "guidance": "ride the leader"},
    ])
    return HarnessState(doctrine=doctrine, skills=skills, memory=MemoryStore.from_lessons([]))


def test_system_prompt_p_pass():
    sp = build_refiner_system_prompt(_h(), "p", min_retire_samples=5, min_promote_samples=3)
    assert "rewrite_doctrine" in sp and "trend_play" in sp
    assert "stop_discipline" in sp and "immutable" in sp.lower()       # red-lines shown read-only
    assert '"ops"' in sp                                                # output contract


def test_system_prompt_k_pass_discipline():
    sp = build_refiner_system_prompt(_h(), "K", min_retire_samples=5, min_promote_samples=3)
    assert "retire_skill" in sp and "promote_skill" in sp
    assert "5" in sp and "3" in sp                                      # injected thresholds
    assert "faded" in sp.lower() and "whole-field replace" in sp.lower()
    assert "rewrite_doctrine" not in sp                                 # K-pass shows only K tools


def test_user_prompt_renders_evidence_and_history():
    h = _h()
    d = date(2026, 6, 10)
    sc = ScoredCandidate(decision_date=d, symbol="RUN", pattern="gap_and_go", outcome="nuked",
                         score=-0.5, day_baseline=0.0)
    from alpha.universe.stock import StockSnapshot
    step = TrajectoryStep(date=d, market=MarketState(date=d, gainer_count=1, gap_up_count=0, loser_count=0,
                          failed_breakout_count=0, max_runner_tier=1, echelon=[], breadth_raw=1.0,
                          as_of=datetime(2026, 6, 10, 16, 0)),
                          decision=DecisionPackage(date=d, candidates=[Candidate(symbol="RUN", pattern="gap_and_go")]),
                          entries={"RUN": StockSnapshot(symbol="RUN", name="Runner", status="gainer", consecutive_up_days=1)},
                          outcomes={"RUN": sc}, scored=True)
    traj = Trajectory(steps=[step])
    credit = apply_credit(traj, h)
    sigs = extract_signatures(traj, h)
    up = build_refiner_user_prompt(traj, credit, sigs, window=10, recent_reports=[])
    assert "gap_and_go" in up and "RUN" in up and "nuk" in up.lower()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/refine/test_refiner_prompt.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'alpha.refine.refiner_prompt'`

- [ ] **Step 3: Write minimal implementation**

```python
# alpha/refine/refiner_prompt.py
from __future__ import annotations

from alpha.harness.skill import Skill
from alpha.harness.state import HarnessState
from alpha.refine.credit import CreditReport
from alpha.refine.ops import PassKind
from alpha.refine.signatures import FailureSignature
from alpha.eval.trajectory import Trajectory

_PASS_DESC: dict[PassKind, str] = {
    "p": "DOCTRINE pass: rewrite the guidance text of a MUTABLE doctrine entry. You cannot add, remove, "
         "or edit immutable red-line entries.",
    "K": "SKILLS pass: write (new -> incubating), patch, retire (-> dormant), revive, or promote skills.",
    "M": "MEMORY pass: process (add) a lesson, update a lesson's text, or demote a lesson's weight.",
}

_PASS_TOOLS_DOC: dict[PassKind, str] = {
    "p": '- rewrite_doctrine{section, new_guidance, rationale}',
    "K": ('- write_skill{skill_id,name,type,family?,phases?,trigger?,entry?,exit_stop?,taboo?,gate?, rationale}  '
          '(always minted INCUBATING)\n'
          '- patch_skill{skill_id, <fields...>, rationale}  (WHOLE-FIELD REPLACE: include ALL existing list '
          'items you want to keep)\n'
          '- retire_skill{skill_id, permanent?, rationale}\n'
          '- revive_skill{skill_id, rationale}  (dormant -> incubating)\n'
          '- promote_skill{skill_id, rationale}  (incubating -> active)'),
    "M": ('- process_memory{lesson_id,outcome,lesson,phases?,family?,pattern?, rationale}\n'
          '- update_memory{lesson_id, <fields...>, rationale}\n'
          '- demote_memory{lesson_id, factor (0..1], rationale}'),
}

_OUTPUT_CONTRACT = ('Output STRICT JSON only: {"ops": [{"tool": "<one tool above>", "args": {...}, '
                    '"rationale": "<why, non-empty>"}]}. Be sparing — emit an empty ops list if the '
                    'evidence does not justify a change. Every op MUST carry a non-empty rationale.')


def _skill_line(s: Skill) -> str:
    st = s.stats
    rec = (f" [n={st.n} nukes={st.nukes}"
           + (f" exp={st.expectancy:+.2f}" if st.expectancy is not None else "")
           + (f" exp_raw={st.expectancy_raw:+.2f}" if st.expectancy_raw is not None else "") + "]") if st.n > 0 else ""
    return f"- {s.skill_id} ({s.name}) [{s.type}, {s.status}, {s.family or 'any'}]{rec}"


def build_refiner_system_prompt(h: HarnessState, pass_kind: PassKind, *, min_retire_samples: int = 5,
                                min_promote_samples: int = 3,
                                involved_skill_ids: set[str] | None = None) -> str:
    """Per-pass system prompt: role + this pass's tools + discipline + a slice of the current H + contract."""
    involved = involved_skill_ids or set()
    parts: list[str] = [
        "You are the Refiner (复盘官) of a US speculative-momentum trading harness. You revise the playbook "
        "H from realized evidence. You edit ONLY via the tools listed; you never trade.",
        "\n" + _PASS_DESC[pass_kind],
        "\nTOOLS (this pass only):\n" + _PASS_TOOLS_DOC[pass_kind],
        "\nRULES: immutable red-line doctrine is READ-ONLY (never editable). Every op needs a non-empty "
        "rationale. patch_skill / update_memory are WHOLE-FIELD REPLACE — re-list every existing item you keep.",
    ]
    if pass_kind == "p":
        parts.append("\nMUTABLE doctrine (editable):")
        parts += [f"- {e.section}: {e.guidance}" for e in h.doctrine.mutable_entries()]
        parts.append("\nIMMUTABLE red-lines (READ-ONLY, cannot be edited):")
        parts += [f"- [RED-LINE] {e.section}: {e.guidance}" for e in h.doctrine.immutable_core()]
    elif pass_kind == "K":
        parts.append(f"\nRETIRE DISCIPLINE: retire_skill is REJECTED unless the skill has n>={min_retire_samples} "
                     "scored samples. 'faded' is a no-follow-through MISS (score 0), NOT a loss — do not retire on "
                     "a few fadeds. 'nuked' is the real loss; contract on nukes first. Prefer patch over retire.")
        parts.append(f"PROMOTE DISCIPLINE: promote_skill is REJECTED unless n>={min_promote_samples} AND "
                     "expectancy (advantage vs the same-day pool) > 0. No zero-evidence activation.")
        parts.append("\nCURRENT SKILLS (involved skills carry their track record):")
        parts += [_skill_line(s) for s in h.skills.all()
                  if s.skill_id in involved or s.status in ("active", "incubating", "dormant")]  # dormant => revive candidates visible
    elif pass_kind == "M":
        parts.append("\nCURRENT LESSONS:")
        parts += [f"- {l.lesson_id} [{l.outcome}] {l.lesson}" for l in h.memory.all()]
    parts.append("\n" + _OUTPUT_CONTRACT)
    return "\n".join(parts)


def build_refiner_user_prompt(traj: Trajectory, credit: CreditReport, signatures: list[FailureSignature], *,
                              window: int = 10, recent_reports: list | None = None) -> str:
    """Shared evidence across passes: recent scored steps, per-skill credit, failure signatures, and the
    last <=2 RefineReports (applied: don't re-propose; rejected: don't resend verbatim)."""
    parts: list[str] = ["EVIDENCE (realized, <= t-horizon):"]
    parts.append("\nRecent scored days:")
    for step in traj.scored_steps()[-window:]:
        picks = ", ".join(f"{sym}:{sc.outcome}({sc.advantage:+.2f})" for sym, sc in step.outcomes.items()) or "no-trade"
        parts.append(f"- {step.date}: {picks}")
    parts.append("\nPer-skill credit (this window):")
    for sid, c in credit.per_skill.items():
        parts.append(f"- {sid}: n={c.n} hit={c.hit_rate:.2f} nuke={c.nuke_rate:.2f} "
                     f"exp(adv)={c.expectancy:+.2f} exp_raw={c.expectancy_raw:+.2f}")
    if credit.unattributed:
        parts.append(f"- (unattributed picks: n={credit.unattributed.n})")
    if signatures:
        parts.append("\nFailure signatures (where it lost):")
        parts += [f"- {s.date} {s.symbol} [{s.kind}] {s.evidence} (skill={s.skill_id or '?'})" for s in signatures]
    for rep in (recent_reports or []):
        if rep.applied:
            parts.append("\nAlready APPLIED recently (do NOT re-propose): "
                         + "; ".join(f"{e.tool}:{e.target_id}" for e in rep.applied))
        if rep.rejected:
            parts.append("Recently REJECTED (do NOT resend verbatim): "
                         + "; ".join(f"{e.tool}:{e.target_id} ({e.reason})" for e in rep.rejected))
    return "\n".join(parts)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/refine/test_refiner_prompt.py -q`
Expected: PASS (3 passed)

- [ ] **Step 5: Commit**

```bash
git add alpha/refine/refiner_prompt.py tests/refine/test_refiner_prompt.py
git commit -m "US-2b Task 6: refiner prompts (per-pass system w/ discipline + shared evidence user prompt)"
```

---

### Task 7: Refiner config + dispatch + discipline gates

**Files:**
- Create: `alpha/refine/refiner.py`
- Create: `tests/refine/test_refiner_apply.py`

`RefinerConfig`, the audit models (`AppliedEdit`/`RejectedEdit`/`RefineReport`), `_target_id`, `_dispatch` (op → `MetaTools` with sanitization), and `_apply_op` (whitelist → rationale → retire/promote evidence gates → dispatch-with-catch). The 4-pass `refine()` driver is added in Task 8.

- [ ] **Step 1: Write the failing test**

```python
# tests/refine/test_refiner_apply.py
import pytest
from alpha.harness.skill import Skill, SkillStats
from alpha.harness.doctrine import Doctrine
from alpha.harness.registry import SkillRegistry, MemoryStore
from alpha.harness.state import HarnessState
from alpha.harness.metatools import MetaTools
from alpha.harness.edit_log import EditLog
from alpha.refine.ops import RefineOp, PASS_TOOLS
from alpha.refine.refiner import Refiner, RefinerConfig
from alpha.llm.client import MockLLMClient


def _skill(sid, status="active", n=0, expectancy=None):
    st = SkillStats(n=n, expectancy=expectancy)
    return Skill(skill_id=sid, name=sid, type="pattern", status=status, stats=st)


def _refiner(skills):
    h = HarnessState(doctrine=Doctrine(), skills=SkillRegistry.from_skills(skills),
                     memory=MemoryStore.from_lessons([]))
    meta = MetaTools(h, EditLog())
    return Refiner(h, MockLLMClient("{}"), meta, RefinerConfig()), h, meta


def test_tool_not_in_pass_rejected():
    r, h, meta = _refiner([_skill("a")])
    ok, edit = r._apply_op(RefineOp(tool="rewrite_doctrine", args={}, rationale="x"), "K", PASS_TOOLS["K"])
    assert ok is False and "not in this pass" in edit.reason and len(meta.log) == 0


def test_missing_rationale_rejected():
    r, h, meta = _refiner([_skill("a")])
    ok, edit = r._apply_op(RefineOp(tool="promote_skill", args={"skill_id": "a"}, rationale="  "),
                           "K", PASS_TOOLS["K"])
    assert ok is False and "rationale" in edit.reason and len(meta.log) == 0


def test_retire_evidence_gate():
    r, h, meta = _refiner([_skill("a", n=2)])             # n < min_retire_samples (5)
    ok, edit = r._apply_op(RefineOp(tool="retire_skill", args={"skill_id": "a"}, rationale="decayed"),
                           "K", PASS_TOOLS["K"])
    assert ok is False and "retire blocked" in edit.reason and h.skills.get("a").status == "active"
    # with enough samples it applies and is logged
    r2, h2, meta2 = _refiner([_skill("a", n=9)])
    ok2, edit2 = r2._apply_op(RefineOp(tool="retire_skill", args={"skill_id": "a"}, rationale="decayed"),
                              "K", PASS_TOOLS["K"])
    assert ok2 is True and h2.skills.get("a").status == "dormant" and len(meta2.log) == 1


def test_promote_evidence_gate():
    r, h, meta = _refiner([_skill("a", status="incubating", n=5, expectancy=-0.1)])   # expectancy<=0
    ok, edit = r._apply_op(RefineOp(tool="promote_skill", args={"skill_id": "a"}, rationale="ready"),
                           "K", PASS_TOOLS["K"])
    assert ok is False and "expectancy" in edit.reason and h.skills.get("a").status == "incubating"
    r2, h2, meta2 = _refiner([_skill("a", status="incubating", n=5, expectancy=0.2)])
    ok2, _ = r2._apply_op(RefineOp(tool="promote_skill", args={"skill_id": "a"}, rationale="ready"),
                          "K", PASS_TOOLS["K"])
    assert ok2 is True and h2.skills.get("a").status == "active"


def test_dispatch_error_becomes_rejection():
    r, h, meta = _refiner([_skill("a")])
    # missing target -> KeyError inside MetaTools -> RejectedEdit, nothing logged
    ok, edit = r._apply_op(RefineOp(tool="patch_skill", args={"skill_id": "ghost", "entry": "x"},
                                    rationale="fix"), "K", PASS_TOOLS["K"])
    assert ok is False and edit.target_id == "ghost" and len(meta.log) == 0


def test_empty_patch_rejected():
    r, h, meta = _refiner([_skill("a")])
    ok, edit = r._apply_op(RefineOp(tool="patch_skill", args={"skill_id": "a"}, rationale="noop"),
                           "K", PASS_TOOLS["K"])
    assert ok is False and "empty patch" in edit.reason and len(meta.log) == 0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/refine/test_refiner_apply.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'alpha.refine.refiner'`

- [ ] **Step 3: Write minimal implementation**

```python
# alpha/refine/refiner.py
from __future__ import annotations

from collections import deque

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from alpha.harness.edit_log import EditRecord
from alpha.harness.errors import HarnessError
from alpha.harness.memory import Lesson
from alpha.harness.metatools import MetaTools
from alpha.harness.skill import Skill
from alpha.harness.state import HarnessState
from alpha.llm.client import LLMClient
from alpha.refine.ops import PASS_ORDER, PASS_TOOLS, PassKind, RefineOp, parse_ops
from alpha.refine.credit import CreditReport
from alpha.refine.signatures import FailureSignature
from alpha.refine.refiner_prompt import build_refiner_system_prompt, build_refiner_user_prompt
from alpha.eval.trajectory import Trajectory

# Errors a dispatched meta-tool may raise that the Refiner converts into a clean RejectedEdit.
_DISPATCH_ERRORS = (HarnessError, KeyError, ValueError, ValidationError, TypeError, AttributeError)


class RefinerConfig(BaseModel):
    max_edits_per_pass: int = 5
    max_edits_per_refine: int = 12
    window: int = 10
    min_retire_samples: int = Field(default=5, ge=1)
    min_promote_samples: int = Field(default=3, ge=1)
    # (credit `decay` is a parameter of apply_credit / the US-2c LoopConfig, not the Refiner's concern)


class AppliedEdit(BaseModel):
    model_config = ConfigDict(frozen=True)
    pass_kind: PassKind
    tool: str
    target_id: str
    seq: int
    rationale: str


class RejectedEdit(BaseModel):
    model_config = ConfigDict(frozen=True)
    pass_kind: PassKind
    tool: str
    target_id: str | None
    reason: str


class RefineReport(BaseModel):
    model_config = ConfigDict(frozen=True)
    applied: list[AppliedEdit] = Field(default_factory=list)
    rejected: list[RejectedEdit] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)


def _target_id(tool: str, args: dict) -> str | None:
    """Normalize the target id to str|None (an LLM may emit a numeric id; RejectedEdit.target_id is str|None)."""
    if tool in ("write_skill", "patch_skill", "retire_skill", "revive_skill", "promote_skill"):
        v = args.get("skill_id")
    elif tool in ("process_memory", "update_memory", "demote_memory"):
        v = args.get("lesson_id")
    elif tool == "rewrite_doctrine":
        v = args.get("section")
    else:
        v = None
    return str(v) if v is not None else None


class Refiner:
    """Edits H=(p,K,M) from realized evidence via the 9 meta-tools, behind discipline gates. Edits IN
    PLACE (the agent sees them next decision); does NOT checkpoint or roll back (that is US-2c's InnerLoop)."""

    def __init__(self, harness: HarnessState, llm: LLMClient, meta: MetaTools,
                 config: RefinerConfig | None = None) -> None:
        self._h = harness
        self._llm = llm
        self._meta = meta
        self._cfg = config or RefinerConfig()
        self._recent_reports: "deque[RefineReport]" = deque(maxlen=2)

    def _dispatch(self, op: RefineOp) -> EditRecord:
        """Map an op to its US MetaTools call (rationale is a required positional). Defensive sanitization:
        force write_skill -> incubating + strip stats; strip importance on process_memory."""
        tool, args, r = op.tool, dict(op.args), op.rationale
        m = self._meta
        if tool == "write_skill":
            args.pop("stats", None)
            args["status"] = "incubating"
            return m.write_skill(Skill.from_seed(args), rationale=r)
        if tool == "patch_skill":
            sid = args.pop("skill_id")
            return m.patch_skill(sid, rationale=r, **args)
        if tool == "retire_skill":
            sid = args.pop("skill_id")
            perm = bool(args.pop("permanent", False))
            return m.retire_skill(sid, rationale=r, permanent=perm)
        if tool == "revive_skill":
            return m.revive_skill(args.pop("skill_id"), rationale=r)
        if tool == "promote_skill":
            return m.promote_skill(args.pop("skill_id"), rationale=r)
        if tool == "process_memory":
            args.pop("importance", None)
            return m.process_memory(Lesson.from_seed(args), rationale=r)
        if tool == "update_memory":
            lid = args.pop("lesson_id")
            return m.update_memory(lid, rationale=r, **args)
        if tool == "demote_memory":
            lid = args.pop("lesson_id")
            factor = float(args.pop("factor"))
            return m.demote_memory(lid, factor, rationale=r)
        if tool == "rewrite_doctrine":
            return m.rewrite_doctrine(args.pop("section"), args.pop("new_guidance"), rationale=r)
        raise ValueError(f"unknown tool: {tool}")

    def _apply_op(self, op: RefineOp, pk: PassKind, allowed: frozenset) -> tuple[bool, object]:
        """Gate order: whitelist -> rationale -> empty-patch -> retire/promote evidence -> dispatch (errors -> reject).
        Evidence gates key on the canonical skill_id (h.skills.get(tid)); an op addressing a skill by its
        display NAME (not id) skips the gate and is rejected at dispatch (KeyError) — still a clean reject."""
        tid = _target_id(op.tool, op.args)
        if op.tool not in allowed:
            return False, RejectedEdit(pass_kind=pk, tool=op.tool, target_id=tid,
                                       reason="tool not in this pass or unknown")
        if not op.rationale or not op.rationale.strip():
            return False, RejectedEdit(pass_kind=pk, tool=op.tool, target_id=tid, reason="missing rationale")
        if op.tool in ("patch_skill", "update_memory") and not (set(op.args) - {"skill_id", "lesson_id"}):
            return False, RejectedEdit(pass_kind=pk, tool=op.tool, target_id=tid,
                                       reason="empty patch (no fields to change)")
        if op.tool == "retire_skill" and tid is not None:
            sk = self._h.skills.get(tid)
            if sk is not None and sk.stats.n < self._cfg.min_retire_samples:
                return False, RejectedEdit(pass_kind=pk, tool=op.tool, target_id=tid,
                                           reason=f"retire blocked: n={sk.stats.n} < min_retire_samples={self._cfg.min_retire_samples}")
        if op.tool == "promote_skill" and tid is not None:
            sk = self._h.skills.get(tid)
            if sk is not None:
                if sk.stats.n < self._cfg.min_promote_samples:
                    return False, RejectedEdit(pass_kind=pk, tool=op.tool, target_id=tid,
                                               reason=f"promote blocked: n={sk.stats.n} < min_promote_samples={self._cfg.min_promote_samples}")
                if sk.stats.expectancy is None or sk.stats.expectancy <= 0:
                    return False, RejectedEdit(pass_kind=pk, tool=op.tool, target_id=tid,
                                               reason="promote blocked: expectancy (advantage) not > 0")
        try:
            rec = self._dispatch(op)
        except _DISPATCH_ERRORS as e:
            return False, RejectedEdit(pass_kind=pk, tool=op.tool, target_id=tid, reason=f"{type(e).__name__}: {e}")
        return True, AppliedEdit(pass_kind=pk, tool=op.tool, target_id=str(rec.target_id),
                                 seq=rec.seq, rationale=op.rationale)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/refine/test_refiner_apply.py -q`
Expected: PASS (6 passed)

- [ ] **Step 5: Commit**

```bash
git add alpha/refine/refiner.py tests/refine/test_refiner_apply.py
git commit -m "US-2b Task 7: Refiner config + dispatch + discipline gates (whitelist/rationale/retire/promote)"
```

---

### Task 8: The 4-pass `refine()` driver

**Files:**
- Modify: `alpha/refine/refiner.py`
- Create: `tests/refine/test_refiner_passes.py`

Add `refine(traj, credit, signatures) -> RefineReport`: iterate `('p','G','K','M')`; `G` is a reserved no-op (note, no LLM call); each non-empty pass = one scoped LLM call → `parse_ops` → apply each op under per-pass / per-refine caps; record the report into `_recent_reports`.

- [ ] **Step 1: Write the failing test**

```python
# tests/refine/test_refiner_passes.py
from datetime import date, datetime
from alpha.harness.skill import Skill, SkillStats
from alpha.harness.doctrine import Doctrine
from alpha.harness.registry import SkillRegistry, MemoryStore
from alpha.harness.state import HarnessState
from alpha.harness.metatools import MetaTools
from alpha.harness.edit_log import EditLog
from alpha.refine.refiner import Refiner, RefinerConfig
from alpha.refine.credit import CreditReport
from alpha.eval.trajectory import Trajectory
from alpha.llm.client import MockLLMClient


def _h():
    skills = SkillRegistry.from_skills([
        Skill(skill_id="winner", name="Winner", type="pattern", status="incubating",
              stats=SkillStats(n=6, expectancy=0.3)),
        Skill(skill_id="loser", name="Loser", type="pattern", status="active", stats=SkillStats(n=8, expectancy=-0.2)),
    ])
    doctrine = Doctrine.from_seed_list([{"section": "trend_play", "regime": "trend", "immutable": False,
                                         "guidance": "ride the leader"}])
    return HarnessState(doctrine=doctrine, skills=skills, memory=MemoryStore.from_lessons([]))


def _refiner(h, scripts):
    meta = MetaTools(h, EditLog())
    return Refiner(h, MockLLMClient(scripts), meta, RefinerConfig()), meta


def _empty_traj():
    return Trajectory(steps=[]), CreditReport(), []


def test_g_pass_is_noop_three_live_calls():
    h = _h()
    # scripts replayed in pass order p, K, M (G makes NO call)
    scripts = ['{"ops": []}',                                                              # p
               '{"ops": [{"tool": "promote_skill", "args": {"skill_id": "winner"}, "rationale": "proven"}, '
               '{"tool": "retire_skill", "args": {"skill_id": "loser"}, "rationale": "bleeding"}]}',  # K
               '{"ops": []}']                                                              # M
    r, meta = _refiner(h, scripts)
    traj, credit, sigs = _empty_traj()
    report = r.refine(traj, credit, sigs)
    llm = r._llm
    assert len(llm.calls) == 3                              # p, K, M — G made no call
    assert any("G-pass" in n for n in report.notes)        # G no-op recorded
    assert {e.tool for e in report.applied} == {"promote_skill", "retire_skill"}
    assert h.skills.get("winner").status == "active" and h.skills.get("loser").status == "dormant"
    assert len(meta.log) == 2                               # exactly the 2 applied edits logged


def test_per_pass_cap_enforced():
    h = _h()
    # 6 patch ops in the K pass; cap is 5 per pass -> 6th rejected
    ops = ", ".join('{"tool": "patch_skill", "args": {"skill_id": "loser", "notes": "n%d"}, "rationale": "r"}' % i
                    for i in range(6))
    r, meta = _refiner(h, ['{"ops": []}', '{"ops": [%s]}' % ops, '{"ops": []}'])
    report = r.refine(*_empty_traj())
    assert sum(1 for e in report.applied if e.pass_kind == "K") == 5
    assert any("per-pass limit" in e.reason for e in report.rejected)


def test_edit_history_recorded():
    h = _h()
    r, meta = _refiner(h, ['{"ops": []}',
                           '{"ops": [{"tool": "promote_skill", "args": {"skill_id": "winner"}, "rationale": "ok"}]}',
                           '{"ops": []}'])
    r.refine(*_empty_traj())
    assert len(r._recent_reports) == 1 and r._recent_reports[-1].applied[0].tool == "promote_skill"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/refine/test_refiner_passes.py -q`
Expected: FAIL — `AttributeError: 'Refiner' object has no attribute 'refine'`

- [ ] **Step 3: Write the implementation**

Append this method to the `Refiner` class in `alpha/refine/refiner.py`:

```python
    def refine(self, traj: Trajectory, credit: CreditReport,
               signatures: list[FailureSignature]) -> RefineReport:
        """Run the 4 passes (p, G, K, M) over the live H. G is a reserved no-op (no LLM call). Each
        non-empty pass = one scoped LLM call -> parse_ops -> apply under per-pass / per-refine caps."""
        history = list(self._recent_reports)            # snapshot BEFORE the loop (never see our own report)
        applied: list[AppliedEdit] = []
        rejected: list[RejectedEdit] = []
        notes: list[str] = []
        involved = set(credit.per_skill) | {s.skill_id for s in signatures if s.skill_id}
        user = build_refiner_user_prompt(traj, credit, signatures, window=self._cfg.window,
                                         recent_reports=history)
        for pk in PASS_ORDER:
            allowed = PASS_TOOLS[pk]
            if not allowed:                              # G-pass: reserved no-op (sub-agents unbuilt)
                notes.append(f"{pk}-pass reserved (no sub-agents yet); skipped")
                continue
            system = build_refiner_system_prompt(self._h, pk, min_retire_samples=self._cfg.min_retire_samples,
                                                 min_promote_samples=self._cfg.min_promote_samples,
                                                 involved_skill_ids=involved)
            ops = parse_ops(self._llm.complete(system, user))
            pass_count = 0
            for op in ops:
                tid = _target_id(op.tool, op.args)
                if len(applied) >= self._cfg.max_edits_per_refine:
                    rejected.append(RejectedEdit(pass_kind=pk, tool=op.tool, target_id=tid,
                                                 reason="exceeds per-refine limit"))
                    continue
                if pass_count >= self._cfg.max_edits_per_pass:
                    rejected.append(RejectedEdit(pass_kind=pk, tool=op.tool, target_id=tid,
                                                 reason="exceeds per-pass limit"))
                    continue
                ok, edit = self._apply_op(op, pk, allowed)
                if ok:
                    applied.append(edit)
                    pass_count += 1
                else:
                    rejected.append(edit)
        report = RefineReport(applied=applied, rejected=rejected, notes=notes)
        self._recent_reports.append(report)
        return report
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/refine/test_refiner_passes.py -q`
Expected: PASS (3 passed)

- [ ] **Step 5: Commit**

```bash
git add alpha/refine/refiner.py tests/refine/test_refiner_passes.py
git commit -m "US-2b Task 8: 4-pass refine() driver (G no-op; scoped LLM calls; edit caps; history)"
```

---

### Task 9: US-2b acceptance gate + docs update

**Files:**
- Create: `tests/refine/test_us2b_acceptance.py`
- Modify: `docs/PROJECT_STATE.md` (mark US-2b done)

End-to-end: a `MockLLMClient` agent walks a `FakeSource` → `Trajectory` → `apply_credit` populates `SkillStats` → `extract_signatures` → the `Refiner` (driven by the manager's `MetaTools`) edits `H` with discipline; the `EditLog` records the applied edits; a `HarnessManager` checkpoint/rollback reverts them (proving US-2c can safely drive this).

- [ ] **Step 1: Write the acceptance test**

```python
# tests/refine/test_us2b_acceptance.py
"""US-2b acceptance: the agent's realized trajectory feeds credit assignment + signatures, and the
Refiner edits the SEEDED harness H via the manager's MetaTools under discipline — audited in the
EditLog and reversible via checkpoint/rollback. This is the Refiner the US-2c InnerLoop will drive."""
from pathlib import Path
from datetime import date
import pandas as pd
from alpha.data.source import FakeSource
from alpha.harness.loader import load_seeds
from alpha.harness.snapshot import SnapshotStore
from alpha.harness.manager import HarnessManager
from alpha.llm.client import MockLLMClient
from alpha.agent.agent import LLMAgentPolicy
from alpha.eval.walk_forward import WalkForwardEval
from alpha.eval.scorer import ReturnScorer
from alpha.refine.credit import apply_credit
from alpha.refine.signatures import extract_signatures
from alpha.refine.refiner import Refiner, RefinerConfig

SEEDS = Path(__file__).resolve().parents[2] / "seeds"


def _source():
    cal = [date(2026, 6, 10), date(2026, 6, 11), date(2026, 6, 12), date(2026, 6, 15)]
    rows = {date(2026, 6, 10): [("RUN", 14.0, 10.0)], date(2026, 6, 11): [("RUN", 18.0, 14.0)],
            date(2026, 6, 12): [("RUN", 17.0, 18.0)], date(2026, 6, 15): [("RUN", 20.0, 17.0)]}
    snaps = {d: pd.DataFrame({"symbol": ["RUN"], "name": ["RUN"], "open": [r[2] for r in v],
                              "high": [r[1] for r in v], "low": [r[2] for r in v], "close": [r[1] for r in v],
                              "volume": [1], "prev_close": [r[2] for r in v]}) for d, v in rows.items()}
    bars = {"RUN": pd.DataFrame({"date": cal, "open": [10.0, 14.0, 18.0, 17.0], "high": [14, 18, 18, 20],
                                 "low": [10, 14, 17, 17], "close": [14.0, 18.0, 17.0, 20.0], "volume": [1, 1, 1, 1]})}
    return FakeSource(calendar=cal, bars=bars, snapshots=snaps)


def test_refiner_edits_seeded_harness_end_to_end(tmp_path):
    mgr = HarnessManager(load_seeds(SEEDS), SnapshotStore(tmp_path))
    v0 = mgr.checkpoint("seed")
    original = mgr.harness.doctrine.get("trend_play").guidance       # capture seed text (not brittle)

    # 1) agent walks -> trajectory of realized outcomes (agent always picks RUN as gap_and_go)
    agent = LLMAgentPolicy(mgr.harness, MockLLMClient('{"regime_read": "trend", "candidates": '
                           '[{"symbol": "RUN", "pattern": "gap_and_go", "confidence": 0.7}]}'))
    traj = WalkForwardEval(_source(), date(2026, 6, 10), date(2026, 6, 15), horizon=2,
                           scorer=ReturnScorer()).walk(agent)

    # 2) credit assignment populates SkillStats on the real seed skill
    #    (RUN screens as a gainer on 6/10 [+40%] & 6/11 [+28.6%], so the pick is in-universe and both
    #     decisions reach their t+2 exit -> 2 scored candidates attributed to gap_and_go by exact-id match)
    credit = apply_credit(traj, mgr.harness)
    assert mgr.harness.skills.get("gap_and_go").stats.n >= 1
    sigs = extract_signatures(traj, mgr.harness)

    # 3) the Refiner edits H via the manager's MetaTools, under discipline (scripted: rewrite a mutable
    #    doctrine line in p; no-op K/M). Edits are audited + reversible.
    refiner = Refiner(mgr.harness, MockLLMClient([
        '{"ops": [{"tool": "rewrite_doctrine", "args": {"section": "trend_play", '
        '"new_guidance": "ride the lead runner; trim into blowoffs (refined)"}, "rationale": "evidence"}]}',
        '{"ops": []}', '{"ops": []}']), mgr.tools, RefinerConfig())
    report = refiner.refine(traj, credit, sigs)
    assert any(e.tool == "rewrite_doctrine" for e in report.applied)
    assert len(mgr.log) == 1 and "refined" in mgr.harness.doctrine.get("trend_play").guidance

    # 4) an immutable red-line cannot be rewritten (discipline holds)
    bad = Refiner(mgr.harness, MockLLMClient([
        '{"ops": [{"tool": "rewrite_doctrine", "args": {"section": "stop_discipline", '
        '"new_guidance": "loosen"}, "rationale": "x"}]}', '{"ops": []}', '{"ops": []}']),
        mgr.tools, RefinerConfig())
    rep2 = bad.refine(traj, credit, sigs)
    assert rep2.applied == [] and any("Immutable" in e.reason or "immutable" in e.reason for e in rep2.rejected)

    # 5) rollback reverts the structural edit (US-2c's safety net works on this Refiner's output)
    mgr.rollback_to(v0)
    assert mgr.harness.doctrine.get("trend_play").guidance == original   # structural edit reverted
```

- [ ] **Step 2: Run the full suite**

Run: `python -m pytest -q`
Expected: PASS — all US-0/US-1/US-2a tests plus the new US-2b tests green.

- [ ] **Step 3: Update `docs/PROJECT_STATE.md`**

Add a **US-2b** entry under the US-2 section: the Refiner + evidence substrate is complete — `Trajectory`/`walk()`, `apply_credit` (in-place Welford on advantage; cumulative; unattributed bucket), US-native failure `signatures`, and the 4-pass (`p`/`G`/`K`/`M`, G reserved no-op) `Refiner` with retire/promote evidence gates, edit caps, required rationale, and reject-don't-crash dispatch, editing `H` only through `MetaTools` and reversible via the manager's checkpoint/rollback. Note the full-suite test count. Update the "Next" pointer to **US-2c (the InnerLoop: interleaved online credit + checkpoint-before-refine + scorer-aware capability-floor breaker + rollback/rebind / freeze)**. Keep the US-2d (three-way compare) and sizing/guard-wiring deferrals.

- [ ] **Step 4: Commit**

```bash
git add tests/refine/test_us2b_acceptance.py docs/PROJECT_STATE.md
git commit -m "US-2b Task 9: acceptance gate (Refiner edits seeded H end-to-end; audited + reversible) + PROJECT_STATE"
```

---

## Self-Review (run after writing, fix inline)

**Spec coverage (§4 inner loop, §6 immutable, §7 advantage):** Trajectory + walk() (Tasks 1-2) ✓ · credit assignment populating advantage-based expectancy + raw lens, unattributed bucket (Task 3) ✓ · US-native failure signatures (Task 4) ✓ · 4-pass taxonomy with G reserved no-op + robust parse (Task 5) ✓ · per-pass prompts with retire/promote discipline + immutable red-lines read-only + output contract (Task 6) ✓ · dispatch + evidence gates + reject-don't-crash (Task 7) ✓ · 4-pass driver with caps + edit-history (Task 8) ✓ · end-to-end seeded-H refine, audited + reversible (Task 9) ✓. **Deferred & documented:** InnerLoop + scorer-aware floor-breaker + checkpoint/rollback-on-trip → US-2c; three-way HCH/Hexpert/Hmin compare → US-2d; sizing/guard → DecisionPackage wiring → later; master-dispatch G sub-agents → keeps the G-pass a reserved no-op.

**Type consistency:** `Trajectory.scored_steps()/all_scored()` feed `apply_credit`/`extract_signatures`/`build_refiner_user_prompt`. `CreditReport`/`SkillCredit` from credit used by prompts + driver. `RefineOp`/`PASS_TOOLS`/`PassKind` from ops used by refiner + prompts. `apply_credit` mutates `SkillStats` (`expectancy`=advantage, `expectancy_raw`=raw, `nukes`, via `record`). `_dispatch` calls US `MetaTools` signatures (rationale required positional; `retire_skill(skill_id, rationale, permanent=False)`). `RefineReport`/`AppliedEdit.seq` link to `EditRecord.seq`. The Refiner reads `skill.stats.n`/`.expectancy` (populated by `apply_credit`) for the gates.

**Placeholder scan:** no TBD/TODO; every code step is complete; the Refiner edits only via `MetaTools` (audited); credit mutates stats in place by design (the documented observation channel, not a meta-tool edit).

**Scope:** Refiner + evidence substrate only. No InnerLoop, no breaker, no rollback-on-trip, no compare. Produces the audited, discipline-gated, reversible Refiner the US-2c InnerLoop will drive.

**Adversarial-review fixes folded (2026-06-14, 4-lens review — no critical findings):**
- **[important] `parse_ops` crashed on a non-list `ops`** (`{"ops": 5}` → `TypeError`, breaking reject-don't-crash): added an explicit `isinstance(raw_ops, list)` guard + a `parse_ops('{"ops": 5}') == []` regression case.
- **[important] nuke-signature taxonomy inert on real walks**: `build_universe` entries lack `consecutive_up_days` and the walk's `max_runner_tier=0`, so live nukes resolve to `generic_nuke` (the discriminating kinds fire only on hand-built snapshots). Documented as a known limitation/deferral (US-2c/US-3 runner enrichment) — coarser-but-correct, not wrong.
- **[minor] empty-patch hardening**: `_apply_op` now rejects `patch_skill`/`update_memory` ops with no fields beyond the id (`reason="empty patch"`) + a test, so a content-free edit can't slip through the gates and log.
- **[minor] K-pass prompt** now also lists `dormant` skills so `revive` candidates are visible.
- **[minor] dropped `RefinerConfig.decay`** (unused by the Refiner; `decay` is `apply_credit`'s param / a US-2c `LoopConfig` concern — YAGNI).
- **[minor] docstring/clarity**: reworded `apply_credit`'s "once per trajectory" contract (re-calling on a NEW trajectory is the intended cumulative path), corrected the Task-1 import-cycle rationale, noted that name-addressed promote/retire ops reject at dispatch, and removed a dead `if False else` subexpression in the Task-2 test fixture.
- **[minor] strengthened tests**: absolute pin `n_candidates == 2` in the walk-equivalence test + acceptance comment on why RUN screens in.
