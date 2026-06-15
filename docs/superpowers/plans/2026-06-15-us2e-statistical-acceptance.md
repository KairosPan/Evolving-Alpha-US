# US-2e Statistical Acceptance Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Close the spec §9/§10 US-2 acceptance gate by building the **statistical decision procedure** the bar is defined as — a paired HCH−Hexpert day-level verdict (moving-block-bootstrap **CI** + sign-permutation **p-value** + **MDE**) plus the spec-required **offense-vs-defense + per-family contribution split** — wired into the US-2d compare, and aggregated across windows.

**Architecture:** Two new modules + one extension. (1) `alpha/eval/stats.py` — a verbatim, **deterministic** port of the CN statistics layer: `StatVerdict`, `daily_series`, `paired_daily_diff`, `_default_block_len`, `moving_block_bootstrap`, `sign_permutation_pvalue`, `mde`, `verdict`. Pure stdlib (`math`/`random`/`statistics`); every randomized routine uses a **local `random.Random(seed)`** (never the global RNG) so the same `(diffs, seed)` reproduces identical numbers. (2) `alpha/eval/contribution.py` — US-native `ContributionReport`/`contribution_split(traj, h)`: bucket each scored candidate by its resolved skill (`offense` = pattern/feature, `defense` = failure_detector, `unknown` = unresolved) and by `Skill.family`, aggregating mean **advantage** — does self-evolution add edge (offense) or only trim risk (defense)? (3) `alpha/loop/compare.py` extension — `ComparisonReport` gains additive-Optional `stat_verdict` + `contribution` (computed inline in `compare_harnesses` from the HCH and Hexpert trajectories it already holds), and `multi_window`/`MultiWindowReport` aggregate the per-window verdict labels into a tally.

**Tech Stack:** Python ≥3.11, pydantic v2, pytest. Reuses US-2d `compare_harnesses`/`ComparisonReport`/`multi_window`, US-2b `resolve_skill`, US-1d `Trajectory`/`ScoredCandidate`. Offline tests pin exact numbers with synthetic diffs + small `n_boot`/`n_perm`; no network.

**Spec:** `docs/superpowers/specs/2026-06-13-us-market-adaptation-design.md` (§9 acceptance = a statistical decision procedure; §10 methodology; §6/§9/§10 offense-vs-defense + per-family; §12 noise/MDE). CN reference (verbatim port source): `reference/cn/youzi/eval/stats.py` + `reference/cn/tests/test_stats.py`.

**Scope — what US-2e builds vs defers:**
- **BUILD (closes the §9 acceptance procedure):** `alpha/eval/stats.py` (the full statistical layer); `alpha/eval/contribution.py` (offense/defense + per-family); wire `stat_verdict` + `contribution` into `ComparisonReport`; aggregate per-window verdicts in `multi_window`.
- **DEFER (documented §10 *methodology refinements* — gate-non-blocking, CN deferred them too):** purged + embargoed CV (the US firewall + strict walk-forward already enforce no-lookahead, so this is a tightening, not a precondition for a valid paired verdict); regime-stratified evaluation (needs a calibrated G_cycle phase classifier); the Hcredit (C4) ablation arm (an additive 5th arm reusing the same `stats.py`).
- **Honest framing (state, do not over-claim):** US-2e builds and **deterministically validates the acceptance PROCEDURE**. Rendering the actual pass/fail verdict (does HCH ≥ Hexpert?) requires a **live temp=0 LLM run on real data** — `MockLLMClient` ignores prompts, so the offline suite proves the *apparatus* (verdict math, contribution bucketing, wiring), **not** efficacy. **temp=0** is already a §8 invariant (`make_client` defaults to it). "Multi-seed" at temp=0 reduces to multi-**window** (the genuine OOS replication, already in `multi_window`) + the bootstrap seed.

**Conventions:** all code/comments English; `from __future__ import annotations` atop every module; commit after each passing task; run via `python -m pytest`.

**Key invariants (each gets a test):**
1. `moving_block_bootstrap` / `sign_permutation_pvalue` are **deterministic** (local `random.Random(seed)`; identical output for the same `(diffs, seed)`); `_default_block_len(10) == 2` (builtin `round`); CI indices are `int()` truncation (`lo=int(0.025·n_boot)`, `hi=min(n_boot−1, int(0.975·n_boot))`); empty series → `ValueError`; `n==1` → `(x, x)`.
2. `mde` is the closed-form `(z_{0.975}+z_{0.8})·sd/√n` (sample sd); `n<2` → `inf`; `sd==0` → `0.0`; pins `mde([1,−1]*12+[0]) ≈ 0.5604`.
3. `verdict` gates `insufficient` when `n_days < min_days (8)`, else `win` (CI_low>0) / `loss` (CI_high<0) / `flat`; CI/p/MDE attach whenever `n≥2` (even when insufficient); records all params.
4. `contribution_split` buckets by resolved `Skill.type` (offense=pattern/feature, defense=failure_detector, unknown=unresolved) and `Skill.family`, mean-advantage per bucket; resolves against the **passed (evolved) H**.
5. `compare_harnesses` populates `ComparisonReport.stat_verdict` (paired `daily_series(HCH)−daily_series(Hexpert)`) and `.contribution` (HCH trajectory vs the evolved HCH H); both additive-Optional (US-2d reports/tests unaffected); `multi_window` returns a per-window verdict tally.

---

### Task 1: `alpha/eval/stats.py` — models + deterministic closed-form pieces

