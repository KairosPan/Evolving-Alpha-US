# tests/test_phase0b3_integration.py
from pathlib import Path
import pytest
from youzi.harness.loader import load_seeds
from youzi.harness.snapshot import SnapshotStore
from youzi.harness.manager import HarnessManager
from youzi.harness.skill import Skill
from youzi.harness.errors import ImmutableDoctrineError

SEEDS = Path(__file__).resolve().parent.parent / "seeds"


def test_full_persist_edit_rollback_cycle(tmp_path):
    mgr = HarnessManager(load_seeds(SEEDS), SnapshotStore(tmp_path))
    n0 = len(mgr.harness.skills)
    log0 = len(mgr.log)

    v0 = mgr.checkpoint(label="种子初始")

    # 一串编辑
    active = mgr.harness.skills.by_status("active")[0]
    mgr.tools.retire_skill(active.skill_id)
    mgr.tools.write_skill(Skill.from_seed({"skill_id": "p0b3_new", "name_cn": "新生", "type": "pattern",
                                           "applicable_regime": ["退潮"], "trigger": "t",
                                           "entry": "e", "exit_stop": "x", "status": "incubating"}))
    mutable = mgr.harness.doctrine.mutable_entries()[0]
    original_guidance = mutable.guidance                  # 保存改写前的原文
    original_section = mutable.section
    mgr.tools.rewrite_doctrine(mutable.section, "新作战指导")
    assert len(mgr.harness.skills) == n0 + 1
    assert len(mgr.log) == log0 + 3

    v1 = mgr.checkpoint(label="编辑后")
    assert sorted(mgr.store.list_versions()) == [v0, v1]

    # 回滚到 v0:全部编辑撤销
    mgr.rollback_to(v0)
    assert len(mgr.harness.skills) == n0
    assert mgr.harness.skills.get("p0b3_new") is None
    assert mgr.harness.skills.get(active.skill_id).status == "active"
    assert mgr.harness.doctrine.get(original_section).guidance == original_guidance  # 改写被撤销
    assert len(mgr.log) == log0

    # 还原后 immutable 守卫仍生效
    core = mgr.harness.doctrine.immutable_core()
    assert len(core) >= 10
    with pytest.raises(ImmutableDoctrineError):
        mgr.tools.rewrite_doctrine(core[0].section, "试图篡改")


def test_rollback_to_edited_version_keeps_edits(tmp_path):
    mgr = HarnessManager(load_seeds(SEEDS), SnapshotStore(tmp_path))
    mgr.checkpoint()                                  # v0 干净
    sid = mgr.harness.skills.by_status("active")[0].skill_id
    mgr.tools.retire_skill(sid)
    v1 = mgr.checkpoint()                              # v1 含退役
    mgr.rollback_to(0)
    assert mgr.harness.skills.get(sid).status == "active"
    mgr.rollback_to(v1)                               # 回到编辑后版本
    assert mgr.harness.skills.get(sid).status == "dormant"
