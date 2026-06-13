from youzi.harness.skill import Skill, SkillStats


def test_skill_stats_ewma_winrate():
    st = SkillStats()
    assert st.n == 0 and st.ewma_winrate is None
    st.record(win=True, decay=0.5)
    assert st.n == 1 and st.ewma_winrate == 1.0     # 首样本直接置入
    st.record(win=False, decay=0.5)
    # ewma = 0.5*0 + 0.5*1.0 = 0.5
    assert st.n == 2 and abs(st.ewma_winrate - 0.5) < 1e-9


def test_skill_from_seed_normalizes_regime():
    seed = {
        "skill_id": "relay_2to3_w2s", "name_cn": "二进三弱转强", "type": "pattern",
        "applicable_regime": ["主升", "启动", "连板生态", "情绪极值1500-"],
        "trigger": "二板放量封死", "entry": "竞价弱转强扫", "exit_stop": "承接无力放弃",
        "taboo": ["板块死口不做"], "status": "active", "source_lines": [893, 894],
    }
    s = Skill.from_seed(seed)
    assert s.skill_id == "relay_2to3_w2s"
    assert s.phases == ["主升", "题材启动"]       # 归一 + 去重, 顺序保留
    assert s.ecologies == ["连板生态"]
    assert s.applicable_regime == ["主升", "启动", "连板生态", "情绪极值1500-"]  # 原始保留
    assert s.stats.n == 0


def test_skill_defaults_for_optional_fields():
    s = Skill.from_seed({
        "skill_id": "x", "name_cn": "x", "type": "feature",
        "applicable_regime": [], "trigger": "t", "entry": "e", "exit_stop": "x",
        "status": "incubating",
    })
    assert s.taboo == [] and s.depends_on == [] and s.examples == []
    assert s.notes == "" and s.phases == [] and s.ecologies == []


def test_skill_from_seed_forbids_unknown_keys():
    import pytest
    from pydantic import ValidationError
    with pytest.raises(ValidationError):
        Skill.from_seed({"skill_id": "x", "name_cn": "x", "type": "pattern",
                         "applicable_regime": [], "trigger": "t", "entry": "e",
                         "exit_stop": "x", "status": "active", "taboos": ["typo"]})


def test_skill_stats_record_rejects_bad_decay():
    import pytest
    st = SkillStats()
    with pytest.raises(ValueError):
        st.record(win=True, decay=1.5)
    with pytest.raises(ValueError):
        st.record(win=True, decay=0.0)


def test_skill_from_seed_applies_all():
    s = Skill.from_seed({"skill_id": "u", "name_cn": "通用", "type": "pattern",
                         "applicable_regime": ["all"], "trigger": "t", "entry": "e",
                         "exit_stop": "x", "status": "active"})
    assert s.applies_all is True
    assert s.phases == [] and s.ecologies == []      # "all" 不进 phases
    s2 = Skill.from_seed({"skill_id": "v", "name_cn": "甲", "type": "pattern",
                          "applicable_regime": ["主升"], "trigger": "t", "entry": "e",
                          "exit_stop": "x", "status": "active"})
    assert s2.applies_all is False and s2.phases == ["主升"]
