# alpha/features/short_squeeze.py
#
# Derived, PIT-safe short-squeeze SIGNALS (P5 consume-path activation; spec
# docs/superpowers/specs/2026-07-13-p5-consume-path-activations-design.md §1). The data layer answers
# "what is KNOWABLE at as_of" — short_interest_known filters on publication_date, float_known on
# knowable_date. This module folds those two feeds into the two StockSnapshot legs the dormant
# `short_squeeze` skill depends_on (seeds/skills.json depends_on ["short_interest", "days_to_cover"]):
#
#   days_to_cover  — rides straight from the LATEST-published FINRA observation (short-interest feed ALONE).
#   short_interest — % of float = shares_short / free_float * 100, so it needs BOTH feeds; without the float
#                    feed the denominator is missing and the leg is None (the skill stays dormant — its
#                    depends_on is unmet until short interest AND float are both live).
#
# Inputs are the lists a source's short_interest_known(symbol, as_of) / float_known(symbol, as_of) ALREADY
# PIT-filtered — so this helper never re-opens a lookahead window; it only picks among what was knowable
# (the alpha/features/earnings.py philosophy). Additive/default-off: empty short-interest list -> (None,
# None), so wiring this in with no feed present is byte-identical (nothing computes).
from __future__ import annotations

from collections.abc import Iterable
from datetime import date as Date

from alpha.data.float_shares import FloatFact, latest_known_float
from alpha.data.short_interest import ShortInterest


def short_squeeze_signals(short_records: Iterable[ShortInterest], float_records: Iterable[FloatFact],
                          symbol: str, as_of: Date) -> tuple[float | None, float | None]:
    """(short_interest %-of-float, days_to_cover) for `symbol` from the PIT-filtered FINRA short-interest
    + float record lists. days_to_cover comes from the most-recently-PUBLISHED observation; %-of-float
    also needs a positive free float from the float feed (else None). Assumes both lists were already
    PIT-filtered by the source (publication_date / knowable_date <= as_of)."""
    published = [r for r in short_records if r.symbol == symbol]
    if not published:
        return None, None
    latest = max(published, key=lambda r: r.publication_date)   # the current short position at as_of
    days_to_cover = latest.days_to_cover
    percent_of_float: float | None = None
    fl = latest_known_float(float_records, symbol, as_of)
    if fl is not None and fl.free_float and fl.free_float > 0:
        percent_of_float = latest.shares_short / fl.free_float * 100.0
    return percent_of_float, days_to_cover
