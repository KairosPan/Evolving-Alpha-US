import json
from alpha.converse.project import Project
from alpha.converse.sqlite_store import SqliteProjectStore
from alpha.llm.chat import ChatMessage
from scripts.migrate_projects_to_sqlite import migrate_projects


def test_migrate_imports_json_projects(tmp_path):
    jdir = tmp_path / "projects"
    jdir.mkdir()
    p = Project(project_id="p1", created_at="2026-06-27T00:00:00", title="t",
                messages=[ChatMessage(role="user", text="hello world")])
    (jdir / "p1.json").write_text(p.model_dump_json())
    db = tmp_path / "state.db"

    n = migrate_projects(str(jdir), str(db))
    assert n == 1
    got = SqliteProjectStore.open(str(db)).get("p1")
    assert got.model_dump() == p.model_dump()


def test_migrate_is_idempotent(tmp_path):
    jdir = tmp_path / "projects"
    jdir.mkdir()
    p = Project(project_id="p1", created_at="2026-06-27T00:00:00", title="t")
    (jdir / "p1.json").write_text(p.model_dump_json())
    db = tmp_path / "state.db"
    migrate_projects(str(jdir), str(db))
    migrate_projects(str(jdir), str(db))            # re-run: upsert, no duplicate / no error
    assert len(SqliteProjectStore.open(str(db)).list()) == 1
