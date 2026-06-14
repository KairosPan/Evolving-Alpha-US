import pytest
from datetime import date
from alpha.eval.decision import Candidate, FillFeasibility, TabooCheck, DecisionPackage


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
