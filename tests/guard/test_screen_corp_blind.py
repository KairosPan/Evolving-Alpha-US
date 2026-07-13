"""P3 — corp-actions tri-state guard-blind fix (spec 2026-07-13-p3-corp-actions-tristate-design).

When a captured window has no corp_actions.parquet, the reverse-split / dilution guard flags compute
False just as they would on a genuinely clean (present-but-empty) window — the guard runs blind and
nothing says so. This file pins the co-pilot fix: screen_decision surfaces the MISSING case into
key_risks as a self-describing note (warn-the-human, NOT a new veto), once per package, and does NOT
emit it when the artifact is present (empty or with rows) — the acceptance gate's core distinction.
"""
from datetime import date, datetime

import pandas as pd

from alpha.data.source import FakeSource
from alpha.eval.decision import Candidate, DecisionPackage
from alpha.guard.screen import CORP_BLIND_NOTE, GuardedPolicy, screen_decision
from alpha.state.market import MarketState
from alpha.universe.universe import CandidateUniverse

_EMPTY_CORP = pd.DataFrame(columns=["symbol", "announce_date", "ex_date", "kind", "ratio"])


def _state(d=date(2026, 6, 12), *, sn=0.7, ft=0.5):
    return MarketState(date=d, gainer_count=2, gap_up_count=0, loser_count=0,
                       failed_breakout_count=0, max_runner_tier=1, echelon=[], breadth_raw=1.0,
                       sentiment_norm=sn, follow_through_rate=ft,
                       as_of=datetime(d.year, d.month, d.day, 16, 0))


def _src(*, corp_available: bool, corp=None):
    """A rising 'CLEAN' gainer (frontside, no SSR). corp availability + frame content set explicitly."""
    cal = [date(2026, 6, 10), date(2026, 6, 11), date(2026, 6, 12)]
    bars = {"CLEAN": pd.DataFrame({"date": cal, "open": [10., 11., 12.], "high": [10., 11., 12.],
                                   "low": [10., 11., 12.], "close": [10., 11., 12.], "volume": [1, 1, 1]})}
    return FakeSource(calendar=cal, bars=bars, snapshots={}, corp_actions=corp,
                      corp_actions_available=corp_available)


def _pkg(*symbols, action="enter"):
    return DecisionPackage(date=date(2026, 6, 12),
                           candidates=[Candidate(symbol=s, pattern="gap_and_go", action=action)
                                       for s in symbols])


def test_missing_corp_artifact_surfaces_blind_note_but_keeps_the_candidate():
    out = screen_decision(_pkg("CLEAN"), source=_src(corp_available=False), state=_state())
    assert [c.symbol for c in out.candidates] == ["CLEAN"]            # warn, not veto — clean name kept
    assert CORP_BLIND_NOTE in out.key_risks
    assert sum(r == CORP_BLIND_NOTE for r in out.key_risks) == 1      # once per package, not per candidate


def test_present_but_empty_corp_artifact_has_no_blind_note():
    out = screen_decision(_pkg("CLEAN"), source=_src(corp_available=True, corp=_EMPTY_CORP), state=_state())
    assert [c.symbol for c in out.candidates] == ["CLEAN"]
    assert out.key_risks == []                                       # byte-identical to the pre-fix clean path


def test_missing_and_present_empty_are_distinguishable_both_directions():
    # THE acceptance gate: the same candidate/state yields the note iff the artifact is MISSING.
    miss = screen_decision(_pkg("CLEAN"), source=_src(corp_available=False), state=_state())
    pres = screen_decision(_pkg("CLEAN"), source=_src(corp_available=True, corp=_EMPTY_CORP), state=_state())
    assert CORP_BLIND_NOTE in miss.key_risks
    assert CORP_BLIND_NOTE not in pres.key_risks


def test_present_corp_with_rows_still_vetoes_and_emits_no_blind_note():
    corp = pd.DataFrame({"symbol": ["CLEAN"], "announce_date": [date(2026, 6, 9)],
                         "ex_date": [date(2026, 6, 20)], "kind": ["reverse_split"], "ratio": [0.1]})
    out = screen_decision(_pkg("CLEAN"), source=_src(corp_available=True, corp=corp), state=_state())
    assert out.candidates == []                                      # the real reverse-split veto still fires
    assert any("reverse split" in r for r in out.key_risks)
    assert CORP_BLIND_NOTE not in out.key_risks


def test_no_blind_note_when_package_has_no_enter_candidate():
    # missing corp, but the package only trims/exits -> the new-entry corp veto was never consulted,
    # so there is no blind entry decision to warn about.
    out = screen_decision(_pkg("CLEAN", action="trim"), source=_src(corp_available=False), state=_state())
    assert CORP_BLIND_NOTE not in out.key_risks


def test_blind_note_propagates_through_guarded_policy():
    class _Stub:
        def decide(self, state, universe):
            return _pkg("CLEAN")
    gp = GuardedPolicy(_Stub(), _src(corp_available=False))
    out = gp.decide(_state(), CandidateUniverse.from_stocks([]))
    assert CORP_BLIND_NOTE in out.key_risks


def test_note_is_verdict_neutral_scoring_input():
    # the note lives in key_risks; eval scoring reads candidates + returns, never key_risks. Pin that a
    # package carrying the note is otherwise identical to the same package without it (same candidates).
    blind = screen_decision(_pkg("CLEAN"), source=_src(corp_available=False), state=_state())
    clean = screen_decision(_pkg("CLEAN"), source=_src(corp_available=True, corp=_EMPTY_CORP), state=_state())
    assert [c.symbol for c in blind.candidates] == [c.symbol for c in clean.candidates]
    assert blind.regime == clean.regime
