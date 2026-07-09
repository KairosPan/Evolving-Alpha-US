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


def test_run_evolve_propose_default_packages_then_user_adopts(tmp_path):
    """Charter conformance (2026-07-09): forge promotes on a FORK; the live brain moves only
    when the USER adopts the packet."""
    from alpha.meta.evolution import adopt_proposal
    from alpha.meta.proposal_store import ProposalQueue

    brain_dir = tmp_path / "brain"; db = tmp_path / "brain.db"; conflicts = tmp_path / "conflicts"
    _seed_brain(brain_dir); _seed_episodes(db)
    mod = importlib.import_module("scripts.evolve_from_episodes")
    out = mod.run_evolve_from_episodes(brain_dir=str(brain_dir), conflicts_dir=str(conflicts),
                                       episodes_db=str(db), asof=date(2026, 6, 20),
                                       proposals_root=str(tmp_path / "proposals"))
    assert out["mode"] == "propose" and out["applied"] == ["s1"]    # fork-applied
    h, _ = LiveBrainStore(str(brain_dir)).load()
    assert h.skills.get("s1").status == "incubating"                # live brain UNTOUCHED

    prop = ProposalQueue(str(tmp_path / "proposals")).get(out["proposal_id"])
    ok, reason = adopt_proposal(LiveBrainStore(str(brain_dir)), prop)
    assert ok, reason
    h2, log2 = LiveBrainStore(str(brain_dir)).load()
    assert h2.skills.get("s1").status == "active"                   # landed on USER adoption
    assert log2.records()[-1].provenance.proposer == "forge"        # true principal preserved
    assert log2.records()[-1].provenance.human_approver == "user"


def test_run_evolve_autonomous_persists_with_unsafe_env(tmp_path, monkeypatch):
    monkeypatch.setenv("ALPHA_UNSAFE_AUTONOMOUS", "1")
    brain_dir = tmp_path / "brain"; db = tmp_path / "brain.db"; conflicts = tmp_path / "conflicts"
    _seed_brain(brain_dir); _seed_episodes(db)
    mod = importlib.import_module("scripts.evolve_from_episodes")
    out = mod.run_evolve_from_episodes(brain_dir=str(brain_dir), conflicts_dir=str(conflicts),
                                       episodes_db=str(db), asof=date(2026, 6, 20),
                                       mode="autonomous")
    assert out["applied"] == ["s1"]
    h, _ = LiveBrainStore(str(brain_dir)).load()
    assert h.skills.get("s1").status == "active"                    # promotion persisted to the live brain
