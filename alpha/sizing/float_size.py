# alpha/sizing/float_size.py
#
# Float-aware L3 sizing (P5b; spec docs/superpowers/specs/2026-07-13-p5b-float-feed-design.md). Today
# `size_tier` (flat|probe|core|heavy) comes from confidence x risk_gate and knows nothing about how much
# stock actually trades. Real free float is the missing liquidity input: a `heavy` on a 3M-share micro-float
# name and a `heavy` on a 500M-share large-cap are NOT the same bet — the micro name can't absorb the same
# dollars without the buyer moving the tape.
#
# A PURE module: tier + a float number (RAW shares) + SizingConfig in, refined tier / share-count out. No
# source or universe imports (the universe->shares extraction lives at the SizingPolicy seam). Everything
# here is ADDITIVE / DEFAULT-OFF / VERDICT-NEUTRAL: `free_float_shares is None` (no float feed) leaves the
# tier exactly as today, and nothing here is ever read by scoring (size_tier never enters the eval).
from __future__ import annotations

from dataclasses import dataclass

from alpha.sizing.position import SIZE_TIER_WEIGHT, SizeTier, SizingConfig


def float_capped_tier(tier: SizeTier, free_float_shares: float | None, config: SizingConfig) -> SizeTier:
    """Liquidity-aware cap: a small free-float name can't carry a big position without moving the tape, so
    cap its tier. `None` float (no feed) or float >= float_large_shares -> tier UNCHANGED (the byte-identical
    default-off case / a huge-float name is not float-constrained). [mid, large) -> ceiling 'core';
    below mid -> ceiling 'probe'. Only ever TIGHTENS (never raises a smaller tier) — safety-only, exactly
    like sizing.action.derisk_tier. It never zeroes a kept candidate to 'flat': dropping a name is the L4
    guard's job, not sizing's."""
    if free_float_shares is None or free_float_shares >= config.float_large_shares:
        return tier
    ceiling: SizeTier = "core" if free_float_shares >= config.float_mid_shares else "probe"
    return tier if SIZE_TIER_WEIGHT[tier] <= SIZE_TIER_WEIGHT[ceiling] else ceiling


def float_participation_shares(tier: SizeTier, price: float | None, free_float_shares: float | None,
                               config: SizingConfig) -> tuple[int | None, bool]:
    """The share count for `tier`'s dollar budget at `price`, CAPPED so it never exceeds
    max_float_participation of the free float. Returns (shares, participation_capped). A small-float name ->
    the cap binds -> fewer shares for the same dollar risk; a huge-float name -> the cap never binds -> the
    full dollar-budget shares. `None`/non-positive price or `None` float -> (None, False) (not computable /
    off). `flat` (weight 0) -> (0, False)."""
    if price is None or price <= 0 or free_float_shares is None:
        return None, False
    dollar_budget = SIZE_TIER_WEIGHT[tier] * config.name_dollar_unit * config.max_name_weight
    budget_shares = dollar_budget / price
    cap_shares = config.max_float_participation * free_float_shares
    capped = budget_shares > cap_shares
    return int(min(budget_shares, cap_shares)), capped


@dataclass(frozen=True)
class FloatSizing:
    """The float-refined size for one name: the capped tier + the liquidity-capped share-count target."""
    tier: SizeTier                    # float-capped tier (float_capped_tier)
    target_shares: int | None         # participation-capped share count (None if price/float absent)
    participation_capped: bool        # the float participation cap bound (fewer shares than the $ budget)


def refine_sizing(tier: SizeTier, free_float_shares: float | None, config: SizingConfig, *,
                  price: float | None = None) -> FloatSizing:
    """Bundle both refinements: cap the tier for a small float, then compute the participation-capped
    share-count for that capped tier. `free_float_shares is None` -> tier unchanged, target_shares None."""
    capped_tier = float_capped_tier(tier, free_float_shares, config)
    shares, part_capped = float_participation_shares(capped_tier, price, free_float_shares, config)
    return FloatSizing(tier=capped_tier, target_shares=shares, participation_capped=part_capped)
