from youzi.harness.regime import classify_regime, split_regimes, CANONICAL_PHASES, parse_regime_field


def test_classify_phase_variants():
    assert classify_regime("情绪冰点") == ("phase", "混沌冰点")
    assert classify_regime("修复启动") == ("phase", "修复启动")
    assert classify_regime("启动") == ("phase", "题材启动")
    assert classify_regime("主升期") == ("phase", "主升")
    assert classify_regime("震荡补涨") == ("phase", "震荡补涨")
    assert classify_regime("退潮期") == ("phase", "退潮")


def test_classify_ecology_and_other():
    assert classify_regime("连板生态") == ("ecology", "连板生态")
    assert classify_regime("20cm生态") == ("ecology", "20cm生态")
    assert classify_regime("情绪极值1500-") == ("other", None)
    assert classify_regime("") == ("other", None)


def test_split_regimes_dedup_and_order():
    phases, ecologies = split_regimes(
        ["启动", "修复", "连板生态", "情绪极值1500-", "启动"])
    assert phases == ["题材启动", "修复启动"]   # 首见序, 去重
    assert ecologies == ["连板生态"]


def test_canonical_phases_are_seven():
    assert len(CANONICAL_PHASES) == 7
    assert CANONICAL_PHASES[0] == "混沌冰点" and CANONICAL_PHASES[-1] == "退潮"


def test_parse_regime_field_multi_and_all():
    assert parse_regime_field("主升/退潮") == (["主升", "退潮"], [], False)
    assert parse_regime_field("修复/回暖/启动") == (["修复启动", "情绪回暖", "题材启动"], [], False)
    assert parse_regime_field("次新生态/超跌生态") == ([], ["次新生态", "超跌生态"], False)
    assert parse_regime_field("all") == ([], [], True)
    assert parse_regime_field("退潮期") == (["退潮"], [], False)
    assert parse_regime_field("") == ([], [], False)


def test_parse_regime_field_drops_unrecognized_token():
    # '高潮' 非 canonical 相位 -> 从 phases 丢弃, 不报错(仅留在调用方 regime_raw)
    assert parse_regime_field("主升/高潮") == (["主升"], [], False)
