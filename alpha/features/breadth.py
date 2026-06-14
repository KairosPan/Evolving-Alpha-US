from __future__ import annotations

from alpha.universe.universe import CandidateUniverse


def counts(universe: CandidateUniverse) -> tuple[int, int, int]:
    """(gainer_count, gap_up_count, loser_count) by snapshot status."""
    return (len(universe.by_status("gainer")), len(universe.by_status("gap_up")),
            len(universe.by_status("loser")))


def failed_breakout_count(universe: CandidateUniverse) -> int:
    """Gapped up (gap_pct>0) but closed red (close < prev_close) — the 炸板 analog."""
    n = 0
    for s in universe.all():
        if (s.gap_pct is not None and s.gap_pct > 0 and s.close is not None
                and s.prev_close is not None and s.close < s.prev_close):
            n += 1
    return n


def gap_and_go_count(universe: CandidateUniverse) -> int:
    """Gainers that gapped up and held (status gainer with gap_pct>0) — the 弱转强 daily proxy."""
    return sum(1 for s in universe.by_status("gainer") if s.gap_pct is not None and s.gap_pct > 0)


def follow_through_rate(universe: CandidateUniverse, prev_gainers: frozenset[str]) -> float | None:
    """Fraction of yesterday's gainers that are gainers again today (risk-on/off effect).
    None when there were no prior gainers (undefined)."""
    if not prev_gainers:
        return None
    today = {s.symbol for s in universe.by_status("gainer")}
    return len(today & prev_gainers) / len(prev_gainers)
