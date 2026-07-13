# alpha/features/earnings.py
#
# Derived, PIT-safe earnings SIGNALS (P5a; spec docs/superpowers/specs/2026-07-13-p5a-earnings-feed-design.md).
# The data layer (alpha/data/earnings.py) answers "what is KNOWABLE at as_of" — its PIT primitives already
# filter on filing_date / known_asof. This module derives the consume-path-facing signals a FUTURE
# guard/doctrine step reads (the earnings_gap_discipline.rule T-3 check, the verification-node actual leg).
#
# Every helper is default-safe: an empty calendar / no matching entry -> None or False, so wiring these in
# with no earnings feed present is byte-identical (nothing computes). The CONSUME-PATH activation (guard
# veto, per-candidate state field) is a SEPARATE later step — this module only makes the signals COMPUTABLE.
#
# Inputs are the lists returned by a source's earnings_calendar(as_of) / earnings_known(symbol, as_of) —
# ALREADY PIT-filtered by the source — so these helpers never re-open a lookahead window; they only pick
# among what was knowable.
from __future__ import annotations

from collections.abc import Iterable
from datetime import date as Date

from alpha.data.earnings import EarningsCalendarEntry, EarningsFact


def next_earnings(entries: Iterable[EarningsCalendarEntry], symbol: str,
                  as_of: Date) -> EarningsCalendarEntry | None:
    """The soonest calendar entry for `symbol` whose expected_date is on/after as_of (None if none).

    Assumes `entries` were already PIT-filtered by the source (known_asof <= as_of); among those, the
    upcoming (or today's) report is the min expected_date >= as_of."""
    upcoming = [e for e in entries if e.symbol == symbol and e.expected_date >= as_of]
    return min(upcoming, key=lambda e: e.expected_date) if upcoming else None


def days_to_earnings(entries: Iterable[EarningsCalendarEntry], symbol: str, as_of: Date) -> int | None:
    """Trading-agnostic calendar days until `symbol`'s next known report; None if no upcoming entry."""
    nxt = next_earnings(entries, symbol, as_of)
    return (nxt.expected_date - as_of).days if nxt is not None else None


def has_upcoming_earnings(entries: Iterable[EarningsCalendarEntry], symbol: str, as_of: Date,
                          within_days: int = 3) -> bool:
    """True iff `symbol` reports within [as_of, as_of+within_days]. Default within_days=3 = the doctrine's
    earnings_gap_discipline.rule (§4.5) T-3 checklist trigger."""
    d = days_to_earnings(entries, symbol, as_of)
    return d is not None and 0 <= d <= within_days


def latest_actual(facts: Iterable[EarningsFact], symbol: str, as_of: Date) -> EarningsFact | None:
    """The most recently FILED fact for `symbol` known by as_of — the verification-node 'what did they
    actually report' leg. Restatement-aware: among facts already filed, the max filing_date wins (a later
    10-K/A supersedes the original). Assumes `facts` were PIT-filtered by the source (filing_date <= as_of).
    Returns None if the name has not reported yet."""
    reported = [f for f in facts if f.symbol == symbol and f.filing_date <= as_of]
    if not reported:
        return None
    return max(reported, key=lambda f: f.filing_date)
