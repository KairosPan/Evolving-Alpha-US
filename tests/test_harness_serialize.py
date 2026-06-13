from youzi.harness.skill import Skill
from youzi.harness.registry import SkillRegistry
from youzi.harness.memory_item import Lesson
from youzi.harness.memory_store import MemoryStore
from youzi.harness.doctrine import Doctrine, DoctrineEntry
from youzi.harness.cycle import StateMachine
from youzi.harness.harness import HarnessState
from youzi.harness.errors import ImmutableDoctrineError


def _harness():
    a = Skill.from_seed({"skill_id": "a", "name_cn": "甲", "type": "pattern",
                         "applicable_regime": ["主升"], "trigger": "t", "entry": "e",
                         "exit_stop": "x", "status": "active"})
    a.stats.record(win=True, decay=0.3)          # 让 stats 非默认
    a.status = "dormant"
    skills = SkillRegistry.from_skills([a])
    mem = MemoryStore.from_lessons([
        Lesson.from_seed({"lesson_id": "l1", "regime": "主升/退潮", "outcome": "loss",
                          "lesson": "教训"})])
    mem.demote("l1", 0.5)
    doc = Doctrine(entries=[
        DoctrineEntry.from_seed({"section": "主升作战", "regime": "主升",
                                 "immutable": False, "guidance": "持有龙头"}),
        DoctrineEntry.from_seed({"section": "纪律:退潮不接力", "regime": "all",
                                 "immutable": True, "guidance": "退潮禁接力"})])
    cyc = StateMachine.from_seed_list([{"phase": "主升", "you_see": ["龙头突破"],
                                        "transitions": [{"to": "震荡补涨", "signal": "强分歧阴K"}]}])
    return HarnessState(doctrine=doc, skills=skills, memory=mem, cycle=cyc)


def test_harness_roundtrip_preserves_state():
    h = _harness()
    h2 = HarnessState.from_dict(h.to_dict())
    # 技能:status / stats 保真
    s = h2.skills.get("a")
    assert s.status == "dormant"
    assert s.stats.n == 1 and s.stats.ewma_winrate == 1.0
    assert s.phases == ["主升"]
    # 记忆:多 regime + importance 保真
    l = h2.memory.get("l1")
    assert l.phases == ["主升", "退潮"]
    assert abs(l.importance.time_decay - 0.5) < 1e-9
    # doctrine / cycle 数量保真
    assert len(h2.doctrine.entries) == 2
    assert h2.cycle.get("主升").you_see == ["龙头突破"]
    assert h.to_dict() == h2.to_dict()           # 全字段往返幂等


def test_roundtrip_preserves_immutable_protection():
    h2 = HarnessState.from_dict(_harness().to_dict())
    imm = h2.doctrine.immutable_core()[0]
    assert imm.immutable is True
    import pytest
    with pytest.raises(ImmutableDoctrineError):
        imm.guidance = "篡改"           # 还原后守卫仍生效
    # 可变条目仍可改
    mut = h2.doctrine.mutable_entries()[0]
    mut.guidance = "改了"
    assert mut.guidance == "改了"
