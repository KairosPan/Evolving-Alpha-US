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
