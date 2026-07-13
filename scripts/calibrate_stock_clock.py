"""Growth stock-clock calibration: the §1.3 stage distribution over a captured PIT window.

Offline, keyless. The stock-scale sibling of `scripts/calibrate_growth_clock.py`. Replays
`alpha/regime/stock_clock.py::classify_stock_stage` per symbol, day by day, over the captured bars —
each call sees only that symbol's strictly-prior history + today (PIT) — and prints the aggregated
`stock:base / advance / top / decline` distribution, the `climax_run` flag fire-rate, the abstain
(warm-up) rate, and the per-symbol flicker triple (`state_changes / single_day_islands / abab_points`)
averaged — flicker being the thing a per-day classifier most needs to be checked for.

WHAT THE BED PROVIDES vs WHAT THE CLOCK READS (read this — it bounds how much is exercisable). The
captured bed carries ONLY OHLCV bars; the `StockSnapshot` fields the clock reads beyond `close`
(`rvol`, `consecutive_up_days`, `rs_percentile`, `pct_change`) are NOT stored. This script DERIVES them
from the bars with the SAME live-path formulas, so the read matches what the live decide path would feed
the clock — provenance stated, not hidden:
  - pct_change            = (close - prev_close) / prev_close            (the clock also derives this)
  - rvol                  = today_vol / mean(prior RVOL_WINDOW vols)     (mirrors universe._trailing_rvol)
  - consecutive_up_days   = trailing run of up-closes ending today       (mirrors runner.consecutive_up_days)
  - rs_percentile         = cross-sectional percentile of a trailing RS  (mirrors trend_template rs_*)
Fed ONLY the literal bed (no derivation) the clock cannot fire a breakout (no rs/cud) and would sit at
100% `base` — inert. With derivation it is exercised; the caveats below say by how much.

CAVEATS on a ~90-trading-day bed:
  - The clock's OWN constants are fixed (they are the thresholds under test): `MIN_HISTORY = 60`
    priced days for a determined rising-SMA50, so per symbol only the LAST ~30 days are post-warm-up —
    two thirds of every symbol's reads are ABSTAIN by construction of the short bed.
  - `rs_percentile` needs the literature 126/252-day RS legs, which CANNOT FORM on 90 bars → the RS
    ranking would be empty and `rs_strong` (market confirmation) could never fire → no breakout → 100%
    `base`. So this script defaults to BED-FITTED RS legs (`--rs-short 21 --rs-long 42`); the RS
    percentile is a PROXY on this bed. Pass `--rs-short 126 --rs-long 252` to see the all-`base` inert
    read. `advance` therefore leans on a shortened market-confirmation leg — read it as such.
  - `top` needs `TOP_CONFIRM = 5` distribution days within `DD_WINDOW = 25` sessions SINCE an advance
    anchor; in a ~30-day exercisable window that is barely reachable, so a near-zero `top` count here is
    as much a bed-length artifact as a threshold read.

Usage:
  python scripts/calibrate_stock_clock.py <pit_root> [start] [end] [--rs-short N] [--rs-long N] [--rvol N]

  <pit_root>     a PIT store built by scripts/capture_window.py (e.g. ./verdict_pit_broad)
  [start] [end]  ISO dates (YYYY-MM-DD) narrowing the window; default = the full captured snapshot range
  --rs-short N   RS short leg (default 21; literature 126 — inert on a <252-day bed)
  --rs-long N    RS long leg (default 42; literature 252)
  --rvol N       RVOL trailing window (default 20, the live universe default)
"""
from __future__ import annotations

import statistics
import sys
from collections import Counter
from dataclasses import dataclass
from datetime import date as Date
from pathlib import Path

from alpha.data.integrity_check import verify_checksums
from alpha.data.pit_store import PITStore
from alpha.data.snapshot_source import SnapshotSource
from alpha.features.trend_template import rs_percentiles
from alpha.regime.stock_clock import _TOKENS, classify_stock_stage
from alpha.universe.stock import StockSnapshot

DEF_RS_SHORT, DEF_RS_LONG, DEF_RVOL = 21, 42, 20       # bed-fitted RS; literature 126/252 (see docstring)
_STAGES = tuple(_TOKENS.values())                       # ("stock:base", "advance", "top", "decline")
_ABSTAIN = "abstain"                                    # warm-up (<MIN_HISTORY) or no close today


@dataclass(frozen=True)
class Series:
    """One symbol's chronological OHLCV, ready for PIT feature derivation."""
    symbol: str
    dates: list        # ascending Date
    closes: list       # aligned float|None
    vols: list         # aligned float|None


def _rs_raw(closes: list, i: int, short: int, long: int) -> float | None:
    """Trailing raw RS at trailing index `i` — mirrors trend_template.rs_raw_score's 0.5/0.5 blend of the
    short- and long-leg total returns from RAW closes; None when the long leg cannot be formed."""
    if i < long or closes[i] is None or closes[i - short] is None or closes[i - long] is None:
        return None
    if closes[i - short] == 0 or closes[i - long] == 0:
        return None
    return 0.5 * (closes[i] / closes[i - short] - 1.0) + 0.5 * (closes[i] / closes[i - long] - 1.0)


