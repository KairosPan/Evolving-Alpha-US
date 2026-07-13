from datetime import date

from alpha.eval.stratify import (momo_phase, growth_clock_phase, regime_key_for, label_steps,
                                 stratified_reports, stratified_verdicts)
from alpha.eval.trajectory import Trajectory
from tests.eval._fixtures import days, step


def _traj(specs, *, horizon=2, advantage=1.0):
    """specs = list of (gainers, losers[, follow_through_rate]); last `horizon` steps unscored."""
    ds = days(len(specs))
    n = len(specs)
    steps = []
    for i, (d, spec) in enumerate(zip(ds, specs)):
        g, l = spec[0], spec[1]
        kw = {"follow_through_rate": spec[2]} if len(spec) > 2 else {}
        steps.append(step(d, scored=(i <= n - 1 - horizon), gainers=g, losers=l, advantage=advantage, **kw))
    return Trajectory(steps=steps)


def test_regime_key_for_dispatches_on_vocabulary():
    assert regime_key_for("growth") is growth_clock_phase
    assert regime_key_for("momo") is momo_phase
    assert regime_key_for("anything-else") is momo_phase
    m = step(date(2026, 6, 1), gainers=9, losers=1, follow_through_rate=0.5).market
    assert momo_phase(m, []) == "trend"                       # single-day GCycle (history ignored)
    assert growth_clock_phase(m, []).startswith("market:")    # three-state clock label


def test_label_steps_covers_every_step_and_warms_up():
    traj = _traj([(9, 1)] * 8)                                # strong up days
    labels = label_steps(traj, growth_clock_phase)
    assert set(labels) == {s.date for s in traj.steps}         # one label per step (scored or not)
    # growth clock warm-up: the first MIN_HISTORY days abstain to under_pressure
    first = traj.steps[0].date
    assert labels[first] == "market:under_pressure"


def test_stratified_reports_bucket_by_decision_day_regime():
    # two washout days then several ignition days (all scored except the last horizon)
    specs = [(1, 9), (1, 9), (5, 5), (5, 5), (5, 5), (5, 5)]   # 6 days, horizon 2 -> 4 scored
    traj = _traj(specs, horizon=2)
    reports = stratified_reports(traj, momo_phase, horizon=2)
    assert set(reports) == {"washout", "ignition"}
    # scored steps: idx 0,1 washout; idx 2,3 ignition (idx 4,5 unscored)
    assert reports["washout"].n_candidates == 2
    assert reports["ignition"].n_candidates == 2
    # totals reconcile with the pooled report
    pooled = sum(r.n_candidates for r in reports.values())
    assert pooled == len(traj.all_scored())


def test_stratified_verdicts_are_symmetric_and_per_regime():
    specs = [(1, 9), (1, 9), (1, 9), (5, 5), (5, 5), (5, 5), (5, 5), (5, 5)]   # 8 days horizon 2 -> 6 scored
    hch = _traj(specs, advantage=1.0)
    hexpert = _traj(specs, advantage=0.0)                     # identical markets, HCH advantage +1 each day
    vs = stratified_verdicts(hch, hexpert, momo_phase)
    assert set(vs) == {"washout", "ignition"}
    # every regime's paired diff is +1.0 (HCH minus Hexpert), symmetric bucketing off the shared market
    for lab, v in vs.items():
        assert abs(v.mean_diff - 1.0) < 1e-9

    # identical trajectories -> every per-regime diff is exactly 0 (verdict symmetry)
    zero = stratified_verdicts(hch, hch, momo_phase)
    assert zero and all(abs(v.mean_diff) < 1e-9 for v in zero.values())
