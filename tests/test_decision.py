from datetime import date
from youzi.eval.decision import Candidate, DecisionPackage


def test_candidate_and_package_frozen():
    c = Candidate(code="000001", name="甲", pattern="highest_board", confidence=0.7)
    assert c.code == "000001" and c.confidence == 0.7
    pkg = DecisionPackage(date=date(2024, 6, 27), candidates=[c])
    assert pkg.candidates[0].code == "000001" and pkg.no_trade_reason == ""
    import pytest
    from pydantic import ValidationError
    with pytest.raises(ValidationError):
        c.code = "x"                 # frozen


def test_no_trade_package():
    pkg = DecisionPackage(date=date(2024, 6, 27), no_trade_reason="退潮空仓")
    assert pkg.candidates == [] and pkg.no_trade_reason == "退潮空仓"