def _rs_percentile_by_day(series: dict[str, Series], days: list[Date], short: int,
                          long: int) -> dict[Date, dict[str, float]]:
    """Cross-sectional RS percentile per day: for each day rank every symbol's trailing raw RS through
    the real `rs_percentiles` (whole-tape ranking, the calibration-relevant convention). PIT: each
    symbol's trailing index is the count of its bars dated <= the day, minus one."""
    pos = {s: {d: k for k, d in enumerate(ser.dates)} for s, ser in series.items()}
    out: dict[Date, dict[str, float]] = {}
    for d in days:
        raw: dict[str, float | None] = {}
        for s, ser in series.items():
            i = pos[s].get(d)
            raw[s] = _rs_raw(ser.closes, i, short, long) if i is not None else None
        out[d] = rs_percentiles(raw)
    return out


def _rvol(vols: list, i: int, window: int) -> float | None:
    """today_vol / mean(the `window` vols strictly BEFORE today) — mirrors universe._trailing_rvol."""
    if i < window or vols[i] is None:
        return None
    win = [v for v in vols[i - window:i] if v is not None]
    if not win:
        return None
    avg = statistics.fmean(win)
    return vols[i] / avg if avg > 0 else None


def _cud(closes: list, i: int) -> int:
    """Trailing consecutive up-closes ending at index `i` — mirrors runner.consecutive_up_days."""
    n = 0
    for j in range(i, 0, -1):
        if closes[j] is not None and closes[j - 1] is not None and closes[j] > closes[j - 1]:
            n += 1
        else:
            break
    return n


def _snapshots(ser: Series, rs_by_day: dict[Date, dict[str, float]], rvol_window: int) -> list[StockSnapshot]:
    """Derive `ser`'s chronological `StockSnapshot` series (each field PIT-derived, trailing-only)."""
    snaps: list[StockSnapshot] = []
    for i, d in enumerate(ser.dates):
        close = ser.closes[i]
        prev = ser.closes[i - 1] if i > 0 else None
        pct = ((close - prev) / prev) if (close is not None and prev) else None
        snaps.append(StockSnapshot(
            symbol=ser.symbol, name=ser.symbol, status="gainer",
            close=close, prev_close=prev, pct_change=pct, volume=ser.vols[i],
            rvol=_rvol(ser.vols, i, rvol_window), consecutive_up_days=_cud(ser.closes, i),
            rs_percentile=rs_by_day.get(d, {}).get(ser.symbol)))
    return snaps


def _stability(seq: list[str]) -> tuple[int, int, int]:
    """(state_changes, single_day_islands, abab_points) — the same flicker triple the market-clock
    calibration prints (copied, not imported: self-contained script)."""
    changes = sum(1 for a, b in zip(seq, seq[1:]) if a != b)
    islands = sum(1 for i in range(len(seq))
                  if (i == 0 or seq[i] != seq[i - 1]) and (i == len(seq) - 1 or seq[i] != seq[i + 1]))
    abab = sum(1 for i in range(1, len(seq) - 1) if seq[i - 1] == seq[i + 1] != seq[i])
    return changes, islands, abab


@dataclass(frozen=True)
class CalibrationReport:
    n_days: int
    n_symbols: int
    stages: dict                 # stage token -> determined-read count
    determined: int              # total determined (non-abstain) reads
    warmup: int                  # abstain reads (warm-up / no close)
    climax: int                  # determined reads with climax_run=True
    exercised_symbols: int       # symbols with >= 1 determined read
    mean_changes: float
    mean_islands: float
    mean_abab: float
    start: Date | None = None
    end: Date | None = None


def calibrate(series: dict[str, Series], days: list[Date], *, rs_short: int, rs_long: int,
              rvol_window: int) -> CalibrationReport:
    """Replay `classify_stock_stage` per symbol over `days`. PIT: every derived feature and every
    classify call reads only trailing data. Pure over the source — no writes, no LLM, no keys."""
    rs_by_day = _rs_percentile_by_day(series, days, rs_short, rs_long)
    stages: Counter = Counter()
    determined = warmup = climax = 0
    per_changes: list[int] = []
    per_islands: list[int] = []
    per_abab: list[int] = []
    for ser in series.values():
        snaps = _snapshots(ser, rs_by_day, rvol_window)
        seq: list[str] = []
        for i in range(len(snaps)):
            read = classify_stock_stage(snaps[:i], snaps[i])
            if read is None:
                warmup += 1
                seq.append(_ABSTAIN)
                continue
            determined += 1
            stages[read.stage] += 1
            climax += read.climax_run
            seq.append(read.stage)
        active = seq[next((i for i, s in enumerate(seq) if s != _ABSTAIN), len(seq)):]  # drop warm-up runway
        if active:
            ch, isl, ab = _stability(active)
            per_changes.append(ch)
            per_islands.append(isl)
            per_abab.append(ab)
    return CalibrationReport(
        n_days=len(days), n_symbols=len(series), stages=dict(stages), determined=determined,
        warmup=warmup, climax=climax, exercised_symbols=len(per_changes),
        mean_changes=(statistics.fmean(per_changes) if per_changes else 0.0),
        mean_islands=(statistics.fmean(per_islands) if per_islands else 0.0),
        mean_abab=(statistics.fmean(per_abab) if per_abab else 0.0),
        start=(days[0] if days else None), end=(days[-1] if days else None))


