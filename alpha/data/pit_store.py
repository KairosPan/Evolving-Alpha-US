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

    # ── earnings (P5a) — facts keyed on filing_date, calendar on known_asof; frames from
    #    alpha/data/earnings.py's converters. has_earnings() is the tri-state MISSING seam (mirrors
    #    has_corp_actions): True even for an empty facts frame, False only when the artifact is absent. ──
    def _earnings_facts_path(self) -> Path:
        return self._root / "earnings_facts.parquet"

    def has_earnings(self) -> bool:
        return self._earnings_facts_path().exists()

    def put_earnings(self, df: pd.DataFrame) -> None:
        out = df.copy()
        for c in ("period_end", "filing_date"):
            if c in out.columns:
                out[c] = out[c].map(lambda d: d.isoformat() if d is not None else None)
        _atomic_to_parquet(out, self._earnings_facts_path())

    def get_earnings(self) -> pd.DataFrame | None:
        p = self._earnings_facts_path()
        if not p.exists():
            return None
        df = pd.read_parquet(p)
        for c in ("period_end", "filing_date"):
            if c in df.columns:
                df[c] = pd.to_datetime(df[c]).dt.date
        return df

    def put_earnings_calendar(self, df: pd.DataFrame) -> None:
        out = df.copy()
        for c in ("expected_date", "known_asof"):
            if c in out.columns:
                out[c] = out[c].map(lambda d: d.isoformat() if d is not None else None)
        _atomic_to_parquet(out, self._root / "earnings_calendar.parquet")

    def get_earnings_calendar(self) -> pd.DataFrame | None:
        p = self._root / "earnings_calendar.parquet"
        if not p.exists():
            return None
        df = pd.read_parquet(p)
        for c in ("expected_date", "known_asof"):
            if c in df.columns:
                df[c] = pd.to_datetime(df[c]).dt.date
        return df

    # ── short interest (P5b) — records keyed on publication_date; has_short_interest() is the tri-state
    #    MISSING seam (True even for an empty frame, False only when the artifact is absent). ──
    def _short_interest_path(self) -> Path:
        return self._root / "short_interest.parquet"

    def has_short_interest(self) -> bool:
        return self._short_interest_path().exists()

    def put_short_interest(self, df: pd.DataFrame) -> None:
        out = df.copy()
        for c in ("settlement_date", "publication_date"):
            if c in out.columns:
                out[c] = out[c].map(lambda d: d.isoformat() if d is not None else None)
        _atomic_to_parquet(out, self._short_interest_path())

    def get_short_interest(self) -> pd.DataFrame | None:
        p = self._short_interest_path()
        if not p.exists():
            return None
        df = pd.read_parquet(p)
        for c in ("settlement_date", "publication_date"):
            if c in df.columns:
                df[c] = pd.to_datetime(df[c]).dt.date
        return df

    # ── offerings lifecycle (P5b) — typed events keyed on process_date; has_offering_events() tri-state. ──
    def _offering_events_path(self) -> Path:
        return self._root / "offering_events.parquet"

    def has_offering_events(self) -> bool:
        return self._offering_events_path().exists()

    def put_offering_events(self, df: pd.DataFrame) -> None:
        out = df.copy()
        if "process_date" in out.columns:
            out["process_date"] = out["process_date"].map(lambda d: d.isoformat() if d is not None else None)
        _atomic_to_parquet(out, self._offering_events_path())

    def get_offering_events(self) -> pd.DataFrame | None:
        p = self._offering_events_path()
        if not p.exists():
            return None
        df = pd.read_parquet(p)
        if "process_date" in df.columns:
            df["process_date"] = pd.to_datetime(df["process_date"]).dt.date
        return df

    # ── free float (P5b) — facts keyed on knowable_date; has_float() is the tri-state MISSING seam (True
    #    even for an empty frame, False only when the artifact is absent — like has_short_interest). ──
    def _float_path(self) -> Path:
        return self._root / "float_shares.parquet"

    def has_float(self) -> bool:
        return self._float_path().exists()

    def put_float(self, df: pd.DataFrame) -> None:
        out = df.copy()
        for c in ("knowable_date", "as_of_period"):
            if c in out.columns:
                out[c] = out[c].map(lambda d: d.isoformat() if d is not None else None)
        _atomic_to_parquet(out, self._float_path())

    def get_float(self) -> pd.DataFrame | None:
        p = self._float_path()
        if not p.exists():
            return None
        df = pd.read_parquet(p)
        for c in ("knowable_date", "as_of_period"):
            if c in df.columns:
                df[c] = pd.to_datetime(df[c]).dt.date
        return df
