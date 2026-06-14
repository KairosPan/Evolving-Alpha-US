from alpha.regime.classifier import RegimeRead
from alpha.guard.veto import CandidateContext, veto


_RISK_ON = RegimeRead(phase="trend", confidence=0.7, frontside=True, risk_gate=0.7)
_RISK_OFF = RegimeRead(phase="washout", confidence=0.5, frontside=False, risk_gate=0.1)


def test_clean_entry_not_vetoed():
    v = veto(CandidateContext(symbol="RUN", regime=_RISK_ON))
    assert v.vetoed is False and v.reasons == []


def test_deep_risk_off_vetoes_new_entry():
    v = veto(CandidateContext(symbol="RUN", regime=_RISK_OFF))
    assert v.vetoed is True and any("risk-off" in r for r in v.reasons)


def test_backside_distribution_vetoes_new_entry():
    # distribution: backside (frontside=False) but risk_gate above the deep-risk-off threshold
    distribution = RegimeRead(phase="distribution", confidence=0.6, frontside=False, risk_gate=0.4)
    v = veto(CandidateContext(symbol="RUN", regime=distribution))
    assert v.vetoed is True and any("backside" in r for r in v.reasons)


def test_reverse_split_pending_vetoes():
    v = veto(CandidateContext(symbol="RUN", regime=_RISK_ON, reverse_split_pending=True))
    assert v.vetoed is True and any("reverse split" in r for r in v.reasons)


def test_data_flags_veto_when_set():
    for flag in ("dilution", "halt_then_dump", "going_concern", "regulatory", "ssr"):
        v = veto(CandidateContext(symbol="RUN", regime=_RISK_ON, **{flag: True}))
        assert v.vetoed is True


def test_multiple_reasons_accumulate():
    v = veto(CandidateContext(symbol="RUN", regime=_RISK_OFF, reverse_split_pending=True))
    assert v.vetoed is True and len(v.reasons) >= 2