def format_report(r: CalibrationReport, *, rs_short: int, rs_long: int, rvol_window: int) -> str:
    """Render the §1.3 stage distribution + flicker table (the calibration evidence)."""
    total = r.determined + r.warmup or 1
    det = r.determined or 1
    lit = " (LITERATURE — inert/all-base on a <252-day bed)" if rs_long >= 252 else " (bed-fitted proxy)"
    lines = [f"growth stock-clock calibration: {r.n_days} days ({r.start}..{r.end})  {r.n_symbols} symbols",
             f"windows: rs_short={rs_short} rs_long={rs_long}{lit}  rvol={rvol_window}  "
             f"(clock MIN_HISTORY=60 fixed)",
             "",
             f"reads: {r.determined} determined / {r.warmup} abstain(warm-up) of {r.determined + r.warmup}"
             f"  (abstain {r.warmup / total:.1%})",
             "", "stage distribution (of determined reads):"]
    for s in _STAGES:
        c = r.stages.get(s, 0)
        lines.append(f"  {s:16s} {c:6d}  ({c / det:5.1%})")
    lines += ["",
              f"climax_run fires:            {r.climax}/{r.determined} ({r.climax / det:.2%} of determined)",
              f"exercised symbols (>=1 read): {r.exercised_symbols}/{r.n_symbols}",
              "",
              f"per-symbol flicker (mean over exercised symbols): state_changes={r.mean_changes:.2f}  "
              f"single_day_islands={r.mean_islands:.2f}  abab_points={r.mean_abab:.2f}"]
    return "\n".join(lines)


def _load_series(source, days: list[Date]) -> dict[str, Series]:
    """Assemble each symbol's ascending OHLCV series from the store's bars/*.parquet (via SnapshotSource,
    normalized date). Trailing-only reads slice these by day downstream."""
    out: dict[str, Series] = {}
    for f in sorted((source._store.root / "bars").glob("*.parquet")):  # noqa: SLF001
        df = source.daily_bars(f.stem, days[0], days[-1]).sort_values("date").reset_index(drop=True)
        if df.empty:
            continue
        out[f.stem] = Series(
            symbol=f.stem, dates=list(df["date"]),
            closes=[float(c) if c == c else None for c in df["close"]],   # NaN -> None
            vols=[float(v) if v == v else None for v in df["volume"]])
    return out


def _snapshot_days(root: Path) -> list[Date]:
    """The captured snapshot days (chronological) — the calibration window. Mirrors the template."""
    out = []
    for f in sorted((root / "snapshot").glob("*.parquet")):
        s = f.stem
        out.append(Date(int(s[:4]), int(s[4:6]), int(s[6:8])))
    return sorted(out)


def _flag(args: list[str], name: str, default: int) -> int:
    if name in args:
        return int(args[args.index(name) + 1])
    return default


def main() -> None:
    flags = {"--rs-short", "--rs-long", "--rvol"}
    argv = sys.argv[1:]
    rs_short = _flag(argv, "--rs-short", DEF_RS_SHORT)
    rs_long = _flag(argv, "--rs-long", DEF_RS_LONG)
    rvol_window = _flag(argv, "--rvol", DEF_RVOL)
    pos = [a for i, a in enumerate(argv)
           if a not in flags and (i == 0 or argv[i - 1] not in flags)]
    if not pos:
        print(__doc__)
        raise SystemExit(2)
    root = Path(pos[0])
    source = SnapshotSource(PITStore(root))
    verify_checksums(root, fail_closed=False)             # warn — a calibration tolerates a stale window
    days = _snapshot_days(root)
    if len(pos) >= 2:
        days = [d for d in days if d >= Date.fromisoformat(pos[1])]
    if len(pos) >= 3:
        days = [d for d in days if d <= Date.fromisoformat(pos[2])]
    if not days:
        raise SystemExit(f"no captured snapshot days in {root} for the requested range")
    series = _load_series(source, days)
    report = calibrate(series, days, rs_short=rs_short, rs_long=rs_long, rvol_window=rvol_window)
    print(format_report(report, rs_short=rs_short, rs_long=rs_long, rvol_window=rvol_window))


if __name__ == "__main__":
    main()
