from datetime import date

import pytest

from alpha.eval.purged_cv import scored_cutoff, embargo_trajectory, partition_folds
from tests.eval._fixtures import days, trajectory


def test_scored_cutoff_formalizes_the_scored_flag():
    # 10 days, horizon 2: last scored decision index = 10-1-2 = 7 (structural purge). embargo drops more.
    assert scored_cutoff(10, horizon=2, embargo=0) == 7
    assert scored_cutoff(10, horizon=2, embargo=3) == 4
    # over-embargo -> -1 (nothing scored)
    assert scored_cutoff(4, horizon=2, embargo=5) == -1


def test_embargo_zero_is_the_same_object_byte_identical():
    traj = trajectory(days(8), horizon=2)
    assert embargo_trajectory(traj, 0) is traj
    assert embargo_trajectory(traj, -1) is traj


def test_embargo_drops_the_last_scored_steps_and_clears_their_outcomes():
    traj = trajectory(days(8), horizon=2)          # 8 days, last 2 unscored -> 6 scored
    assert len(traj.scored_steps()) == 6
    out = embargo_trajectory(traj, 2)
    scored = out.scored_steps()
    assert len(scored) == 4                          # dropped the last 2 scored
    # the two dropped steps are still present as decisions but unscored + outcomes cleared
    assert len(out.steps) == 8
    dropped = [s for s in out.steps if not s.scored]
    assert len(dropped) == 4 and all(s.outcomes == {} for s in dropped)
    # the SURVIVING scored steps are the earliest ones (right-edge purge)
    assert [s.date for s in scored] == [s.date for s in traj.scored_steps()[:4]]


def test_embargo_beyond_scored_count_leaves_nothing_scored():
    traj = trajectory(days(6), horizon=2)            # 4 scored
    out = embargo_trajectory(traj, 99)
    assert out.scored_steps() == []
    assert len(out.steps) == 6                        # decisions preserved


def test_partition_folds_gaps_prevent_label_crossing():
    d = days(30)
    iterate, reserved = partition_folds(d, n_folds=3, horizon=2, embargo=1, reserved=1)
    assert len(iterate) == 2 and len(reserved) == 1
    folds = iterate + reserved
    gap = 2 - 1 + 1                                   # horizon-1+embargo = 2 days between folds
    for (s0, e0), (s1, e1) in zip(folds, folds[1:]):
        assert s0 <= e0 < s1 <= e1
        # count trading days strictly between e0 and s1 must be >= gap
        between = [x for x in d if e0 < x < s1]
        assert len(between) >= gap


def test_partition_folds_reserved_split_is_the_tail():
    d = days(40)
    iterate, reserved = partition_folds(d, n_folds=4, horizon=2, embargo=0, reserved=2)
    assert len(iterate) == 2 and len(reserved) == 2
    # reserved folds come strictly after the iterate folds (held-out tail)
    assert iterate[-1][1] < reserved[0][0]


def test_partition_folds_raises_when_too_short():
    with pytest.raises(ValueError):
        partition_folds(days(4), n_folds=3, horizon=2, embargo=1)
