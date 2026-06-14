import pytest
from alpha.harness.memory import Lesson
from alpha.harness.registry import MemoryStore


def _lesson(lid):
    return Lesson(lesson_id=lid, phases=["flush"], family="meme", outcome="loss", lesson="x")


def test_add_and_duplicate():
    store = MemoryStore.from_lessons([])
    store.add(_lesson("l1"))
    assert store.get("l1") is not None
    with pytest.raises(ValueError):
        store.add(_lesson("l1"))


def test_update_allowed_and_forbidden():
    store = MemoryStore.from_lessons([_lesson("l1")])
    store.update("l1", lesson="revised", pattern="squeeze top")
    assert store.get("l1").lesson == "revised" and store.get("l1").pattern == "squeeze top"
    with pytest.raises(ValueError):
        store.update("l1", importance={})
    # lesson_id is protected structurally (positional-param collision -> TypeError)
    with pytest.raises(TypeError):
        store.update("l1", **{"lesson_id": "l2"})


def test_update_missing_target():
    store = MemoryStore.from_lessons([])
    with pytest.raises(KeyError):
        store.update("nope", lesson="x")


def test_demote_lowers_weight():
    store = MemoryStore.from_lessons([_lesson("l1")])
    assert store.get("l1").importance.weight() == 1.0
    store.demote("l1", 0.5)
    assert store.get("l1").importance.weight() == 0.5
    with pytest.raises(KeyError):
        store.demote("nope", 0.5)
