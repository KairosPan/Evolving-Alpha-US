from datetime import date, datetime
from alpha.harness.skill import Skill, SkillStats
from alpha.harness.doctrine import Doctrine
from alpha.harness.registry import SkillRegistry, MemoryStore
from alpha.harness.state import HarnessState
from alpha.state.market import MarketState
from alpha.eval.decision import Candidate, DecisionPackage
from alpha.eval.metrics import ScoredCandidate
from alpha.eval.trajectory import TrajectoryStep, Trajectory
from alpha.refine.credit import apply_credit
from alpha.refine.signatures import extract_signatures
from alpha.refine.refiner_prompt import build_refiner_system_prompt, build_refiner_user_prompt


def _h():
    skills = SkillRegistry.from_skills([
        Skill(skill_id="gap_and_go", name="Gap and Go", type="pattern", status="active"),
    ])
    doctrine = Doctrine.from_seed_list([
        {"section": "stop_discipline", "regime": "all", "immutable": True, "guidance": "honor the stop"},
        {"section": "trend_play", "regime": "trend", "immutable": False, "guidance": "ride the leader"},
    ])
    return HarnessState(doctrine=doctrine, skills=skills, memory=MemoryStore.from_lessons([]))


def test_system_prompt_p_pass():
    sp = build_refiner_system_prompt(_h(), "p", min_retire_samples=5, min_promote_samples=3)
    assert "rewrite_doctrine" in sp and "trend_play" in sp
    assert "stop_discipline" in sp and "immutable" in sp.lower()       # red-lines shown read-only
    assert '"ops"' in sp                                                # output contract


def test_system_prompt_k_pass_discipline():
    sp = build_refiner_system_prompt(_h(), "K", min_retire_samples=5, min_promote_samples=3)
    assert "retire_skill" in sp and "promote_skill" in sp
    assert "5" in sp and "3" in sp                                      # injected thresholds
    assert "faded" in sp.lower() and "whole-field replace" in sp.lower()
    assert "rewrite_doctrine" not in sp                                 # K-pass shows only K tools


def test_user_prompt_renders_evidence_and_history():
    h = _h()
    d = date(2026, 6, 10)
    sc = ScoredCandidate(decision_date=d, symbol="RUN", pattern="gap_and_go", outcome="nuked",
                         score=-0.5, day_baseline=0.0)
    from alpha.universe.stock import StockSnapshot
    step = TrajectoryStep(date=d, market=MarketState(date=d, gainer_count=1, gap_up_count=0, loser_count=0,
                          failed_breakout_count=0, max_runner_tier=1, echelon=[], breadth_raw=1.0,
                          as_of=datetime(2026, 6, 10, 16, 0)),
                          decision=DecisionPackage(date=d, candidates=[Candidate(symbol="RUN", pattern="gap_and_go")]),
                          entries={"RUN": StockSnapshot(symbol="RUN", name="Runner", status="gainer", consecutive_up_days=1)},
                          outcomes={"RUN": sc}, scored=True)
    traj = Trajectory(steps=[step])
    credit = apply_credit(traj, h)
    sigs = extract_signatures(traj, h)
    up = build_refiner_user_prompt(traj, credit, sigs, window=10, recent_reports=[])
    assert "gap_and_go" in up and "RUN" in up and "nuk" in up.lower()
