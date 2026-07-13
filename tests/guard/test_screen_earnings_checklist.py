"""P5b — earnings consume-path activation (spec 2026-07-13-p5b-earnings-consume-design).

The P5a feed left the T-3 checklist gate dormant. This file pins the co-pilot activation:
screen_decision surfaces the §4.5 `earnings_gap_discipline` checklist requirement into key_risks for
a KEPT new-entry candidate reporting within T-3 (warn-the-human, NOT a veto — the checklist's
completeness is a human/LLM judgment the guard cannot make; rationale in the spec). Additive /
default-off: no earnings feed -> byte-identical, no note.
"""
from datetime import date, datetime

import pandas as pd

from alpha.data.earnings import EarningsCalendarEntry
from alpha.eval.decision import Candidate, DecisionPackage
from alpha.guard.screen import earnings_checklist_note, screen_decision
from alpha.state.market import MarketState

_DAY = date(2026, 6, 12)


def _state(d=_DAY, *, sn=0.7, ft=0.5):
    return MarketState(date=d, gainer_count=2, gap_up_count=0, loser_count=0,
                       failed_breakout_count=0, max_runner_tier=1, echelon=[], breadth_raw=1.0,
                       sentiment_norm=sn, follow_through_rate=ft,
                       as_of=datetime(d.year, d.month, d.day, 16, 0))


def _cal_entry(sym, expected, *, known=date(2026, 6, 1)):
    return EarningsCalendarEntry(symbol=sym, expected_date=expected, known_asof=known)


def _src(*, earnings_calendar=None, earnings_available=None):
    """A rising 'CLEAN' gainer (frontside, no SSR/halt), corp present-and-empty so the ONLY variable
    under test is the earnings feed. earnings_calendar=None -> feed absent (default-off)."""
    from alpha.data.source import FakeSource
    cal = [date(2026, 6, 10), date(2026, 6, 11), date(2026, 6, 12)]
    bars = {"CLEAN": pd.DataFrame({"date": cal, "open": [10., 11., 12.], "high": [10., 11., 12.],
                                   "low": [10., 11., 12.], "close": [10., 11., 12.], "volume": [1, 1, 1]})}
    empty_corp = pd.DataFrame(columns=["symbol", "announce_date", "ex_date", "kind", "ratio"])
    return FakeSource(calendar=cal, bars=bars, snapshots={}, corp_actions=empty_corp,
                      corp_actions_available=True, earnings_calendar=earnings_calendar,
                      earnings_available=earnings_available)


def _pkg(*symbols, action="enter"):
    return DecisionPackage(date=_DAY,
                           candidates=[Candidate(symbol=s, pattern="gap_and_go", action=action)
                                       for s in symbols])


# ── (a) present feed + within T-3 -> the checklist note ─────────────────────────────────────────
def test_within_t3_new_entry_surfaces_the_checklist_note_and_keeps_the_candidate():
    src = _src(earnings_calendar=[_cal_entry("CLEAN", date(2026, 6, 15))])   # 3 days out
    out = screen_decision(_pkg("CLEAN"), source=src, state=_state())
    assert [c.symbol for c in out.candidates] == ["CLEAN"]        # warn, not veto — candidate kept
    note = earnings_checklist_note("CLEAN", 3)
    assert note in out.key_risks
    assert sum(r == note for r in out.key_risks) == 1            # once per candidate


# ── (b) no earnings feed -> byte-identical, no note ─────────────────────────────────────────────
def test_no_earnings_feed_is_byte_identical_no_note():
    out = screen_decision(_pkg("CLEAN"), source=_src(), state=_state())
    assert [c.symbol for c in out.candidates] == ["CLEAN"]
    assert out.key_risks == []                                   # byte-identical to the pre-P5b path


def test_feed_present_but_not_within_t3_has_no_note():
    src = _src(earnings_calendar=[_cal_entry("CLEAN", date(2026, 6, 30))])   # far out
    out = screen_decision(_pkg("CLEAN"), source=src, state=_state())
    assert out.key_risks == []


