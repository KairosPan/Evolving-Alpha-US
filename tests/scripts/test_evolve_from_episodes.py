from datetime import date
import importlib
from alpha.harness.doctrine import Doctrine
from alpha.harness.skill import Skill, SkillStats
from alpha.harness.registry import SkillRegistry, MemoryStore
from alpha.harness.state import HarnessState
from alpha.harness.edit_log import EditLog
from alpha.memory.episodes import Episode
from alpha.memory.store import EpisodeStore
from alpha.meta.store import LiveBrainStore


def _seed_brain(brain_dir):
    h = HarnessState(doctrine=Doctrine(),
                     skills=SkillRegistry.from_skills([Skill(skill_id="s1", name="s1", type="pattern",
                            family="runner", phases=["trend"], status="incubating",
                            stats=SkillStats(n=5, expectancy=1.0))]),
                     memory=MemoryStore.from_lessons([]))
    LiveBrainStore(str(brain_dir)).save(h, EditLog())


def _seed_episodes(db_path):
    s = EpisodeStore.open(str(db_path))
    for i in range(5):
        s.add(Episode(episode_id=f"s1:{i}", symbol="RUN", skill_id="s1", entry_date=date(2026, 6, 1),
                      exit_date=date(2026, 6, 3), outcome="continued", advantage=2.0))
    s.close()


def test_run_evolve_promotes_in_saved_brain(tmp_path):
    brain_dir = tmp_path / "brain"; db = tmp_path / "brain.db"; conflicts = tmp_path / "conflicts"
    _seed_brain(brain_dir); _seed_episodes(db)
    mod = importlib.import_module("scripts.evolve_from_episodes")
    out = mod.run_evolve_from_episodes(brain_dir=str(brain_dir), conflicts_dir=str(conflicts),
                                       episodes_db=str(db), asof=date(2026, 6, 20))
    assert out["applied"] == ["s1"]
    h, _ = LiveBrainStore(str(brain_dir)).load()
    assert h.skills.get("s1").status == "active"                    # promotion persisted to the live brain
