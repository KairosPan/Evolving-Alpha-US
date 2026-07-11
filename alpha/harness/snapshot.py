from __future__ import annotations

import json
import os
from pathlib import Path

from alpha.harness.edit_log import EditLog
from alpha.harness.state import HarnessState
from alpha.integrity import sha256_canonical_json


def harness_digest(h: HarnessState) -> str:
    """Canonical content digest of a HarnessState (feeds A10's joint rollback; eval never reads it).
    Equal content -> equal digest; any content change -> a different digest (sha256 of the canonical
    JSON of h.to_dict(), via alpha.integrity — the same canonicalizer used for edit-log/file hashing)."""
    return sha256_canonical_json(h.to_dict())


class SnapshotStore:
    """Versioned disk snapshots: one JSON per version at root/snap_<NNNN>.json,
    containing {version, label, harness, log}. (`log` is a list[dict] — EditLog.to_dict
    returns a list, not a dict — so the payload is intentionally heterogeneous.)"""

    def __init__(self, root: str | Path) -> None:
        self._root = Path(root)

    def _path(self, version: int) -> Path:
        return self._root / f"snap_{version:04d}.json"

    def list_versions(self) -> list[int]:
        if not self._root.is_dir():
            return []
        out: list[int] = []
        for p in self._root.glob("snap_*.json"):
            parts = p.stem.split("_")
            if len(parts) != 2:           # ignore foreign files (e.g. snap_0000_extra.json)
                continue
            try:
                out.append(int(parts[1]))
            except ValueError:
                continue
        return sorted(out)

    def latest(self) -> int | None:
        vs = self.list_versions()
        return vs[-1] if vs else None

    def save(self, harness: HarnessState, log: EditLog, label: str = "") -> int:
        self._root.mkdir(parents=True, exist_ok=True)
        latest = self.latest()
        version = 0 if latest is None else latest + 1
        payload = {"version": version, "label": label,
                   "harness": harness.to_dict(), "log": log.to_dict()}
        final = self._path(version)
        tmp = final.with_suffix(".tmp")     # snap_NNNN.tmp -> not matched by snap_*.json glob
        tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        # atomic same-dir rename (gives the atomicity the spec requires). Crash-durability (fsync of
        # the temp + dir before replace) is deferred — the corrupt-load guard fails loudly on a torn
        # file from power-loss, so it degrades safely.
        os.replace(tmp, final)
        return version

    def load(self, version: int) -> tuple[HarnessState, EditLog]:
        p = self._path(version)
        if not p.exists():
            raise FileNotFoundError(f"no such snapshot version: {version} ({p})")
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
            return (HarnessState.from_dict(data["harness"]), EditLog.from_dict(data["log"]))
        except (json.JSONDecodeError, KeyError) as e:
            raise RuntimeError(f"snapshot {p.name} is corrupt or malformed: {e}") from e
