from youzi.harness.skill import Skill, SkillStats
from youzi.harness.registry import SkillRegistry
from youzi.harness.memory_store import MemoryStore
from youzi.harness.doctrine import Doctrine
from youzi.harness.cycle import StateMachine
from youzi.harness.harness import HarnessState
from youzi.harness.edit_log import EditLog
from youzi.harness.metatools import MetaTools
from youzi.harness.snapshot import SnapshotStore


def _h():
    skills = SkillRegistry.from_skills([
        Skill.from_seed({"skill_id": "a", "name_cn": "甲", "type": "pattern",
                         "applicable_regime": ["主升"], "trigger": "t", "entry": "e",
                         "exit_stop": "x", "status": "active"})])
    return HarnessState(doctrine=Doctrine(), skills=skills,
                        memory=MemoryStore.from_lessons([]),
                        cycle=StateMachine())


def test_snapshot_save_list_load(tmp_path):
    store = SnapshotStore(tmp_path)
    assert store.list_versions() == [] and store.latest() is None
    log = EditLog()
    log.append("write_skill", "skill", "a", "create")
    v0 = store.save(_h(), log, label="初始")
    v1 = store.save(_h(), EditLog(), label="次版")
    assert v0 == 0 and v1 == 1
    assert store.list_versions() == [0, 1] and store.latest() == 1

    h, lg = store.load(0)
    assert h.skills.get("a").name_cn == "甲"
    assert len(lg) == 1 and lg.records()[0].tool == "write_skill"


def test_snapshot_load_missing_raises(tmp_path):
    import pytest
    with pytest.raises(FileNotFoundError):
        SnapshotStore(tmp_path).load(99)


def test_snapshot_load_corrupt_raises(tmp_path):
    import pytest
    (tmp_path / "snap_0000.json").write_text("{ not valid json", encoding="utf-8")
    with pytest.raises(RuntimeError):
        SnapshotStore(tmp_path).load(0)


def test_snapshot_with_nested_model_payload_is_jsonable(tmp_path):
    # EditLog payload 含嵌套 pydantic 模型(经 MetaTools._jsonable 转 dict)-> snapshot
    # json.dumps 不应崩溃,且能再 load 回来。
    # (注:stats/importance 现为写保护观测字段,不能经 patch/update 进 payload;
    #  此处直接经 _jsonable + EditLog.append 复现"嵌套模型进 payload"的序列化路径。)
    from youzi.harness.metatools import _jsonable
    h = _h()
    mt = MetaTools(h)
    snap = _jsonable(SkillStats())                   # 嵌套模型 -> dict
    assert isinstance(snap, dict)
    mt.log.append("patch_skill", "skill", "a", "update",
                  payload={"before": {"stats": snap}, "after": {"stats": snap}})
    store = SnapshotStore(tmp_path)
    v0 = store.save(h, mt.log)                        # json.dumps 不崩
    h2, lg = store.load(v0)
    assert h2.skills.get("a") is not None
    rec = lg.records()[-1]
    assert isinstance(rec.payload["before"]["stats"], dict)
    assert isinstance(rec.payload["after"]["stats"], dict)
