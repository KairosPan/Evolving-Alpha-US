from __future__ import annotations

from datetime import date as Date, datetime as DateTime

from alpha.data.source import MarketDataSource
from alpha.features.breadth import counts, failed_breakout_count, follow_through_rate, gap_and_go_count
from alpha.features.runner import runner_echelon
from alpha.features.sentiment import normalize_sentiment, raw_sentiment
from alpha.state.market import MarketState
from alpha.universe.universe import build_universe

DEFAULT_MIN_SAMPLES = 60


def build_market_state(day: Date, source: MarketDataSource, history: list[float], as_of: DateTime,
                       prev_gainers: frozenset[str] = frozenset(),
                       min_samples: int = DEFAULT_MIN_SAMPLES) -> MarketState:
    """Full L1 perception build: enrich the day's universe with trailing runner depth + features.

    history = prior sentiment_raw values (<= day only); prev_gainers = the previous day's gainer set
    (the caller/loop threads it for follow-through). Reads only <= day data.

    FIREWALL CONTRACT: in production the caller (US-2 loop) MUST pass a GuardedSource(AsOfGuard(day))
    so any accidental >day fetch raises. This function reads <= day by construction (window ends at
    day; calendar filtered <= day) but does not itself install the guard.
    """
    universe = build_universe(source, day)            # snapshots already carry consecutive_up_days (US-3a)
    g, gu, lo = counts(universe)
    ft = follow_through_rate(universe, prev_gainers)
    fb = failed_breakout_count(universe)
    echelon = runner_echelon(universe.by_status("gainer"))   # same gainer set, now read (not re-fetched)
    max_tier = echelon[0].tier if echelon else 0
    raw = raw_sentiment(gainer_count=g, max_runner_tier=max_tier, follow_through=(ft or 0.0),
                        failed_breakout_rate=(fb / g if g else 0.0), loser_count=lo)
    return MarketState(
        date=day, gainer_count=g, gap_up_count=gu, loser_count=lo,
        failed_breakout_count=fb, max_runner_tier=max_tier, echelon=echelon,
        breadth_raw=float(g - lo), sentiment_raw=raw,
        sentiment_norm=normalize_sentiment(raw, history, min_samples),
        follow_through_rate=ft, gap_and_go_count=gap_and_go_count(universe), as_of=as_of)