**Files:**
- Create: `alpha/eval/stats.py`
- Create: `tests/eval/test_stats.py`

`StatVerdict`, `daily_series`, `paired_daily_diff`, `_default_block_len`, `mde` (no RNG — exact, hand-checkable).

- [ ] **Step 1: Write the failing test**

```python
# tests/eval/test_stats.py
from datetime import date, datetime
import math
import pytest
from alpha.state.market import MarketState
from alpha.eval.decision import Candidate, DecisionPackage
from alpha.eval.metrics import ScoredCandidate
from alpha.eval.trajectory import TrajectoryStep, Trajectory
from alpha.eval.stats import (StatVerdict, daily_series, paired_daily_diff, _default_block_len, mde,
                              DEFAULT_MIN_DAYS, DEFAULT_N_BOOT, DEFAULT_N_PERM)


def _mkt(d):
    return MarketState(date=d, gainer_count=1, gap_up_count=0, loser_count=0, failed_breakout_count=0,
                       max_runner_tier=1, echelon=[], breadth_raw=1.0, as_of=datetime(d.year, d.month, d.day, 16, 0))


def _step(d, advs, scored=True):
    outcomes = {f"S{i}": ScoredCandidate(decision_date=d, symbol=f"S{i}", pattern="p", outcome="continued",
                                         score=a, day_baseline=0.0) for i, a in enumerate(advs)}
    dec = DecisionPackage(date=d, candidates=[Candidate(symbol=s, pattern="p") for s in outcomes])
    return TrajectoryStep(date=d, market=_mkt(d), decision=dec, outcomes=outcomes, scored=scored)


def test_constants():
    assert (DEFAULT_MIN_DAYS, DEFAULT_N_BOOT, DEFAULT_N_PERM) == (8, 10_000, 20_000)


def test_daily_series_mean_advantage_zero_on_empty_and_excludes_tail():
    traj = Trajectory(steps=[
        _step(date(2026, 6, 12), [0.2, 0.4]),          # mean advantage 0.3
        _step(date(2026, 6, 11), []),                  # no-trade scored day -> 0.0
        _step(date(2026, 6, 15), [0.9], scored=False), # unscored tail -> excluded
    ])
    ds = daily_series(traj)
    assert [d for d, _ in ds] == [date(2026, 6, 11), date(2026, 6, 12)]   # sorted ascending; unscored tail excluded
    assert ds[0][1] == 0.0 and abs(ds[1][1] - 0.3) < 1e-9                 # no-trade=0.0; mean(0.2,0.4)~0.3 (float-safe)


def test_paired_daily_diff_over_common_dates():
    a = [(date(2026, 6, 10), 1.0), (date(2026, 6, 11), 2.0), (date(2026, 6, 12), 3.0)]
    b = [(date(2026, 6, 11), 0.5), (date(2026, 6, 12), 1.0), (date(2026, 6, 13), 9.0)]
    assert paired_daily_diff(a, b) == [1.5, 2.0]      # only common dates 6/11, 6/12


def test_default_block_len_bankers_rounding():
    assert _default_block_len(1) == 1 and _default_block_len(10) == 2   # round(10**(1/3))=round(2.154)=2
    assert _default_block_len(200) == 5                                 # round(200**(1/3))=6, clamped to 5


def test_mde_closed_form():
    assert mde([1.0]) == math.inf                       # n<2
    assert mde([3.0, 3.0, 3.0]) == 0.0                  # sd==0
    assert abs(mde([1.0, -1.0] * 12 + [0.0]) - 0.5604) < 1e-3   # n=25, sd=1 -> 2.80159/5


def test_stat_verdict_frozen():
    v = StatVerdict(verdict="flat", n_days=3, mean_diff=0.0)
    with pytest.raises(Exception):
        v.verdict = "win"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/eval/test_stats.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'alpha.eval.stats'`

- [ ] **Step 3: Write minimal implementation**

```python
# alpha/eval/stats.py
from __future__ import annotations

import math
import random
import statistics
from datetime import date as Date
from typing import Literal

from pydantic import BaseModel, ConfigDict

from alpha.eval.trajectory import Trajectory

# Day-level paired statistical decision procedure (spec §9/§10). Pure stdlib + DETERMINISTIC: every
# randomized routine uses a LOCAL random.Random(seed) — never the global RNG — so the same (diffs, seed)
# reproduces identical numbers regardless of test order or global state.
DEFAULT_N_BOOT = 10_000
DEFAULT_N_PERM = 20_000
DEFAULT_MIN_DAYS = 8
DEFAULT_SEED = 0


class StatVerdict(BaseModel):
    """Frozen snapshot of a paired day-level verdict + the parameters that produced it (reproducible)."""
    model_config = ConfigDict(frozen=True)
    verdict: Literal["win", "loss", "flat", "insufficient"]
    n_days: int
    mean_diff: float
    ci_low: float | None = None
    ci_high: float | None = None
    p_value: float | None = None
    mde: float | None = None
    seed: int = DEFAULT_SEED
    block_len: int = 1
    n_boot: int = DEFAULT_N_BOOT
    n_perm: int = DEFAULT_N_PERM


def daily_series(traj: Trajectory) -> list[tuple[Date, float]]:
    """Per scored decision day: mean candidate advantage (0.0 on a no-trade day). Sorted ascending.
    Unscored tail steps are excluded. Same lens as the InnerLoop breaker / compare.daily_advantage,
    but returns a sorted list[tuple] (paired_daily_diff needs the tuple shape)."""
    out: list[tuple[Date, float]] = []
    for step in traj.scored_steps():
        cands = list(step.outcomes.values())
        v = sum(c.advantage for c in cands) / len(cands) if cands else 0.0
        out.append((step.date, v))
    out.sort(key=lambda t: t[0])
    return out


def paired_daily_diff(a: list[tuple[Date, float]], b: list[tuple[Date, float]]) -> list[float]:
    """a - b over the common dates (ascending). len == StatVerdict.n_days."""
    da, db = dict(a), dict(b)
    common = sorted(set(da) & set(db))
    return [da[d] - db[d] for d in common]


def _default_block_len(n: int) -> int:
    """Moving-block length ~ n^(1/3), clamped to [2, 5] then to n. Uses builtin round (banker's)."""
    if n <= 1:
        return 1
    return min(max(2, round(n ** (1 / 3))), 5, n)


def mde(diffs: list[float], alpha: float = 0.05, power: float = 0.8) -> float:
    """Normal-approx minimum detectable effect: (z_{1-alpha/2} + z_power) * sd / sqrt(n). Sample sd.
    n<2 -> inf (can't estimate); sd==0 -> 0.0."""
    n = len(diffs)
    if n < 2:
        return math.inf
    sd = statistics.stdev(diffs)
    if sd == 0.0:
        return 0.0
    nd = statistics.NormalDist()
    z = nd.inv_cdf(1 - alpha / 2) + nd.inv_cdf(power)
    return z * sd / math.sqrt(n)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/eval/test_stats.py -q`
