"""Growth theme-clock calibration: the §1.2 lifecycle distribution over a captured PIT window.

Offline, keyless. The theme-scale sibling of `scripts/calibrate_growth_clock.py`. Replays
`alpha/regime/theme_clock.py::GrowthThemeClock` day by day over the captured bars — accumulating each
group's strictly-prior `ThemeBreadthReading` history exactly as the live decide path would — and prints
the per-group AND aggregated `theme:emerging / institutional / public_laggard / exhaustion` distribution,
the abstain (warm-up / undetermined / dormant) rate, and the flicker triple
(`state_changes / single_day_islands / abab_points`) the market-clock calibration prints — flicker is the
thing a per-day classifier most needs to be checked for.

PIT: `alpha/features/theme_breadth.py::theme_breadth` is trailing-only by CONTRACT (every window closes
with date <= `day`; a future-dated row is ignored — belt-and-suspenders on the caller's AsOfGuard), so
the PIT firewall is enforced by the per-day `day` cutoff, not by a per-fetch `GuardedSource(AsOfGuard)`
wrap (which the template threads around `daily_snapshot`, a per-day read). We still load through
`SnapshotSource(PITStore)` and `verify_checksums`, matching the template's ingest.

WINDOWS (READ THIS — it is why the read is non-degenerate on a short bed). The doctrine's literature
windows are 文献值待verdict校准: `theme_breadth` defaults to a 200-day breadth MA and 126/252-day RS
legs. A ~90-trading-day capture (e.g. `./verdict_pit_broad`) CANNOT FORM ANY of them, so with the
literature defaults EVERY group's every lifecycle signal is None and the clock abstains on everything
(0% placement — inert, tells us nothing about the §1.2 phase thresholds). This script therefore defaults
to BED-FITTED windows (`--ma 40 --rs-short 21 --rs-long 42 --lookback 10`) so the clock is actually
exercised; the phase thresholds under test (`BREADTH_HIGH`, `DISPERSION_WIDE`, `EXHAUSTION_CONFIRM`, …)
are unchanged. Pass `--ma 200 --rs-short 126 --rs-long 252 --lookback 21` to reproduce the literature-
default all-abstain. The active profile is printed in the report header.

NOTE the bootstrap sector map (`alpha/data/sector_map.py::StaticSectorMap`) maps only ~140 liquid names;
the rest of a broad capture lands in the `unmapped` bucket (a large, heterogeneous non-theme — its read
is noise, flagged in the table). The mapped groups here carry 3-19 members, so per-group breadth is thin.

Usage:
  python scripts/calibrate_theme_clock.py <pit_root> [start] [end] [--ma N] [--rs-short N]
                                          [--rs-long N] [--lookback N]

  <pit_root>     a PIT store built by scripts/capture_window.py (e.g. ./verdict_pit_broad)
  [start] [end]  ISO dates (YYYY-MM-DD) narrowing the window; default = the full captured snapshot range
  --ma N         breadth MA window (default 40; literature 200 abstains on a <200-day bed)
  --rs-short N   RS short leg (default 21; literature 126)
  --rs-long N    RS long leg (default 42; literature 252)
  --lookback N   breadth_trend / rs_trend lookback (default 10; literature 21)
"""
from __future__ import annotations

import sys
from collections import Counter
from dataclasses import dataclass, field
from datetime import date as Date, datetime as DateTime
from pathlib import Path

from alpha.data.integrity_check import verify_checksums
from alpha.data.pit_store import PITStore
from alpha.data.sector_map import make_sector_map
from alpha.data.snapshot_source import SnapshotSource
from alpha.features.theme_breadth import theme_breadth
from alpha.regime.theme_clock import GrowthThemeClock, _TOKENS
from alpha.state.market import MarketState

# bed-fitted window defaults (see the WINDOWS note in the module docstring). Literature: 200/126/252/21.
DEF_MA, DEF_RS_SHORT, DEF_RS_LONG, DEF_LOOKBACK, DEF_HIGH_LOW = 40, 21, 42, 10, 63
_PHASES = tuple(_TOKENS.values())          # ("theme:emerging", "institutional", "public_laggard", "exhaustion")
_ABSTAIN = "abstain"                        # undetermined-today | warm-up (<MIN_HISTORY) | dormant


