from __future__ import annotations

from datetime import date as Date, datetime as DateTime

from youzi.config import SENTIMENT_MIN_SAMPLES
from youzi.features.blowup import blowup_rate
from youzi.features.echelon import build_echelon, max_board_height
from youzi.features.money_effect import money_effect
from youzi.features.sentiment import normalize_sentiment, raw_sentiment
from youzi.schemas.market import MarketState


def build_market_state(
    day: Date,
    source,                       # MarketDataSource(回放时为 GuardedSource)
    history: list[float],         # 历史 sentiment_raw 序列(仅 ≤ day)
    as_of: DateTime,
    min_samples: int = SENTIMENT_MIN_SAMPLES,
) -> MarketState:
    zt = source.zt_pool(day)
    prev = source.zt_pool_previous(day)
    blow = source.zt_pool_blowup(day)
    dt = source.dt_pool(day)

    limit_up = 0 if zt is None or zt.empty else len(zt)
    blow_n = 0 if blow is None or blow.empty else len(blow)
    dt_n = 0 if dt is None or dt.empty else len(dt)

    me = money_effect(prev)
    br = blowup_rate(zt, blow)
    mh = max_board_height(zt)
    raw = raw_sentiment(mh, limit_up, me, br, dt_n)
    norm = normalize_sentiment(raw, history, min_samples)

    return MarketState(
        date=day,
        max_board_height=mh,
        limit_up_count=limit_up,
        blowup_count=blow_n,
        blowup_rate=br,
        limit_down_count=dt_n,
        echelon=build_echelon(zt),
        money_effect_raw=me,
        sentiment_raw=raw,
        sentiment_norm=norm,
        as_of=as_of,
    )
