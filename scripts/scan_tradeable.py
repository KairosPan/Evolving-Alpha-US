"""Fast tradeability scan (no LLM): regime + screen survival per day over a captured PIT store.
Skips build_universe's per-gainer trailing RVOL/runner fetches (GCycle/veto don't use them) so it
runs in seconds. Usage: python scripts/scan_tradeable.py <pit_root> <start> <end>"""
from __future__ import annotations

import sys
from collections import Counter
from datetime import date as Date, datetime as DateTime
from pathlib import Path

import statistics as stats

from alpha.data.integrity_check import verify_checksums
from alpha.data.pit_store import PITStore
from alpha.data.snapshot_source import SnapshotSource
from alpha.data.firewall import AsOfGuard
from alpha.data.source import GuardedSource
from alpha.data.calendar import trading_days_between
from alpha.universe.universe import CandidateUniverse
from alpha.universe.stock import StockSnapshot
from alpha.state.builder import build_market_state
from alpha.regime.classifier import GCycle
from alpha.guard.screen import screen_decision
from alpha.eval.baselines import PoolAveragePolicy

GAINER_PCT, GAP_PCT = 10.0, 5.0


def fast_universe(guarded, day: Date) -> CandidateUniverse:
    snap = guarded.daily_snapshot(day)
    stocks: dict[str, StockSnapshot] = {}
    if snap is None or snap.empty:
        return CandidateUniverse(stocks)
    for rec in snap.to_dict("records"):
        close, prev, open_ = rec.get("close"), rec.get("prev_close"), rec.get("open")
        pct = ((close - prev) / prev * 100.0) if (close is not None and prev) else None
        gap = ((open_ - prev) / prev * 100.0) if (open_ is not None and prev) else None
        if pct is not None and pct >= GAINER_PCT:
            status = "gainer"
        elif gap is not None and gap >= GAP_PCT:
            status = "gap_up"
        elif pct is not None and pct <= -GAINER_PCT:
            status = "loser"
        else:
            continue
        stocks[str(rec["symbol"])] = StockSnapshot(
            symbol=str(rec["symbol"]), name=str(rec.get("name", "")), status=status,
            close=(float(close) if close is not None else None),
            prev_close=(float(prev) if prev is not None else None),
            pct_change=pct, gap_pct=gap,
            volume=(float(rec["volume"]) if rec.get("volume") is not None else None),
            rvol=None, consecutive_up_days=None)
    return CandidateUniverse(stocks)


def main() -> None:
    root, start, end = Path(sys.argv[1]), Date.fromisoformat(sys.argv[2]), Date.fromisoformat(sys.argv[3])
    src = SnapshotSource(PITStore(root))
    verify_checksums(root, fail_closed=False)   # D6: warn — a fast scan tolerates a stale window
    days = trading_days_between(src.trading_calendar(), start, end)
    hist: list[float] = []
    prevg: frozenset[str] = frozenset()
    phases: Counter = Counter()
    frontside = risk_on = kept_total = tradeable = 0
    gainer_counts: list[int] = []
    for cur in days:
        g = GuardedSource(src, AsOfGuard(cur))
        u = fast_universe(g, cur)
        st = build_market_state(u, cur, as_of=DateTime(cur.year, cur.month, cur.day, 16, 0),
                                history=hist, prev_gainers=prevg)
        hist.append(st.sentiment_raw)
        prevg = frozenset(s.symbol for s in u.by_status("gainer"))
        reg = GCycle().read(st)
        phases[reg.phase] += 1
        gainer_counts.append(st.gainer_count)
        if reg.frontside:
            frontside += 1
        if reg.risk_gate >= 0.2:
            risk_on += 1
        kept = screen_decision(PoolAveragePolicy().decide(st, u), source=src, state=st).candidates
        kept_total += len(kept)
        if kept:
            tradeable += 1
    print(f"window days={len(days)}  ({days[0]}..{days[-1]})")
    print(f"phase dist: {dict(phases)}")
    print(f"frontside days: {frontside}/{len(days)}   risk_on(risk_gate>=0.2): {risk_on}/{len(days)}")
    print(f"days with >=1 gainer SURVIVING screen: {tradeable}/{len(days)}")
    print(f"total surviving gainer-candidates: {kept_total}")
    print(f"gainers/day: mean={stats.mean(gainer_counts):.1f} median={stats.median(gainer_counts)} "
          f"max={max(gainer_counts)}  (prompt-size sanity)")


if __name__ == "__main__":
    main()