def _market_state_with_theme(reading, day: Date) -> MarketState:
    """Thread a `ThemeBreadthReading` onto an otherwise-empty `MarketState` so the read goes through the
    real `GrowthThemeClock.read(history, today)` (the additive `theme_breadth` field is all the clock
    reads; the count fields are required by the model but ignored by the theme clock)."""
    return MarketState(date=day, gainer_count=0, gap_up_count=0, loser_count=0, failed_breakout_count=0,
                       max_runner_tier=0, echelon=[], breadth_raw=0.0, theme_breadth=reading,
                       as_of=DateTime(day.year, day.month, day.day, 16, 0))


@dataclass(frozen=True)
class GroupTrace:
    """One group's per-day read sequence over the window ('abstain' or a `theme:` token per day)."""
    group: str
    member_count: int = 0        # latest determined member count (thin groups = noisy breadth)
    seq: list = field(default_factory=list)


def _stability(seq: list[str]) -> tuple[int, int, int]:
    """(state_changes, single_day_islands, abab_points) over a chronological state sequence — the same
    flicker triple `calibrate_growth_clock.py` prints (copied, not imported: self-contained script)."""
    changes = sum(1 for a, b in zip(seq, seq[1:]) if a != b)
    islands = sum(1 for i in range(len(seq))
                  if (i == 0 or seq[i] != seq[i - 1]) and (i == len(seq) - 1 or seq[i] != seq[i + 1]))
    abab = sum(1 for i in range(1, len(seq) - 1) if seq[i - 1] == seq[i + 1] != seq[i])
    return changes, islands, abab


def _trim_warmup(seq: list[str]) -> list[str]:
    """Drop the leading run of 'abstain' (pre-first-placement warm-up) so flicker measures the ACTIVE
    life of the group, not the warm-up runway; interior abstains (a phase dropping out and back) are a
    real flicker signal and kept."""
    i = 0
    while i < len(seq) and seq[i] == _ABSTAIN:
        i += 1
    return seq[i:]


def calibrate(source, sector_map, days: list[Date], *, ma: int, rs_short: int, rs_long: int,
              lookback: int) -> dict[str, GroupTrace]:
    """Replay `GrowthThemeClock` over `days`, accumulating each group's determined-reading history like
    the live path. Returns per-group traces. PIT-safe via `theme_breadth`'s trailing-only `day` cutoff
    (see the module docstring). Pure over the source — no writes, no LLM, no keys."""
    bars_by = {sym: source.daily_bars(sym, days[0], days[-1]) for sym in _bar_symbols(source)}
    clock = GrowthThemeClock()
    history: list[MarketState] = []
    traces: dict[str, GroupTrace] = {}
    for d in days:
        reading = theme_breadth(bars_by, sector_map, d, ma_window=ma, high_low_window=DEF_HIGH_LOW,
                                rs_short_window=rs_short, rs_long_window=rs_long, trend_lookback=lookback)
        state = _market_state_with_theme(reading, d)
        placed = clock.read(history, state)
        for group, gr in reading.groups.items():
            tr = traces.setdefault(group, GroupTrace(group=group, seq=[]))
            if gr.determined and gr.member_count > (tr.member_count or 0):
                traces[group] = tr = GroupTrace(group, gr.member_count, tr.seq)
            tr.seq.append(placed[group].phase if group in placed else _ABSTAIN)
        history.append(state)
    return traces


def _bar_symbols(source) -> list[str]:
    """The symbols with a bars/*.parquet in the store (the theme-breadth cross-section)."""
    return sorted(f.stem for f in (source._store.root / "bars").glob("*.parquet"))  # noqa: SLF001


