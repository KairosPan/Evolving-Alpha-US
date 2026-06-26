from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path

from pydantic import BaseModel

from alpha.meta.models import new_session_id, now_iso


class HeldConflict(BaseModel):
    conflict_id: str
    created_at: str
    op: dict
    provenance: dict | None = None
    contested: dict | None = None


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


class ConflictQueue:
    """Flat by-id store of held conflicts (atomic write, newest-first listing)."""

    def __init__(self, root: str | Path) -> None:
        self._root = Path(root)

    def _path(self, conflict_id: str) -> Path:
        # conflict_id may come from a URL param; never let `..`/absolute paths
        # escape the store dir. Reject anything that resolves out.
        p = (self._root / f"{conflict_id}.json").resolve()
        if not p.is_relative_to(self._root.resolve()):
            raise ValueError(f"invalid conflict_id: {conflict_id!r}")
        return p

    def add(
        self,
        op: dict,
        provenance: dict | None = None,
        contested: dict | None = None,
    ) -> HeldConflict:
        conflict_id = new_session_id()
        h = HeldConflict(
            conflict_id=conflict_id,
            created_at=now_iso(),
            op=op,
            provenance=provenance,
            contested=contested,
        )
        _atomic_write(self._path(conflict_id), h.model_dump_json())
        return h

    def get(self, conflict_id: str) -> HeldConflict | None:
        p = self._path(conflict_id)
        if not p.exists():
            return None
        return HeldConflict.model_validate_json(p.read_text(encoding="utf-8"))

    def all(self) -> list[HeldConflict]:
        if not self._root.is_dir():
            return []
        out: list[HeldConflict] = []
        for p in self._root.glob("*.json"):
            try:
                out.append(HeldConflict.model_validate_json(p.read_text(encoding="utf-8")))
            except Exception:
                continue
        return sorted(out, key=lambda h: h.conflict_id, reverse=True)

    def resolve(self, conflict_id: str) -> None:
        self._path(conflict_id).unlink(missing_ok=True)
