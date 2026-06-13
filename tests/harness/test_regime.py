from alpha.harness.regime import (
    CANONICAL_PHASES, FAMILIES, normalize_phase, normalize_phases, is_family,
)


def test_canonical_sets():
    assert CANONICAL_PHASES == ["washout", "recovery", "ignition", "trend", "distribution", "flush"]
    assert FAMILIES == ["runner", "swing", "event", "meme"]


def test_normalize_phase_aliases():
    assert normalize_phase("Trend") == "trend"
    assert normalize_phase("momentum") == "trend"
    assert normalize_phase("first-green") == "recovery"
    assert normalize_phase("freeze") == "washout"
    assert normalize_phase("exhaustion") == "flush"
    assert normalize_phase("nonsense") is None
    assert normalize_phase(123) is None          # non-str does not crash


def test_normalize_phases_dedup_and_all():
    phases, applies_all = normalize_phases(["trend", "momentum", "all", "churn"])
    assert phases == ["trend", "distribution"]   # momentum->trend (dedup); churn->distribution; 'all' excluded from list
    assert applies_all is True


def test_normalize_phases_accepts_string():
    assert normalize_phases("all") == ([], True)
    assert normalize_phases("trend") == (["trend"], False)
    assert normalize_phases("momentum") == (["trend"], False)


def test_is_family():
    assert is_family("runner") is True
    assert is_family("crypto") is False
