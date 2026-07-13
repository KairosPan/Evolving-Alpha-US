"""FloatFact model + source-agnostic PIT primitives (P5b float feed; spec
2026-07-13-p5b-float-feed-design.md). PIT key = knowable_date (the disclosure/filing/effective date the
float figure became knowable); as_of_period is INFORMATIONAL — keying on it would leak the filing lag."""
from datetime import date

import pandas as pd

from alpha.data.float_shares import (
    FloatFact,
    float_from_frame,
    float_to_frame,
    known_float,
    latest_known_float,
)


def _fact(sym="ACME", free_float=8_000_000.0, knowable=date(2026, 5, 1), period=date(2026, 3, 31), **kw):
    return FloatFact(symbol=sym, free_float=free_float, knowable_date=knowable, as_of_period=period, **kw)


def test_known_float_filters_on_knowable_date_not_period():
    # a figure MEASURED as of the quarter-end (period) but DISCLOSED later is invisible until disclosure
    facts = [_fact(knowable=date(2026, 5, 1), period=date(2026, 3, 31))]
    assert known_float(facts, date(2026, 4, 15)) == []          # measured 3/31 but not knowable until 5/1
    assert known_float(facts, date(2026, 5, 1)) == facts        # knowable exactly on disclosure day
    # keying on as_of_period would (wrongly) admit it on 4/15 -> the filing-lag leak this guards against


def test_latest_known_float_picks_most_recent_revision():
    # a fresh count each quarter + an intra-quarter revision after a secondary; latest-knowable wins
    q1 = _fact(free_float=8_000_000.0, knowable=date(2026, 5, 1))
    secondary = _fact(free_float=12_000_000.0, knowable=date(2026, 6, 20))   # float grew after an offering
    facts = [q1, secondary]
    assert latest_known_float(facts, "ACME", date(2026, 6, 1)).free_float == 8_000_000.0    # only q1 knowable
    assert latest_known_float(facts, "ACME", date(2026, 6, 20)).free_float == 12_000_000.0  # revision knowable
    assert latest_known_float(facts, "OTHER", date(2026, 6, 20)) is None                    # symbol filter
    assert latest_known_float(facts, "ACME", date(2026, 1, 1)) is None                      # nothing knowable yet


def test_float_frame_roundtrip():
    facts = [_fact(free_float=8_000_000.0, shares_outstanding=10_000_000.0, restricted_shares=2_000_000.0,
                   source="vendor"),
             _fact(sym="BETA", free_float=None if False else 5_000_000.0, period=None)]
    back = float_from_frame(float_to_frame(facts))
    assert [f.symbol for f in back] == ["ACME", "BETA"]
    assert back[0].free_float == 8_000_000.0 and back[0].shares_outstanding == 10_000_000.0
    assert back[0].knowable_date == date(2026, 5, 1)
    assert back[1].as_of_period is None                        # None period survives the round-trip (not NaT)


def test_float_from_frame_empty():
    assert float_from_frame(None) == []
    assert float_from_frame(pd.DataFrame()) == []