Expected: PASS (6 passed)

- [ ] **Step 5: Commit**

```bash
git add alpha/eval/stats.py tests/eval/test_stats.py
git commit -m "US-2e Task 1: stats.py models + daily_series/paired_daily_diff/_default_block_len/mde (deterministic closed-form)"
```

---

### Task 2: `alpha/eval/stats.py` — bootstrap CI, permutation p, verdict

**Files:**
- Modify: `alpha/eval/stats.py`
- Modify: `tests/eval/test_stats.py`

The RNG-based routines + the orchestrating `verdict`. Determinism is pinned via repeated-call equality.

- [ ] **Step 1: Write the failing test (append to `tests/eval/test_stats.py`)**

```python
from alpha.eval.stats import moving_block_bootstrap, sign_permutation_pvalue, verdict


def test_bootstrap_degenerate_and_empty():
    assert moving_block_bootstrap([0.3]) == (0.3, 0.3)         # n==1 point CI
    with pytest.raises(ValueError):
        moving_block_bootstrap([])


def test_bootstrap_deterministic_and_directional():
    lo1, hi1 = moving_block_bootstrap([0.5] * 10, n_boot=500, seed=0)
    lo2, hi2 = moving_block_bootstrap([0.5] * 10, n_boot=500, seed=0)
    assert (lo1, hi1) == (lo2, hi2) == (0.5, 0.5)             # constant series + determinism
    lo, hi = moving_block_bootstrap([-0.4] * 10, n_boot=500, seed=0)
    assert lo == hi == -0.4


def test_permutation_pvalue_symmetric_high_signal_low():
    assert sign_permutation_pvalue([]) == 1.0
    # symmetric mean 0 -> every flip has |mean|>=0 -> all hits -> p == 1.0
    assert sign_permutation_pvalue([0.5, -0.5] * 8, n_perm=500, seed=0) == 1.0
    # strong one-sided signal -> almost no flip reaches |mean|>=1.0 -> small p
    assert sign_permutation_pvalue([1.0] * 10, n_perm=500, seed=0) < 0.05


def test_verdict_branches_and_determinism():
    assert verdict([0.5] * 10, n_boot=500, n_perm=500).verdict == "win"     # CI low > 0
    assert verdict([-0.5] * 10, n_boot=500, n_perm=500).verdict == "loss"   # CI high < 0
    assert verdict([0.0] * 10, n_boot=500, n_perm=500).verdict == "flat"    # CI straddles 0
    short = verdict([0.5, 0.5, 0.5], n_boot=500, n_perm=500)                # n<min_days(8)
    assert short.verdict == "insufficient" and short.ci_low is not None     # CI still attached (n>=2)
    assert short.n_days == 3 and short.block_len == _default_block_len(3) and short.n_boot == 500
    a = verdict([0.5, -0.3, 0.2, 0.4, -0.1, 0.6, 0.1, -0.2, 0.3], seed=0, n_boot=500, n_perm=500)
    b = verdict([0.5, -0.3, 0.2, 0.4, -0.1, 0.6, 0.1, -0.2, 0.3], seed=0, n_boot=500, n_perm=500)
    assert a == b                                                            # full StatVerdict equality
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/eval/test_stats.py -q`
Expected: FAIL — `ImportError: cannot import name 'moving_block_bootstrap' ...`

- [ ] **Step 3: Write the implementation (append to `alpha/eval/stats.py`)**

