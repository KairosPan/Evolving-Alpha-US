from datetime import date, datetime
from alpha.harness.skill import Skill, SkillStats
from alpha.harness.doctrine import Doctrine
from alpha.harness.registry import SkillRegistry, MemoryStore
from alpha.harness.state import HarnessState
from alpha.state.market import MarketState
from alpha.eval.decision import Candidate, DecisionPackage
from alpha.eval.metrics import ScoredCandidate
from alpha.eval.trajectory import TrajectoryStep, Trajectory
from alpha.refine.credit import apply_credit, merge_credit_reports, resolve_skill, UNATTRIBUTED


def _h():
    skills = SkillRegistry.from_skills([
        Skill(skill_id="gap_and_go", name="Gap and Go", type="pattern", status="active"),
    ])
    return HarnessState(doctrine=Doctrine(), skills=skills, memory=MemoryStore.from_lessons([]))


def _mkt(d):
    return MarketState(date=d, gainer_count=1, gap_up_count=0, loser_count=0, failed_breakout_count=0,
                       max_runner_tier=1, echelon=[], breadth_raw=1.0, as_of=datetime(d.year, d.month, d.day, 16, 0))


def _step(d, pattern, outcome, score, baseline):
    sc = ScoredCandidate(decision_date=d, symbol="RUN", pattern=pattern, outcome=outcome,
                         score=score, day_baseline=baseline)
    dec = DecisionPackage(date=d, candidates=[Candidate(symbol="RUN", pattern=pattern)])
    return TrajectoryStep(date=d, market=_mkt(d), decision=dec, outcomes={"RUN": sc}, scored=True)


def test_resolve_skill_cascade():
    h = _h()
    assert resolve_skill("gap_and_go", h).skill_id == "gap_and_go"      # exact id
    assert resolve_skill("  GAP_AND_GO ", h).skill_id == "gap_and_go"   # normalized
    assert resolve_skill("Gap and Go", h).skill_id == "gap_and_go"      # by name
    assert resolve_skill("ghost", h) is None and resolve_skill("", h) is None


def test_apply_credit_mutates_stats_in_place():
    h = _h()
    traj = Trajectory(steps=[
        _step(date(2026, 6, 10), "gap_and_go", "continued", 0.30, 0.10),   # win, advantage 0.20
        _step(date(2026, 6, 11), "gap_and_go", "nuked", -0.50, 0.10),      # loss+nuke, advantage -0.60
    ])
    rep = apply_credit(traj, h)
    st = h.skills.get("gap_and_go").stats
    assert st.n == 2 and st.wins == 1 and st.losses == 1 and st.nukes == 1
    assert abs(st.expectancy - (-0.20)) < 1e-9          # mean advantage = (0.20 + -0.60)/2
    assert abs(st.expectancy_raw - (-0.10)) < 1e-9      # mean raw score = (0.30 + -0.50)/2
    assert st.ewma_winrate is not None
    assert rep.per_skill["gap_and_go"].n == 2 and rep.n_scored == 2
    assert rep.per_skill["gap_and_go"].nuke_rate == 0.5


def test_unattributed_bucket():
    h = _h()
    traj = Trajectory(steps=[_step(date(2026, 6, 10), "hallucinated", "faded", 0.0, 0.0)])
    rep = apply_credit(traj, h)
    assert rep.per_skill == {} and rep.unattributed is not None
    assert rep.unattributed.skill_id == UNATTRIBUTED and rep.unattributed.n == 1


def test_merge_is_readonly_and_additive():
    h = _h()
    r1 = apply_credit(Trajectory(steps=[_step(date(2026, 6, 10), "gap_and_go", "continued", 0.4, 0.1)]), h)
    n_after_first = h.skills.get("gap_and_go").stats.n
    merged = merge_credit_reports([r1, r1])                 # merge does NOT touch H stats
    assert h.skills.get("gap_and_go").stats.n == n_after_first   # unchanged by merge
    assert merged.per_skill["gap_and_go"].n == 2 and merged.n_scored == 2
