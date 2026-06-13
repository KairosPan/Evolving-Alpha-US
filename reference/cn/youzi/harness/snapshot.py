from __future__ import annotations

import json
import os
from pathlib import Path

from youzi.harness.edit_log import EditLog
from youzi.harness.harness import HarnessState


class SnapshotStore:
    """版本化磁盘快照:每个版本一个 JSON 文件 root/snap_<NNNN>.json,内含 {version,label,harness,log}。"""

    def __init__(self, root: str | Path) -> None:
        self._root = Path(root)

    def _path(self, version: int) -> Path:
        return self._root / f"snap_{version:04d}.json"

    def list_versions(self) -> list[int]:
        if not self._root.is_dir():
            return []
        out: list[int] = []
        for p in self._root.glob("snap_*.json"):
            try:
                out.append(int(p.stem.split("_")[1]))
            except (IndexError, ValueError):
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
        tmp = final.with_suffix(".tmp")     # snap_NNNN.tmp -> 不被 snap_*.json glob 命中
        tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        os.replace(tmp, final)
        return version

    def load(self, version: int) -> tuple[HarnessState, EditLog]:
        p = self._path(version)
        if not p.exists():
            raise FileNotFoundError(f"无此快照版本: {version} ({p})")
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
            return (HarnessState.from_dict(data["harness"]), EditLog.from_dict(data["log"]))
        except (json.JSONDecodeError, KeyError) as e:
            raise RuntimeError(f"快照 {p.name} 损坏或格式错误: {e}") from e
