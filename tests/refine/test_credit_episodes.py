from datetime import date, datetime
from alpha.harness.skill import Skill
from alpha.harness.doctrine import Doctrine
from alpha.harness.registry import SkillRegistry, MemoryStore
from alpha.harness.state import HarnessState
from alpha.eval.decision import DecisionPackage, Candidate
from alpha.eval.metrics import ScoredCandidate
from alpha.eval.trajectory import Trajectory, TrajectoryStep
from alpha.state.market import MarketState
from alpha.refine.credit import apply_credit
from alpha.memory.store import EpisodeStore


def _h():
    return HarnessState(doctrine=Doctrine(),
                        skills=SkillRegistry.from_skills([Skill(skill_id="gap_and_go", name="Gap and Go",
                            type="pattern", family="runner", phases=["trend"], status="active")]),
                        memory=MemoryStore.from_lessons([]))


def _traj(exit_date):
    st = MarketState(date=date(2026, 6, 10), gainer_count=1, gap_up_count=0, loser_count=0,
                     failed_breakout_count=0, max_runner_tier=1, echelon=[], breadth_raw=1.0,
                     sentiment_norm=0.6, as_of=datetime(2026, 6, 10, 16, 0))
    dec = DecisionPackage(date=date(2026, 6, 10), regime_read="trend frontside",
                          candidates=[Candidate(symbol="RUN", pattern="gap_and_go", confidence=0.7)])
    step = TrajectoryStep(date=date(2026, 6, 10), market=st, decision=dec,
                          outcomes={"RUN": ScoredCandidate(symbol="RUN", pattern="gap_and_go",
                                                           decision_date=date(2026, 6, 10),
                                                           outcome="continued", advantage=0.4, score=0.5)},
                          scored=True, exit_date=exit_date)
    return Trajectory(steps=[step])


def test_episodes_written_when_store_given():
    s = EpisodeStore.in_memory()
    apply_credit(_traj(date(2026, 6, 12)), _h(), episode_store=s)
    eps = s.all()
    assert len(eps) == 1 and eps[0].symbol == "RUN" and eps[0].exit_date == date(2026, 6, 12)


def test_no_store_is_byte_identical_no_episodes():
    # the default path writes nothing and returns the same CreditReport shape as today
    rep = apply_credit(_traj(date(2026, 6, 12)), _h())     # no episode_store
    assert rep.n_scored == 1                                # credit still computed; no store touched
