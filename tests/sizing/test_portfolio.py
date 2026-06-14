from alpha.sizing.correlation import Pick
from alpha.sizing.portfolio import plan_portfolio, PortfolioPlan
from alpha.sizing.position import SizingConfig


def test_per_pick_tier_assigned():
    plan = plan_portfolio([Pick("RUN", "ai", 0.9)], risk_gate=0.9, config=SizingConfig())
    assert isinstance(plan, PortfolioPlan)
    assert plan.sized[0].symbol == "RUN" and plan.sized[0].size_tier == "heavy"


def test_same_narrative_nets_to_one_bet():
    # two AI names, both heavy (weight 1.0 each). Netted = ONE bet at the max weight (1.0), not 2.0.
    plan = plan_portfolio([Pick("AI1", "ai", 0.9), Pick("AI2", "ai", 0.9)],
                          risk_gate=1.0, config=SizingConfig())
    assert plan.correlated_groups == [["AI1", "AI2"]]
    assert plan.total_exposure == 1.0                 # one netted bet, not 2.0


def test_total_exposure_capped_by_risk_gate():
    # 6 independent names: conf 0.9 x risk_gate 0.5 = 0.45 -> core (weight 0.5) -> raw 6*0.5 = 3.0;
    # budget = risk_gate(0.5) * max_total(4) = 2.0 -> capped, total clamped to 2.0
    picks = [Pick(f"N{i}", f"narr{i}", 0.9) for i in range(6)]
    plan = plan_portfolio(picks, risk_gate=0.5, config=SizingConfig())
    assert plan.total_exposure_budget == 2.0
    assert plan.total_exposure == 2.0 and plan.capped is True


def test_no_picks():
    plan = plan_portfolio([], risk_gate=0.8, config=SizingConfig())
    assert plan.sized == [] and plan.total_exposure == 0.0 and plan.capped is False
