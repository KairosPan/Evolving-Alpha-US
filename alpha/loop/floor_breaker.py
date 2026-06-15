from __future__ import annotations

import statistics

# Scorer-aware CAPABILITY-floor breaker (self-evolution-degrades-capability). Distinct from the
# portfolio loss circuit-breaker in alpha/guard/breaker.py — different concern, different module.

_MAD_EPS = 1e-9   # MAD below this => degenerate (near-constant) series -> use the absolute floor


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
