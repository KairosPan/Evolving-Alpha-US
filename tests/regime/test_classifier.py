from datetime import date, datetime
from alpha.state.market import MarketState
from alpha.regime.classifier import GCycle, RegimeRead
from alpha.harness.regime import CANONICAL_PHASES


def _ms(**kw):
    base = dict(date=date(2026, 6, 12), gainer_count=0, gap_up_count=0, loser_count=0,
               failed_breakout_count=0, max_runner_tier=0, echelon=[], breadth_raw=0.0,
               sentiment_raw=0.0, sentiment_norm=None, follow_through_rate=None,
               gap_and_go_count=0, as_of=datetime(2026, 6, 12, 16, 0))
    base.update(kw)
    return MarketState(**base)


def test_read_is_in_canonical_vocab_and_bounded():
    r = GCycle().read(_ms(sentiment_norm=0.7, gainer_count=30, max_runner_tier=4,
                          follow_through_rate=0.8, failed_breakout_count=1))
    assert isinstance(r, RegimeRead)
    assert r.phase in CANONICAL_PHASES
    assert 0.0 <= r.risk_gate <= 1.0 and 0.0 <= r.confidence <= 1.0


def test_strong_tape_is_trend_frontside():
    r = GCycle().read(_ms(sentiment_norm=0.85, gainer_count=40, max_runner_tier=5,
                          follow_through_rate=0.85, failed_breakout_count=1, loser_count=2))
    assert r.phase == "trend" and r.frontside is True and r.risk_gate > 0.6


def test_weak_tape_is_washout():
    r = GCycle().read(_ms(sentiment_norm=0.1, gainer_count=2, max_runner_tier=0,
                          follow_through_rate=0.05, failed_breakout_count=8, loser_count=40))
    assert r.phase == "washout" and r.frontside is False and r.risk_gate < 0.3


def test_distribution_is_backside():
    r = GCycle().read(_ms(sentiment_norm=0.6, gainer_count=20, max_runner_tier=3,
                          follow_through_rate=0.3, failed_breakout_count=12, loser_count=10))
    assert r.phase in ("distribution", "flush") and r.frontside is False


def test_none_sentiment_degrades_confidence():
    r = GCycle().read(_ms(sentiment_norm=None, gainer_count=5))
    assert r.phase in CANONICAL_PHASES and r.confidence <= 0.5      # uncertain without normalization
    assert r.risk_gate <= 0.5                                       # size multiplier capped when uncertain


def test_classifier_is_read_only_ssot():
    # SSOT (the hardest-won P0): G_cycle reads only — it must expose NO public method beyond read()
    # and hold no harness reference (constructs with no harness arg). Enumerated structurally so a
    # future write/update method can't slip past a hardcoded name list.
    import inspect
    GCycle()                                                        # constructs with no harness
    public = [m for m, _ in inspect.getmembers(GCycle(), predicate=inspect.ismethod)
              if not m.startswith("_")]
    assert public == ["read"], f"GCycle exposes non-read public methods: {public}"
