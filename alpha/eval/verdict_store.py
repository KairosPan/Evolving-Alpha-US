"""VerdictStore — a labeled JSON-dict store for verdict *view dicts* (the shape `run_verdict --json`
writes and the web console's verdict page reads). Twin of DecisionStore, but keyed by an arbitrary
string label (typically the window, e.g. "2026-01-02_2026-03-31") rather than a date, and intentionally
shape-agnostic: it persists and returns plain dicts; the console validates the shape on read.
"""
from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path


class VerdictStore:
    """A flat by-label store of verdict view dicts at `<root>/<label>.json`. `put` is atomic; readers
    tolerate an absent directory and also see files written directly by `run_verdict --json`."""

    def __init__(self, root: str | Path) -> None:
        self._root = Path(root)

    def _path(self, label: str) -> Path:
        return self._root / f"{label}.json"

    def put(self, label: str, data: dict) -> Path:
        self._root.mkdir(parents=True, exist_ok=True)
        p = self._path(label)
        fd, tmp = tempfile.mkstemp(dir=self._root, suffix=".json.tmp")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2)
            os.replace(tmp, p)
        except BaseException:
            if os.path.exists(tmp):
                os.unlink(tmp)
            raise
        return p

    def names(self) -> list[str]:
        if not self._root.is_dir():
            return []
        return sorted(p.stem for p in self._root.glob("*.json"))

    def get(self, label: str) -> dict | None:
        p = self._path(label)
        if not p.exists():
            return None
        return json.loads(p.read_text(encoding="utf-8"))

    def latest(self) -> dict | None:
        ns = self.names()
        return self.get(ns[-1]) if ns else None

    def __len__(self) -> int:
        return len(self.names())
