"""Growth market-clock calibration: the three-state distribution over a captured PIT window.

Offline, keyless. Replays `alpha/regime/growth_clock.py::GrowthMarketClock` day by day over the
captured daily snapshots — accumulating the strictly-prior history exactly as the live GuardedPolicy
does — and prints the `market:confirmed_uptrend / under_pressure / correction` distribution plus the
frontside (new-buys-allowed) and panic (`detect_panic_state`) base rates. This is the reproducible P2
acceptance evidence (DEVELOPMENT-PLAN §1 P2): a real US window must classify frontside days at a
plausible base rate, NOT thin-by-construction like the momo ~35/59-backside read.

The per-day gainer/loser counts use the SAME ±10% screen as `build_universe`, so the read matches the
live decide path (gainer_share proxy). `--breadth` additionally threads the FULL-cross-section
advance/decline (close vs prior close over EVERY snapshot row, not just the ±10% tail) into the read —
a richer market-trend signal the clock prefers when present (`market_share`); the default reads
gainer_share, the live path's signal.

Usage:
  python scripts/calibrate_growth_clock.py <pit_root> [start] [end] [--breadth]

  <pit_root>     a PIT store built by scripts/capture_window.py (e.g. ./verdict_pit_broad)
  [start] [end]  ISO dates (YYYY-MM-DD) narrowing the window; default = the full captured snapshot range
  --breadth      also thread full advance/decline into the read (default: gainer_share, the live path)
"""
from __future__ import annotations

import statistics
import sys
from collections import Counter
from dataclasses import dataclass, field
from datetime import date as Date, datetime as DateTime
from pathlib import Path

from alpha.data.firewall import AsOfGuard
from alpha.data.integrity_check import verify_checksums
from alpha.data.pit_store import PITStore
from alpha.data.snapshot_source import SnapshotSource
from alpha.data.source import GuardedSource
from alpha.guard.panic import detect_panic_state
from alpha.regime.growth_clock import GrowthMarketClock, market_share
from alpha.state.market import MarketState

GAINER_PCT, GAP_PCT = 10.0, 5.0    # the build_universe screen — same counts the live path reads
_STATES = ("confirmed_uptrend", "under_pressure", "correction")


def market_state_from_snapshot(snap, day: Date, *, breadth: bool = False) -> MarketState:
    """The clock's inputs from one day's raw snapshot: gainer/loser counts under the ±10% build_universe
    screen (so gainer_share matches the live path), and — when `breadth` — the FULL-cross-section
    advance/decline (every row's close vs its prior close). Only the fields the clock reads are populated."""
    g = gu = lo = adv = dec = 0
    for rec in (snap.to_dict("records") if snap is not None and not snap.empty else []):
        close, prev, open_ = rec.get("close"), rec.get("prev_close"), rec.get("open")
        pct = ((close - prev) / prev * 100.0) if (close is not None and prev) else None
        gap = ((open_ - prev) / prev * 100.0) if (open_ is not None and prev) else None
        if pct is not None and pct >= GAINER_PCT:
            g += 1
        elif gap is not None and gap >= GAP_PCT:
            gu += 1
        elif pct is not None and pct <= -GAINER_PCT:
            lo += 1
        if breadth and close is not None and prev:      # full-cross-section a/d (all rows, not the tail)
            adv += close > prev
            dec += close < prev
    return MarketState(date=day, gainer_count=g, gap_up_count=gu, loser_count=lo, failed_breakout_count=0,
                       max_runner_tier=0, echelon=[], breadth_raw=float(g - lo),
                       advances=(adv if breadth else None), declines=(dec if breadth else None),
                       as_of=DateTime(day.year, day.month, day.day, 16, 0))


@dataclass(frozen=True)
class CalibrationReport:
    """The growth-clock state distribution over a window (the P2 acceptance evidence)."""
    n_days: int
    states: dict = field(default_factory=dict)   # state -> day count
    frontside: int = 0                            # days new buys are allowed (== confirmed_uptrend count)
    panic: int = 0                                # days the panic flag fires
    empty_days: int = 0                           # 0/0 (no-signal) tape days
    share_min: float = 0.0
    share_mean: float = 0.0
    share_max: float = 0.0
    # stability diagnostics (post-fix these must be low — a jittery machine flickers day to day)
    state_changes: int = 0                        # adjacent-day state transitions
    single_day_islands: int = 0                   # states that last exactly one day
    abab_points: int = 0                          # A-B-A flips (day-parity oscillation signature)
    start: Date | None = None
    end: Date | None = None


