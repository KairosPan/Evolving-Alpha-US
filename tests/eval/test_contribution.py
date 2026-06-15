from datetime import date, datetime
from alpha.harness.skill import Skill
from alpha.harness.doctrine import Doctrine
from alpha.harness.registry import SkillRegistry, MemoryStore
from alpha.harness.state import HarnessState
from alpha.state.market import MarketState
from alpha.eval.decision import Candidate, DecisionPackage
from alpha.eval.metrics import ScoredCandidate
from alpha.eval.trajectory import TrajectoryStep, Trajectory
from alpha.eval.contribution import contribution_split, ContributionReport


def _h():
    # families here are SYNTHETIC test fixtures (not the seed values) — keep as-is
    return HarnessState(doctrine=Doctrine(), memory=MemoryStore.from_lessons([]),
                        skills=SkillRegistry.from_skills([
                            Skill(skill_id="gap_and_go", name="Gap", type="pattern", family="runner",
                                  status="active"),
                            Skill(skill_id="rvol_feat", name="RVOL", type="feature", family="runner",
                                  status="active"),
                            Skill(skill_id="failed_breakout", name="FB", type="failure_detector",
                                  family="runner", status="active")]))


def _step(d, picks):  # picks: list of (pattern, outcome, advantage)
    outcomes = {f"{pat}{i}": ScoredCandidate(decision_date=d, symbol=f"{pat}{i}", pattern=pat,
                                             outcome=oc, score=adv, day_baseline=0.0)
                for i, (pat, oc, adv) in enumerate(picks)}
    dec = DecisionPackage(date=d, candidates=[Candidate(symbol=s, pattern="p") for s in outcomes])
    return TrajectoryStep(date=d, market=MarketState(date=d, gainer_count=1, gap_up_count=0, loser_count=0,
                          failed_breakout_count=0, max_runner_tier=1, echelon=[], breadth_raw=1.0,
                          as_of=datetime(d.year, d.month, d.day, 16, 0)),
                          decision=dec, outcomes=outcomes, scored=True)


def test_offense_defense_unknown_bucketing():
    traj = Trajectory(steps=[_step(date(2026, 6, 10), [
        ("gap_and_go", "continued", 0.3),       # offense (pattern)
        ("rvol_feat", "continued", 0.1),        # offense (feature) -> pattern+feature both bucket to offense
        ("failed_breakout", "nuked", -0.5),     # defense (failure_detector)
        ("ghost", "faded", 0.0),                # unknown (unresolved pattern)
    ])])
    rep = contribution_split(traj, _h())
    assert isinstance(rep, ContributionReport)
    assert rep.offense.n == 2 and abs(rep.offense.expectancy - 0.2) < 1e-9 and rep.offense.hit_rate == 1.0
    assert rep.defense.n == 1 and abs(rep.defense.expectancy - (-0.5)) < 1e-9 and rep.defense.nuke_rate == 1.0
    assert rep.unknown.n == 1


def test_per_family_split():
    traj = Trajectory(steps=[_step(date(2026, 6, 10), [
        ("gap_and_go", "continued", 0.4), ("failed_breakout", "continued", 0.2)])])
    rep = contribution_split(traj, _h())
    assert rep.by_family["runner"].n == 2 and abs(rep.by_family["runner"].expectancy - 0.3) < 1e-9
