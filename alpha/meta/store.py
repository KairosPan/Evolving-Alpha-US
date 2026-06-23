from __future__ import annotations

import json
import os
import shutil
import tempfile
from pathlib import Path

from alpha.harness.edit_log import EditLog
from alpha.harness.loader import load_seeds
from alpha.harness.state import HarnessState

DEFAULT_SEEDS_DIR = Path(__file__).resolve().parents[2] / "seeds"


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


class LiveBrainStore:
    """The persistent evolving brain (HarnessState + EditLog) as one JSON. Empty/missing -> seeds
    in-memory (no write on read). Rollback is a pre-apply file copy under history/."""

    def __init__(self, root: str | Path, *, seeds_dir: str | Path = DEFAULT_SEEDS_DIR) -> None:
        self._root = Path(root)
        self._seeds_dir = Path(seeds_dir)
        self._brain = self._root / "brain.json"
        self._history = self._root / "history"

    def is_live(self) -> bool:
        return self._brain.exists()

    def load(self) -> tuple[HarnessState, EditLog]:
        if not self._brain.exists():
            return load_seeds(self._seeds_dir), EditLog()
        data = json.loads(self._brain.read_text(encoding="utf-8"))
        return HarnessState.from_dict(data["harness"]), EditLog.from_dict(data["log"])

    def save(self, harness: HarnessState, log: EditLog) -> Path:
        _atomic_write(self._brain, json.dumps({"harness": harness.to_dict(), "log": log.to_dict()}))
        return self._brain

    def edit_count(self) -> int:
        if not self._brain.exists():
            return 0
        return len(json.loads(self._brain.read_text(encoding="utf-8")).get("log", []))

    def snapshot(self, session_id: str) -> str:
        self._history.mkdir(parents=True, exist_ok=True)
        dest = self._history / f"{session_id}.json"
        shutil.copyfile(self._brain, dest)
        return str(dest)

    def restore(self, snapshot_path: str) -> None:
        _atomic_write(self._brain, Path(snapshot_path).read_text(encoding="utf-8"))


from alpha.meta.models import Session


class SessionStore:
    """Flat by-id store of teaching Sessions (atomic write, newest-first listing)."""

    def __init__(self, root: str | Path) -> None:
        self._root = Path(root)

    def _path(self, session_id: str) -> Path:
        return self._root / f"{session_id}.json"

    def put(self, session: Session) -> Path:
        p = self._path(session.session_id)
        _atomic_write(p, session.model_dump_json())
        return p

    def get(self, session_id: str) -> Session | None:
        p = self._path(session_id)
        if not p.exists():
            return None
        return Session.model_validate_json(p.read_text(encoding="utf-8"))

    def list(self) -> list[Session]:
        if not self._root.is_dir():
            return []
        out = [Session.model_validate_json(p.read_text(encoding="utf-8"))
               for p in self._root.glob("*.json")]
        return sorted(out, key=lambda s: s.session_id, reverse=True)