def _stability(seq: list[str]) -> tuple[int, int, int]:
    """(state_changes, single_day_islands, abab_points) over a chronological state sequence."""
    changes = sum(1 for a, b in zip(seq, seq[1:]) if a != b)
    islands = sum(1 for i in range(len(seq))
                  if (i == 0 or seq[i] != seq[i - 1]) and (i == len(seq) - 1 or seq[i] != seq[i + 1]))
    abab = sum(1 for i in range(1, len(seq) - 1) if seq[i - 1] == seq[i + 1] != seq[i])
    return changes, islands, abab


def calibrate(source, days: list[Date], *, breadth: bool = False) -> CalibrationReport:
    """Replay the growth market clock over `days`, accumulating strictly-prior history like the live
    GuardedPolicy. Returns the state/frontside/panic distribution. PIT-safe: each day is read through a
    GuardedSource(AsOfGuard(day)) (no future). Pure over the source — no writes, no LLM, no keys."""
    clock = GrowthMarketClock()
    history: list[MarketState] = []
    states: Counter = Counter()
    seq: list[str] = []
    frontside = panic = empty = 0
    shares: list[float] = []
    for d in days:
        guarded = GuardedSource(source, AsOfGuard(d))
        st = market_state_from_snapshot(guarded.daily_snapshot(d), d, breadth=breadth)
        read = clock.read(history, st)
        state = read.phase.split(":", 1)[1]
        states[state] += 1
        seq.append(state)
        frontside += read.frontside
        panic += detect_panic_state(history, st) if history else False
        shares.append(market_share(st))
        if (st.gainer_count + st.loser_count) == 0 and st.advances is None:
            empty += 1
        history.append(st)
    changes, islands, abab = _stability(seq)
    return CalibrationReport(
        n_days=len(days), states=dict(states), frontside=frontside, panic=panic, empty_days=empty,
        share_min=(min(shares) if shares else 0.0), share_max=(max(shares) if shares else 0.0),
        share_mean=(statistics.mean(shares) if shares else 0.0),
        state_changes=changes, single_day_islands=islands, abab_points=abab,
        start=(days[0] if days else None), end=(days[-1] if days else None))


def format_report(r: CalibrationReport, *, breadth: bool = False) -> str:
    """Render the distribution table (the printed acceptance evidence)."""
    n = r.n_days or 1
    lines = [f"growth market-clock calibration: {r.n_days} days ({r.start}..{r.end})  breadth={breadth}",
             "", "state distribution:"]
    for s in _STATES:
        c = r.states.get(s, 0)
        lines.append(f"  market:{s:20s} {c:4d}  ({c / n:5.1%})")
    lines += ["",
              f"frontside (new-buys-allowed): {r.frontside}/{r.n_days} ({r.frontside / n:.1%})",
              f"panic-flag days:              {r.panic}/{r.n_days} ({r.panic / n:.1%})",
              f"market_share min/mean/max:    {r.share_min:.2f} / {r.share_mean:.2f} / {r.share_max:.2f}",
              f"empty (0/0) tape days:        {r.empty_days}/{r.n_days}",
              "",
              f"stability: state_changes={r.state_changes}  single_day_islands={r.single_day_islands}  "
              f"abab_points={r.abab_points}"]
    return "\n".join(lines)


def _snapshot_days(root: Path) -> list[Date]:
    """The captured snapshot days (from snapshot/YYYYMMDD.parquet), chronological. The captured calendar
    can span years while only a sub-window has snapshots, so enumerate the files, not the calendar."""
    out = []
    for f in sorted((root / "snapshot").glob("*.parquet")):
        s = f.stem
        out.append(Date(int(s[:4]), int(s[4:6]), int(s[6:8])))
    return sorted(out)


def main() -> None:
    args = [a for a in sys.argv[1:] if a != "--breadth"]
    breadth = "--breadth" in sys.argv
    if not args:
        print(__doc__)
        raise SystemExit(2)
    root = Path(args[0])
    source = SnapshotSource(PITStore(root))
    verify_checksums(root, fail_closed=False)          # D6: warn — a calibration tolerates a stale window
    days = _snapshot_days(root)
    if len(args) >= 2:
        days = [d for d in days if d >= Date.fromisoformat(args[1])]
    if len(args) >= 3:
        days = [d for d in days if d <= Date.fromisoformat(args[2])]
    if not days:
        raise SystemExit(f"no captured snapshot days in {root} for the requested range")
    print(format_report(calibrate(source, days, breadth=breadth), breadth=breadth))


if __name__ == "__main__":
    main()
