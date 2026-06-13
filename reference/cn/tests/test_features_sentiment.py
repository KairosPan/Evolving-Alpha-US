# tests/test_features_sentiment.py
from youzi.features.sentiment import raw_sentiment, normalize_sentiment


def test_raw_sentiment_monotonic_in_height_and_money():
    low = raw_sentiment(max_board_height=2, limit_up_count=10,
                        money_effect=-3.0, blowup_rate=0.6, limit_down_count=30)
    high = raw_sentiment(max_board_height=9, limit_up_count=80,
                         money_effect=5.0, blowup_rate=0.1, limit_down_count=2)
    assert high > low


def test_normalize_returns_none_when_too_few_samples():
    assert normalize_sentiment(5.0, history=[1.0, 2.0], min_samples=60) is None


def test_normalize_is_percentile_rank():
    hist = [float(i) for i in range(100)]        # 0..99
    # 当前值 50 在 0..99 里的分位约 0.5
    p = normalize_sentiment(50.0, history=hist, min_samples=60)
    assert p == 51 / 100   # count(h<=50)=51 in 0..99
    assert normalize_sentiment(1000.0, history=hist, min_samples=60) == 1.0
    assert normalize_sentiment(-1.0, history=hist, min_samples=60) == 0.0   # 低于全部 → 0.0
