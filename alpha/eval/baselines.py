from __future__ import annotations

from alpha.eval.decision import Candidate, DecisionPackage
from alpha.state.market import MarketState
from alpha.universe.universe import CandidateUniverse


class NoTradePolicy:
    """Floor baseline: never trade."""

    def decide(self, state: MarketState, universe: CandidateUniverse) -> DecisionPackage:
        return DecisionPackage(date=state.date, no_trade_reason="baseline:no-trade")


class ChaseBiggestGainerPolicy:
    """Floor baseline (Hmin): blindly chase the day's biggest gainer (naivest US momentum)."""

    def decide(self, state: MarketState, universe: CandidateUniverse) -> DecisionPackage:
        gainers = universe.by_status("gainer")
        ranked = [s for s in gainers if s.pct_change is not None]
        if not ranked:
            return DecisionPackage(date=state.date, no_trade_reason="no gainers")
        top = max(s.pct_change for s in ranked)
        picks = sorted((s for s in ranked if abs(s.pct_change - top) < 1e-9), key=lambda s: s.symbol)
        cands = [Candidate(symbol=s.symbol, name=s.name, pattern="chase_biggest_gainer",
                           reason=f"+{s.pct_change:.0f}% biggest gainer") for s in picks]
        return DecisionPackage(date=state.date, candidates=cands)


class PoolAveragePolicy:
    """Benchmark baseline: buy the WHOLE gainer pool — the ~zero-advantage reference that answers
    'how much better than buying every gainer is the agent?'.

    NOTE: it buys the *universe* gainers (build_universe's regime-relative gainer_pct screen), which
    is NOT identical to the scorer's day_baseline pool (the EXOGENOUS fixed-threshold gainers). So its
    advantage is only APPROXIMATELY zero — exactly zero would require the screen threshold to equal
    the exogenous GAINER_PCT. It is the closest practical zero-point, not an algebraic identity."""

    def decide(self, state: MarketState, universe: CandidateUniverse) -> DecisionPackage:
        gainers = sorted(universe.by_status("gainer"), key=lambda s: s.symbol)
        if not gainers:
            return DecisionPackage(date=state.date, no_trade_reason="no gainers")
        cands = [Candidate(symbol=s.symbol, name=s.name, pattern="pool_avg", reason="pool baseline")
                 for s in gainers]
        return DecisionPackage(date=state.date, candidates=cands)
