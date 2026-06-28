# tests/converse/test_gated_write_conflict.py
from alpha.harness.doctrine import Doctrine
from alpha.harness.registry import SkillRegistry, MemoryStore
from alpha.harness.state import HarnessState
from alpha.converse.tools import make_gated_write_tool


def _bare_h():
    return HarnessState(doctrine=Doctrine(), skills=SkillRegistry.from_skills([]),
                        memory=MemoryStore.from_lessons([]))


def test_gated_write_accepts_conflict_queue_kw():
    h = _bare_h()
    # must accept the kwargs without error (wiring gap closed)
    schema, fn = make_gated_write_tool(h, conflict_queue=None)
    assert schema["name"] == "propose_memory_edit"


def test_held_result_surfaces_when_conflict_queue_holds(monkeypatch):
    import alpha.converse.tools as t
    h = _bare_h()
    captured = {}

    def fake_try_apply_op(meta, harness, op, **kw):
        captured.update(kw)
        return None, "held_for_review: self-study contests a teaching-owned element"

    monkeypatch.setattr(t, "try_apply_op", fake_try_apply_op)

    class _Q: pass
    schema, fn = make_gated_write_tool(h, conflict_queue=_Q())
    out = fn(tool="process_memory", args={}, rationale="r")
    assert out["status"] == "held"
    assert "held_for_review" in out["reason"]
    assert captured.get("conflict_queue") is not None   # the queue was threaded to the gate
