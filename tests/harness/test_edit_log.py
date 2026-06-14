from alpha.harness.edit_log import EditLog, EditRecord


def test_append_assigns_sequential_seq():
    log = EditLog()
    r0 = log.append("write_skill", "skill", "a", "create", "A", rationale="seed")
    r1 = log.append("rewrite_doctrine", "doctrine", "trend", "rewrite",
                    payload={"old": "x", "new": "y"}, rationale="regime shift")
    assert (r0.seq, r1.seq) == (0, 1)
    assert len(log) == 2 and bool(log) is True


def test_queries():
    log = EditLog()
    log.append("write_skill", "skill", "a", "create", rationale="r")
    log.append("rewrite_doctrine", "doctrine", "t", "rewrite", rationale="r")
    assert [r.target_id for r in log.by_kind("skill")] == ["a"]
    assert [r.target_id for r in log.by_tool("rewrite_doctrine")] == ["t"]


def test_record_is_frozen():
    import pytest
    from pydantic import ValidationError
    rec = EditRecord(seq=0, tool="t", target_kind="skill", target_id="a", op="create")
    with pytest.raises(ValidationError):
        rec.seq = 5


def test_roundtrip():
    log = EditLog()
    log.append("write_skill", "skill", "a", "create", "A",
               payload={"before": None, "after": {"x": 1}}, rationale="seed")
    data = log.to_dict()
    log2 = EditLog.from_dict(data)
    assert len(log2) == 1
    assert log2.records()[0].rationale == "seed"
    assert log2.records()[0].payload == {"before": None, "after": {"x": 1}}
