from alpha.harness.growth_regime import (
    GROWTH_PHASES,
    GROWTH_SCALES,
    GROWTH_TOKENS,
    growth_scale_of,
    normalize_growth_phase,
    normalize_growth_phases,
)
from alpha.harness.regime import CANONICAL_PHASES, normalize_phases


def test_scales_and_tokens_declared():
    assert GROWTH_SCALES == ["market", "theme", "stock"]
    assert "market:panic_state" in GROWTH_TOKENS          # cross-cut market flag is a legal token
    assert set(GROWTH_TOKENS) == {f"{s}:{p}" for s in GROWTH_SCALES for p in GROWTH_PHASES[s]}


def test_normalize_growth_phase_valid_and_invalid():
    assert normalize_growth_phase("market:confirmed_uptrend") == "market:confirmed_uptrend"
    assert normalize_growth_phase(" Stock:Advance ") == "stock:advance"   # trimmed + lowercased
    assert normalize_growth_phase("market:bogus") is None                 # unknown phase for scale
    assert normalize_growth_phase("galaxy:advance") is None               # unknown scale
    assert normalize_growth_phase("advance") is None                      # bare token (no scale)
    assert normalize_growth_phase(123) is None


def test_normalize_growth_phases_list_all_and_dedup():
    phases, applies_all = normalize_growth_phases(["theme:emerging", "theme:emerging", "all"])
    assert phases == ["theme:emerging"] and applies_all is True
    # single string is one token (mirrors normalize_phases)
    assert normalize_growth_phases("market:correction") == (["market:correction"], False)
    assert normalize_growth_phases(None) == ([], False)


def test_unknown_tokens_dropped_loudly(capsys):
    phases, applies_all = normalize_growth_phases(["stock:top", "nonsense", "trend"])
    assert phases == ["stock:top"] and applies_all is False
    warn = capsys.readouterr().out
    assert "warning:" in warn and "nonsense" in warn and "trend" in warn


def test_growth_scale_of():
    assert growth_scale_of("theme:public_laggard") == "theme"
    assert growth_scale_of("bogus") is None


def test_momo_and_growth_namespaces_are_disjoint():
    # a growth token is dropped by the momo normalizer, and a momo token by the growth one — this
    # is the co-residence tripwire: neither vocabulary silently accepts the other's tokens.
    assert normalize_phases(["stock:advance"]) == ([], False)
    assert normalize_growth_phases(["trend"]) == ([], False)
    # and the exhaustion landmine (P0.1 §1): the growth theme token never becomes momo flush
    assert normalize_growth_phase("theme:exhaustion") == "theme:exhaustion"
    assert "flush" not in normalize_growth_phases(["theme:exhaustion"])[0]
    assert "exhaustion" not in CANONICAL_PHASES
