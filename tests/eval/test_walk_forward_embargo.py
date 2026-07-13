from datetime import date

import pandas as pd

from alpha.data.source import FakeSource
from alpha.eval.baselines import ChaseBiggestGainerPolicy
from alpha.eval.scorer import ReturnScorer
from alpha.eval.walk_forward import WalkForwardEval


def _source(n, rate=1.15):
    cal = [date(2026, 6, d) for d in range(1, 1 + n)]
    snaps, px, closes = {}, 10.0, []
    for d in cal:
        prev = px; px = px * rate; closes.append(px)
        snaps[d] = pd.DataFrame({"symbol": ["RUN"], "name": ["RUN"], "open": [prev], "high": [px],
                                 "low": [prev], "close": [px], "volume": [1], "prev_close": [prev]})
    bars = {"RUN": pd.DataFrame({"date": cal, "open": [10.0] + closes[:-1], "high": closes,
                                 "low": [10.0] + closes[:-1], "close": closes, "volume": [1] * n})}
    return FakeSource(calendar=cal, bars=bars, snapshots=snaps)


def _run(src, embargo):
    return WalkForwardEval(src, src.trading_calendar()[0], src.trading_calendar()[-1], horizon=2,
                           scorer=ReturnScorer(), embargo=embargo).run(ChaseBiggestGainerPolicy())


def test_embargo_zero_is_byte_identical_to_default():
    src = _source(8)
    base = WalkForwardEval(src, src.trading_calendar()[0], src.trading_calendar()[-1], horizon=2,
                           scorer=ReturnScorer()).run(ChaseBiggestGainerPolicy())        # no embargo kwarg
    z = _run(_source(8), 0)
    assert (base.n_candidates, base.mean_score, base.mean_excess) == (z.n_candidates, z.mean_score, z.mean_excess)


def test_embargo_drops_trailing_scored_decisions():
    # 8 days horizon 2 -> 6 scored decisions; embargo 2 -> 4 scored.
    full = _run(_source(8), 0)
    emb = _run(_source(8), 2)
    assert full.n_candidates == 6
    assert emb.n_candidates == 4
    # decisions are preserved (only the scored SET shrinks)
    assert emb.n_decisions == full.n_decisions
