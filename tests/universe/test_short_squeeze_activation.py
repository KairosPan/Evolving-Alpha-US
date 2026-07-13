"""P5 short-squeeze activation (spec 2026-07-13-p5-consume-path-activations-design §1).

build_universe populates StockSnapshot.short_interest (% of float) + .days_to_cover from the FINRA
short-interest + float feeds, PIT-keyed, so the dormant `short_squeeze` skill's depends_on
(["short_interest", "days_to_cover"]) is satisfied and the skill surfaces to the agent. Additive /
default-off: no feeds -> fields stay None -> depends_on unmet -> byte-identical to the pre-P5 build.
"""
from __future__ import annotations

from datetime import date

import pandas as pd

from alpha.agent.prompt import available_data_signals
from alpha.data.firewall import AsOfGuard
from alpha.data.float_shares import FloatFact
from alpha.data.short_interest import ShortInterest
from alpha.data.source import FakeSource, GuardedSource
from alpha.harness.skill import Skill
from alpha.universe.universe import build_universe

_DAY = date(2026, 6, 12)
_CAL = [date(2026, 6, 10), date(2026, 6, 11), date(2026, 6, 12)]

_SQUEEZE = Skill(skill_id="short_squeeze", name="Short Squeeze", type="pattern",
                 depends_on=["short_interest", "days_to_cover"])


def _source(*, short_interest=None, float_facts=None):
    """RUN gaps +21% -> a screened gainer. The feeds are optional (default absent = default-off)."""
    bars = {"RUN": pd.DataFrame({"date": _CAL, "open": [14., 15., 16.], "high": [14., 15., 18.],
                                 "low": [13., 14., 15.], "close": [14., 15., 17.],
                                 "volume": [1_000_000, 1_000_000, 5_000_000]})}
    snap = pd.DataFrame({"symbol": ["RUN"], "name": ["Runner Inc"], "open": [16.0], "high": [18.0],
                         "low": [15.0], "close": [17.0], "volume": [5_000_000], "prev_close": [14.0]})
    return FakeSource(calendar=_CAL, bars=bars, snapshots={_DAY: snap},
                      short_interest=short_interest, float_facts=float_facts)


def _guarded(src):
    return GuardedSource(src, AsOfGuard(_DAY))


def _si(pub=date(2026, 6, 10)):
    return ShortInterest(symbol="RUN", settlement_date=date(2026, 5, 31), publication_date=pub,
                         shares_short=3_000_000.0, days_to_cover=4.0)


def _fl(knowable=date(2026, 6, 1)):
    return FloatFact(symbol="RUN", free_float=30_000_000.0, knowable_date=knowable)


# ── both feeds present -> the skill activates ───────────────────────────────────────────────────
def test_both_feeds_populate_the_squeeze_legs_and_activate_the_skill():
    uni = build_universe(_guarded(_source(short_interest=[_si()], float_facts=[_fl()])), _DAY)
    run = uni.get("RUN")
    assert run.days_to_cover == 4.0
    assert run.short_interest == 10.0                     # 3M / 30M * 100
    signals = available_data_signals(uni)
    assert {"short_interest", "days_to_cover"} <= signals
    assert set(_SQUEEZE.depends_on) <= signals            # depends_on satisfied -> skill surfaces


# ── short-interest alone: days_to_cover lights, %-of-float does not -> skill still dormant ───────
def test_short_interest_without_float_leaves_the_skill_dormant():
    uni = build_universe(_guarded(_source(short_interest=[_si()])), _DAY)
    run = uni.get("RUN")
    assert run.days_to_cover == 4.0
    assert run.short_interest is None                     # no float feed -> no %-of-float denominator
    assert not (set(_SQUEEZE.depends_on) <= available_data_signals(uni))   # depends_on unmet


# ── default-off: no feeds -> byte-identical (fields None, skill dormant) ─────────────────────────
def test_no_feeds_is_byte_identical_and_dormant():
    uni = build_universe(_guarded(_source()), _DAY)
    run = uni.get("RUN")
    assert run.short_interest is None and run.days_to_cover is None
    assert not (set(_SQUEEZE.depends_on) <= available_data_signals(uni))


# ── PIT: a short-interest observation published AFTER as_of is invisible ─────────────────────────
def test_future_published_short_interest_is_invisible_pit():
    late = _si(pub=date(2026, 6, 20))                     # published after _DAY
    uni = build_universe(_guarded(_source(short_interest=[late], float_facts=[_fl()])), _DAY)
    run = uni.get("RUN")
    assert run.short_interest is None and run.days_to_cover is None   # not yet knowable at as_of
