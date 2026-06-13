from __future__ import annotations

import os
import tempfile
from datetime import date as Date
from pathlib import Path

import pandas as pd


def _atomic_to_parquet(df: pd.DataFrame, p: Path) -> None:
    """原子写 parquet:先写同目录临时文件再 os.replace(同盘原子 rename)。
    硬 kill 写到一半只留 .tmp(被 has() 忽略),决不在最终路径留截断文件——保任何读者(含 SnapshotSource)。"""
    p.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=p.parent, suffix=".parquet.tmp")
    os.close(fd)
    try:
        df.to_parquet(tmp, index=False)
        os.replace(tmp, p)
    except BaseException:               # 含 KeyboardInterrupt:清理临时、决不发布半成品
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


class PITStore:
    """point-in-time 缓存:每日每类原始帧落一个 parquet,路径 = root/kind/YYYYMMDD.parquet。

    一旦写入即视为"该日 as-of 快照",不应被未来修订覆盖(由调用方保证幂等)。
    """

    def __init__(self, root: Path) -> None:
        self._root = Path(root)

    def _path(self, kind: str, day: Date) -> Path:
        return self._root / kind / f"{day.strftime('%Y%m%d')}.parquet"

    def has(self, kind: str, day: Date) -> bool:
        return self._path(kind, day).exists()

    def get(self, kind: str, day: Date) -> pd.DataFrame | None:
        p = self._path(kind, day)
        if not p.exists():
            return None
        return pd.read_parquet(p)

    def put(self, kind: str, day: Date, df: pd.DataFrame) -> None:
        _atomic_to_parquet(df, self._path(kind, day))

    def _ohlcv_path(self, code: str) -> Path:
        return self._root / "ohlcv" / f"{code}.parquet"

    def has_ohlcv(self, code: str) -> bool:
        return self._ohlcv_path(code).exists()

    def get_ohlcv(self, code: str) -> pd.DataFrame | None:
        p = self._ohlcv_path(code)
        return pd.read_parquet(p) if p.exists() else None

    def put_ohlcv(self, code: str, df: pd.DataFrame) -> None:
        _atomic_to_parquet(df, self._ohlcv_path(code))

    def put_calendar(self, days: list[Date]) -> None:
        _atomic_to_parquet(
            pd.DataFrame({"date": [d.isoformat() for d in days]}), self._root / "calendar.parquet")

    def get_calendar(self) -> list[Date] | None:
        p = self._root / "calendar.parquet"
        if not p.exists():
            return None
        return [pd.to_datetime(s).date() for s in pd.read_parquet(p)["date"]]
