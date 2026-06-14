from alpha.features.sentiment import raw_sentiment, normalize_sentiment


def test_raw_sentiment_directionality():
    strong = raw_sentiment(gainer_count=40, max_runner_tier=5, follow_through=0.8,
                           failed_breakout_rate=0.1, loser_count=2)
    weak = raw_sentiment(gainer_count=3, max_runner_tier=1, follow_through=0.1,
                         failed_breakout_rate=0.7, loser_count=40)
    assert strong > weak                       # more gainers/runners/follow-through -> higher


def test_normalize_percentile():
    hist = [0.0, 1.0, 2.0, 3.0, 4.0]
    assert normalize_sentiment(2.0, hist, min_samples=3) == 3 / 5     # <=2.0 are {0,1,2}
    assert normalize_sentiment(5.0, hist, min_samples=3) == 1.0


def test_normalize_insufficient_samples_is_none():
    assert normalize_sentiment(2.0, [0.0, 1.0], min_samples=3) is None
    assert normalize_sentiment(2.0, None, min_samples=3) is None
