# tests/test_manager.py
from youzi.harness.skill import Skill
from youzi.harness.registry import SkillRegistry
from youzi.harness.memory_store import MemoryStore
from youzi.harness.doctrine import Doctrine
from youzi.harness.cycle import StateMachine
from youzi.harness.harness import HarnessState
from youzi.harness.snapshot import SnapshotStore
from youzi.harness.manager import HarnessManager


def _h():
    skills = SkillRegistry.from_skills([
        Skill.from_seed({"skill_id": "a", "name_cn": "甲", "type": "pattern",
                         "applicable_regime": ["主升"], "trigger": "t", "entry": "e",
                         "exit_stop": "x", "status": "active"})])
    return HarnessState(doctrine=Doctrine(), skills=skills,
                        memory=MemoryStore.from_lessons([]), cycle=StateMachine())


def test_checkpoint_then_edit_then_rollback(tmp_path):
    mgr = HarnessManager(_h(), SnapshotStore(tmp_path))
    v0 = mgr.checkpoint(label="干净")
    assert v0 == 0 and mgr.latest_version() == 0

    # 编辑:退役 a + 新增 b
    mgr.tools.retire_skill("a")
    mgr.tools.write_skill(Skill.from_seed({"skill_id": "b", "name_cn": "乙", "type": "pattern",
                                           "applicable_regime": ["退潮"], "trigger": "t",
                                           "entry": "e", "exit_stop": "x", "status": "incubating"}))
    assert mgr.harness.skills.get("a").status == "dormant"
    assert mgr.harness.skills.get("b") is not None
    assert len(mgr.log) == 2

    # 回滚到 v0:编辑全部撤销
    mgr.rollback_to(0)
    assert mgr.harness.skills.get("a").status == "active"   # 退役被撤销
    assert mgr.harness.skills.get("b") is None              # 新增被撤销
    assert len(mgr.log) == 0                                # 日志回到 v0(空)
    # tools 已重绑到还原后的 H:继续编辑作用在还原态上
    mgr.tools.retire_skill("a")
    assert mgr.harness.skills.get("a").status == "dormant"


def test_manager_shares_passed_empty_log(tmp_path):
    from youzi.harness.edit_log import EditLog
    shared = EditLog()
    mgr = HarnessManager(_h(), SnapshotStore(tmp_path), log=shared)
    assert mgr.log is shared                 # 共享同一对象, 不被空 log 的 falsy 旁路替换
    mgr.tools.retire_skill("a")
    assert len(shared) == 1                   # 编辑记到了调用方传入的 log


def test_rollback_missing_version_raises(tmp_path):
    import pytest
    mgr = HarnessManager(_h(), SnapshotStore(tmp_path))
    with pytest.raises(FileNotFoundError):
        mgr.rollback_to(0)
