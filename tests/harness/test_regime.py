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


def test_normalize_phases_warns_on_dropped_token(capsys):
    # the silent-drop is today's worst failure shape (no crash, just wrong); the drop stays but is loud.
    phases, applies_all = normalize_phases(["trend", "bogus_phase"])
    assert phases == ["trend"] and applies_all is False   # drop behavior byte-identical
    out = capsys.readouterr().out
    assert "warning" in out.lower() and "bogus_phase" in out   # names the dropped token


def test_normalize_phases_silent_when_all_recognized(capsys):
    # no false-positive warning: an alias (momentum->trend), a dedup, and 'all' are all "recognized".
    normalize_phases(["trend", "momentum", "all"])
    assert capsys.readouterr().out == ""


def test_is_family():
    assert is_family("runner") is True
    assert is_family("crypto") is False
