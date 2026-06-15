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
