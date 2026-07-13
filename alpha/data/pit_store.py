from __future__ import annotations

import os
import tempfile
from datetime import date as Date
from pathlib import Path

import pandas as pd


def _atomic_to_parquet(df: pd.DataFrame, p: Path) -> None:
    """Atomic parquet write: temp in same dir then os.replace; never leave a truncated final file."""
    p.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=p.parent, suffix=".parquet.tmp")
    os.close(fd)
    try:
        df.to_parquet(tmp, index=False)
        os.replace(tmp, p)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


class PITStore:
    """Point-in-time parquet cache. Once written, a day's frame is its as-of snapshot."""

    def __init__(self, root: Path) -> None:
        self._root = Path(root)

    @property
    def root(self) -> Path:
        return self._root

    def _snap_path(self, day: Date) -> Path:
        return self._root / "snapshot" / f"{day.strftime('%Y%m%d')}.parquet"

    def has_snapshot(self, day: Date) -> bool:
        return self._snap_path(day).exists()

    def get_snapshot(self, day: Date) -> pd.DataFrame | None:
        p = self._snap_path(day)
        return pd.read_parquet(p) if p.exists() else None

    def put_snapshot(self, day: Date, df: pd.DataFrame) -> None:
        _atomic_to_parquet(df, self._snap_path(day))

    def _bars_path(self, symbol: str) -> Path:
        return self._root / "bars" / f"{symbol}.parquet"

    def get_bars(self, symbol: str) -> pd.DataFrame | None:
        p = self._bars_path(symbol)
        return pd.read_parquet(p) if p.exists() else None

    def put_bars(self, symbol: str, df: pd.DataFrame) -> None:
        _atomic_to_parquet(df, self._bars_path(symbol))

    def put_calendar(self, days: list[Date]) -> None:
        _atomic_to_parquet(pd.DataFrame({"date": [d.isoformat() for d in days]}),
                           self._root / "calendar.parquet")

    def get_calendar(self) -> list[Date] | None:
        p = self._root / "calendar.parquet"
        if not p.exists():
            return None
        return [pd.to_datetime(s).date() for s in pd.read_parquet(p)["date"]]

    def has_corp_actions(self) -> bool:
        """Whether corp_actions.parquet was written (tri-state seam, mirrors has_snapshot): True even for
        an empty frame (checked, nothing announced); False ONLY when the artifact is absent — the one
        place 'guard could not check' is distinguishable from 'checked, clean'."""
        return (self._root / "corp_actions.parquet").exists()

    def put_corp_actions(self, df: pd.DataFrame) -> None:
        out = df.copy()
        for c in ("announce_date", "ex_date"):
            if c in out.columns:
                out[c] = out[c].map(lambda d: d.isoformat())
        _atomic_to_parquet(out, self._root / "corp_actions.parquet")

    def get_corp_actions(self) -> pd.DataFrame | None:
        p = self._root / "corp_actions.parquet"
        if not p.exists():
            return None
        df = pd.read_parquet(p)
        for c in ("announce_date", "ex_date"):
            if c in df.columns:
                df[c] = pd.to_datetime(df[c]).dt.date
        return df
