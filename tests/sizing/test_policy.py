"""L3 sizing decorator: size_decision assigns a per-candidate size_tier (confidence x regime risk_gate)
and attaches the Portfolio plan; SizingPolicy wraps any policy. Verdict-neutral — sizing never touches
scoring (proven in tests/eval/test_l3_sizing_acceptance.py)."""
from datetime import date, datetime
from alpha.eval.decision import Candidate, DecisionPackage
from alpha.regime.classifier import RegimeRead
from alpha.sizing.policy import SizingPolicy, size_decision
from alpha.state.market import MarketState
from alpha.universe.universe import CandidateUniverse

CUR = date(2026, 6, 12)


def _state(**kw):
    return MarketState(date=CUR, gainer_count=1, gap_up_count=0, loser_count=0, failed_breakout_count=0,
                       max_runner_tier=0, echelon=[], breadth_raw=1.0, sentiment_norm=None,
                       as_of=datetime(2026, 6, 12, 16, 0), **kw)


def _pkg(*cands, regime=None):
    return DecisionPackage(date=CUR, candidates=list(cands), regime=regime)


def test_size_decision_assigns_tier_from_confidence_and_risk_gate():
    # risk_gate=0.8, confidence=0.9 -> score 0.72 -> 'heavy'; confidence=0.4 -> 0.32 -> 'probe'
    regime = RegimeRead(phase="trend", confidence=0.7, frontside=True, risk_gate=0.8)
    out = size_decision(_pkg(Candidate(symbol="RUN", confidence=0.9),
                             Candidate(symbol="LAG", confidence=0.4), regime=regime), state=_state())
    tiers = {c.symbol: c.size_tier for c in out.candidates}
    assert tiers == {"RUN": "heavy", "LAG": "probe"}
    assert out.portfolio is not None
    assert out.portfolio.total_exposure_budget == 0.8 * 4.0          # risk_gate x max_total_exposure


def test_size_decision_falls_back_to_gcycle_when_regime_absent():
    # no regime on the package (screen off) -> size_decision computes GCycle().read(state) itself
    out = size_decision(_pkg(Candidate(symbol="RUN", confidence=0.9)), state=_state())
    assert out.candidates[0].size_tier in {"flat", "probe", "core", "heavy"}
    assert out.portfolio is not None


def test_size_decision_nets_same_narrative_to_one_bet():
    # the narrative key now comes from candidate.narrative (set by the agent), activating L3 netting
    regime = RegimeRead(phase="trend", confidence=0.7, frontside=True, risk_gate=0.9)
    out = size_decision(_pkg(
        Candidate(symbol="GPUX", confidence=0.9, narrative="ai-compute"),
        Candidate(symbol="CHPS", confidence=0.9, narrative="ai-compute"),
        Candidate(symbol="SOLO", confidence=0.9, narrative=""), regime=regime), state=_state())
    assert out.portfolio.correlated_groups == [["CHPS", "GPUX"]]      # the two ai-compute names = one bet
    # netted: ai-compute (one bet, heavy=1.0) + SOLO (heavy=1.0) = 2.0, NOT 3.0
    assert out.portfolio.total_exposure == 2.0
    assert out.portfolio.capped is False


def test_size_decision_distinct_narratives_do_not_net():
    regime = RegimeRead(phase="trend", confidence=0.7, frontside=True, risk_gate=0.9)
    out = size_decision(_pkg(Candidate(symbol="A", confidence=0.9, narrative="x"),
                             Candidate(symbol="B", confidence=0.9, narrative="y"), regime=regime),
                        state=_state())
    assert out.portfolio.correlated_groups == []                     # different themes -> two bets
    assert out.portfolio.total_exposure == 2.0                       # 1.0 + 1.0


