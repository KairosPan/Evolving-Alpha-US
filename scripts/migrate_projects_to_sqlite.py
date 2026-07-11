"""One-time migration: import JSON ProjectStore files into a SqliteProjectStore (state.db).

Usage:
    ALPHA_PROJECTS_DIR=./state/projects \
    ALPHA_PROJECTS_DB=./state/projects/state.db \
    python scripts/migrate_projects_to_sqlite.py

Idempotent (upsert by project_id). Safe to re-run.
"""
from __future__ import annotations

import os
from pathlib import Path

from alpha.converse.project import Project
from alpha.converse.sqlite_store import SqliteProjectStore
from alpha.settings import Settings


def migrate_projects(json_dir: str, db_path: str) -> int:
    """Import every *.json Project under *json_dir* into the SQLite store at *db_path*.
    Returns the number of projects migrated."""
    store = SqliteProjectStore.open(db_path)
    n = 0
    for jf in sorted(Path(json_dir).glob("*.json")):
        try:
            project = Project.model_validate_json(jf.read_text(encoding="utf-8"))
        except Exception:
            continue
        store.put(project)
        n += 1
    return n


if __name__ == "__main__":
    s = Settings.from_env()
    src = os.environ.get("ALPHA_PROJECTS_DIR", "./state/projects")
    dst = s.projects_db
    count = migrate_projects(src, dst)
    print(f"migrated {count} project(s) from {src} -> {dst}")