```python
def moving_block_bootstrap(diffs: list[float], block_len: int | None = None,
                           n_boot: int = DEFAULT_N_BOOT, seed: int = DEFAULT_SEED) -> tuple[float, float]:
    """95% percentile CI of the resampled MEAN via the moving-block bootstrap (autocorrelation-robust).
    Deterministic via a LOCAL random.Random(seed). Draw order is load-bearing: per boot, n_blocks ints
    in sequence. Percentile indices use int() truncation."""
    n = len(diffs)
    if n == 0:
        raise ValueError("moving_block_bootstrap: empty series")
    if n == 1:
        return (diffs[0], diffs[0])
    L = block_len if block_len is not None else _default_block_len(n)
    L = max(1, min(L, n))
    rng = random.Random(seed)
    n_blocks = math.ceil(n / L)
    max_start = n - L
    means: list[float] = []
    for _ in range(n_boot):
        sample: list[float] = []
        for _ in range(n_blocks):
            s = rng.randint(0, max_start)
            sample.extend(diffs[s:s + L])
        del sample[n:]                       # truncate to the original length n
        means.append(sum(sample) / n)
    means.sort()
    lo_idx = int(0.025 * n_boot)
    hi_idx = min(n_boot - 1, int(0.975 * n_boot))
    return (means[lo_idx], means[hi_idx])


def sign_permutation_pvalue(diffs: list[float], n_perm: int = DEFAULT_N_PERM,
                            seed: int = DEFAULT_SEED) -> float:
    """Two-sided sign-flip permutation p for mean(diffs) != 0. Each day's diff is flipped +/- with prob
    0.5 (one rng.random() per day, in diffs order). Add-one smoothed -> never 0. Empty -> 1.0."""
    n = len(diffs)
    if n == 0:
        return 1.0
    obs = abs(sum(diffs) / n)
    rng = random.Random(seed)
    hits = 0
    for _ in range(n_perm):
        s = sum(d if rng.random() < 0.5 else -d for d in diffs)
        if abs(s / n) >= obs:                # >= : ties count as a hit (conservative)
            hits += 1
    return (1 + hits) / (1 + n_perm)


def verdict(diffs: list[float], min_days: int = DEFAULT_MIN_DAYS, *, block_len: int | None = None,
            n_boot: int = DEFAULT_N_BOOT, n_perm: int = DEFAULT_N_PERM,
            seed: int = DEFAULT_SEED) -> StatVerdict:
    """Paired day-level decision: insufficient (n<min_days) / win (CI_low>0) / loss (CI_high<0) / flat.
    CI/p/MDE attach whenever n>=2 (even when insufficient), so a small window still reports its
    uncertainty. The same seed feeds the (independent) bootstrap and permutation RNGs."""
    n = len(diffs)
    mean = sum(diffs) / n if n else 0.0
    ci_lo = ci_hi = p = m = None
    eff_block = 1
    if n >= 2:
        eff_block = block_len if block_len is not None else _default_block_len(n)
        eff_block = max(1, min(eff_block, n))
        ci_lo, ci_hi = moving_block_bootstrap(diffs, block_len=eff_block, n_boot=n_boot, seed=seed)
        p = sign_permutation_pvalue(diffs, n_perm=n_perm, seed=seed)
        m = mde(diffs)
    if n < min_days:
        v: Literal["win", "loss", "flat", "insufficient"] = "insufficient"
    elif ci_lo is not None and ci_lo > 0:
        v = "win"
    elif ci_hi is not None and ci_hi < 0:
        v = "loss"
    else:
        v = "flat"
    return StatVerdict(verdict=v, n_days=n, mean_diff=mean, ci_low=ci_lo, ci_high=ci_hi, p_value=p,
                       mde=m, seed=seed, block_len=eff_block, n_boot=n_boot, n_perm=n_perm)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/eval/test_stats.py -q`
Expected: PASS (10 passed)

- [ ] **Step 5: Commit**

```bash
git add alpha/eval/stats.py tests/eval/test_stats.py
git commit -m "US-2e Task 2: stats.py moving-block bootstrap CI + sign-permutation p + verdict (deterministic)"
```

---

### Task 3: `alpha/eval/contribution.py` — offense/defense + per-family split

**Files:**
- Create: `alpha/eval/contribution.py`
- Create: `tests/eval/test_contribution.py`

US-native (no CN source). Bucket scored candidates by resolved `Skill.type`/`Skill.family`, aggregating mean advantage.

- [ ] **Step 1: Write the failing test**

