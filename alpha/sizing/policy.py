from __future__ import annotations

from alpha.eval.decision import DecisionPackage, Portfolio
from alpha.regime.classifier import GCycle
from alpha.sizing.correlation import Pick
from alpha.sizing.portfolio import plan_portfolio
from alpha.sizing.position import SizingConfig, size_tier
from alpha.state.market import MarketState

_DEFAULT_CONFIG = SizingConfig()


def size_decision(decision: DecisionPackage, *, state: MarketState,
                  config: SizingConfig = _DEFAULT_CONFIG) -> DecisionPackage:
    """Apply L3 sizing to a (already L4-guarded) DecisionPackage: assign each KEPT candidate a size_tier
    from confidence x regime risk_gate, and attach the portfolio plan (exposure budget + correlated
    groups). VERDICT-NEUTRAL: scoring is equal-weighted and never reads size_tier/portfolio, so this only
    enriches the human-confirmation surface (+ the DAgger record). FIREWALL-CLEAN: reads only the decision
    + state (no source fetch). Frozen models -> rebuilt via model_copy.

    The correlation key is candidate.narrative (the sympathy/theme tag the agent emits, US-5): same
    narrative -> one netted bet, so the portfolio reflects the "one correlated bet" doctrine. Untagged
    ("") names stand alone. DEFERRED: fill_feasibility (needs the intraday inference path — no eval/fill
    module), per-candidate taboo_check (the L4 guard drops vetoed candidates rather than soft-annotating),
    and a per-narrative-line regime read (needs theme-level market breadth we don't have offline).
    """
    regime = decision.regime or GCycle().read(state)
    rg = regime.risk_gate
    sized = [c.model_copy(update={"size_tier": size_tier(c.confidence, rg)}) for c in decision.candidates]
    plan = plan_portfolio([Pick(symbol=c.symbol, narrative=c.narrative, confidence=c.confidence)
                           for c in sized], rg, config)
    portfolio = Portfolio(total_exposure_budget=plan.total_exposure_budget,
                          correlated_groups=plan.correlated_groups,
                          total_exposure=plan.total_exposure, capped=plan.capped)
    return decision.model_copy(update={"candidates": sized, "portfolio": portfolio})


class SizingPolicy:
    """Composable L3 sizing decorator: wraps any DecisionPolicy, runs it, then sizes the result. Compose
    OUTSIDE GuardedPolicy so it sizes the post-veto survivors: SizingPolicy(GuardedPolicy(agent, source))."""

    def __init__(self, inner) -> None:
        self._inner = inner

    def decide(self, state: MarketState, universe) -> DecisionPackage:
        return size_decision(self._inner.decide(state, universe), state=state)
