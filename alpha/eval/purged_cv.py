"""Purged & embargoed cross-validation for the honest-eval harness (P6 spec §1; kairos-mining §2.8).

A decision at day t enters at t+1 and exits at t+horizon — its forward-return LABEL spans [t+1, t+horizon].
`WalkForwardEval` / the `InnerLoop` already leave the last `horizon` decisions of a window UNSCORED (no
t+horizon day inside it); that trailing-tail unscored set IS the built-in López de Prado purge (a
window's scored labels only read data <= its own last day). This module makes the purge explicit and
generalizes it:

  * `embargo` drops `embargo` MORE trailing scored decisions (an autocorrelation / edge buffer),
  * fold GAPS of `horizon - 1 + embargo` days keep any label (+ its buffer) from crossing a fold split,
  * a `reserved` holdout tail is never looked at while iterating (the residual Goodhart surface is
    HUMAN meta-iteration — reserving folds mitigates, cannot eliminate; documented, not enforced).

Pure stdlib; applied SYMMETRICALLY to every verdict arm (one embargo implementation both
`WalkForwardEval.walk()` and `compare_harnesses` call), so verdict symmetry is preserved by construction.
"""
from __future__ import annotations

from datetime import date as Date

from alpha.eval.trajectory import Trajectory


def scored_cutoff(n_days: int, horizon: int, embargo: int = 0) -> int:
    """Highest 0-based decision index that is scored: a decision at index j is scored iff
    j <= n_days - 1 - horizon - embargo. The `horizon` tail is the structural purge (the exit must fall
    inside the window); `embargo` drops that many MORE trailing decisions. Clamped to -1 (nothing scores)."""
    return max(-1, n_days - 1 - horizon - embargo)


def embargo_trajectory(traj: Trajectory, embargo: int = 0) -> Trajectory:
    """Return a copy of `traj` with the last `embargo` SCORED steps re-marked scored=False (outcomes
    cleared) — their labels sit at the window's right edge / would cross a contiguous-fold boundary.

    embargo <= 0 returns `traj` UNCHANGED (same object -> reports byte-identical). Decisions are always
    preserved (n_decisions/n_no_trade unchanged); only the scored SET shrinks, identically for whichever
    arm this is applied to."""
    if embargo <= 0:
        return traj
    scored_idxs = [i for i, s in enumerate(traj.steps) if s.scored]
    if not scored_idxs:
        return traj
    k = min(embargo, len(scored_idxs))
    drop = set(scored_idxs[-k:])
    new_steps = [s.model_copy(update={"scored": False, "outcomes": {}}) if i in drop else s
                 for i, s in enumerate(traj.steps)]
    return Trajectory(steps=new_steps)


def partition_folds(days: list[Date], n_folds: int, horizon: int, embargo: int = 0,
                    reserved: int = 0) -> tuple[list[tuple[Date, Date]], list[tuple[Date, Date]]]:
    """Split `days` (a trading-day slice) into `n_folds` contiguous NON-overlapping windows separated by
    a gap of `horizon - 1 + embargo` days, so no scored label (nor its embargo buffer) of fold k crosses
    into fold k+1 (purged cross-validation). The last `reserved` folds are the HELD-OUT set never looked
    at while iterating on refiner prompts/config. Returns (iterate_folds, reserved_folds).

    Each fold is >= horizon + 1 days (>= 1 scored decision). Raises ValueError if `days` is too short, or
    on out-of-range n_folds / reserved / horizon / embargo."""
    if horizon < 2:
        raise ValueError(f"horizon must be >= 2, got {horizon}")
    if embargo < 0:
        raise ValueError(f"embargo must be >= 0, got {embargo}")
    if n_folds < 1:
        raise ValueError(f"n_folds must be >= 1, got {n_folds}")
    if not 0 <= reserved < n_folds:
        raise ValueError(f"reserved must be in [0, n_folds), got {reserved}")
    gap = horizon - 1 + embargo
    n = len(days)
    min_fold = horizon + 1
    avail = n - gap * (n_folds - 1)
    if avail < min_fold * n_folds:
        raise ValueError(f"{n} days too short for {n_folds} folds of >= {min_fold} days with gap {gap}")
    fold_len = avail // n_folds
    folds: list[tuple[Date, Date]] = []
    cursor = 0
    for i in range(n_folds):
        end_idx = n - 1 if i == n_folds - 1 else cursor + fold_len - 1
        folds.append((days[cursor], days[end_idx]))
        cursor = end_idx + 1 + gap
    split = n_folds - reserved
    return folds[:split], folds[split:]
