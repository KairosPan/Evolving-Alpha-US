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
