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
