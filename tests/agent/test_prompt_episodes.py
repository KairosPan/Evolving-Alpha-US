from datetime import date
from alpha.harness.doctrine import Doctrine
from alpha.harness.registry import SkillRegistry, MemoryStore
from alpha.harness.state import HarnessState
from alpha.memory.episodes import Episode
from alpha.memory.store import EpisodeStore
from alpha.agent.prompt import build_system_prompt


def _h():
    return HarnessState(doctrine=Doctrine(), skills=SkillRegistry.from_skills([]), memory=MemoryStore.from_lessons([]))


def _store(*eps):
    s = EpisodeStore.in_memory()
    for e in eps:
        s.add(e)
    return s


def _ep(eid, phase, exit_d, adv, refl=""):
    return Episode(episode_id=eid, symbol="RUN", skill_id="gap_and_go", phase=phase,
                   entry_date=date(2026, 6, 1), exit_date=exit_d, outcome="continued", advantage=adv,
                   reflection_text=refl)


def test_no_store_no_block():
    p = build_system_prompt(_h(), asof=date(2026, 6, 20))
    assert "RECALLED EPISODES" not in p


def test_store_renders_recalled_block():
    s = _store(_ep("e1", "trend frontside", date(2026, 6, 5), 1.5, refl="held the gap into close"))
    p = build_system_prompt(_h(), phase_prior="trend", asof=date(2026, 6, 20), episode_store=s)
    assert "RECALLED EPISODES" in p
    assert "RUN/gap_and_go" in p and "continued" in p and "+1.5" in p and "held the gap into close" in p


def test_block_honors_asof_pit():
    s = _store(_ep("future", "trend frontside", date(2026, 6, 25), 9.0))   # learned_asof 06-25
    p = build_system_prompt(_h(), phase_prior="trend", asof=date(2026, 6, 10), episode_store=s)
    assert "RECALLED EPISODES" not in p                                    # nothing knowable at asof -> no block
