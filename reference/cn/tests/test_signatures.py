# tests/test_signatures.py
from datetime import date, datetime, time

from youzi.eval.decision import Candidate, DecisionPackage
from youzi.eval.metrics import ScoredCandidate
from youzi.eval.trajectory import EntrySnap, Trajectory, TrajectoryStep
from youzi.harness.cycle import StateMachine
from youzi.harness.doctrine import Doctrine
from youzi.harness.harness import HarnessState
from youzi.harness.memory_store import MemoryStore
from youzi.harness.registry import SkillRegistry
from youzi.harness.skill import Skill
from youzi.refine.signatures import extract_signatures
from youzi.schemas.market import MarketState

_SCORE = {"continued": 1.0, "faded": 0.0, "nuked": -1.0}


def _state(d, max_board):
    return MarketState(date=d, max_board_height=max_board, limit_up_count=0,
                       blowup_count=0, blowup_rate=0.0, limit_down_count=0,
                       echelon=[], money_effect_raw=0.0, sentiment_raw=0.0,
                       as_of=datetime.combine(d, time(15, 0)))


def _h():
    return HarnessState(
        doctrine=Doctrine(),
        skills=SkillRegistry.from_skills([
            Skill(skill_id="pat_a", name_cn="接力", type="pattern",
                  trigger="t", entry="e", exit_stop="s", status="active")]),
        memory=MemoryStore.from_lessons([]), cycle=StateMachine())


def _step(d, code, oc, boards, max_board, pattern="pat_a"):
    sc = ScoredCandidate(decision_date=d, code=code, pattern=pattern, outcome=oc,
                         score=_SCORE[oc])
    return TrajectoryStep(
        date=d, market=_state(d, max_board),
        decision=DecisionPackage(date=d, candidates=[Candidate(code=code, pattern=pattern)]),
        entries={code: EntrySnap(code=code, status="limit_up", boards=boards)},
        scored=True, outcomes={code: sc})


def test_signatures_four_kinds_and_skip_continued():
    d = date(2024, 6, 26)
    traj = Trajectory(steps=[
        _step(d, "TOP", "nuked", 3, 3),      # boards==max → chased_into_nuke
        _step(d, "WEED", "nuked", 1, 3),     # boards<max → weed_over_dragon
        _step(d, "UNK", "nuked", None, 3),   # boards None → generic_nuke
        _step(d, "FADE", "faded", 2, 3),     # faded → faded_miss
        _step(d, "WIN", "continued", 3, 3),  # continued → 无签名
    ], horizon=1)
    sigs = extract_signatures(traj, _h())
    kinds = {s.code: s.kind for s in sigs}
    assert kinds == {"TOP": "chased_into_nuke", "WEED": "weed_over_dragon",
                     "UNK": "generic_nuke", "FADE": "faded_miss"}
    assert all(s.skill_id == "pat_a" for s in sigs)        # pattern 命中技能
    top = next(s for s in sigs if s.code == "TOP")
    assert "boards=3/max=3" in top.evidence and top.score == -1.0


def test_signatures_unresolved_pattern_skill_id_none():
    d = date(2024, 6, 26)
    traj = Trajectory(steps=[_step(d, "X", "faded", 1, 2, pattern="无")], horizon=1)
    sigs = extract_signatures(traj, _h())
    assert len(sigs) == 1 and sigs[0].skill_id is None and sigs[0].kind == "faded_miss"
