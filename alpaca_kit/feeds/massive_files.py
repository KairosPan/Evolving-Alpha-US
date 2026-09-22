# alpaca_kit.feeds.massive_files.py
#
# MassiveFilesSource — BOUGHT daily-bar files as a MarketDataSource (the `bars` + `calendar` capability
# groups only). The files are the bytes a Massive/Polygon-shaped aggregates endpoint returned to a paid
# `wallet_pay({url, save_to})` call (the `bought-data` mechanics skill), laid out as
# `<root>/<TICKER>/*.json`. Nothing in the file NAME is parsed; every fact comes from the body, and the
# body's `ticker` must match the directory it sits in. This source is the capture-side reader only: a
# backtest never opens these JSON files (backtest-rules rule 1) — it replays the PIT bed that
# `capture_window(MassiveFilesSource(root), PITStore(bed), ...)` writes from them.
#
# Fail-closed on the file: `adjusted` must be literally False (missing counts as unknown -> refused,
# because backtest-rules rule 4 wants RAW/unadjusted prices and a vendor's default is adjusted),
# `status` must be "OK", every row must carry t/o/h/l/c/v. `vw` and `n` are dropped. Files for one
# ticker merge; the same date in two files is fine when the OHLCV agree and refused when they differ.
#
# The calendar is the sorted union of every ticker's bar dates unless an explicit calendar is given.
# Consequence (recorded on purpose): a bed captured from this source has the BOUGHT WINDOW as its
# calendar — a day no bought file covers is not a trading day to the bed, and a symbol's missing day
# inside the window is a gap (rule 5: skipped, never interpolated), never a holiday.
from __future__ import annotations

import json
from datetime import date as Date
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

import pandas as pd

_BARS_COLS = ["date", "open", "high", "low", "close", "volume"]
_ET = ZoneInfo("America/New_York")
_REQUIRED_ROW_KEYS = ("t", "o", "h", "l", "c", "v")
# Massive/Polygon aggregate keys -> the six RAW columns, exactly as alpaca.py's _normalize_bars produces.
_COLUMN_MAP = {"o": "open", "h": "high", "l": "low", "c": "close", "v": "volume"}


class MassiveFileError(ValueError):
    """A bought file is refused. The message names the file so the operator can find the bytes."""


def _ms_to_et_date(t_ms: int | float) -> Date:
    """A Massive bar's `t` is the bar's start in Unix milliseconds (UTC). A daily bar starts at the
    session's midnight in New York, which is 04:00/05:00 UTC — so the date is read in America/New_York,
    never in UTC (where a 05:00 UTC timestamp already carries the right date, but 00:00 ET is 04:00 or
    05:00 UTC and a tz-naive read of a vendor that stamps 00:00 UTC would be wrong the other way)."""
    return datetime.fromtimestamp(t_ms / 1000.0, tz=timezone.utc).astimezone(_ET).date()


def _load_file(path: Path, ticker: str) -> pd.DataFrame:
    """One bought file -> a six-column RAW frame, or MassiveFileError naming the file."""
    try:
        body = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as e:
        raise MassiveFileError(f"{path}: not readable JSON ({e})") from e
    if not isinstance(body, dict):
        raise MassiveFileError(f"{path}: body is not a JSON object")
    if body.get("adjusted") is not False:
        raise MassiveFileError(f"{path}: adjusted is {body.get('adjusted')!r}, expected false "
                               "(RAW/unadjusted prices only — backtest-rules rule 4)")
    if body.get("status") != "OK":
        raise MassiveFileError(f"{path}: status is {body.get('status')!r}, expected 'OK'")
    file_ticker = body.get("ticker")
    if not isinstance(file_ticker, str) or file_ticker.upper() != ticker:
        raise MassiveFileError(f"{path}: ticker is {file_ticker!r} but the file sits under {ticker}/")
    results = body.get("results")
    if results is None:
        results = []
    if not isinstance(results, list):
        raise MassiveFileError(f"{path}: results is not a list")
    rows = []
    for i, r in enumerate(results):
        if not isinstance(r, dict) or any(k not in r or r[k] is None for k in _REQUIRED_ROW_KEYS):
            missing = ([k for k in _REQUIRED_ROW_KEYS if not isinstance(r, dict) or r.get(k) is None])
            raise MassiveFileError(f"{path}: row {i} is missing {missing} (need t/o/h/l/c/v)")
        rows.append({"date": _ms_to_et_date(r["t"]),
                     **{col: r[k] for k, col in _COLUMN_MAP.items()}})   # vw / n dropped here
    if not rows:
        return pd.DataFrame(columns=_BARS_COLS)
    out = pd.DataFrame(rows)
    for c in ("open", "high", "low", "close", "volume"):
        out[c] = pd.to_numeric(out[c], errors="coerce")
    return out[_BARS_COLS]


