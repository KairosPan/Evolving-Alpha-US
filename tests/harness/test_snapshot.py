import json
import pytest
from alpha.harness.skill import Skill
from alpha.harness.memory import Lesson
from alpha.harness.doctrine import Doctrine
from alpha.harness.registry import SkillRegistry, MemoryStore
from alpha.harness.state import HarnessState
from alpha.harness.edit_log import EditLog
from alpha.harness.errors import ImmutableDoctrineError
from alpha.harness.snapshot import SnapshotStore


def _state():
    skills = SkillRegistry.from_skills([
        Skill(skill_id="a", name="A", type="pattern", family="runner", phases=["trend"], status="active"),
    ])
    memory = MemoryStore.from_lessons([Lesson(lesson_id="l1", phases=["flush"], outcome="loss", lesson="x")])
    doctrine = Doctrine.from_seed_list([
        {"section": "core", "regime": "all", "immutable": True, "guidance": "stop discipline"},
    ])
    return HarnessState(doctrine=doctrine, skills=skills, memory=memory)


def _log():
    log = EditLog()
    log.append("write_skill", "skill", "a", "create", "A",
               payload={"before": None, "after": {"x": 1}}, rationale="seed")
    return log


def test_empty_store(tmp_path):
    store = SnapshotStore(tmp_path)
    assert store.list_versions() == []
    assert store.latest() is None
    with pytest.raises(FileNotFoundError):
        store.load(0)


def test_save_increments_version(tmp_path):
    store = SnapshotStore(tmp_path)
    assert store.save(_state(), _log(), label="v0") == 0
    assert store.save(_state(), _log(), label="v1") == 1
    assert store.list_versions() == [0, 1]
    assert store.latest() == 1


def test_roundtrip_lossless_and_immutable_survives(tmp_path):
    store = SnapshotStore(tmp_path)
    v = store.save(_state(), _log(), label="cp")
    h2, log2 = store.load(v)
    assert h2.skills.get("a").status == "active"
    assert h2.memory.get("l1").lesson == "x"
    assert len(log2) == 1 and log2.records()[0].rationale == "seed"
    with pytest.raises(ImmutableDoctrineError):           # guard restored after load
        h2.doctrine.get("core").guidance = "tampered"


def test_atomic_write_leaves_no_temp(tmp_path):
    store = SnapshotStore(tmp_path)
    store.save(_state(), _log())
    files = sorted(p.name for p in tmp_path.iterdir())
    assert files == ["snap_0000.json"]
    assert store.list_versions() == [0]


def test_corrupt_snapshot_fails_loudly(tmp_path):
    store = SnapshotStore(tmp_path)
    store.save(_state(), _log())
    (tmp_path / "snap_0000.json").write_text("{ not valid json", encoding="utf-8")
    with pytest.raises(RuntimeError):
        store.load(0)
    (tmp_path / "snap_0000.json").write_text(json.dumps({"version": 0}), encoding="utf-8")
    with pytest.raises(RuntimeError):
        store.load(0)
