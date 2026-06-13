# tests/test_edit_log_rationale.py
from youzi.harness.edit_log import EditLog, EditRecord
from youzi.harness.metatools import MetaTools
from tests.test_metatools import _harness   # 复用既有 fixture
from youzi.harness.memory_item import Lesson


def test_append_carries_rationale():
    log = EditLog()
    rec = log.append("write_skill", "skill", "x", "create", "甲", rationale="因为亏")
    assert rec.rationale == "因为亏"


def test_rationale_defaults_empty():
    rec = EditLog().append("promote_skill", "skill", "x", "promote")
    assert rec.rationale == ""


def test_old_dict_without_rationale_loads():
    old = [{"seq": 0, "tool": "promote_skill", "target_kind": "skill",
            "target_id": "x", "op": "promote", "summary": "", "payload": None}]
    log = EditLog.from_dict(old)
    assert log.records()[0].rationale == ""


def test_roundtrip_byte_identical():
    log = EditLog()
    log.append("write_skill", "skill", "x", "create", "甲", rationale="r1")
    d1 = log.to_dict()
    d2 = EditLog.from_dict(d1).to_dict()
    assert d1 == d2


def test_metatool_forwards_rationale():
    mt = MetaTools(_harness())
    rec = mt.update_memory("l1", lesson="改", rationale="教训过时")
    assert rec.rationale == "教训过时"
    assert mt.log.records()[-1].rationale == "教训过时"