```python
# tests/eval/test_contribution.py
from datetime import date, datetime
from alpha.harness.skill import Skill
from alpha.harness.doctrine import Doctrine
from alpha.harness.registry import SkillRegistry, MemoryStore
from alpha.harness.state import HarnessState
from alpha.state.market import MarketState
from alpha.eval.decision import Candidate, DecisionPackage
from alpha.eval.metrics import ScoredCandidate
from alpha.eval.trajectory import TrajectoryStep, Trajectory
from alpha.eval.contribution import contribution_split, ContributionReport


def _h():
    # families here are SYNTHETIC test fixtures (not the seed values) — keep as-is
    return HarnessState(doctrine=Doctrine(), memory=MemoryStore.from_lessons([]),
                        skills=SkillRegistry.from_skills([
                            Skill(skill_id="gap_and_go", name="Gap", type="pattern", family="runner",
                                  status="active"),
                            Skill(skill_id="rvol_feat", name="RVOL", type="feature", family="runner",
                                  status="active"),
                            Skill(skill_id="failed_breakout", name="FB", type="failure_detector",
                                  family="runner", status="active")]))


def _step(d, picks):  # picks: list of (pattern, outcome, advantage)
    outcomes = {f"{pat}{i}": ScoredCandidate(decision_date=d, symbol=f"{pat}{i}", pattern=pat,
                                             outcome=oc, score=adv, day_baseline=0.0)
                for i, (pat, oc, adv) in enumerate(picks)}
    dec = DecisionPackage(date=d, candidates=[Candidate(symbol=s, pattern="p") for s in outcomes])
    return TrajectoryStep(date=d, market=MarketState(date=d, gainer_count=1, gap_up_count=0, loser_count=0,
                          failed_breakout_count=0, max_runner_tier=1, echelon=[], breadth_raw=1.0,
                          as_of=datetime(d.year, d.month, d.day, 16, 0)),
                          decision=dec, outcomes=outcomes, scored=True)


def test_offense_defense_unknown_bucketing():
    traj = Trajectory(steps=[_step(date(2026, 6, 10), [
        ("gap_and_go", "continued", 0.3),       # offense (pattern)
        ("rvol_feat", "continued", 0.1),        # offense (feature) -> pattern+feature both bucket to offense
        ("failed_breakout", "nuked", -0.5),     # defense (failure_detector)
        ("ghost", "faded", 0.0),                # unknown (unresolved pattern)
    ])])
    rep = contribution_split(traj, _h())
    assert isinstance(rep, ContributionReport)
    assert rep.offense.n == 2 and abs(rep.offense.expectancy - 0.2) < 1e-9 and rep.offense.hit_rate == 1.0
    assert rep.defense.n == 1 and abs(rep.defense.expectancy - (-0.5)) < 1e-9 and rep.defense.nuke_rate == 1.0
    assert rep.unknown.n == 1


def test_per_family_split():
    traj = Trajectory(steps=[_step(date(2026, 6, 10), [
        ("gap_and_go", "continued", 0.4), ("failed_breakout", "continued", 0.2)])])
    rep = contribution_split(traj, _h())
    assert rep.by_family["runner"].n == 2 and abs(rep.by_family["runner"].expectancy - 0.3) < 1e-9
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/eval/test_contribution.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'alpha.eval.contribution'`

- [ ] **Step 3: Write minimal implementation**

```python
# alpha/eval/contribution.py
from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from alpha.eval.metrics import ScoredCandidate
from alpha.eval.trajectory import Trajectory
from alpha.harness.state import HarnessState
from alpha.refine.credit import resolve_skill


class ContributionBucket(BaseModel):
    """Aggregate over one bucket of scored picks. expectancy = mean advantage (de-market-beta lens)."""
    model_config = ConfigDict(frozen=True)
    n: int = 0
    wins: int = 0
    nukes: int = 0
    hit_rate: float = 0.0
    nuke_rate: float = 0.0
    expectancy: float = 0.0
    expectancy_raw: float = 0.0


class ContributionReport(BaseModel):
    """Offense (pattern/feature) vs defense (failure_detector) vs unknown (unresolved pattern), plus a
    per-family breakdown — does self-evolution add edge (offense) or only trim risk (defense)? (§6/§9/§10)"""
    model_config = ConfigDict(frozen=True)
    offense: ContributionBucket = Field(default_factory=ContributionBucket)
    defense: ContributionBucket = Field(default_factory=ContributionBucket)
    unknown: ContributionBucket = Field(default_factory=ContributionBucket)
    by_family: dict[str, ContributionBucket] = Field(default_factory=dict)


class _BucketAcc:
    __slots__ = ("n", "wins", "nukes", "adv_sum", "score_sum")

    def __init__(self) -> None:
        self.n = self.wins = self.nukes = 0
        self.adv_sum = self.score_sum = 0.0

    def add(self, sc: ScoredCandidate) -> None:
        self.n += 1
        self.wins += int(sc.outcome == "continued")
        self.nukes += int(sc.outcome == "nuked")
        self.adv_sum += sc.advantage
        self.score_sum += sc.score

    def bucket(self) -> ContributionBucket:
        d = self.n or 1
        return ContributionBucket(n=self.n, wins=self.wins, nukes=self.nukes, hit_rate=self.wins / d,
                                  nuke_rate=self.nukes / d, expectancy=self.adv_sum / d,
                                  expectancy_raw=self.score_sum / d)


def contribution_split(traj: Trajectory, h: HarnessState) -> ContributionReport:
    """Bucket each scored candidate by its resolved skill: offense = Skill.type in {pattern, feature},
    defense = failure_detector, unknown = unresolved pattern; plus per Skill.family. Resolve against the
    H the trajectory was produced under (the EVOLVED HCH harness) so Refiner-minted/renamed skills
    bucket correctly. A non-empty `unknown` flags patterns the agent emitted that aren't in K."""
    off, dfn, unk = _BucketAcc(), _BucketAcc(), _BucketAcc()
    fam: dict[str, _BucketAcc] = {}
    for step in traj.scored_steps():
        for sc in step.outcomes.values():
            skill = resolve_skill(sc.pattern, h)
            if skill is None:
                unk.add(sc)
                continue
            (dfn if skill.type == "failure_detector" else off).add(sc)
            if skill.family:
                fam.setdefault(skill.family, _BucketAcc()).add(sc)
    return ContributionReport(offense=off.bucket(), defense=dfn.bucket(), unknown=unk.bucket(),
                              by_family={k: a.bucket() for k, a in fam.items()})
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/eval/test_contribution.py -q`
Expected: PASS (2 passed)

- [ ] **Step 5: Commit**

```bash
git add alpha/eval/contribution.py tests/eval/test_contribution.py
git commit -m "US-2e Task 3: offense/defense + per-family contribution split (resolve against evolved H)"
```

---

### Task 4: Wire `stat_verdict` + `contribution` into the compare

**Files:**
- Modify: `alpha/loop/compare.py`
- Modify: `tests/loop/test_compare.py`