def _merge(frames: list[tuple[Path, pd.DataFrame]], ticker: str) -> pd.DataFrame:
    """Concatenate one ticker's files; identical duplicate dates collapse, conflicting ones refuse."""
    if not frames:
        return pd.DataFrame(columns=_BARS_COLS)
    seen: dict[Date, tuple[Path, tuple]] = {}
    for path, df in frames:
        for row in df.itertuples(index=False):
            key = (row.open, row.high, row.low, row.close, row.volume)
            prior = seen.get(row.date)
            if prior is not None and prior[1] != key:
                raise MassiveFileError(f"{path}: {ticker} {row.date} has OHLCV {key} but {prior[0]} "
                                       f"has {prior[1]} — conflicting bought files for one date")
            seen.setdefault(row.date, (path, key))
    out = pd.DataFrame([{"date": d, "open": k[0], "high": k[1], "low": k[2], "close": k[3], "volume": k[4]}
                        for d, (_, k) in sorted(seen.items())])
    return out[_BARS_COLS].reset_index(drop=True)


class MassiveFilesSource:
    """Bought Massive/Polygon-shaped daily-bar files under `<root>/<TICKER>/*.json` as a RAW source.

    Serves `daily_bars` (six RAW columns) and `trading_calendar` (explicit `calendar`, else the sorted
    union of every ticker's bar dates). Files are read and validated lazily on first use and cached;
    any refused file raises MassiveFileError naming it. Every other capability raises
    NotImplementedError and its `*_available()` reports False: this source cannot check corporate
    actions, so a bed captured from it carries no corp_actions.parquet and replays as MISSING.
    """

    def __init__(self, root: str | Path, *, calendar: list[Date] | None = None) -> None:
        self._root = Path(root)
        self._calendar = sorted(calendar) if calendar is not None else None
        self._bars: dict[str, pd.DataFrame] | None = None

    @property
    def root(self) -> Path:
        return self._root

    def _load_all(self) -> dict[str, pd.DataFrame]:
        if self._bars is None:
            if not self._root.is_dir():
                raise MassiveFileError(f"{self._root}: not a directory")
            bars: dict[str, pd.DataFrame] = {}
            for d in sorted(p for p in self._root.iterdir() if p.is_dir()):
                ticker = d.name.upper()
                frames = [(f, _load_file(f, ticker)) for f in sorted(d.glob("*.json"))]
                if frames:
                    bars[ticker] = _merge(frames, ticker)
            self._bars = bars
        return self._bars

    # ── bars + calendar capabilities ────────────────────────────────────────────────────────────────
    def trading_calendar(self) -> list[Date]:
        if self._calendar is not None:
            return list(self._calendar)
        days: set[Date] = set()
        for df in self._load_all().values():
            days.update(df["date"].tolist())
        return sorted(days)

    def daily_bars(self, symbol: str, start: Date, end: Date) -> pd.DataFrame:
        df = self._load_all().get(symbol.upper())
        if df is None or df.empty:
            return pd.DataFrame(columns=_BARS_COLS)
        return df[(df["date"] >= start) & (df["date"] <= end)].reset_index(drop=True)

    # ── everything else: not served; availability is honestly False (MISSING, never "checked, clean") ──
    def _only_bars(self, *_a, **_k):
        raise NotImplementedError("MassiveFilesSource serves only the `bars` and `calendar` capabilities "
                                  "(bought daily-bar files); compose other feeds via CompositeSource")

    def _unavailable(self) -> bool:
        return False

    daily_snapshot = _only_bars
    corporate_actions = _only_bars
    corporate_actions_known = _only_bars
    corp_actions_available = _unavailable
    earnings_known = _only_bars
    earnings_calendar = _only_bars
    earnings_available = _unavailable
    short_interest_known = _only_bars
    short_interest_available = _unavailable
    offering_events_known = _only_bars
    offerings_available = _unavailable
    float_known = _only_bars
    float_available = _unavailable
