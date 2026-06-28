import pytest
from alpha.harness.memory import Lesson, Importance


def test_importance_weight_and_demote():
    imp = Importance(base=0.8, time_decay=1.0, regime_decay=1.0)
    assert imp.weight() == 0.8
    imp.demote(0.5)
    assert imp.weight() == 0.4
    with pytest.raises(ValueError):
        imp.demote(0.0)


def test_lesson_from_seed():
    le = Lesson.from_seed({
        "lesson_id": "ssr_squeeze_top", "phases": ["flush"], "family": "meme",
        "outcome": "loss", "failure_signature": "chased squeeze top",
        "named_analog": "GME 2021 blowoff", "lesson": "don't chase parabolic squeeze into the flush",
    })
    assert le.phases == ["flush"] and le.family == "meme"
    assert le.outcome == "loss"
    assert le.importance.weight() == 1.0          # default


def test_lesson_from_seed_string_regime():
    le = Lesson.from_seed({"lesson_id": "x", "regime": "momentum", "outcome": "principle", "lesson": "y"})
    assert le.phases == ["trend"] and le.applies_all_phases is False


def test_lesson_bad_family_rejected():
    with pytest.raises(ValueError):
        Lesson.from_seed({"lesson_id": "x", "outcome": "principle", "lesson": "y", "family": "forex"})


def test_lesson_domain_defaults_to_trading():
    le = Lesson.from_seed({"lesson_id": "x", "outcome": "principle", "lesson": "y"})
    assert le.domain == "trading"


def test_lesson_domain_seedable_to_operational():
    le = Lesson.from_seed({
        "lesson_id": "x", "outcome": "principle", "lesson": "y",
        "domain": "operational",
    })
    assert le.domain == "operational"
