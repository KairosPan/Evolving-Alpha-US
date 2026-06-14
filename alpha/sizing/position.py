from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

SizeTier = Literal["flat", "probe", "core", "heavy"]

# fraction of a single-name unit allocated at each tier
SIZE_TIER_WEIGHT: dict[str, float] = {"flat": 0.0, "probe": 0.25, "core": 0.5, "heavy": 1.0}


@dataclass(frozen=True)
class SizingConfig:
    """Risk budget (in single-name 'units'). Seed initial values — evolvable later."""
    max_name_weight: float = 1.0       # max weight any one name can carry
    max_total_exposure: float = 4.0    # max aggregate netted exposure at full risk-on (risk_gate=1)


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