def test_feed_present_but_no_entry_for_the_symbol_has_no_note():
    src = _src(earnings_calendar=[_cal_entry("OTHER", date(2026, 6, 13))])
    out = screen_decision(_pkg("CLEAN"), source=src, state=_state())
    assert out.key_risks == []


# ── (c) verdict-neutral at the guard level (candidates/regime unchanged by the note) ────────────
def test_note_is_verdict_neutral_scoring_input():
    noted = screen_decision(_pkg("CLEAN"),
                            source=_src(earnings_calendar=[_cal_entry("CLEAN", date(2026, 6, 15))]),
                            state=_state())
    plain = screen_decision(_pkg("CLEAN"), source=_src(), state=_state())
    assert [c.symbol for c in noted.candidates] == [c.symbol for c in plain.candidates]
    assert noted.regime == plain.regime                          # only key_risks differs


# ── (e) exact boundary: day 3 in, day 4 out ─────────────────────────────────────────────────────
def test_t3_boundary_day3_in_day4_out():
    in3 = screen_decision(_pkg("CLEAN"),
                          source=_src(earnings_calendar=[_cal_entry("CLEAN", date(2026, 6, 15))]),
                          state=_state())                         # 15 - 12 = 3 -> in
    out4 = screen_decision(_pkg("CLEAN"),
                           source=_src(earnings_calendar=[_cal_entry("CLEAN", date(2026, 6, 16))]),
                           state=_state())                        # 16 - 12 = 4 -> out
    assert earnings_checklist_note("CLEAN", 3) in in3.key_risks
    assert out4.key_risks == []


def test_reports_today_t0_still_notes():
    src = _src(earnings_calendar=[_cal_entry("CLEAN", _DAY)])     # d = 0
    out = screen_decision(_pkg("CLEAN"), source=src, state=_state())
    assert earnings_checklist_note("CLEAN", 0) in out.key_risks


# ── gating edges: vetoed / trim-exit within T-3 -> no note ──────────────────────────────────────
def test_within_t3_but_vetoed_for_another_reason_is_dropped_with_no_earnings_note():
    # a genuine reverse-split veto drops CLEAN; there is no kept entry to warn about.
    corp = pd.DataFrame({"symbol": ["CLEAN"], "announce_date": [date(2026, 6, 9)],
                         "ex_date": [date(2026, 6, 20)], "kind": ["reverse_split"], "ratio": [0.1]})
    from alpha.data.source import FakeSource
    cal = [date(2026, 6, 10), date(2026, 6, 11), date(2026, 6, 12)]
    bars = {"CLEAN": pd.DataFrame({"date": cal, "open": [10., 11., 12.], "high": [10., 11., 12.],
                                   "low": [10., 11., 12.], "close": [10., 11., 12.], "volume": [1, 1, 1]})}
    src = FakeSource(calendar=cal, bars=bars, snapshots={}, corp_actions=corp,
                     corp_actions_available=True,
                     earnings_calendar=[_cal_entry("CLEAN", date(2026, 6, 13))])
    out = screen_decision(_pkg("CLEAN"), source=src, state=_state())
    assert out.candidates == []                                  # the reverse-split veto still fires
    assert not any("earnings" in r for r in out.key_risks)       # no earnings note for a dropped candidate


def test_trim_exit_within_t3_gets_no_note():
    src = _src(earnings_calendar=[_cal_entry("CLEAN", date(2026, 6, 13))])
    out = screen_decision(_pkg("CLEAN", action="trim"), source=src, state=_state())
    assert [c.symbol for c in out.candidates] == ["CLEAN"]       # trim passes through unvetoed
    assert out.key_risks == []                                   # reducing exposure into earnings isn't a warn


def test_present_but_empty_calendar_has_no_note():
    # feed marked present (earnings_available True) but zero entries -> no name is within T-3.
    src = _src(earnings_calendar=[], earnings_available=True)
    out = screen_decision(_pkg("CLEAN"), source=src, state=_state())
    assert out.key_risks == []
