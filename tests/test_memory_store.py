# tests/test_memory_store.py  (整体替换)
from youzi.harness.memory_item import Lesson
from youzi.harness.memory_store import MemoryStore


def _lessons():
    return [
        Lesson.from_seed({"lesson_id": "l1", "regime": "退潮", "pattern": "接力",
                          "outcome": "principle", "lesson": "退潮不接力"}),
        Lesson.from_seed({"lesson_id": "l2", "regime": "主升/退潮", "pattern": "高位",
                          "outcome": "loss", "named_analog": "神马电力2024/6/28",
                          "lesson": "由强转弱即退潮拐点"}),
        Lesson.from_seed({"lesson_id": "l3", "regime": "all", "pattern": "纪律",
                          "outcome": "principle", "lesson": "计划交易不上头"}),
        Lesson.from_seed({"lesson_id": "l4", "regime": "次新生态", "pattern": "次新",
                          "outcome": "loss", "lesson": "次新周期"}),
    ]


def test_for_regime_membership_and_all():
    store = MemoryStore.from_lessons(_lessons())
    # 退潮: l1(退潮) + l2(主升/退潮 命中退潮) + l3(all)
    assert {l.lesson_id for l in store.for_regime("退潮")} == {"l1", "l2", "l3"}
    # 主升: l2(命中主升) + l3(all)
    assert {l.lesson_id for l in store.for_regime("主升")} == {"l2", "l3"}


def test_for_ecology_and_other_queries():
    store = MemoryStore.from_lessons(_lessons())
    assert {l.lesson_id for l in store.for_ecology("次新生态")} == {"l4"}
    assert {l.lesson_id for l in store.by_outcome("principle")} == {"l1", "l3"}
    assert {l.lesson_id for l in store.by_pattern("纪律")} == {"l3"}
    assert store.get("l2").named_analog == "神马电力2024/6/28"
    assert len(store) == 4


def test_store_rejects_duplicate_ids():
    import pytest
    with pytest.raises(ValueError):
        MemoryStore.from_lessons([_lessons()[0], _lessons()[0]])


def test_memory_store_crud():
    import pytest
    store = MemoryStore.from_lessons(_lessons())
    store.add(Lesson.from_seed({"lesson_id": "l9", "regime": "主升",
                                "outcome": "win", "lesson": "新教训"}))
    assert store.get("l9") is not None
    with pytest.raises(ValueError):
        store.add(_lessons()[0])                 # 重复 id
    store.update("l1", lesson="改写后的教训")
    assert store.get("l1").lesson == "改写后的教训"
    store.demote("l1", 0.5)
    assert abs(store.get("l1").importance.time_decay - 0.5) < 1e-9
    with pytest.raises(KeyError):
        store.update("没有", lesson="x")


def test_update_atomic_on_failure():
    import pytest
    from pydantic import ValidationError
    store = MemoryStore.from_lessons(_lessons())
    before = store.get("l1").lesson
    with pytest.raises(ValidationError):
        store.update("l1", lesson="改了", outcome="非法值")  # outcome 是 Literal, 失败
    assert store.get("l1").lesson == before
