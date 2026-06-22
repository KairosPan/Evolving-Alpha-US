"""DecisionStore — persist the day's `DecisionPackage` as `<root>/<YYYY-MM-DD>.json` (atomic write,
same idiom as PITStore). The web console reads these by date (`ALPHA_WEB_DECISIONS_DIR`) so the
`/decisions` page browses the real packages a run produced instead of a single one-off file.
"""
from __future__ import annotations

import os
import tempfile
from datetime import date as Date
from pathlib import Path

from alpha.eval.decision import DecisionPackage


class DecisionStore:
    """A flat by-date store of DecisionPackages. Read-only consumers (the console) tolerate an absent
    directory and ignore non-decision files; `put` is atomic (temp-in-dir + os.replace)."""

    def __init__(self, root: str | Path) -> None:
        self._root = Path(root)

    def _path(self, day: Date) -> Path:
        return self._root / f"{day.isoformat()}.json"

    def put(self, pkg: DecisionPackage) -> Path:
        """Write (or overwrite) the package for its date. Never leaves a truncated final file."""
        self._root.mkdir(parents=True, exist_ok=True)
        p = self._path(pkg.date)
        fd, tmp = tempfile.mkstemp(dir=self._root, suffix=".json.tmp")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                f.write(pkg.model_dump_json())
            os.replace(tmp, p)
        except BaseException:
            if os.path.exists(tmp):
                os.unlink(tmp)
            raise
        return p

    def dates(self) -> list[Date]:
        """Sorted dates present. Files whose stem is not an ISO date are ignored, not an error."""
        if not self._root.is_dir():
            return []
        out: list[Date] = []
        for p in self._root.glob("*.json"):
            try:
                out.append(Date.fromisoformat(p.stem))
            except ValueError:
                continue
        return sorted(out)

    def get(self, day: Date) -> DecisionPackage | None:
        p = self._path(day)
        if not p.exists():
            return None
        return DecisionPackage.model_validate_json(p.read_text(encoding="utf-8"))

    def latest(self) -> DecisionPackage | None:
        ds = self.dates()
        return self.get(ds[-1]) if ds else None

    def __len__(self) -> int:
        return len(self.dates())
