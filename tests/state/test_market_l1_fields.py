from datetime import date, datetime
from alpha.state.market import MarketState


def _ms(**kw):
    base = dict(date=date(2026, 6, 12), gainer_count=0, gap_up_count=0, loser_count=0,
               failed_breakout_count=0, max_runner_tier=0, echelon=[], breadth_raw=0.0,
               sentiment_norm=None, as_of=datetime(2026, 6, 12, 16, 0))
    base.update(kw)
    return MarketState(**base)


def test_new_fields_default_backward_compatible():
    ms = _ms()                                      # US-0/1d-style construction (no new fields)
    assert ms.sentiment_raw == 0.0
    assert ms.follow_through_rate is None
    assert ms.gap_and_go_count == 0


def test_new_fields_settable():
    ms = _ms(sentiment_raw=4.2, follow_through_rate=0.6, gap_and_go_count=5)
    assert ms.sentiment_raw == 4.2 and ms.follow_through_rate == 0.6 and ms.gap_and_go_count == 5
