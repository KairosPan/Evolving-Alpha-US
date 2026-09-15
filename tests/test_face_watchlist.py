"""Cross-market route's US producer: real guarded history and honest absence."""
import json
import sys
from datetime import date, timedelta
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import face_watchlist


class Source:
    def __init__(self, days):
        self.days = days
        self.calls = []

    def daily_snapshot(self, day):
        self.calls.append(("snapshot", day))
        return pd.DataFrame([
            {"symbol": "AAA", "name": "Alpha", "close": 12, "prev_close": 10, "volume": 42},
            {"symbol": "BBB", "name": "BBB", "close": float("nan"), "prev_close": 5, "volume": float("inf")},
            {"symbol": "CCC", "name": "CCC", "close": 7, "prev_close": 0, "volume": 0},
        ])

    def daily_bars(self, symbol, start, end):
        self.calls.append(("bars", end))
        if symbol != "AAA":
            return pd.DataFrame()
        # Deliberately ignore request bounds. The producer still cannot leak
        # the extra future observation into the chart.
        return pd.DataFrame({"date": self.days + [end + timedelta(days=1)],
                             "close": [10 + i for i in range(len(self.days))] + [999]})


def test_quotes_preserve_missing_values_and_measure_change_in_percentage_points():
    days = [date(2026, 7, 8), date(2026, 7, 9)]
    result = face_watchlist.watchlist_payload(Source(days), days, days[-1])
    assert result["ok"]
    apple, missing, no_previous = result["assets"]
    assert apple["price"] == 12
    assert apple["change"] == 2
    assert apple["change_pct"] == 20
    assert apple["as_of"] == "2026-07-09"
    assert apple["quote_status"] == "snapshot"
    assert apple["spark"] == [10, 11]
    assert missing["price"] is None and missing["volume"] is None
    assert missing["quote_status"] == "unavailable" and missing["as_of"] is None
    assert missing["change"] is None and missing["change_pct"] is None
    assert no_previous["change"] is None and no_previous["change_pct"] is None
    json.dumps(result, allow_nan=False)


def test_every_source_read_is_guarded_and_spark_is_bounded(monkeypatch):
    days = [date(2026, 6, 1) + timedelta(days=i) for i in range(35)]
    source = Source(days)
    guarded = []
    original = face_watchlist.GuardedSource

    class RecordingGuard(original):
        def daily_snapshot(self, day):
            guarded.append(("snapshot", day))
            return super().daily_snapshot(day)

        def daily_bars(self, symbol, start, end):
            guarded.append(("bars", end))
            return super().daily_bars(symbol, start, end)

    monkeypatch.setattr(face_watchlist, "GuardedSource", RecordingGuard)
    result = face_watchlist.watchlist_payload(source, days, days[-1])
    assert guarded == source.calls and guarded
    assert len(result["assets"][0]["spark"]) == 30
    assert result["assets"][0]["spark"][0] == 15
    assert 999 not in result["assets"][0]["spark"]


def test_missing_capture_does_not_invent_quotes_or_an_as_of():
    result = face_watchlist.watchlist_payload(Source([]), [], date(2026, 7, 9))
    assert result["assets"] == []
    assert result["markets"][0]["status"] == "unavailable"
    assert result["markets"][0]["as_of"] is None


def test_real_watchlist_stays_inside_documented_bed_window(tmp_path, monkeypatch):
    from alpaca_kit.pit.pit_store import PITStore

    store = PITStore(tmp_path)
    days = [date(2026, 7, 8), date(2026, 7, 9), date(2026, 7, 10)]
    store.put_calendar([date(2016, 1, 1)] + days)
    for day in days:
        store.put_snapshot(day, pd.DataFrame([{"symbol": "AAA", "close": 10, "prev_close": 9}]))
    monkeypatch.setenv("ALPHA_PIT_ROOT", str(tmp_path))
    monkeypatch.setattr(face_watchlist, "BED_WINDOWS", {tmp_path.resolve(): (days[0], days[1])})
    result = face_watchlist.real_watchlist()
    assert result["assets"][0]["as_of"] == "2026-07-09"


def test_cli_failure_uses_fixed_error_and_no_sensitive_exception_message(monkeypatch, capsys):
    def fail():
        raise ValueError("SECRET_ENV_VALUE")
    monkeypatch.setattr(face_watchlist, "real_watchlist", fail)
    assert face_watchlist.main() == 1
    captured = capsys.readouterr()
    assert json.loads(captured.out) == {"ok": False, "error": "watchlist snapshot unavailable"}
    assert "SECRET_ENV_VALUE" not in captured.out + captured.err
