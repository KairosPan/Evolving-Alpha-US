import pytest
from pydantic import ValidationError
from datetime import date
from alpha.eval.decision import Candidate, DecisionPackage


def test_candidate_defaults_and_bounds():
    c = Candidate(symbol="RUN")
    assert c.name == "" and c.pattern == "" and c.confidence == 0.5
    with pytest.raises(ValidationError):
        Candidate(symbol="RUN", confidence=1.5)


def test_decision_package_frozen():
    d = DecisionPackage(date=date(2026, 6, 12),
                        candidates=[Candidate(symbol="RUN", pattern="gap_and_go")])
    assert d.candidates[0].symbol == "RUN" and d.no_trade_reason == ""
    with pytest.raises(ValidationError):
        d.no_trade_reason = "x"


def test_no_trade_package():
    d = DecisionPackage(date=date(2026, 6, 12), no_trade_reason="risk-off")
    assert d.candidates == [] and d.no_trade_reason == "risk-off"
