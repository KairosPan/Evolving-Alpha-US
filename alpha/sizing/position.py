from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

SizeTier = Literal["flat", "probe", "core", "heavy"]

# fraction of a single-name unit allocated at each tier
SIZE_TIER_WEIGHT: dict[SizeTier, float] = {"flat": 0.0, "probe": 0.25, "core": 0.5, "heavy": 1.0}


@dataclass(frozen=True)
class SizingConfig:
    """Risk budget (in single-name 'units'). Seed initial values — evolvable later."""
    max_name_weight: float = 1.0       # max weight any one name can carry
    max_total_exposure: float = 4.0    # max aggregate netted exposure at full risk-on (risk_gate=1)
    # ── float-aware sizing (P5b; spec 2026-07-13-p5b-float-feed-design.md). Thresholds in RAW SHARES;
    #    all default-off unless a float number is threaded into size_decision/plan_portfolio (floats=None
    #    -> the cap branch is never entered -> byte-identical). Seed values, evolvable later.
    float_large_shares: float = 50_000_000.0   # free float >= this -> UNCONSTRAINED (huge-float name)
    float_mid_shares: float = 10_000_000.0     # [mid, large) -> cap 'core'; below mid -> cap 'probe'
    max_float_participation: float = 0.01      # one bet takes at most this fraction of free float (liquidity)
    name_dollar_unit: float = 100_000.0        # $ per single-name unit (heavy = 1.0x) -> share-count target

    def __post_init__(self) -> None:
        # Fail-fast on a non-monotone float-threshold misconfig: mid must not exceed large, else the
        # [mid, large) 'core' band is empty and mid-float names silently miss capping (a cap-loosening
        # surprise the float review flagged). The only-tightens invariant itself is structural (the
        # SIZE_TIER_WEIGHT min-guard in float_capped_tier), independent of this check.
        if self.float_mid_shares > self.float_large_shares:
            raise ValueError(
                f"float_mid_shares ({self.float_mid_shares}) must be <= float_large_shares "
                f"({self.float_large_shares})")


def size_tier(confidence: float, risk_gate: float) -> SizeTier:
    """Map conviction x regime appetite to a discrete size tier. score = confidence * risk_gate.

    The regime risk_gate (from G_cycle) gates conviction: a strong pick in a risk-off tape sizes
    small — the executable form of 'respect the regime'.
    """
    score = max(0.0, confidence) * max(0.0, risk_gate)
    if score < 0.15:
        return "flat"
    if score < 0.35:
        return "probe"
    if score < 0.6:
        return "core"
    return "heavy"
