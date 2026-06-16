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

    Narrative key for correlation is candidate.family (the agent does not set it yet -> "" -> each name is
    its own bet, correlated_groups empty); netting auto-activates when family/narrative tagging lands.
    DEFERRED (not this slice): fill_feasibility (needs the intraday inference path — no eval/fill module)
    and per-candidate taboo_check (the L4 guard drops vetoed candidates rather than soft-annotating kept ones).
    """
    regime = decision.regime or GCycle().read(state)
    rg = regime.risk_gate
    sized = [c.model_copy(update={"size_tier": size_tier(c.confidence, rg)}) for c in decision.candidates]
    plan = plan_portfolio([Pick(symbol=c.symbol, narrative=c.family, confidence=c.confidence)
                           for c in sized], rg, config)
    portfolio = Portfolio(total_exposure_budget=plan.total_exposure_budget,
                          correlated_groups=plan.correlated_groups)
    return decision.model_copy(update={"candidates": sized, "portfolio": portfolio})


class SizingPolicy:
    """Composable L3 sizing decorator: wraps any DecisionPolicy, runs it, then sizes the result. Compose
    OUTSIDE GuardedPolicy so it sizes the post-veto survivors: SizingPolicy(GuardedPolicy(agent, source))."""

    def __init__(self, inner) -> None:
        self._inner = inner

    def decide(self, state: MarketState, universe) -> DecisionPackage:
        return size_decision(self._inner.decide(state, universe), state=state)
