from alpha.regime.classifier import RegimeRead
from alpha.guard.veto import CandidateContext, veto


def _ok_regime():
    # a frontside, risk-on regime so NOTHING else vetoes — isolate the episode-taboo reason.
    return RegimeRead(phase="trend", confidence=0.7, frontside=True, risk_gate=0.8)


def test_episode_taboo_vetoes():
    v = veto(CandidateContext(symbol="RUN", regime=_ok_regime(), episode_taboo=True))
    assert v.vetoed is True and any("episode taboo" in r for r in v.reasons)


def test_no_taboo_no_veto():
    v = veto(CandidateContext(symbol="RUN", regime=_ok_regime(), episode_taboo=False))
    assert v.vetoed is False                                # default — nothing fires under a clean regime
