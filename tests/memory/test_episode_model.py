# tests/memory/test_episode_model.py
from datetime import date
from alpha.memory.episodes import Episode

def test_episode_constructs_and_round_trips():
    e = Episode(episode_id="2026-06-12:RUN:gap_and_go", symbol="RUN", skill_id="gap_and_go",
                family="runner", phase="trend", narrative="ai-compute",
                entry_date=date(2026, 6, 10), exit_date=date(2026, 6, 12),
                outcome="continued", advantage=0.4, score=0.5, failure_kind="",
                reflection_text="RUN held the breakout")
    assert e.learned_asof == date(2026, 6, 12)            # learned_asof defaults to exit_date
    assert Episode.model_validate_json(e.model_dump_json()) == e

def test_learned_asof_can_be_overridden_but_defaults_to_exit_date():
    e = Episode(episode_id="x", symbol="X", skill_id="s", entry_date=date(2026, 6, 1),
                exit_date=date(2026, 6, 3), outcome="faded", advantage=0.0, score=0.0)
    assert e.learned_asof == date(2026, 6, 3)
