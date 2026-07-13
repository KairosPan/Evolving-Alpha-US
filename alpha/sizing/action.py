from __future__ import annotations

from typing import Literal

from alpha.sizing.position import SIZE_TIER_WEIGHT, SizeTier

# The recommendation vocabulary (P0.6, spec 2026-07-13-p06). `enter` = a NEW bet (today's only
# shape); `trim`/`exit` = derisk a name we already HOLD. Holdings are not modeled yet, so nothing
# emits trim/exit and the vocabulary defaults to `enter` = byte-identical to pre-P0.6 behaviour.
RecommendationAction = Literal["enter", "trim", "exit"]
DEFAULT_ACTION: RecommendationAction = "enter"


def candidate_action(candidate) -> RecommendationAction:
    """The candidate's recommendation action; `enter` when the field is absent. The shared `Candidate`
    now carries `action` (default "enter", spec 2026-07-13-p05 §7); this stays a defensive `getattr` so
    the L4/L3 seams also accept any non-Candidate caller (e.g. a bare Pick/namespace) and remain
    byte-identical while no producer emits trim/exit."""
    return getattr(candidate, "action", DEFAULT_ACTION)


def derisk_tier(action: RecommendationAction, tier: SizeTier) -> SizeTier:
    """The executable meaning of `derisk_on_breakdown.rule` ('持仓降至核心仓位'): map a target
    action onto a size tier. `enter` leaves the sized tier alone; `trim` caps it at `core`
    (weight 0.5 = 原仓位的 1/2) and never RAISES a smaller tier; `exit` goes `flat`."""
    if action == "exit":
        return "flat"
    if action == "trim":
        return tier if SIZE_TIER_WEIGHT[tier] <= SIZE_TIER_WEIGHT["core"] else "core"
    return tier
