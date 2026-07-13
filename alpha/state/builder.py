from __future__ import annotations

from collections.abc import Sequence
from datetime import date as Date, datetime as DateTime

from alpha.features.breadth import (
    BreadthReading, counts, failed_breakout_count, follow_through_rate, gap_and_go_count,
)
from alpha.features.runner import runner_echelon
from alpha.features.sentiment import DEFAULT_MIN_SAMPLES, normalize_sentiment, raw_sentiment
from alpha.state.market import MarketState
from alpha.universe.universe import CandidateUniverse


def build_market_state(universe: CandidateUniverse, day: Date, *, as_of: DateTime,
                       history: Sequence[float] = (),
                       prev_gainers: frozenset[str] = frozenset(),
                       min_samples: int = DEFAULT_MIN_SAMPLES,
                       breadth: BreadthReading | None = None,
                       market_counts: tuple[int, int] | None = None) -> MarketState:
    """The L1 perception build from the day's (prebuilt) universe: breadth counts + runner echelon +
    follow-through + sentiment composite. The driver threads `history` (prior-day sentiment_raw, <= day)
    and `prev_gainers` (the previous day's gainer symbols); with the empty defaults this reproduces the
    earlier minimal build (follow_through_rate=None, sentiment_norm=None) for back-compat.

    Bootstrap: on the first day `prev_gainers` is empty, so follow_through_rate is None (same as the old
    minimal builder); a persistent runner reads frontside from day 2 onward. `sentiment_raw` is appended
    by the caller to `history` to feed the NEXT day's sentiment_norm percentile — today's regime read is
    driven by follow_through_rate, not sentiment_raw. sentiment_norm stays None until history reaches
    min_samples (never fabricate an absolute threshold).

    FIREWALL: reads only the passed universe + threaded history/breadth — no >day fetch. The caller
    (the live loop) builds `universe` through a GuardedSource(AsOfGuard(day)); this function does not
    re-fetch. Breadth is computed the same trailing-only way and threaded in via `breadth` (like
    history/prev_gainers): default None leaves the four breadth fields None ("not computed") so every
    current caller's MarketState is byte-identical to the pre-P0.4 build.

    `market_counts` (P2, gainer/loser over the FULL tape via `universe.tape_breadth`) decouples the
    MARKET-breadth fields (`gainer_count`/`loser_count`/`breadth_raw` — the growth market clock + panic
    inputs) from the candidate universe screen. Under the "gainer" screen it equals `counts(universe)`
    (byte-identical); under "trend_template" the candidate universe carries no gainer/loser counts, so
    without this the clock + panic would starve. Default None -> the candidate counts (byte-identical).
    The momo-oriented features (sentiment / echelon / follow-through / failed-breakout) stay derived from
    the candidate `universe` — the momo GCycle that reads them only runs under the gainer screen, where
    the two coincide; the growth clock reads only the decoupled gainer/loser counts.
    """
    g, gu, lo = counts(universe)
    ft = follow_through_rate(universe, prev_gainers)
    fb = failed_breakout_count(universe)
    echelon = runner_echelon(universe.by_status("gainer"))
    max_tier = echelon[0].tier if echelon else 0
    raw = raw_sentiment(gainer_count=g, max_runner_tier=max_tier, follow_through=(ft or 0.0),
                        failed_breakout_rate=(fb / g if g else 0.0), loser_count=lo)
    mg, mlo = market_counts if market_counts is not None else (g, lo)   # market breadth (clock/panic input)
    return MarketState(
        date=day, gainer_count=mg, gap_up_count=gu, loser_count=mlo, failed_breakout_count=fb,
        max_runner_tier=max_tier, echelon=echelon, breadth_raw=float(mg - mlo), sentiment_raw=raw,
        sentiment_norm=normalize_sentiment(raw, list(history), min_samples),
        follow_through_rate=ft, gap_and_go_count=gap_and_go_count(universe),
        pct_above_200dma=(breadth.pct_above_200dma if breadth else None),
        net_new_highs=(breadth.net_new_highs if breadth else None),
        advances=(breadth.advances if breadth else None),
        declines=(breadth.declines if breadth else None), as_of=as_of)
