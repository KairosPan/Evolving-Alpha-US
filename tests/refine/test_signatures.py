from datetime import date, datetime
from alpha.harness.skill import Skill
from alpha.harness.doctrine import Doctrine
from alpha.harness.registry import SkillRegistry, MemoryStore
from alpha.harness.state import HarnessState
from alpha.state.market import MarketState
from alpha.universe.stock import StockSnapshot
from alpha.eval.decision import Candidate, DecisionPackage
from alpha.eval.metrics import ScoredCandidate
from alpha.eval.trajectory import TrajectoryStep, Trajectory
from alpha.refine.signatures import extract_signatures


def _h():
    skills = SkillRegistry.from_skills([Skill(skill_id="gap_and_go", name="Gap and Go", type="pattern")])
    return HarnessState(doctrine=Doctrine(), skills=skills, memory=MemoryStore.from_lessons([]))


def _step(d, outcome, cud, max_tier):
    sc = ScoredCandidate(decision_date=d, symbol="RUN", pattern="gap_and_go", outcome=outcome,
                         score=(-0.5 if outcome == "nuked" else 0.0), day_baseline=0.0)
    snap = StockSnapshot(symbol="RUN", name="Runner", status="gainer", consecutive_up_days=cud)
    mkt = MarketState(date=d, gainer_count=1, gap_up_count=0, loser_count=0, failed_breakout_count=0,
                      max_runner_tier=max_tier, echelon=[], breadth_raw=1.0,
                      as_of=datetime(d.year, d.month, d.day, 16, 0))
    dec = DecisionPackage(date=d, candidates=[Candidate(symbol="RUN", pattern="gap_and_go")])
    return TrajectoryStep(date=d, market=mkt, decision=dec, entries={"RUN": snap},
                          outcomes={"RUN": sc}, scored=True)


def _kinds(steps):
    return [s.kind for s in extract_signatures(Trajectory(steps=steps), _h())]


def test_continued_produces_no_signature():
    assert _kinds([_step(date(2026, 6, 10), "continued", 3, 3)]) == []


def test_faded_is_idle_miss():
    sigs = extract_signatures(Trajectory(steps=[_step(date(2026, 6, 10), "faded", 1, 3)]), _h())
    assert [s.kind for s in sigs] == ["faded_miss"] and sigs[0].skill_id == "gap_and_go"


def test_nuke_taxonomy():
    assert _kinds([_step(date(2026, 6, 10), "nuked", 3, 3)]) == ["chased_blowoff"]      # cud >= max_tier
    assert _kinds([_step(date(2026, 6, 11), "nuked", 1, 3)]) == ["weak_laggard_nuke"]   # cud < max_tier
    assert _kinds([_step(date(2026, 6, 12), "nuked", None, 3)]) == ["generic_nuke"]     # tier unknown
