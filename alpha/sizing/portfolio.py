from __future__ import annotations

from dataclasses import dataclass

from alpha.sizing.correlation import Pick, correlated_groups, group_by_narrative
from alpha.sizing.position import SIZE_TIER_WEIGHT, SizeTier, SizingConfig, size_tier


@dataclass(frozen=True)
class SizedPick:
    symbol: str
    narrative: str
    size_tier: SizeTier


@dataclass(frozen=True)
class PortfolioPlan:
    sized: list[SizedPick]                 # per-pick size tier (what the human sees per name)
    correlated_groups: list[list[str]]     # multi-ticker narratives = one bet each
    total_exposure: float                  # sum of per-narrative netted weights (post-cap)
    total_exposure_budget: float           # risk_gate * max_total_exposure (matches DecisionPackage §4.1)
    capped: bool                           # raw netted exposure exceeded the budget


def plan_portfolio(picks: list[Pick], risk_gate: float, config: SizingConfig) -> PortfolioPlan:
    """Assign size tiers, net same-narrative picks to one bet, cap aggregate exposure by risk_gate."""
    sized = [SizedPick(symbol=p.symbol, narrative=p.narrative,
                       size_tier=size_tier(p.confidence, risk_gate)) for p in picks]
    tier_by_symbol = {s.symbol: s.size_tier for s in sized}
    # each narrative group counts ONCE, at its strongest-conviction member's weight (one bet)
    raw_exposure = 0.0
    for members in group_by_narrative(picks).values():
        raw_exposure += max(SIZE_TIER_WEIGHT[tier_by_symbol[m.symbol]] for m in members) \
            * config.max_name_weight
    budget = max(0.0, risk_gate) * config.max_total_exposure
    capped = raw_exposure > budget
    total = min(raw_exposure, budget)
    return PortfolioPlan(sized=sized, correlated_groups=correlated_groups(picks),
                         total_exposure=total, total_exposure_budget=budget, capped=capped)