def test_sizing_policy_sizes_inner_decision():
    class _Stub:
        def decide(self, state, universe):
            return _pkg(Candidate(symbol="RUN", confidence=0.9),
                        regime=RegimeRead(phase="trend", confidence=0.7, frontside=True, risk_gate=0.9))
    out = SizingPolicy(_Stub()).decide(_state(), CandidateUniverse.from_stocks([]))
    assert out.candidates[0].size_tier == "heavy"                    # 0.9 x 0.9 = 0.81 -> heavy


# ── P0.6 trim-derisk action vocabulary (spec 2026-07-13-p06) ────────────────────────────────────
# Candidate now carries `action` directly (spec 2026-07-13-p05 §7), so these construct it inline.

def test_size_decision_trim_caps_tier_at_core_and_excludes_from_exposure():
    regime = RegimeRead(phase="trend", confidence=0.7, frontside=True, risk_gate=0.9)
    out = size_decision(_pkg(
        Candidate(symbol="HELD", confidence=0.9, action="trim"),   # would size heavy -> capped core
        Candidate(symbol="NEW", confidence=0.9, action="enter"),   # a real new bet
        regime=regime), state=_state())
    tiers = {c.symbol: c.size_tier for c in out.candidates}
    assert tiers == {"HELD": "core", "NEW": "heavy"}
    # only the `enter` name is a new bet -> exposure counts NEW alone (1.0), not the trimmed HELD
    assert out.portfolio.total_exposure == 1.0


def test_size_decision_exit_goes_flat_and_adds_no_exposure():
    regime = RegimeRead(phase="trend", confidence=0.7, frontside=True, risk_gate=0.9)
    out = size_decision(_pkg(Candidate(symbol="GONE", confidence=0.9, action="exit"),
                             regime=regime), state=_state())
    assert out.candidates[0].size_tier == "flat"
    assert out.portfolio.total_exposure == 0.0                        # nothing entered


def test_size_decision_byte_identical_when_all_enter():
    # explicit annotation present but action=enter everywhere -> same as a plain Candidate package
    regime = RegimeRead(phase="trend", confidence=0.7, frontside=True, risk_gate=0.8)
    plain = size_decision(_pkg(Candidate(symbol="RUN", confidence=0.9),
                               Candidate(symbol="LAG", confidence=0.4), regime=regime), state=_state())
    annotated = size_decision(_pkg(Candidate(symbol="RUN", confidence=0.9, action="enter"),
                                   Candidate(symbol="LAG", confidence=0.4, action="enter"),
                                   regime=regime), state=_state())
    assert {c.symbol: c.size_tier for c in plain.candidates} == {c.symbol: c.size_tier for c in annotated.candidates}
    assert plain.portfolio == annotated.portfolio


def test_sizing_annotations_are_verdict_neutral():
    # scoring reads only symbol/pattern + forward returns; size_tier/action never enter the score
    from alpha.eval.scorer import PoolScorer
    from alpha.eval.oracle import DayMembership
    from datetime import date as _date
    regime = RegimeRead(phase="trend", confidence=0.7, frontside=True, risk_gate=0.9)
    plain = size_decision(_pkg(Candidate(symbol="RUN", confidence=0.9),
                               Candidate(symbol="LAG", confidence=0.6), regime=regime), state=_state())
    annotated = size_decision(_pkg(Candidate(symbol="RUN", confidence=0.9, action="trim"),
                                   Candidate(symbol="LAG", confidence=0.6, action="exit"),
                                   regime=regime), state=_state())
    dmem = DayMembership(gainers=frozenset({"RUN"}), losers=frozenset())
    emem = DayMembership(gainers=frozenset({"RUN"}), losers=frozenset({"LAG"}))
    kw = dict(decision_mem=dmem, exit_mem=emem, entry_day=CUR, exit_day=_date(2026, 6, 16), oracle=None)
    sp = PoolScorer()
    assert ({s: c.score for s, c in sp.score_step(plain, **kw).items()}
            == {s: c.score for s, c in sp.score_step(annotated, **kw).items()})
