import pytest

from youzi.harness.skill import Skill
from youzi.harness.registry import SkillRegistry
from youzi.harness.memory_item import Lesson
from youzi.harness.memory_store import MemoryStore
from youzi.harness.doctrine import Doctrine, DoctrineEntry
from youzi.harness.cycle import StateMachine
from youzi.harness.harness import HarnessState
from youzi.harness.metatools import MetaTools
from youzi.harness.errors import ImmutableDoctrineError


def _harness():
    skills = SkillRegistry.from_skills([
        Skill.from_seed({"skill_id": "a", "name_cn": "甲", "type": "pattern",
                         "applicable_regime": ["主升"], "trigger": "t", "entry": "e",
                         "exit_stop": "x", "status": "active"})])
    mem = MemoryStore.from_lessons([
        Lesson.from_seed({"lesson_id": "l1", "regime": "退潮", "outcome": "loss",
                          "lesson": "教训"})])
    doc = Doctrine(entries=[
        DoctrineEntry.from_seed({"section": "主升作战", "regime": "主升",
                                 "immutable": False, "guidance": "持有龙头"}),
        DoctrineEntry.from_seed({"section": "纪律:退潮不接力", "regime": "all",
                                 "immutable": True, "guidance": "退潮禁接力"})])
    cyc = StateMachine.from_seed_list([{"phase": "主升", "you_see": [], "transitions": []}])
    return HarnessState(doctrine=doc, skills=skills, memory=mem, cycle=cyc)


def test_metatools_edits_and_logs():
    mt = MetaTools(_harness())
    mt.write_skill(Skill.from_seed({"skill_id": "b", "name_cn": "乙", "type": "pattern",
                                    "applicable_regime": ["退潮"], "trigger": "t",
                                    "entry": "e", "exit_stop": "x", "status": "incubating"}))
    mt.retire_skill("a")                          # active -> dormant
    mt.revive_skill("a")                          # dormant -> incubating
    mt.promote_skill("a")                         # incubating -> active
    mt.patch_skill("a", notes="备注")
    mt.process_memory(Lesson.from_seed({"lesson_id": "l2", "regime": "主升",
                                        "outcome": "win", "lesson": "新"}))
    mt.update_memory("l1", lesson="改写教训")
    mt.demote_memory("l1", 0.5)
    mt.rewrite_doctrine("主升作战", "新指导")
    h = mt.h
    assert h.skills.get("a").status == "active" and h.skills.get("a").notes == "备注"
    assert h.skills.get("b") is not None
    assert h.memory.get("l2") is not None
    assert h.memory.get("l1").lesson == "改写教训"
    assert abs(h.memory.get("l1").importance.time_decay - 0.5) < 1e-9
    assert h.doctrine.get("主升作战").guidance == "新指导"
    # 审计:9 条编辑,且每条都有 seq/tool/target
    assert len(mt.log) == 9
    assert [r.tool for r in mt.log.by_kind("skill")][0] == "write_skill"


def test_metatools_rewrite_immutable_rejected_and_not_logged():
    mt = MetaTools(_harness())
    with pytest.raises(ImmutableDoctrineError):
        mt.rewrite_doctrine("纪律:退潮不接力", "篡改")
    assert len(mt.log) == 0                       # 被拒的编辑不入审计


def test_metatools_payload_has_before_after():
    mt = MetaTools(_harness())
    mt.patch_skill("a", notes="新备注")
    rec = mt.log.records()[-1]
    assert rec.payload["before"] == {"notes": ""} and rec.payload["after"] == {"notes": "新备注"}

    mt.retire_skill("a")
    rec = mt.log.records()[-1]
    assert rec.payload == {"before": "active", "after": "dormant"}

    mt.demote_memory("l1", 0.5)
    rec = mt.log.records()[-1]
    assert rec.payload["factor"] == 0.5 and "before_time_decay" in rec.payload
