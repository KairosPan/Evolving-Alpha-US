from alpha.sizing.position import size_tier, SIZE_TIER_WEIGHT, SizingConfig


def test_size_tier_scales_with_confidence_and_risk_gate():
    assert size_tier(0.9, 0.9) == "heavy"        # score 0.81
    assert size_tier(0.8, 0.7) == "core"         # score 0.56
    assert size_tier(0.6, 0.4) == "probe"        # score 0.24
    assert size_tier(0.3, 0.3) == "flat"         # score 0.09


def test_risk_off_shrinks_to_flat():
    # high conviction but deep risk-off regime -> flat (regime gates size)
    assert size_tier(0.95, 0.05) == "flat"       # score 0.0475


def test_tier_weights_monotonic():
    w = SIZE_TIER_WEIGHT
    assert w["flat"] == 0.0 < w["probe"] < w["core"] < w["heavy"] == 1.0


def test_config_defaults():
    cfg = SizingConfig()
    assert cfg.max_name_weight > 0 and cfg.max_total_exposure > 0
