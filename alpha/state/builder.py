from __future__ import annotations

from datetime import date as Date, datetime as DateTime

from alpha.state.market import MarketState, RunnerRung
from alpha.universe.universe import CandidateUniverse


def build_market_state(universe: CandidateUniverse, day: Date, *, as_of: DateTime) -> MarketState:
    """Minimal MarketState from the day's universe (counts + runner echelon). US-1 adds normalization."""
    stocks = universe.all()
    gainers = [s for s in stocks if s.status == "gainer"]
    gap_ups = [s for s in stocks if s.status == "gap_up"]
    losers = [s for s in stocks if s.status == "loser"]
    failed = [s for s in stocks
              if s.status == "gap_up" and s.close is not None and s.prev_close is not None
              and s.close < s.prev_close]

    by_tier: dict[int, list[str]] = {}
    for s in stocks:
        t = s.consecutive_up_days
        if t is not None and t >= 1:
            by_tier.setdefault(t, []).append(s.symbol)
    echelon = [RunnerRung(tier=t, count=len(syms), representatives=sorted(syms))
               for t, syms in sorted(by_tier.items(), reverse=True)]
    max_tier = max(by_tier) if by_tier else 0

    return MarketState(
        date=day, gainer_count=len(gainers), gap_up_count=len(gap_ups),
        loser_count=len(losers), failed_breakout_count=len(failed),
        max_runner_tier=max_tier, echelon=echelon,
        breadth_raw=float(len(gainers) - len(losers)), sentiment_norm=None, as_of=as_of)
