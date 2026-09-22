# tests/data/test_massive_files.py
"""MassiveFilesSource: bought Massive/Polygon-shaped daily-bar files under <root>/<TICKER>/*.json as a
bars + calendar RAW source. Fixtures are written to tmp_path (test_edgar.py style: the seam is the file)."""
from __future__ import annotations

import json
from datetime import date
from pathlib import Path

import pytest

from alpaca_kit.feeds.massive_files import MassiveFileError, MassiveFilesSource

# 2026-06-10 00:00 ET = 04:00 UTC (EDT) -> t in ms. Consecutive bars are one day apart.
_T0 = 1781064000000            # 2026-06-10T04:00:00Z
_DAY = 86_400_000


def _row(t: int, o: float, h: float, l: float, c: float, v: float, **extra) -> dict:
    return {"t": t, "o": o, "h": h, "l": l, "c": c, "v": v, "vw": (o + c) / 2, "n": 42, **extra}


def _body(ticker: str, rows: list[dict], *, adjusted=False, status="OK") -> dict:
    body = {"ticker": ticker, "queryCount": len(rows), "resultsCount": len(rows), "status": status,
            "results": rows, "request_id": "x", "count": len(rows)}
    if adjusted is not None:
        body["adjusted"] = adjusted
    return body


def _write(root: Path, ticker: str, name: str, body: dict) -> Path:
    d = root / ticker
    d.mkdir(parents=True, exist_ok=True)
    p = d / name
    p.write_text(json.dumps(body))
    return p


_ACME_ROWS = [_row(_T0, 10.0, 12.0, 9.5, 11.0, 1_000_000),
              _row(_T0 + _DAY, 12.5, 15.0, 12.0, 14.0, 3_000_000),
              _row(_T0 + 2 * _DAY, 16.0, 18.0, 15.0, 17.0, 5_000_000)]


def test_maps_polygon_keys_to_the_six_raw_columns(tmp_path):
    _write(tmp_path, "ACME", "a.json", _body("ACME", _ACME_ROWS))
    src = MassiveFilesSource(tmp_path)
    df = src.daily_bars("ACME", date(2026, 6, 10), date(2026, 6, 12))
    assert list(df.columns) == ["date", "open", "high", "low", "close", "volume"]   # vw / n dropped
    assert list(df["date"]) == [date(2026, 6, 10), date(2026, 6, 11), date(2026, 6, 12)]
    assert list(df["open"]) == [10.0, 12.5, 16.0] and list(df["close"]) == [11.0, 14.0, 17.0]
    assert list(df["high"]) == [12.0, 15.0, 18.0] and list(df["low"]) == [9.5, 12.0, 15.0]
    assert list(df["volume"]) == [1_000_000, 3_000_000, 5_000_000]


def test_daily_bars_windows_and_unknown_symbol_is_empty(tmp_path):
    _write(tmp_path, "ACME", "a.json", _body("ACME", _ACME_ROWS))
    src = MassiveFilesSource(tmp_path)
    assert list(src.daily_bars("ACME", date(2026, 6, 11), date(2026, 6, 11))["close"]) == [14.0]
    empty = src.daily_bars("ZZZZ", date(2026, 6, 10), date(2026, 6, 12))
    assert empty.empty and list(empty.columns) == ["date", "open", "high", "low", "close", "volume"]


def test_t_ms_is_read_as_an_america_new_york_date(tmp_path):
    # 2026-01-05T05:00:00Z is midnight ET (EST); a bar stamped there belongs to 2026-01-05, and one at
    # 2026-01-05T03:00:00Z (22:00 ET the evening before) belongs to 2026-01-04 — NOT the UTC date.
    t_est_midnight = 1767589200000                       # 2026-01-05T05:00:00Z
    _write(tmp_path, "ACME", "a.json", _body("ACME", [
        _row(t_est_midnight, 1, 2, 1, 2, 10), _row(t_est_midnight - 2 * 3_600_000 - _DAY, 1, 2, 1, 2, 10)]))
    src = MassiveFilesSource(tmp_path)
    assert src.trading_calendar() == [date(2026, 1, 3), date(2026, 1, 5)]


@pytest.mark.parametrize("adjusted", [True, None, "false"])
def test_adjusted_not_literally_false_is_refused_naming_the_file(tmp_path, adjusted):
    p = _write(tmp_path, "ACME", "bought.json", _body("ACME", _ACME_ROWS, adjusted=adjusted))
    with pytest.raises(MassiveFileError, match="adjusted") as ei:
        MassiveFilesSource(tmp_path).trading_calendar()
    assert str(p) in str(ei.value)


