"""P5 offerings veto swap (spec 2026-07-13-p5-consume-path-activations-design §2).

screen_decision's dilution veto becomes lifecycle-aware WHEN the offerings feed is present: an active
announce still vetoes (drops the candidate), but a withdrawn/expired shelf STOPS vetoing as of its own
process_date. When the feed is ABSENT it keeps calling has_dilution_filing (veto-forever fail-closed
default) -> byte-identical. Safety-only-tightens: the swap lifts a veto only with dated proof of closure
and never introduces a new veto on a clean name.
"""
from __future__ import annotations

from datetime import date, datetime

import pandas as pd

from alpha.data.source import FakeSource
from alpha.data.offerings import OfferingEvent
from alpha.eval.decision import Candidate, DecisionPackage
from alpha.guard.screen import screen_decision
from alpha.state.market import MarketState

_CAL = [date(2026, 6, 10), date(2026, 6, 11), date(2026, 6, 12)]


def _state(d=date(2026, 6, 12)):
    return MarketState(date=d, gainer_count=2, gap_up_count=0, loser_count=0, failed_breakout_count=0,
                       max_runner_tier=1, echelon=[], breadth_raw=1.0, sentiment_norm=0.7,
                       follow_through_rate=0.5, as_of=datetime(d.year, d.month, d.day, 16, 0))


def _bars():
    # a clean rising tape: no SSR (prior day up), no halt-then-dump (closes green).
    return {"DILUT": pd.DataFrame({"date": _CAL, "open": [10., 11., 12.], "high": [10., 11., 12.],
                                   "low": [10., 11., 12.], "close": [10., 11., 12.], "volume": [1, 1, 1]})}


def _shelf(event, process_date):
    return OfferingEvent(symbol="DILUT", offering_id="S3-001", event=event, kind="shelf",
                         process_date=process_date)


def _src(*, corp=None, offering_events=None, offerings_available=None):
    empty_corp = pd.DataFrame(columns=["symbol", "announce_date", "ex_date", "kind", "ratio"])
    return FakeSource(calendar=_CAL, bars=_bars(), snapshots={}, corp_actions_available=True,
                      corp_actions=(corp if corp is not None else empty_corp),
                      offering_events=offering_events, offerings_available=offerings_available)


def _corp_shelf(announce=date(2026, 6, 9)):
    return pd.DataFrame({"symbol": ["DILUT"], "announce_date": [announce], "ex_date": [date(2026, 6, 30)],
                         "kind": ["shelf"], "ratio": [None]})


def _pkg():
    return DecisionPackage(date=date(2026, 6, 12),
                           candidates=[Candidate(symbol="DILUT", pattern="gap_and_go", action="enter")])


def _kept(out):
    return [c.symbol for c in out.candidates]


# ── feed ABSENT: veto-forever via has_dilution_filing (unchanged / byte-identical) ───────────────
def test_feed_absent_corp_shelf_vetoes_forever():
    out = screen_decision(_pkg(), source=_src(corp=_corp_shelf()), state=_state())
    assert _kept(out) == []                                      # dropped: corp shelf -> veto-forever
    assert any("dilution" in r for r in out.key_risks)


def test_feed_absent_clean_corp_is_not_vetoed():
    out = screen_decision(_pkg(), source=_src(), state=_state())
    assert _kept(out) == ["DILUT"]                              # no dilution anywhere -> kept


# ── feed PRESENT: lifecycle-aware ────────────────────────────────────────────────────────────────
def test_feed_present_active_announce_still_vetoes():
    # an announce with no known close reduces to "active" -> still an overhang -> still dropped
    # (feed presence alone never clears an active overhang: safety-only-tightens).
    src = _src(offering_events=[_shelf("announce", date(2026, 6, 5))])
    assert _kept(screen_decision(_pkg(), source=src, state=_state())) == []


def test_feed_present_withdrawn_shelf_lifts_the_veto_as_of_the_withdrawal_date():
    events = [_shelf("announce", date(2026, 6, 5)), _shelf("withdrawn", date(2026, 6, 11))]
    # the day BEFORE the withdrawal is knowable -> still active -> vetoed ...
    before = screen_decision(_pkg(), source=_src(offering_events=events), state=_state(date(2026, 6, 10)))
    assert _kept(before) == []
    # ... on/after the withdrawal process_date -> closed -> veto LIFTS (candidate kept).
    after = screen_decision(_pkg(), source=_src(offering_events=events), state=_state(date(2026, 6, 12)))
    assert _kept(after) == ["DILUT"]


def test_feed_present_expired_shelf_also_lifts_the_veto():
    events = [_shelf("announce", date(2026, 6, 5)), _shelf("expired", date(2026, 6, 11))]
    out = screen_decision(_pkg(), source=_src(offering_events=events), state=_state(date(2026, 6, 12)))
    assert _kept(out) == ["DILUT"]


def test_feed_present_supersedes_the_corp_shelf_and_lifts_a_proven_close():
    # the SAME shelf appears in corp (veto-forever) AND the feed (announce+withdrawn). Feed present ->
    # the lifecycle view wins -> a proven withdrawal lifts what corp would have vetoed forever.
    events = [_shelf("announce", date(2026, 6, 5)), _shelf("withdrawn", date(2026, 6, 11))]
    src = _src(corp=_corp_shelf(), offering_events=events)
    assert _kept(screen_decision(_pkg(), source=src, state=_state(date(2026, 6, 12)))) == ["DILUT"]


# ── safety-only-tightens: the swap never introduces a veto on a clean name ───────────────────────
def test_feed_present_but_no_offering_for_the_name_is_not_vetoed():
    # an empty (present) offerings feed for DILUT -> is_dilution_overhang([]) is False, exactly like
    # has_dilution_filing on a clean corp -> no new veto introduced.
    src = _src(offering_events=[], offerings_available=True)
    assert _kept(screen_decision(_pkg(), source=src, state=_state())) == ["DILUT"]
