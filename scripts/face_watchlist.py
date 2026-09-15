"""Fast, read-only US quote catalog for the face's cross-market watchlist.

This walks the latest captured snapshot and at most 30 trailing closes per
symbol; it does not run screens or breadth. All source reads are guarded at
the captured day. The TypeScript route adds the shared reference directory
for instruments without quotes. No network calls and no synthetic prices.
"""
from __future__ import annotations

import json
import math
import os
import sys
from datetime import date, datetime, timezone
from pathlib import Path

import pandas as pd

from alpaca_kit.firewall import AsOfGuard
from alpaca_kit.source import GuardedSource

REPO_ROOT = Path(__file__).resolve().parents[1]
BED_WINDOWS = {
    (REPO_ROOT / "data/pit/2yr").resolve(): (date(2024, 6, 3), date(2026, 7, 9)),
    (REPO_ROOT / "data/pit/broad").resolve(): (date(2025, 11, 17), date(2026, 3, 27)),
}
SOURCE = "本地日线快照 · 原始价格"
SPARK_BARS = 30


def _number(value):
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def _market(as_of=None):
    return {"id": "us", "label": "美股", "status": "snapshot" if as_of else "unavailable",
            "source": SOURCE if as_of else None, "as_of": as_of,
            "note": "本地历史快照，非实时行情；涨跌对比前一交易日收盘。"
                    if as_of else "本地美股快照不可用。"}


def watchlist_payload(source, days, end):
    """Uniform quotes with explicit missing values; prices are raw daily closes."""
    valid_days = sorted(day for day in days if day <= end)
    if not valid_days or valid_days[-1] != end:
        return {"ok": True, "assets": [], "markets": [_market()]}
    guard = GuardedSource(source, AsOfGuard(end))
    snapshot = guard.daily_snapshot(end)
    if snapshot is None or snapshot.empty:
        return {"ok": True, "assets": [], "markets": [_market()]}

    assets = []
    spark_start = valid_days[-min(SPARK_BARS, len(valid_days))]
    for record in snapshot.to_dict(orient="records"):
        symbol = str(record.get("symbol") or "").strip()
        if not symbol:
            continue
        price = _number(record.get("close"))
        previous = _number(record.get("prev_close"))
        change = price - previous if price is not None and previous is not None and previous > 0 else None
        bars = guard.daily_bars(symbol, spark_start, end)
        spark = []
        if bars is not None and not bars.empty and "close" in bars and "date" in bars:
            bars = bars.copy()
            bars["date"] = pd.to_datetime(bars["date"]).dt.date
            # GuardedSource checks the request; slice too in case an adapter
            # ignores the bounds. Missing closes stay gaps, never turn to zero.
            bars = bars[(bars["date"] >= spark_start) & (bars["date"] <= end)]
            spark = [_number(close) for close in bars.sort_values("date").tail(SPARK_BARS)["close"]]
        raw_name = record.get("name")
        name = str(raw_name) if isinstance(raw_name, str) and raw_name.strip() else symbol
        assets.append({
            "id": f"us:{symbol}", "market": "us", "symbol": symbol,
            "name": name, "currency": "USD", "exchange": "US", "aliases": [],
            "price": price, "change": round(change, 6) if change is not None else None,
            "change_pct": round(change / previous * 100, 6) if change is not None else None,
            "volume": _number(record.get("volume")),
            "as_of": end.isoformat() if price is not None else None,
            "source": SOURCE, "quote_status": "snapshot" if price is not None else "unavailable",
            "spark": spark,
        })
    return {"ok": True, "assets": assets, "markets": [_market(end.isoformat())]}


def real_watchlist():
    from alpaca_kit.pit.pit_store import PITStore
    from alpaca_kit.pit.snapshot_source import SnapshotSource

    root = Path(os.environ.get("ALPHA_PIT_ROOT") or REPO_ROOT / "data/pit/2yr").resolve()
    store = PITStore(root)
    window = BED_WINDOWS.get(root)
    # A calendar extends years before the actual capture. Snapshot existence
    # plus the documented usable bounds, rather than the calendar, decides.
    days = sorted(day for day in store.get_calendar() or []
                  if (window is None or window[0] <= day <= window[1]) and store.has_snapshot(day))
    if not days:
        return {"ok": True, "assets": [], "markets": [_market()]}
    return watchlist_payload(SnapshotSource(store), days, days[-1])


def main() -> int:
    try:
        payload = real_watchlist()
        payload["generated_at"] = datetime.now(timezone.utc).isoformat()
        output = json.dumps(payload, ensure_ascii=False, allow_nan=False)
    except Exception as exc:
        # The route can serve its previous cache after a broken read. Do not
        # leak local paths, environment values, or a traceback into a response.
        print(f"face_watchlist: read failed ({type(exc).__name__})", file=sys.stderr)
        print(json.dumps({"ok": False, "error": "watchlist snapshot unavailable"}))
        return 1
    print(output)
    return 0


if __name__ == "__main__":
    sys.exit(main())
