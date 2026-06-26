from datetime import date
from alpha.memory.episodes import Episode
from alpha.memory.store import EpisodeStore


def _ep(eid, exit_d, phase="trend", narr="ai-compute"):
    return Episode(episode_id=eid, symbol="RUN", skill_id="s", entry_date=date(2026, 6, 1),
                   exit_date=exit_d, outcome="continued", advantage=0.1, score=0.1,
                   phase=phase, narrative=narr, reflection_text="t")


def test_for_asof_masks_future_episodes():
    s = EpisodeStore.in_memory()
    s.add(_ep("early", date(2026, 6, 3)))
    s.add(_ep("future", date(2026, 6, 12)))
    ids = {e.episode_id for e in s.for_asof(date(2026, 6, 5))}
    assert ids == {"early"}                               # the 06-12 episode is invisible at 06-05
    assert {e.episode_id for e in s.for_asof(date(2026, 6, 12))} == {"early", "future"}


def test_for_asof_filters_phase_and_narrative():
    s = EpisodeStore.in_memory()
    s.add(_ep("a", date(2026, 6, 3), phase="trend", narr="ai-compute"))
    s.add(_ep("b", date(2026, 6, 3), phase="chop", narr="biotech"))
    assert {e.episode_id for e in s.for_asof(date(2026, 6, 9), phase="trend")} == {"a"}
    assert {e.episode_id for e in s.for_asof(date(2026, 6, 9), narrative="biotech")} == {"b"}
