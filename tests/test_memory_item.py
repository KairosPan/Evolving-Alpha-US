from youzi.harness.memory_item import Lesson, Importance


def test_importance_weight_and_demote():
    imp = Importance(base=0.8, time_decay=1.0, regime_decay=1.0)
    assert abs(imp.weight() - 0.8) < 1e-9
    imp.demote(0.5)                       # 同时打到 time_decay
    assert abs(imp.time_decay - 0.5) < 1e-9
    assert abs(imp.weight() - 0.4) < 1e-9


def test_lesson_from_seed_parses_multi_regime():
    s = Lesson.from_seed({
        "lesson_id": "glory_peak", "regime": "主升/退潮", "outcome": "principle",
        "lesson": "盛极转衰非龙头早退龙头迟退", "source_lines": [344],
    })
    assert s.regime_raw == "主升/退潮"
    assert s.phases == ["主升", "退潮"]          # 两相位都可查(修复 P0 漏检)
    assert s.applies_all is False


def test_lesson_from_seed_all_and_ecology():
    a = Lesson.from_seed({"lesson_id": "disc", "regime": "all", "outcome": "principle",
                          "lesson": "计划交易不上头"})
    assert a.applies_all is True and a.phases == []
    e = Lesson.from_seed({"lesson_id": "cixin", "regime": "次新生态/超跌生态",
                          "outcome": "loss", "lesson": "次新与超跌互为生死"})
    assert e.ecologies == ["次新生态", "超跌生态"] and e.phases == []


def test_lesson_loss_with_analog():
    s = Lesson.from_seed({
        "lesson_id": "shenma_ebb", "regime": "退潮", "outcome": "loss",
        "failure_signature": "最高连板率先走弱断板大阴", "named_analog": "神马电力2024/6/28",
        "lesson": "由强转弱即退潮拐点, 回避高位", "source_lines": [437, 438],
    })
    assert s.named_analog == "神马电力2024/6/28" and s.phases == ["退潮"]


def test_importance_demote_rejects_bad_factor():
    import pytest
    imp = Importance()
    with pytest.raises(ValueError):
        imp.demote(0.0)
    with pytest.raises(ValueError):
        imp.demote(1.5)