def format_report(traces: dict[str, GroupTrace], days: list[Date], *, ma: int, rs_short: int,
                  rs_long: int, lookback: int) -> str:
    """Render the per-group + aggregated §1.2 distribution + flicker table (the calibration evidence)."""
    n = len(days)
    lit = " (LITERATURE — abstains on a <200-day bed)" if ma >= 200 else " (bed-fitted; see docstring)"
    lines = [f"growth theme-clock calibration: {n} days ({days[0]}..{days[-1]})  {len(traces)} groups",
             f"windows: ma={ma} rs_short={rs_short} rs_long={rs_long} lookback={lookback}{lit}",
             ""]

    agg: Counter = Counter()
    agg_changes = agg_islands = agg_abab = 0
    lines.append(f"  {'group':14s} {'n':>3s}  " + "  ".join(f"{p.split(':')[1][:6]:>6s}" for p in _PHASES)
                 + f"  {'abst':>4s}   {'chg':>3s} {'isl':>3s} {'abab':>4s}")
    for group in sorted(traces):
        tr = traces[group]
        c = Counter(tr.seq)
        agg.update(c)
        active = _trim_warmup(tr.seq)
        ch, isl, ab = _stability(active)
        agg_changes += ch
        agg_islands += isl
        agg_abab += ab
        flag = " *unmapped-noise" if group == "unmapped" else ""
        lines.append(f"  {group:14s} {tr.member_count:3d}  "
                     + "  ".join(f"{c.get(p, 0):6d}" for p in _PHASES)
                     + f"  {c.get(_ABSTAIN, 0):4d}   {ch:3d} {isl:3d} {ab:4d}{flag}")

    placements = sum(agg.get(p, 0) for p in _PHASES)
    group_days = placements + agg.get(_ABSTAIN, 0)
    denom = group_days or 1
    lines += ["", f"aggregate over {group_days} group-days ({placements} placed, "
                  f"{agg.get(_ABSTAIN, 0)} abstain = {agg.get(_ABSTAIN, 0) / denom:.1%}):"]
    pdenom = placements or 1
    for p in _PHASES:
        lines.append(f"  {p:26s} {agg.get(p, 0):5d}  ({agg.get(p, 0) / pdenom:5.1%} of placed"
                     f" | {agg.get(p, 0) / denom:5.1%} of all)")
    lines += ["",
              f"flicker (post-warm-up, summed over groups): state_changes={agg_changes}  "
              f"single_day_islands={agg_islands}  abab_points={agg_abab}"]
    return "\n".join(lines)


def _snapshot_days(root: Path) -> list[Date]:
    """The captured snapshot days (from snapshot/YYYYMMDD.parquet), chronological — the calibration
    window. Mirrors calibrate_growth_clock._snapshot_days."""
    out = []
    for f in sorted((root / "snapshot").glob("*.parquet")):
        s = f.stem
        out.append(Date(int(s[:4]), int(s[4:6]), int(s[6:8])))
    return sorted(out)


def _flag(args: list[str], name: str, default: int) -> int:
    """Tiny `--name N` parser (kept minimal, like the template's argv handling)."""
    if name in args:
        return int(args[args.index(name) + 1])
    return default


def main() -> None:
    flags = {"--ma", "--rs-short", "--rs-long", "--lookback"}
    argv = sys.argv[1:]
    ma = _flag(argv, "--ma", DEF_MA)
    rs_short = _flag(argv, "--rs-short", DEF_RS_SHORT)
    rs_long = _flag(argv, "--rs-long", DEF_RS_LONG)
    lookback = _flag(argv, "--lookback", DEF_LOOKBACK)
    pos = [a for i, a in enumerate(argv)                       # positionals: drop flags + their values
           if a not in flags and (i == 0 or argv[i - 1] not in flags)]
    if not pos:
        print(__doc__)
        raise SystemExit(2)
    root = Path(pos[0])
    source = SnapshotSource(PITStore(root))
    verify_checksums(root, fail_closed=False)                  # warn — a calibration tolerates a stale window
    days = _snapshot_days(root)
    if len(pos) >= 2:
        days = [d for d in days if d >= Date.fromisoformat(pos[1])]
    if len(pos) >= 3:
        days = [d for d in days if d <= Date.fromisoformat(pos[2])]
    if not days:
        raise SystemExit(f"no captured snapshot days in {root} for the requested range")
    traces = calibrate(source, make_sector_map(), days,
                       ma=ma, rs_short=rs_short, rs_long=rs_long, lookback=lookback)
    print(format_report(traces, days, ma=ma, rs_short=rs_short, rs_long=rs_long, lookback=lookback))


if __name__ == "__main__":
    main()
