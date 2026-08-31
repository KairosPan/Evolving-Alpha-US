"""market_payload assembles the /market payload from any Protocol-shaped source."""
from datetime import date, timedelta

import pandas as pd

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
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
    assert payload["breadth"]["series"][-1]["pct_above_200dma"] is None


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
    assert row["spark"][0] == 1.0                      # normalized to the spark window's first close
    assert 1 < len(row["spark"]) <= 60
    assert payload["screens"]["gainer"]["raw"].endswith("screen='gainer')")
