"""market_payload assembles the /market payload from any Protocol-shaped source."""
from datetime import date, timedelta

import pandas as pd

from alpaca_kit.source import GuardedSource

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import face_data  # noqa: E402
from face_data import market_payload  # noqa: E402


class _TinySource:
    """Three symbols, ~30 ascending days of bars, one snapshot on the end day."""

    def __init__(self, days):
        self.days = days
        self.syms = ["AAA", "BBB", "CCC"]

    def trading_calendar(self):
        # build_universe's trailing-bar/RVOL helpers ask the source for its calendar; the fixture's
        # captured days ARE its calendar (returning [] would silently starve both screens instead).
        return list(self.days)

    def daily_snapshot(self, day):
        rows = []
        for i, s in enumerate(self.syms):
            close = 10.0 + i + self.days.index(day) * 0.1
            rows.append({"symbol": s, "close": close, "prev_close": close - 0.1,
                         "open": close - 0.05, "high": close + 0.1, "low": close - 0.2,
                         "volume": 1000.0 + i})
        return pd.DataFrame(rows)

    def daily_bars(self, symbol, start, end):
        i = self.syms.index(symbol)
        rows = [{"date": d, "open": 10.0 + i, "high": 11.0 + i, "low": 9.0 + i,
                 "close": 10.0 + i + n * 0.1, "volume": 1000.0}
                for n, d in enumerate(self.days) if start <= d <= end]
        return pd.DataFrame(rows)


class _GainerSource(_TinySource):
    """_TinySource with AAA printing a +20% day, so the gainer screen actually yields a row
    (the base fixture's ~1% moves screen out, leaving the row/spark path unexercised)."""

    def daily_snapshot(self, day):
        df = super().daily_snapshot(day)
        mask = df["symbol"] == "AAA"
        df.loc[mask, "prev_close"] = df.loc[mask, "close"] / 1.2
        return df


class _NoBarsSource(_GainerSource):
    """AAA screens in from the snapshot but has no bars at all (the bar store can lag the
    snapshot store: capture gap / halt / fresh listing)."""

    def daily_bars(self, symbol, start, end):
        if symbol == "AAA":
            return pd.DataFrame(columns=["date", "open", "high", "low", "close", "volume"])
        return super().daily_bars(symbol, start, end)


class _LateEntrantSource(_TinySource):
    """A fourth symbol whose history starts only in the last few days of the window."""

    LATE = "DDD"

    def __init__(self, days, late_from=-4):
        super().__init__(days)
        self.syms = self.syms + [self.LATE]
        self.late_days = days[late_from:]

    def daily_bars(self, symbol, start, end):
        if symbol != self.LATE:
            return super().daily_bars(symbol, start, end)
        rows = [{"date": d, "open": 50.0, "high": 51.0, "low": 49.0,
                 "close": 50.0 + n * 5.0, "volume": 1000.0}
                for n, d in enumerate(self.late_days) if start <= d <= end]
        return pd.DataFrame(rows)


class _SpySource:
    """Records every dated read that reaches the RAW source, and refuses any read past the cursor.
    Paired with _recording_guard below, this fences the firewall discipline: the two recordings must
    match 1:1, so routing any read around the guard breaks the test."""

    def __init__(self, inner, cursor, calls):
        self._inner, self._cursor, self.calls = inner, cursor, calls

    def _record(self, method, day):
        if day is not None and day > self._cursor:
            raise AssertionError(f"lookahead: {method} asked for {day} > cursor {self._cursor}")
        self.calls.append((method, day))

    def trading_calendar(self):
        self._record("trading_calendar", None)
        return self._inner.trading_calendar()

    def daily_snapshot(self, day):
        self._record("daily_snapshot", day)
        return self._inner.daily_snapshot(day)

    def daily_bars(self, symbol, start, end):
        self._record("daily_bars", end)
        return self._inner.daily_bars(symbol, start, end)


def _recording_guard(calls):
    """A real GuardedSource that also records what was asked of it."""

    class _Guard(GuardedSource):
        def trading_calendar(self):
            calls.append(("trading_calendar", None))
            return super().trading_calendar()

        def daily_snapshot(self, day):
            calls.append(("daily_snapshot", day))
            return super().daily_snapshot(day)

        def daily_bars(self, symbol, start, end):
            calls.append(("daily_bars", end))
            return super().daily_bars(symbol, start, end)

    return _Guard


def _days(n=30):
    d0 = date(2026, 6, 1)
    return [d0 + timedelta(days=k) for k in range(n)]


def test_market_payload_shape_and_honesty():
    days = _days()
    payload = market_payload(_TinySource(days), days, days[-1],
                             breadth_days=5, tape_days=10, screen_limit=5)
    assert payload["ok"] is True
    assert payload["as_of"] == days[-1].isoformat()
    assert "bed" in payload and "warmup" in payload["bed"]
    b = payload["breadth"]["series"]
    assert len(b) == 5
    assert {"date", "pct_above_200dma", "net_new_highs", "advances", "declines"} <= set(b[0])
    t = payload["tape"]["series"]
    assert len(t) == 10
    assert t[0]["level"] == 100.0  # normalized to window start
    scr = payload["screens"]
    assert set(scr) == {"trend_template", "gainer"}
    for kind in scr.values():
        assert "rows" in kind and "raw" in kind
        for row in kind["rows"]:
            assert "spark" in row and len(row["spark"]) <= 60