`ComparisonReport` gains two additive-Optional fields; `compare_harnesses` computes them inline from the trajectories it already holds.

- [ ] **Step 1: Write the failing test (append to `tests/loop/test_compare.py`)**

```python
def test_stat_verdict_and_contribution_populated():
    from alpha.eval.stats import StatVerdict
    from alpha.eval.contribution import ContributionReport
    src = _source(10, 1.15)
    cr = compare_harnesses(lambda: load_seeds(SEEDS), src, src.trading_calendar()[0],
                           src.trading_calendar()[-1],
                           agent_llm_factory=lambda: MockLLMClient('{"candidates": '
                                                                   '[{"symbol": "RUN", "pattern": "gap_and_go"}]}'),
                           refiner_llm_factory=lambda: MockLLMClient('{"ops": []}'),
                           store_factory=lambda: SnapshotStore(tempfile.mkdtemp()), loop_config=_cfg())
    assert isinstance(cr.stat_verdict, StatVerdict)
    # same agent script + empty-ops refiner -> HCH==Hexpert picks -> paired diff all 0 -> 'flat' at n_days==8.
    # A non-zero mean_diff would signal a REAL HCH/Hexpert divergence (breaker trip / dropped step), NOT
    # float noise -> debug the divergence, do NOT loosen the tolerance.
    assert cr.stat_verdict.verdict in {"flat", "insufficient"} and abs(cr.stat_verdict.mean_diff) < 1e-9
    assert cr.stat_verdict.n_days >= 1
    assert isinstance(cr.contribution, ContributionReport)
    assert cr.contribution.offense.n >= 1               # gap_and_go is an offense (pattern) seed skill
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/loop/test_compare.py::test_stat_verdict_and_contribution_populated -q`
Expected: FAIL — `AttributeError: 'ComparisonReport' object has no attribute 'stat_verdict'`

- [ ] **Step 3: Write the implementation**

In `alpha/loop/compare.py`:

(a) Add imports:

```python
from alpha.eval.stats import StatVerdict, daily_series, paired_daily_diff, verdict
from alpha.eval.contribution import ContributionReport, contribution_split
```

(b) Add two additive-Optional fields to `ComparisonReport` (after `hch_loop_report`):

```python
    stat_verdict: StatVerdict | None = None        # paired HCH-Hexpert day-level decision (CI/p/MDE)
    contribution: ContributionReport | None = None  # HCH offense/defense + per-family split
```

(c) In `compare_harnesses`, after `hexpert_eval = report_from_trajectory(hexpert_traj, horizon=cfg.horizon)` and before building `arms`, compute the verdict + contribution from the in-scope trajectories:

```python
    # §9/§10 acceptance procedure: paired day-level verdict (HCH - Hexpert) + offense/defense split.
    diffs = paired_daily_diff(daily_series(lr.trajectory), daily_series(hexpert_traj))
    stat = verdict(diffs)
    contribution = contribution_split(lr.trajectory, mgr.harness)   # evolved HCH H
```

(d) Pass them into the `ComparisonReport(...)` return:

```python
        hch_beats_hexpert=(d_excess > 0.0),
        hch_loop_report=lr,
        stat_verdict=stat,
        contribution=contribution,
    )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/loop/test_compare.py -q`
