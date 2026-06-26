from datetime import date
from alpha.harness.memory import Lesson


def test_learned_asof_defaults_none():
    assert Lesson(lesson_id="l", outcome="win", lesson="x").learned_asof is None


def test_from_seed_coerces_learned_asof_iso_string():
    l = Lesson.from_seed({"lesson_id": "l2", "outcome": "win", "lesson": "y",
                          "learned_asof": "2026-06-12"})
    assert l.learned_asof == date(2026, 6, 12)


def test_from_seed_without_learned_asof_is_none():
    assert Lesson.from_seed({"lesson_id": "l3", "outcome": "loss", "lesson": "z"}).learned_asof is None
