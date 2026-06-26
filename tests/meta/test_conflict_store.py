import pytest
from alpha.meta.conflict_store import ConflictQueue, HeldConflict


def test_add_get_all_resolve_round_trip(tmp_path):
    q = ConflictQueue(tmp_path)
    h = q.add(op={"tool": "demote_memory"}, provenance={"path": "self_study"}, contested={"target_id": "m1"})
    assert isinstance(h, HeldConflict) and h.conflict_id and h.created_at
    assert q.get(h.conflict_id) == h
    assert [c.conflict_id for c in q.all()] == [h.conflict_id]
    q.resolve(h.conflict_id)
    assert q.get(h.conflict_id) is None and q.all() == []


def test_path_traversal_guard(tmp_path):
    with pytest.raises(ValueError):
        ConflictQueue(tmp_path)._path("../escape")