Expected: PASS — the new test plus all pre-existing US-2d compare tests (the additive Optional fields don't disturb them).

- [ ] **Step 5: Commit**

```bash
git add alpha/loop/compare.py tests/loop/test_compare.py
git commit -m "US-2e Task 4: wire stat_verdict + contribution into ComparisonReport (computed inline in compare_harnesses)"
```

---

### Task 5: Aggregate per-window verdicts in `multi_window`

**Files:**
- Modify: `alpha/loop/compare.py`
- Modify: `tests/loop/test_compare.py`

`MultiWindowReport` gains the per-window verdict labels + a tally (the temp=0 multi-seed surrogate is multi-window).

- [ ] **Step 1: Write the failing test (append to `tests/loop/test_compare.py`)**

```python
def test_multi_window_collects_verdict_tally():
    from alpha.loop.compare import multi_window
    src = _source(10, 1.15)
    cal = src.trading_calendar()
    mw = multi_window(lambda: load_seeds(SEEDS), src, [(cal[0], cal[4]), (cal[5], cal[9])],
                      agent_llm_factory=lambda: MockLLMClient('{"candidates": '
                                                              '[{"symbol": "RUN", "pattern": "gap_and_go"}]}'),
                      refiner_llm_factory=lambda: MockLLMClient('{"ops": []}'),
                      store_factory=lambda: SnapshotStore(tempfile.mkdtemp()), loop_config=_cfg())
    assert len(mw.verdicts) == 2                                   # one stat verdict label per window
    assert sum(mw.verdict_tally.values()) == 2                     # tally totals the windows
    assert all(v in {"win", "loss", "flat", "insufficient"} for v in mw.verdicts)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/loop/test_compare.py::test_multi_window_collects_verdict_tally -q`
Expected: FAIL — `AttributeError: 'MultiWindowReport' object has no attribute 'verdicts'`

- [ ] **Step 3: Write the implementation**

In `alpha/loop/compare.py`:

(a) Add two fields to `MultiWindowReport` (after `sign_consistent`):

```python
    # A ROLLUP of per-window single-window verdicts (each a within-window CI), NOT a pooled cross-window
    # significance test — cohort-level inference stays the win_rate / sign-consistency direction diagnostic.
    verdicts: list[str] = Field(default_factory=list)             # per-window stat-verdict labels
    verdict_tally: dict[str, int] = Field(default_factory=dict)   # counts by label across windows
```

(b) In `multi_window`, collect each window's verdict label and build the tally. Replace the loop + return:

```python
    deltas: list[float] = []
    verdicts: list[str] = []
    for (start, end) in windows:
        cr = compare_harnesses(harness_factory, source, start, end, agent_llm_factory=agent_llm_factory,
                               refiner_llm_factory=refiner_llm_factory, store_factory=store_factory,
                               loop_config=loop_config, refiner_config=refiner_config,
                               scorer_factory=scorer_factory, shadow=shadow)
        deltas.append(cr.hch_minus_hexpert_mean_excess)
        verdicts.append(cr.stat_verdict.verdict if cr.stat_verdict is not None else "insufficient")
    n = len(deltas)
    mean_delta = sum(deltas) / n if n else 0.0
    win_rate = sum(1 for d in deltas if d > 0.0) / n if n else 0.0
    sign_consistent = n > 0 and (all(d > 0.0 for d in deltas) or all(d < 0.0 for d in deltas))
    tally: dict[str, int] = {}
    for v in verdicts:
        tally[v] = tally.get(v, 0) + 1
    return MultiWindowReport(n_windows=n, deltas=deltas, mean_delta=mean_delta, win_rate=win_rate,
                             sign_consistent=sign_consistent, verdicts=verdicts, verdict_tally=tally)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/loop/test_compare.py -q`
Expected: PASS — the new test plus all prior compare tests.

- [ ] **Step 5: Commit**

```bash
git add alpha/loop/compare.py tests/loop/test_compare.py
git commit -m "US-2e Task 5: multi_window per-window stat-verdict tally (the temp=0 multi-seed surrogate)"
```

---

### Task 6: US-2e acceptance gate + docs update

**Files:**
- Create: `tests/loop/test_us2e_acceptance.py`
- Modify: `docs/PROJECT_STATE.md` (US-2 acceptance procedure complete)

End-to-end on the real seeds: the §9/§10 acceptance procedure renders a `stat_verdict` (CI/p/MDE), a `contribution` split (offense/defense/per-family), and a multi-window verdict tally.

- [ ] **Step 1: Write the acceptance test**

```python
# tests/loop/test_us2e_acceptance.py
"""US-2e acceptance: the §9/§10 statistical decision PROCEDURE renders end-to-end on the SEEDED harness
— a paired HCH-Hexpert day-level StatVerdict (bootstrap CI + permutation p + MDE), an offense/defense +
per-family contribution split, and a multi-window verdict tally. This validates the acceptance APPARATUS
deterministically; the empirical pass/fail verdict needs a live temp=0 LLM run (MockLLM ignores prompts)."""
import tempfile
from pathlib import Path
from datetime import date
import pandas as pd
from alpha.data.source import FakeSource
from alpha.harness.loader import load_seeds
from alpha.harness.snapshot import SnapshotStore
from alpha.llm.client import MockLLMClient
from alpha.loop.inner_loop import LoopConfig
from alpha.loop.compare import compare_harnesses, multi_window
from alpha.eval.stats import StatVerdict
from alpha.eval.contribution import ContributionReport

SEEDS = Path(__file__).resolve().parents[2] / "seeds"


def _source(n=10):
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


def _agent():
    return MockLLMClient('{"candidates": [{"symbol": "RUN", "pattern": "gap_and_go", "confidence": 0.7}]}')


def test_acceptance_procedure_renders_end_to_end():
    src = _source(10)
    cal = src.trading_calendar()
    cr = compare_harnesses(lambda: load_seeds(SEEDS), src, cal[0], cal[-1], agent_llm_factory=_agent,
                           refiner_llm_factory=lambda: MockLLMClient('{"ops": []}'),
                           store_factory=lambda: SnapshotStore(tempfile.mkdtemp()),
                           loop_config=LoopConfig(horizon=2, evidence_min=2, refine_every=1), shadow=True)
    # the statistical decision procedure produced a verdict with its uncertainty recorded
    assert isinstance(cr.stat_verdict, StatVerdict)
    assert cr.stat_verdict.verdict in {"win", "loss", "flat", "insufficient"}
    assert cr.stat_verdict.n_days == len(cr.hch_loop_report.trajectory.scored_steps())
    if cr.stat_verdict.n_days >= 2:                         # CI/MDE attached once estimable
        assert cr.stat_verdict.ci_low is not None and cr.stat_verdict.mde is not None
    # offense/defense contribution split is populated (gap_and_go is an offense seed skill)
    assert isinstance(cr.contribution, ContributionReport) and cr.contribution.offense.n >= 1
    # multi-window verdict tally (the temp=0 multi-seed surrogate)
    mw = multi_window(lambda: load_seeds(SEEDS), src, [(cal[0], cal[4]), (cal[5], cal[9])],
                      agent_llm_factory=_agent, refiner_llm_factory=lambda: MockLLMClient('{"ops": []}'),
                      store_factory=lambda: SnapshotStore(tempfile.mkdtemp()),
                      loop_config=LoopConfig(horizon=2, evidence_min=2, refine_every=1))
    assert len(mw.verdicts) == 2 and sum(mw.verdict_tally.values()) == 2
```

- [ ] **Step 2: Run the full suite**

Run: `python -m pytest -q`
Expected: PASS — all prior tests plus the new US-2e stats/contribution/compare/acceptance tests green.

- [ ] **Step 3: Update `docs/PROJECT_STATE.md`**

**REPLACE the existing "Next — US-2e validation slice" block** (it currently scopes purged+embargoed CV + regime-stratified eval *into* US-2e — move those into the deferred-refinements list so the doc doesn't both claim and defer them). Add a **US-2e** entry under the US-2 section: the statistical acceptance procedure is complete — `alpha/eval/stats.py` (`StatVerdict` + `daily_series`/`paired_daily_diff` + moving-block-bootstrap CI + sign-permutation p + MDE + `verdict`, deterministic via local `random.Random(seed)`); `alpha/eval/contribution.py` (offense/defense + per-family split, resolved against the evolved HCH H); `ComparisonReport.stat_verdict` + `.contribution` computed inline in `compare_harnesses`; `multi_window` per-window verdict tally. Note the full-suite test count. **Frame honestly:** US-2e **closes the §9/§10 acceptance-METHODOLOGY gate** — the formal decision procedure (paired CI + permutation-p + MDE + offense/defense + per-family + multi-window) is built and deterministically tested. **The empirical pass/fail verdict requires a live temp=0 run** (the offline suite validates the apparatus, not efficacy; MockLLM ignores prompts). Deferred §10 refinements: purged + embargoed CV, regime-stratified eval; the Hcredit (C4) ablation arm. Update the "Next" pointer to **US-3 (intraday/halts/short-interest/SSR/social enrichment — unlocking full runner/meme/event offense)**, noting a live-LLM smoke run is the way to render the actual HCH-vs-Hexpert verdict. Keep the remaining deferred list (sizing/guard→DecisionPackage wiring; master-dispatch G sub-agents; keep-last-K checkpoint pruning).

- [ ] **Step 4: Commit**

```bash
git add tests/loop/test_us2e_acceptance.py docs/PROJECT_STATE.md
git commit -m "US-2e Task 6: acceptance gate (statistical decision procedure renders end-to-end) + PROJECT_STATE"
```

---

## Self-Review (run after writing, fix inline)

**Spec coverage (§9/§10 + §6 offense/defense):** deterministic stats models + closed-form pieces (Task 1) ✓ · bootstrap CI / permutation p / verdict (Task 2) ✓ · offense/defense + per-family split (Task 3) ✓ · `stat_verdict` + `contribution` wired into the compare (Task 4) ✓ · multi-window verdict tally — the temp=0 multi-seed surrogate (Task 5) ✓ · end-to-end acceptance procedure (Task 6) ✓. **Deferred & documented:** purged+embargoed CV + regime-stratified eval (§10 methodology refinements, gate-non-blocking — the firewall + strict walk-forward already enforce OOS no-lookahead); the Hcredit (C4) ablation arm (additive 5th arm reusing `stats.py`). **Honest framing:** US-2e closes the acceptance-PROCEDURE gate; the empirical verdict needs a live temp=0 run.

**Type consistency:** `verdict(diffs, min_days=8, *, block_len, n_boot, n_perm, seed) -> StatVerdict`; `daily_series(traj) -> list[tuple[Date,float]]` feeds `paired_daily_diff -> list[float]`. `contribution_split(traj, h) -> ContributionReport`. `ComparisonReport` gains `stat_verdict: StatVerdict|None=None` + `contribution: ContributionReport|None=None` (additive Optional, frozen-safe). `MultiWindowReport` gains `verdicts: list[str]` + `verdict_tally: dict[str,int]`. `resolve_skill` (US-2b) reused; `Skill.type`/`Skill.family` drive the buckets.

**Placeholder scan:** no TBD/TODO; every code step is complete; determinism is enforced via local `random.Random(seed)` and pinned by repeated-call equality + exact-number tests (block_len, mde, bootstrap degenerate/CI, permutation symmetric/signal); the additive Optional fields keep US-2d reports/tests green.

**Scope:** the statistical decision procedure + contribution split + multi-window tally only. No CV, no regime stratification, no ablation arm, no new arms. Closes the §9 acceptance procedure; the live verdict is a separate run.

**Adversarial-review fixes folded (2026-06-15, 4-lens review — reviewers built+ran/recomputed; the stats port is verified faithful + deterministic + CN-pinned-number-correct):**
- **[critical] float-equality test bug:** `daily_series`'s `== 0.3` would fail on a correct impl (`(0.2+0.4)/2 = 0.30000000000000004`). Rewrote the assertion to compare the date list exactly + the value with `abs(... - 0.3) < 1e-9`.
- **[important] doc self-contradiction:** Task 6 Step 3 now explicitly **replaces** the existing "Next — US-2e validation slice" PROJECT_STATE block and moves purged+embargoed CV / regime-stratification into the deferred-refinements list (so they aren't both "done in US-2e" and "deferred").
- **[minor] coverage + clarity:** renamed contribution's private `_Acc` → `_BucketAcc` (avoid two same-named private helpers vs `credit._Acc`); added a `feature`-typed seed skill to the contribution test to lock the pattern/feature→offense contract (`offense.n==2`); commented the synthetic test families; annotated `_default_block_len(200)` (round→6→clamp 5); noted that a non-zero Task-4 `mean_diff` is a real HCH/Hexpert divergence (don't loosen the tol); documented `MultiWindowReport.verdicts/verdict_tally` as a per-window **rollup**, not a pooled cross-window significance test (keeps the honest-bar framing).
