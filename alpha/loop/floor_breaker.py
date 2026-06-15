from __future__ import annotations

import math
import statistics

# Scorer-aware CAPABILITY-floor breaker (self-evolution-degrades-capability). Distinct from the
# portfolio loss circuit-breaker in alpha/guard/breaker.py — different concern, different module.

_MAD_EPS = 1e-9   # MAD below this => degenerate (near-constant) series -> use the absolute floor
_ZERO_EPS = 1e-12  # a shadow advantage below this magnitude counts as exactly zero (excluded from MAD)


def _mad(xs: list[float]) -> float:
    """Median absolute deviation (raw, not scaled): median(|x - median(x)|). Robust scale."""
    m = statistics.median(xs)
    return statistics.median([abs(x - m) for x in xs])


def _fallback_trip(history: list[float], k: int, c: float,
                   floor_abs: float) -> tuple[bool, float, float, str]:
    """Self-calibrating capability floor on the per-day ADVANTAGE series (no shadow arm).

    history = full daily-advantage series (ascending); caller guarantees 1 <= k <= len(history).
    Trip when mean(history[-k:]) < median(history) - c*MAD(history). When MAD ~ 0 (degenerate
    constant series, no robust scale) fall back to the absolute floor: mean(history[-k:]) < floor_abs.
    Returns (tripped, rolling, threshold, reason)."""
    window = history[-k:]
    rolling = sum(window) / len(window)
    mad = _mad(history)
    if mad < _MAD_EPS:
        return (rolling < floor_abs, rolling, floor_abs, "rolling < floor_abs (MAD~0 backstop)")
    threshold = statistics.median(history) - c * mad
    return (rolling < threshold, rolling, threshold, "rolling < median - c*MAD")


def _shadow_eps_abs(shadow_vals: list[float], c: float, floor: float) -> float:
    """Absolute epsilon floor for the paired-diff trip: c * MAD(nonzero shadow values). Falls back to
    `floor` when the shadow series is all-zero (empty-position reference) or constant (MAD ~ 0)."""
    nz = [v for v in shadow_vals if abs(v) > _ZERO_EPS]
    if not nz:
        return floor
    m = _mad(nz)
    if m < _MAD_EPS:
        return floor
    return c * m


def _shadow_trip(diffs: list[float], k: int, lam: float,
                 eps_abs: float) -> tuple[bool, float, float, str]:
    """Paired/shadow capability-floor trip on the per-day (own - reference) advantage diff series.
    Trip iff mean(diffs[-k:]) < -max(lam*stdev, eps_abs) (own under the reference by a real margin) AND
    the direction sub-gate holds: #strictly-negative days in the window >= ceil(k/2)+1 (blocks a single
    big-negative day). Returns (tripped, rolling, threshold, reason) — same 4-tuple shape as _fallback_trip
    so the inner-loop rollback/freeze machinery is shared. Caller guarantees 1 <= k <= len(diffs)."""
    window = diffs[-k:]
    mean_d = sum(window) / len(window)
    sd = statistics.stdev(window) if len(window) >= 2 else 0.0
    thr = max(lam * sd, eps_abs)
    n_neg = sum(1 for d in window if d < 0.0)
    need = math.ceil(k / 2) + 1
    trip = (mean_d < -thr) and (n_neg >= need)
    return (trip, mean_d, -thr, "shadow: mean(diff) < -max(lambda*sd, eps) & direction gate")
