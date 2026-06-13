import pytest
from youzi.harness.skill import Skill
from youzi.harness.registry import SkillRegistry


def _skills():
    return [
        Skill.from_seed({"skill_id": "a", "name_cn": "甲", "type": "pattern",
                         "applicable_regime": ["主升", "连板生态"], "trigger": "t",
                         "entry": "e", "exit_stop": "x", "status": "active"}),
        Skill.from_seed({"skill_id": "b", "name_cn": "乙", "type": "failure_detector",
                         "applicable_regime": ["退潮"], "trigger": "t",
                         "entry": "规避", "exit_stop": "N/A", "status": "active"}),
        Skill.from_seed({"skill_id": "c", "name_cn": "丙", "type": "pattern",
                         "applicable_regime": ["主升"], "trigger": "t",
                         "entry": "e", "exit_stop": "x", "status": "dormant"}),
    ]


def test_registry_rejects_duplicate_ids():
    s = _skills()
    with pytest.raises(ValueError):
        SkillRegistry.from_skills([s[0], s[0]])


def test_registry_queries():
    reg = SkillRegistry.from_skills(_skills())
    assert reg.get("b").name_cn == "乙"
    assert reg.get("zzz") is None
    assert {s.skill_id for s in reg.by_status("active")} == {"a", "b"}
    assert {s.skill_id for s in reg.by_phase("主升")} == {"a", "c"}
    assert {s.skill_id for s in reg.by_type("pattern")} == {"a", "c"}
    assert {s.skill_id for s in reg.by_ecology("连板生态")} == {"a"}
    assert len(reg) == 3


# --- Task 6 CRUD + 生命周期 ---
from youzi.harness.errors import InvalidTransitionError


def _one():
    return Skill.from_seed({"skill_id": "a", "name_cn": "甲", "type": "pattern",
                            "applicable_regime": ["主升"], "trigger": "t",
                            "entry": "e", "exit_stop": "x", "status": "active"})


def test_registry_write_and_reject_dup():
    import pytest
    reg = SkillRegistry.from_skills([_one()])
    new = Skill.from_seed({"skill_id": "z", "name_cn": "新", "type": "pattern",
                           "applicable_regime": ["退潮"], "trigger": "t",
                           "entry": "e", "exit_stop": "x", "status": "incubating"})
    reg.write(new)
    assert reg.get("z").name_cn == "新"
    with pytest.raises(ValueError):
        reg.write(_one())            # 重复 id


def test_registry_patch_validates():
    import pytest
    from pydantic import ValidationError
    reg = SkillRegistry.from_skills([_one()])
    reg.patch("a", notes="改了备注")
    assert reg.get("a").notes == "改了备注"
    with pytest.raises(ValidationError):
        reg.patch("a", entry=123)             # entry 是 str 字段, 类型错 -> 校验失败
    with pytest.raises(KeyError):
        reg.patch("没有", notes="x")


def test_patch_rejects_status_and_recomputes_derived():
    import pytest
    reg = SkillRegistry.from_skills([_one()])
    with pytest.raises(ValueError):
        reg.patch("a", status="active")        # 用 lifecycle
    with pytest.raises(ValueError):
        reg.patch("a", phases=["退潮"])         # 派生字段
    reg.patch("a", applicable_regime=["退潮"])   # 改原始 -> 重算
    assert reg.get("a").phases == ["退潮"]


def test_retire_retired_rejects_non_permanent():
    import pytest
    reg = SkillRegistry.from_skills([_one()])
    reg.retire("a", permanent=True)
    with pytest.raises(InvalidTransitionError):
        reg.retire("a")                        # 不能把永久退役降回 dormant


def test_patch_atomic_on_failure():
    import pytest
    from pydantic import ValidationError
    reg = SkillRegistry.from_skills([_one()])
    before = reg.get("a").notes
    with pytest.raises(ValidationError):
        reg.patch("a", notes="改了", entry=123)   # notes 先成功, entry(str) 收到 int 失败
    assert reg.get("a").notes == before            # 已回滚, 未半改


def test_registry_lifecycle_retire_revive_promote():
    import pytest
    reg = SkillRegistry.from_skills([_one()])
    reg.retire("a")                       # active -> dormant(默认)
    assert reg.get("a").status == "dormant"
    reg.revive("a")                       # dormant -> incubating
    assert reg.get("a").status == "incubating"
    reg.promote("a")                      # incubating -> active
    assert reg.get("a").status == "active"
    reg.retire("a", permanent=True)       # -> retired(永久)
    assert reg.get("a").status == "retired"
    with pytest.raises(InvalidTransitionError):
        reg.revive("a")                   # retired 不能 revive(非 dormant)


def test_by_phase_honors_applies_all():
    universal = Skill.from_seed({"skill_id": "risk", "name_cn": "风控通则", "type": "failure_detector",
                                 "applicable_regime": ["all"], "trigger": "t", "entry": "规避",
                                 "exit_stop": "N/A", "status": "active"})
    reg = SkillRegistry.from_skills([_one(), universal])
    # universal 对任意相位都命中;_one() 只在 主升
    assert {s.skill_id for s in reg.by_phase("退潮")} == {"risk"}
    assert {s.skill_id for s in reg.by_phase("主升")} == {"a", "risk"}


def test_patch_applicable_regime_recomputes_applies_all():
    import pytest
    reg = SkillRegistry.from_skills([_one()])      # _one(): 主升, applies_all False
    reg.patch("a", applicable_regime=["all"])
    assert reg.get("a").applies_all is True and reg.get("a").phases == []
    reg.patch("a", applicable_regime=["退潮"])
    assert reg.get("a").applies_all is False and reg.get("a").phases == ["退潮"]
    with pytest.raises(ValueError):
        reg.patch("a", applies_all=True)           # 派生字段不可直接 patch
