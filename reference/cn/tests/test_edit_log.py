from youzi.harness.edit_log import EditLog, EditRecord


def test_edit_log_appends_with_monotonic_seq():
    log = EditLog()
    r0 = log.append("write_skill", "skill", "a", "create", "甲")
    r1 = log.append("rewrite_doctrine", "doctrine", "退潮作战", "rewrite")
    assert isinstance(r0, EditRecord)
    assert r0.seq == 0 and r1.seq == 1
    assert len(log) == 2


def test_edit_log_queries():
    log = EditLog()
    log.append("write_skill", "skill", "a", "create")
    log.append("retire_skill", "skill", "a", "dormant")
    log.append("process_memory", "memory", "l1", "create")
    assert [r.target_id for r in log.by_kind("skill")] == ["a", "a"]
    assert [r.seq for r in log.by_tool("write_skill")] == [0]
    assert len(log.records()) == 3


def test_edit_log_roundtrip_preserves_seq_and_continues():
    log = EditLog()
    log.append("write_skill", "skill", "a", "create", "甲")
    log.append("retire_skill", "skill", "a", "retire", "dormant", payload={"before": "active"})
    data = log.to_dict()
    assert isinstance(data, list) and len(data) == 2

    restored = EditLog.from_dict(data)
    assert len(restored) == 2
    assert [r.seq for r in restored.records()] == [0, 1]
    assert restored.records()[1].payload == {"before": "active"}
    # 续号:还原后再 append 接着 seq=2
    r2 = restored.append("promote_skill", "skill", "a", "promote")
    assert r2.seq == 2


def test_empty_editlog_is_truthy():
    assert bool(EditLog()) is True and len(EditLog()) == 0
