import pytest
from alpha.converse.project import new_project
from alpha.converse.store import ProjectStore


def test_put_get_list_delete(tmp_path):
    s = ProjectStore(tmp_path)
    p = new_project("a")
    s.put(p)
    assert s.get(p.project_id) == p
    assert [x.project_id for x in s.list()] == [p.project_id]
    s.delete(p.project_id)
    assert s.get(p.project_id) is None and s.list() == []


def test_path_traversal_guard(tmp_path):
    with pytest.raises(ValueError):
        ProjectStore(tmp_path)._path("../escape")
