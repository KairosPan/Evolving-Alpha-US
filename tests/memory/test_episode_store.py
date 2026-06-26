from datetime import date
from alpha.memory.episodes import Episode
from alpha.memory.store import EpisodeStore


def _ep(eid, exit_d, sym="RUN", text="held the breakout"):
    return Episode(episode_id=eid, symbol=sym, skill_id="gap_and_go", entry_date=date(2026, 6, 1),
                   exit_date=exit_d, outcome="continued", advantage=0.3, score=0.4,
                   reflection_text=text, narrative="ai-compute")


def test_add_and_all_round_trip():
    s = EpisodeStore.in_memory()
    s.add(_ep("a", date(2026, 6, 3)))
    s.add(_ep("b", date(2026, 6, 5)))
    got = s.all()
    assert {e.episode_id for e in got} == {"a", "b"}
    assert got[0] == _ep("a", date(2026, 6, 3)) or got[1] == _ep("a", date(2026, 6, 3))


def test_insert_or_ignore_dedups_by_id():
    s = EpisodeStore.in_memory()
    s.add(_ep("a", date(2026, 6, 3), text="first"))
    s.add(_ep("a", date(2026, 6, 3), text="second"))   # same id -> ignored
    assert len(s.all()) == 1 and s.all()[0].reflection_text == "first"
