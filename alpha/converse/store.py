from __future__ import annotations

import os
import tempfile
from pathlib import Path

from alpha.converse.project import Project


def _atomic_write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=path.parent, suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(text)
        os.replace(tmp, path)
    except BaseException:
        if os.path.exists(tmp):
            os.unlink(tmp)
        raise


class ProjectStore:
    """Flat by-id store of Projects (atomic write, newest-first listing)."""

    def __init__(self, root: str | Path) -> None:
        self._root = Path(root)

    def _path(self, project_id: str) -> Path:
        # project_id reaches here straight from a URL path param; never let `..`/absolute paths
        # escape the store dir (the id feeds unlink/read/write). Reject anything that resolves out.
        p = (self._root / f"{project_id}.json").resolve()
        if not p.is_relative_to(self._root.resolve()):
            raise ValueError(f"invalid project_id: {project_id!r}")
        return p

    def put(self, project: Project) -> Path:
        p = self._path(project.project_id)
        _atomic_write(p, project.model_dump_json())
        return p

    def get(self, project_id: str) -> Project | None:
        p = self._path(project_id)
        if not p.exists():
            return None
        return Project.model_validate_json(p.read_text(encoding="utf-8"))

    def delete(self, project_id: str) -> None:
        """Hard-delete a project record. Idempotent: a missing id is a no-op."""
        self._path(project_id).unlink(missing_ok=True)

    def list(self) -> list[Project]:
        if not self._root.is_dir():
            return []
        out: list[Project] = []
        for p in self._root.glob("*.json"):
            try:
                out.append(Project.model_validate_json(p.read_text(encoding="utf-8")))
            except Exception:
                continue
        return sorted(out, key=lambda proj: proj.project_id, reverse=True)
