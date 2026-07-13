"""P5 short-squeeze consume helper (spec 2026-07-13-p5-consume-path-activations-design §1).

`short_squeeze_signals` derives (short_interest %-of-float, days_to_cover) from the FINRA short-interest
+ float feeds' ALREADY-PIT-filtered record lists. days_to_cover rides from short-interest alone;
%-of-float needs BOTH feeds (shares_short / free_float). Missing leg -> None (the depends_on-unmet /
dormant case). The helper never re-opens a lookahead window — it only picks among what was knowable.
"""
from __future__ import annotations

from datetime import date

from alpha.data.float_shares import FloatFact
from alpha.data.short_interest import ShortInterest
from alpha.features.short_squeeze import short_squeeze_signals

_AS_OF = date(2026, 6, 12)


def _si(sym="RUN", *, shares_short=3_000_000.0, dtc=4.0, pub=date(2026, 6, 10)):
    return ShortInterest(symbol=sym, settlement_date=date(2026, 5, 31), publication_date=pub,
                         shares_short=shares_short, days_to_cover=dtc)


def _fl(sym="RUN", *, free_float=30_000_000.0, knowable=date(2026, 6, 1)):
    return FloatFact(symbol=sym, free_float=free_float, knowable_date=knowable)


def test_both_feeds_present_computes_percent_of_float_and_days_to_cover():
    pct, dtc = short_squeeze_signals([_si()], [_fl()], "RUN", _AS_OF)
    assert dtc == 4.0
    assert pct == 10.0                      # 3M / 30M * 100 = 10% of float


def test_short_interest_alone_lights_days_to_cover_but_not_percent_of_float():
    # No float feed -> the %-of-float denominator is missing -> short_interest leg None (skill dormant).
    pct, dtc = short_squeeze_signals([_si()], [], "RUN", _AS_OF)
    assert dtc == 4.0
    assert pct is None


def test_no_short_interest_records_is_all_none():
    pct, dtc = short_squeeze_signals([], [_fl()], "RUN", _AS_OF)
    assert (pct, dtc) == (None, None)


def test_picks_the_latest_published_short_interest():
    old = _si(shares_short=1_000_000.0, dtc=1.0, pub=date(2026, 5, 20))
    new = _si(shares_short=6_000_000.0, dtc=8.0, pub=date(2026, 6, 10))
    pct, dtc = short_squeeze_signals([old, new], [_fl()], "RUN", _AS_OF)
    assert dtc == 8.0                       # the most-recently-published observation
    assert pct == 20.0                      # 6M / 30M * 100


def test_picks_the_latest_knowable_float():
    stale = _fl(free_float=60_000_000.0, knowable=date(2026, 5, 1))
    fresh = _fl(free_float=30_000_000.0, knowable=date(2026, 6, 1))   # after a buyback shrank the float
    pct, _ = short_squeeze_signals([_si()], [stale, fresh], "RUN", _AS_OF)
    assert pct == 10.0                      # uses the fresh 30M float, not the stale 60M


def test_wrong_symbol_records_are_ignored():
    pct, dtc = short_squeeze_signals([_si(sym="OTHER")], [_fl(sym="OTHER")], "RUN", _AS_OF)
    assert (pct, dtc) == (None, None)


def test_zero_float_never_divides_by_zero():
    pct, dtc = short_squeeze_signals([_si()], [_fl(free_float=0.0)], "RUN", _AS_OF)
    assert pct is None                      # guarded: no % without a positive float
    assert dtc == 4.0


def test_days_to_cover_none_passes_through_as_none():
    pct, dtc = short_squeeze_signals([_si(dtc=None)], [_fl()], "RUN", _AS_OF)
    assert dtc is None                      # FINRA gave no avg-daily-volume -> dtc missing -> skill dormant
    assert pct == 10.0
