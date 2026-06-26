from datetime import date, datetime
from alpha.harness.skill import Skill
from alpha.harness.doctrine import Doctrine
from alpha.harness.registry import SkillRegistry, MemoryStore
from alpha.harness.state import HarnessState
from alpha.eval.decision import DecisionPackage, Candidate
from alpha.eval.metrics import ScoredCandidate
from alpha.eval.trajectory import TrajectoryStep
from alpha.state.market import MarketState
from alpha.memory.episodes import episodes_from_step


def _h():
    return HarnessState(
        doctrine=Doctrine(),
        skills=SkillRegistry.from_skills([
            Skill(skill_id="gap_and_go", name="Gap and Go",
                  type="pattern", family="runner", phases=["trend"], status="active"),
        ]),
        memory=MemoryStore.from_lessons([]),
    )


def _state():
    return MarketState(
        date=date(2026, 6, 10), gainer_count=1, gap_up_count=0, loser_count=0,
        failed_breakout_count=0, max_runner_tier=1, echelon=[], breadth_raw=1.0,
        sentiment_norm=0.6, as_of=datetime(2026, 6, 10, 16, 0),
    )


def _step(exit_date):
    decision = DecisionPackage(
        date=date(2026, 6, 10),
        regime_read="trend frontside",
        candidates=[Candidate(symbol="RUN", pattern="gap_and_go",
                              confidence=0.7, narrative="ai-compute")],
    )
    outcomes = {
        "RUN": ScoredCandidate(
            symbol="RUN", pattern="gap_and_go", outcome="continued",
            advantage=0.4, score=0.5, decision_date=date(2026, 6, 10),
        ),
    }
    return TrajectoryStep(
        date=date(2026, 6, 10), market=_state(), decision=decision,
        outcomes=outcomes, scored=True, exit_date=exit_date,
    )


def test_builds_one_episode_per_scored_pick():
    eps = episodes_from_step(_step(date(2026, 6, 12)), _h())
    assert len(eps) == 1
    e = eps[0]
    assert e.symbol == "RUN" and e.skill_id == "gap_and_go" and e.narrative == "ai-compute"
    assert e.exit_date == date(2026, 6, 12) and e.learned_asof == date(2026, 6, 12)
    assert e.entry_date == date(2026, 6, 10) and e.outcome == "continued" and e.advantage == 0.4
    assert e.episode_id == "2026-06-12:RUN:gap_and_go"


def test_no_exit_date_yields_no_episodes():
    assert episodes_from_step(_step(None), _h()) == []