def test_market_payload_short_history_never_fabricates():
    # only 3 days of history: 200DMA/52wk readings must be None, not 0
    days = _days(3)
    payload = market_payload(_TinySource(days), days, days[-1],
                             breadth_days=3, tape_days=3, screen_limit=5)
    last = payload["breadth"]["series"][-1]
    assert last["pct_above_200dma"] is None
    assert last["net_new_highs"] is None
    # ...while the measures that ARE defined on 3 closes stay real: None is the immature reading,
    # not a blanket "no data" for the whole row.
    assert last["advances"] == 3 and last["declines"] == 0


def test_market_payload_screen_rows_carry_snapshot_fields_and_spark():
    """A screen that actually hits: rows are serialized StockSnapshots + a window-normalized spark."""
    days = _days()
    payload = market_payload(_GainerSource(days), days, days[-1],
                             breadth_days=5, tape_days=10, screen_limit=5)
    rows = payload["screens"]["gainer"]["rows"]
    assert [r["symbol"] for r in rows] == ["AAA"]
    row = rows[0]
    assert row["status"] == "gainer"
    assert row["pct_change"] > 10.0
    closes = _GainerSource(days).daily_bars("AAA", days[0], days[-1])["close"].tolist()
    assert row["spark"][0] == 1.0                      # normalized to the spark window's first close
    assert row["spark"][-1] == round(closes[-1] / closes[0], 4)   # ...and it tracks the real move
    assert len(row["spark"]) == len(closes) <= 60
    assert payload["screens"]["gainer"]["raw"].endswith("screen='gainer')")


def test_screen_row_without_bars_still_carries_an_empty_spark():
    """Uniform shape: a screened symbol the bar store has nothing for gets spark [], not no key."""
    days = _days()
    payload = market_payload(_NoBarsSource(days), days, days[-1],
                             breadth_days=3, tape_days=5, screen_limit=5)
    rows = payload["screens"]["gainer"]["rows"]
    assert [r["symbol"] for r in rows] == ["AAA"]
    assert rows[0]["spark"] == []


def test_tape_excludes_late_entrants_instead_of_splicing_them_in():
    """A symbol whose history starts mid-window never joins the composite, so its entry day shows
    no membership jump and no phantom move."""
    days = _days()
    late = market_payload(_LateEntrantSource(days), days, days[-1],
                          breadth_days=3, tape_days=10, screen_limit=5)["tape"]["series"]
    plain = market_payload(_TinySource(days), days, days[-1],
                           breadth_days=3, tape_days=10, screen_limit=5)["tape"]["series"]
    assert {row["n"] for row in late} == {3}          # constant membership across the whole window
    assert late == plain                              # DDD moves the composite not at all


def test_tape_note_states_the_membership_rule():
    days = _days()
    payload = market_payload(_TinySource(days), days, days[-1],
                             breadth_days=3, tape_days=5, screen_limit=5)
    assert "late entrants" in payload["tape"]["note"]
    assert "survivorship" in payload["tape"]["note"]
    assert "survivorship" in payload["breadth"]["note"]


def test_market_payload_bed_carries_measured_counts_without_mutating_the_constant():
    days = _days()
    payload = market_payload(_TinySource(days), days, days[-1],
                             breadth_days=3, tape_days=5, screen_limit=5)
    assert payload["bed"]["symbols"] == 3
    assert payload["bed"]["captured_days"] == len(days)
    assert payload["bed"]["window"] == face_data.BED_INFO["window"]   # constants still carried
    assert "symbols" not in face_data.BED_INFO and "captured_days" not in face_data.BED_INFO


def test_market_payload_no_captured_days_is_an_honest_failure():
    """Empty bed -> a failure payload, not an IndexError on the tape window (and no source read)."""
    payload = market_payload(_TinySource(_days()), [], date(2026, 6, 30))
    assert payload == {"ok": False, "error": "no captured days"}


def test_market_payload_reads_only_through_the_guard(monkeypatch):
    """Firewall fence: every dated read reaching the raw source was mediated by the guard (1:1, in
    order), and nothing past `end` was ever requested. Routing any read around the guard fails this."""
    days = _days()
    end = days[-1]
    raw, guarded = [], []
    monkeypatch.setattr(face_data, "GuardedSource", _recording_guard(guarded))
    market_payload(_SpySource(_TinySource(days), end, raw), days, end,
                   breadth_days=3, tape_days=5, screen_limit=5)
    assert raw, "the payload read nothing - the fence would be vacuous"
    assert raw == guarded
    assert all(day is None or day <= end for _, day in raw)
    assert ("daily_snapshot", end) in raw
    assert any(method == "daily_bars" for method, _ in raw)
