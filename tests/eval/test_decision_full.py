import pytest
from datetime import date
from alpha.eval.decision import Candidate, FillFeasibility, TabooCheck, DecisionPackage, Portfolio


def test_minimal_candidate_still_valid_backward_compat():
    c = Candidate(symbol="RUN", pattern="gap_and_go")     # US-1d-style
    assert c.skill_id == "" and c.size_tier is None and c.fill_feasibility is None
    assert c.taboo_check == [] and c.family == ""


def test_full_candidate():
    c = Candidate(symbol="RUN", name="Runner", pattern="gap_and_go", skill_id="gap_and_go",
                  family="runner", entry="buy ORB-high reclaim", exit_stop="lose VWAP",
                  size_tier="core", confidence=0.7,
                  fill_feasibility=FillFeasibility(buyable=True, reason="liquid open"),
                  taboo_check=[TabooCheck(rule="no-chase-risk-off", status="pass")],
                  counterview="if AI line flips backside, drop")
    assert c.size_tier == "core" and c.fill_feasibility.buyable is True
    assert c.taboo_check[0].status == "pass" and c.family == "runner"


def test_size_tier_must_be_valid():
    with pytest.raises(Exception):
        Candidate(symbol="RUN", size_tier="enormous")     # not a SizeTier literal


def test_minimal_decision_package_backward_compat():
    d = DecisionPackage(date=date(2026, 6, 12))            # US-1d-style
    assert d.key_risks == [] and d.portfolio is None and d.human_confirm is None
    assert d.as_of is None and d.regime is None           # §4.1 fields default for backward-compat


def test_full_decision_package():
    d = DecisionPackage(date=date(2026, 6, 12),
                        candidates=[Candidate(symbol="RUN", pattern="gap_and_go", family="runner")],
                        no_trade_reason="", regime_read="trend, frontside",
                        key_risks=["AI leader rolls over"],
                        portfolio=Portfolio(total_exposure_budget=0.6, correlated_groups=[["RUN", "AI2"]]),
                        human_confirm=None)
    assert d.portfolio.total_exposure_budget == 0.6
    assert d.portfolio.correlated_groups == [["RUN", "AI2"]]
    assert d.key_risks == ["AI leader rolls over"]


def test_structured_regime_and_as_of_round_trip():
    from datetime import datetime
    from alpha.regime.classifier import RegimeRead
    d = DecisionPackage(date=date(2026, 6, 12), as_of=datetime(2026, 6, 12, 16, 0),
                        regime=RegimeRead(phase="trend", confidence=0.7, frontside=True, risk_gate=0.6))
    again = DecisionPackage.model_validate(d.model_dump())
    assert again.regime.phase == "trend" and again.regime.risk_gate == 0.6
    assert again.as_of == datetime(2026, 6, 12, 16, 0)
