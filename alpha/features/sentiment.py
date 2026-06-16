from __future__ import annotations

DEFAULT_MIN_SAMPLES = 60   # regime-relative normalization needs >= this many trailing sentiment_raw days


def raw_sentiment(gainer_count: int, max_runner_tier: int, follow_through: float,
                  failed_breakout_rate: float, loser_count: int) -> float:
    """Raw US-momentum sentiment composite (dimensionless; only for cross-day relative comparison).

    Positive: gainer breadth, runner depth, follow-through; negative: failed-breakout rate, losers.
    Weights are prior initial values — later evolvable skill params (blueprint §6.1 analog).
    """
    return (
        0.1 * gainer_count
        + 2.0 * max_runner_tier
        + 3.0 * follow_through
        - 5.0 * failed_breakout_rate
        - 0.2 * loser_count
    )


def normalize_sentiment(value: float, history: list[float] | None, min_samples: int) -> float | None:
    """Regime-relative normalization: percentile of `value` within history (<= current day) in [0,1].

    Returns None when samples insufficient (never fabricate an absolute threshold).
    """
    if history is None or len(history) < min_samples:
        return None
    le = sum(1 for h in history if h <= value)
    return le / len(history)
