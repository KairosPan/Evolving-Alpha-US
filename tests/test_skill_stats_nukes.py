# tests/test_skill_stats_nukes.py
from youzi.harness.skill import Skill, SkillStats


def test_skillstats_nukes_defaults_zero():
    assert SkillStats().nukes == 0


def test_skillstats_roundtrip_includes_nukes():
    st = SkillStats(n=3, wins=1, losses=2, nukes=1, expectancy=-0.33)
    d = st.model_dump()
    assert d["nukes"] == 1
    assert SkillStats.model_validate(d).nukes == 1


def test_skillstats_loads_old_dict_without_nukes():
    # 旧快照(无 nukes 字段)前向兼容 → 默认 0
    old = {"n": 2, "wins": 1, "losses": 1, "ewma_winrate": 0.5}
    assert SkillStats.model_validate(old).nukes == 0


def test_skill_with_old_stats_dict_loads():
    sk = Skill.model_validate({
        "skill_id": "x", "name_cn": "x", "type": "pattern",
        "trigger": "t", "entry": "e", "exit_stop": "s",
        "stats": {"n": 1, "wins": 1, "losses": 0},   # 无 nukes
    })
    assert sk.stats.nukes == 0
