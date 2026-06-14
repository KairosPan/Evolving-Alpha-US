"""US-1g acceptance: a full §4.1 DecisionPackage is constructible (the human-facing action a_t), and
the v1 seed packs load into a harness H that is queryable by family — the substrate US-2's agent
will read (H) and produce (DecisionPackage)."""
from pathlib import Path
from datetime import date
from alpha.eval.decision import (
    Candidate, FillFeasibility, TabooCheck, Portfolio, DecisionPackage,
)
from alpha.harness.loader import load_seeds

SEEDS = Path(__file__).resolve().parents[2] / "seeds"


def test_full_decision_package_round_trips_through_dict():
    dp = DecisionPackage(
        date=date(2026, 6, 12), regime_read="trend; AI frontside",
        candidates=[Candidate(symbol="AI1", name="Alpha AI", pattern="gap_and_go",
                              skill_id="gap_and_go", family="runner", entry="ORB reclaim",
                              exit_stop="lose VWAP", size_tier="core", confidence=0.7,
                              fill_feasibility=FillFeasibility(buyable=True),
                              taboo_check=[TabooCheck(rule="no-chase-risk-off", status="pass")],
                              counterview="drop if AI flips backside")],
        key_risks=["AI leader rolls over"],
        portfolio=Portfolio(total_exposure_budget=0.6, correlated_groups=[["AI1", "AI2"]]),
        human_confirm=None)
    again = DecisionPackage.model_validate(dp.model_dump())   # frozen + serializable round-trip
    assert again.candidates[0].size_tier == "core"
    assert again.portfolio.correlated_groups == [["AI1", "AI2"]]


def test_agent_substrate_ready():
    # the agent (US-2) reads this H and emits a DecisionPackage like the one above
    h = load_seeds(SEEDS)
    runner_skills = h.skills.by_family("runner")
    assert any(s.skill_id == "gap_and_go" for s in runner_skills)
    assert h.doctrine.immutable_core()                      # discipline red-lines present for the agent
