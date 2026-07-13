"""Float-aware L3 sizing pure module (P5b; spec 2026-07-13-p5b-float-feed-design.md). A small free float
caps the tier (liquidity-aware) and binds the share-count participation cap; a huge float is unconstrained;
None float (no feed) is byte-identical. Nothing here is ever read by scoring (verdict-neutral)."""
from alpha.sizing.float_size import (
    FloatSizing,
    float_capped_tier,
    float_participation_shares,
    refine_sizing,
)
from alpha.sizing.position import SizingConfig

CFG = SizingConfig()   # large=50M, mid=10M, participation=1%, name_dollar_unit=100k


# ── float_capped_tier ───────────────────────────────────────────────────────────────────────────────

def test_none_float_leaves_tier_unchanged():
    for t in ("flat", "probe", "core", "heavy"):
        assert float_capped_tier(t, None, CFG) == t        # no feed -> byte-identical


def test_huge_float_is_unconstrained():
    assert float_capped_tier("heavy", 500_000_000.0, CFG) == "heavy"   # 500M >> large -> not capped


def test_mid_float_caps_at_core():
    assert float_capped_tier("heavy", 20_000_000.0, CFG) == "core"     # [mid, large) -> ceiling core
    assert float_capped_tier("probe", 20_000_000.0, CFG) == "probe"    # already below ceiling -> unchanged


def test_small_float_caps_at_probe():
    assert float_capped_tier("heavy", 3_000_000.0, CFG) == "probe"     # < mid -> ceiling probe
    assert float_capped_tier("core", 3_000_000.0, CFG) == "probe"


def test_cap_only_tightens_never_raises():
    # a small tier stays small even on a huge float (the cap is a ceiling, never a floor)
    assert float_capped_tier("probe", 3_000_000.0, CFG) == "probe"
    assert float_capped_tier("flat", 3_000_000.0, CFG) == "flat"       # never resurrects a flat name


# ── float_participation_shares (the share-count sensitive to float) ──────────────────────────────────

def test_huge_float_gets_full_dollar_budget_shares():
    # heavy: weight 1.0 x $100k / $10 = 10_000 shares; 1% of 500M = 5M >> 10k -> cap does NOT bind
    shares, capped = float_participation_shares("heavy", price=10.0, free_float_shares=500_000_000.0, config=CFG)
    assert shares == 10_000 and capped is False


def test_small_float_participation_cap_binds():
    # heavy dollar-budget = 10_000 shares, but 1% of 800k float = 8_000 -> capped to 8_000 (fewer shares)
    shares, capped = float_participation_shares("heavy", price=10.0, free_float_shares=800_000.0, config=CFG)
    assert shares == 8_000 and capped is True


def test_participation_none_when_price_or_float_absent():
    assert float_participation_shares("heavy", None, 1_000_000.0, CFG) == (None, False)
    assert float_participation_shares("heavy", 10.0, None, CFG) == (None, False)
    assert float_participation_shares("heavy", 0.0, 1_000_000.0, CFG) == (None, False)


def test_flat_tier_is_zero_shares():
    assert float_participation_shares("flat", 10.0, 500_000_000.0, CFG) == (0, False)


# ── refine_sizing bundles both (small float -> capped tier AND capped share-count) ───────────────────

def test_refine_sizing_small_float_caps_tier_and_shares():
    fs = refine_sizing("heavy", free_float_shares=800_000.0, config=CFG, price=10.0)
    assert isinstance(fs, FloatSizing)
    assert fs.tier == "probe"                    # heavy -> probe (< mid)
    # probe dollar-budget = 0.25 x $100k / $10 = 2_500 shares; 1% of 800k = 8_000 -> 2_500 (cap not binding
    # at the reduced tier). The share-count is computed on the CAPPED tier.
    assert fs.target_shares == 2_500 and fs.participation_capped is False


def test_refine_sizing_none_float_unchanged():
    fs = refine_sizing("heavy", free_float_shares=None, config=CFG, price=10.0)
    assert fs.tier == "heavy" and fs.target_shares is None      # no float -> tier untouched, no share-count


def test_sizing_config_rejects_non_monotone_float_thresholds():
    """Fail-fast: mid must not exceed large, else the [mid,large) 'core' band is empty and mid-float
    names silently miss capping (float review hardening). The only-tightens invariant is separately
    structural via float_capped_tier's SIZE_TIER_WEIGHT min-guard."""
    import pytest

    from alpha.sizing.position import SizingConfig

    # correct ordering constructs fine (incl. the default)
    SizingConfig()
    SizingConfig(float_mid_shares=10_000_000.0, float_large_shares=50_000_000.0)
    SizingConfig(float_mid_shares=1.0, float_large_shares=1.0)  # equal is allowed
    # swapped thresholds fail-fast
    with pytest.raises(ValueError, match="float_mid_shares"):
        SizingConfig(float_mid_shares=50_000_000.0, float_large_shares=10_000_000.0)
