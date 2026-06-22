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
