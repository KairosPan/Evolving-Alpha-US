from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

from alpha.sizing.correlation import Pick, correlated_groups, group_by_narrative
from alpha.sizing.float_size import float_capped_tier
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


def plan_portfolio(picks: list[Pick], risk_gate: float, config: SizingConfig, *,
                   floats: Mapping[str, float] | None = None) -> PortfolioPlan:
    """Assign size tiers, net same-narrative picks to one bet, cap aggregate exposure by risk_gate.

    P5b (spec 2026-07-13-p5b-float-feed): when `floats` (symbol -> free float in RAW shares) is provided,
    each pick's tier is further capped for a small float (liquidity-aware), so the netted exposure reflects
    the same caps as the per-name tiers. floats=None -> byte-identical."""
    def _tier(p: Pick) -> SizeTier:
        t = size_tier(p.confidence, risk_gate)
        return float_capped_tier(t, floats.get(p.symbol), config) if floats is not None else t

    sized = [SizedPick(symbol=p.symbol, narrative=p.narrative, size_tier=_tier(p)) for p in picks]
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