def test_status_not_ok_is_refused(tmp_path):
    p = _write(tmp_path, "ACME", "bought.json", _body("ACME", _ACME_ROWS, status="ERROR"))
    with pytest.raises(MassiveFileError, match="status") as ei:
        MassiveFilesSource(tmp_path).daily_bars("ACME", date(2026, 6, 10), date(2026, 6, 12))
    assert str(p) in str(ei.value)


def test_ticker_mismatch_with_directory_is_refused(tmp_path):
    p = _write(tmp_path, "ACME", "bought.json", _body("MSFT", _ACME_ROWS))
    with pytest.raises(MassiveFileError, match="MSFT") as ei:
        MassiveFilesSource(tmp_path).trading_calendar()
    assert str(p) in str(ei.value)


def test_row_missing_a_required_key_is_refused(tmp_path):
    bad = dict(_ACME_ROWS[0]); del bad["v"]
    p = _write(tmp_path, "ACME", "bought.json", _body("ACME", [bad]))
    with pytest.raises(MassiveFileError, match=r"row 0 is missing \['v'\]") as ei:
        MassiveFilesSource(tmp_path).trading_calendar()
    assert str(p) in str(ei.value)


def test_calendar_is_union_of_bar_dates_or_the_explicit_one(tmp_path):
    _write(tmp_path, "ACME", "a.json", _body("ACME", _ACME_ROWS[:2]))                 # 6/10, 6/11
    _write(tmp_path, "BETA", "b.json", _body("BETA", [_row(_T0 + 2 * _DAY, 1, 2, 1, 2, 10)]))  # 6/12
    assert MassiveFilesSource(tmp_path).trading_calendar() == [date(2026, 6, 10), date(2026, 6, 11),
                                                               date(2026, 6, 12)]
    explicit = [date(2026, 6, 9), date(2026, 6, 10)]
    assert MassiveFilesSource(tmp_path, calendar=explicit).trading_calendar() == explicit


def test_a_gap_yields_no_row_never_interpolated(tmp_path):
    # backtest-rules rule 5: ACME has no 6/11 bar; the window read returns two rows, not a filled three.
    _write(tmp_path, "ACME", "a.json", _body("ACME", [_ACME_ROWS[0], _ACME_ROWS[2]]))
    df = MassiveFilesSource(tmp_path).daily_bars("ACME", date(2026, 6, 10), date(2026, 6, 12))
    assert list(df["date"]) == [date(2026, 6, 10), date(2026, 6, 12)]


def test_overlapping_identical_files_merge_and_dedupe(tmp_path):
    _write(tmp_path, "ACME", "2026-06-10_2026-06-11.json", _body("ACME", _ACME_ROWS[:2]))
    _write(tmp_path, "ACME", "2026-06-11_2026-06-12.json", _body("ACME", _ACME_ROWS[1:]))
    df = MassiveFilesSource(tmp_path).daily_bars("ACME", date(2026, 6, 1), date(2026, 6, 30))
    assert list(df["date"]) == [date(2026, 6, 10), date(2026, 6, 11), date(2026, 6, 12)]
    assert list(df["close"]) == [11.0, 14.0, 17.0]


def test_conflicting_ohlcv_for_one_date_is_refused(tmp_path):
    _write(tmp_path, "ACME", "first.json", _body("ACME", _ACME_ROWS[:2]))
    other = dict(_ACME_ROWS[1]); other["c"] = 99.0
    p = _write(tmp_path, "ACME", "second.json", _body("ACME", [other]))
    with pytest.raises(MassiveFileError, match="conflicting") as ei:
        MassiveFilesSource(tmp_path).trading_calendar()
    assert str(p) in str(ei.value) and "2026-06-11" in str(ei.value)


def test_every_other_capability_is_unimplemented_and_unavailable(tmp_path):
    _write(tmp_path, "ACME", "a.json", _body("ACME", _ACME_ROWS))
    src = MassiveFilesSource(tmp_path)
    d = date(2026, 6, 12)
    for call in (lambda: src.daily_snapshot(d), lambda: src.corporate_actions(d, d),
                 lambda: src.corporate_actions_known(d), lambda: src.earnings_known("ACME", d),
                 lambda: src.earnings_calendar(d), lambda: src.short_interest_known("ACME", d),
                 lambda: src.offering_events_known("ACME", d), lambda: src.float_known("ACME", d)):
        with pytest.raises(NotImplementedError):
            call()
    assert src.corp_actions_available() is False          # cannot check -> MISSING, never "clean"
    assert src.earnings_available() is False and src.short_interest_available() is False
    assert src.offerings_available() is False and src.float_available() is False


def test_missing_root_is_refused(tmp_path):
    with pytest.raises(MassiveFileError, match="not a directory"):
        MassiveFilesSource(tmp_path / "nope").trading_calendar()
