# youzi/loop/run_store.py
from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path

from youzi.loop.compare import ComparisonReport


class RunStore:
    """持久化 compare 运行结果(ComparisonReport JSON,原子写)。root/<run_id>.json = {meta, report}。"""

    def __init__(self, root) -> None:
        self._root = Path(root)

    def _path(self, run_id: str) -> Path:
        return self._root / f"{run_id}.json"

    def save(self, run_id: str, report: ComparisonReport, meta: dict) -> str:
        self._root.mkdir(parents=True, exist_ok=True)
        payload = {"meta": {**meta, "run_id": run_id},
                   "report": report.model_dump(mode="json")}
        fd, tmp = tempfile.mkstemp(dir=self._root, suffix=".json.tmp")
        os.close(fd)
        try:
            Path(tmp).write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
            os.replace(tmp, self._path(run_id))         # 原子写
        except BaseException:
            try:
                os.unlink(tmp)
            except OSError:
                pass
            raise
        return run_id

    def list(self) -> list[dict]:
        if not self._root.exists():
            return []
        metas = []
        for p in self._root.glob("*.json"):
            if p.name.startswith("."):                 # 跳过 ._AppleDouble/隐藏(macOS 非原生卷如 /Volumes 会生成二进制 ._*.json)
                continue
            try:                                       # 逐文件守卫:一个外来/损坏/二进制文件不拖垮整列(否则看板全 500)
                metas.append(json.loads(p.read_text(encoding="utf-8"))["meta"])
            except (json.JSONDecodeError, UnicodeDecodeError, KeyError, OSError):
                continue
        return sorted(metas, key=lambda m: m["run_id"], reverse=True)   # 新→旧

    def load(self, run_id: str) -> tuple[ComparisonReport, dict]:
        d = json.loads(self._path(run_id).read_text(encoding="utf-8"))
        return ComparisonReport.model_validate(d["report"]), d["meta"]
