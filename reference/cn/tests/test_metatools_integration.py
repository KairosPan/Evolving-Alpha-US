from pathlib import Path
import pytest
from youzi.harness.loader import load_seeds
from youzi.harness.metatools import MetaTools
from youzi.harness.skill import Skill
from youzi.harness.errors import ImmutableDoctrineError

SEEDS = Path(__file__).resolve().parent.parent / "seeds"


def test_metatool_edit_sequence_on_real_seeds():
    h = load_seeds(SEEDS)
    mt = MetaTools(h)
    n0 = len(h.skills)

    # 取一个真实 active 技能跑完整生命周期
    active = h.skills.by_status("active")[0]
    sid = active.skill_id
    mt.retire_skill(sid)
    assert h.skills.get(sid).status == "dormant"     # 退役不删(轮回保活)
    assert h.skills.get(sid) is not None
    mt.revive_skill(sid)
    assert h.skills.get(sid).status == "incubating"
    mt.promote_skill(sid)
    assert h.skills.get(sid).status == "active"

    # 新增一个孵化技能
    mt.write_skill(Skill.from_seed({"skill_id": "newborn_test", "name_cn": "新生测试",
                                    "type": "pattern", "applicable_regime": ["退潮"],
                                    "trigger": "t", "entry": "e", "exit_stop": "x",
                                    "status": "incubating"}))
    assert len(h.skills) == n0 + 1

    # 可变 doctrine 改写 OK
    mutable = h.doctrine.mutable_entries()[0]
    mt.rewrite_doctrine(mutable.section, "新的作战指导")
    assert h.doctrine.get(mutable.section).guidance == "新的作战指导"

    # 审计齐全(本序列 5 次成功编辑)
    assert len(mt.log) == 5


def test_immutable_core_is_write_protected_on_real_seeds():
    h = load_seeds(SEEDS)
    mt = MetaTools(h)
    core = h.doctrine.immutable_core()
    assert len(core) >= 10                       # v1 纪律红线
    before = core[0].guidance
    with pytest.raises(ImmutableDoctrineError):
        mt.rewrite_doctrine(core[0].section, "试图篡改纪律红线")
    assert h.doctrine.get(core[0].section).guidance == before   # 未被改动
    assert len(mt.log) == 0                       # 被拒不入审计


def test_for_regime_finds_multi_regime_lessons_on_real_seeds():
    # 验证 P0 修复:多 regime 记忆现在能被任一相位查到
    h = load_seeds(SEEDS)
    # 至少有一条记忆 phases 含 >1 相位(主升/退潮 之类)
    multi = [l for l in h.memory.all() if len(l.phases) > 1]
    assert multi, "应存在多相位记忆(P0 修复目标)"
    sample = multi[0]
    for phase in sample.phases:
        ids = {l.lesson_id for l in h.memory.for_regime(phase)}
        assert sample.lesson_id in ids            # 每个所属相位都能查到它
