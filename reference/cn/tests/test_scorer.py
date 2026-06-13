# tests/test_scorer.py
from datetime import date

import pandas as pd

from youzi.eval.scorer import PoolScorer, ReturnScorer
from youzi.eval.oracle import DayMembership
from youzi.eval.decision import DecisionPackage, Candidate
from tests.conftest import FakeSource


def _decision(*codes):
    return DecisionPackage(date=date(2026, 6, 1),
                           candidates=[Candidate(code=c, name=c, pattern="p") for c in codes])


def _ohlcv(rows):
    return pd.DataFrame(rows, columns=["date", "open", "high", "low", "close", "volume"])


def test_pool_scorer_matches_pool_membership():
    mem = DayMembership(limit_up=frozenset({"A"}), blowup=frozenset(),
                        limit_down=frozenset({"B"}))
    out = PoolScorer().score_step(_decision("A", "B", "A"), [mem],
                                  date(2026, 6, 2), date(2026, 6, 2), None)
    assert set(out) == {"A", "B"}                       # 去重
    assert out["A"].outcome == "continued" and out["A"].score == 1.0
    assert out["B"].outcome == "nuked" and out["B"].score == -1.0


def test_return_scorer_uses_return_and_drops_missing():
    mem = DayMembership(limit_up=frozenset({"A"}), blowup=frozenset(),
                        limit_down=frozenset())
    # A 有 OHLCV:entry open@6/2=10 → exit close@6/3=12 → +0.20;B 无 OHLCV → 丢弃
    df = _ohlcv([(date(2026, 6, 2), 10.0, 11, 9, 10.5, 100),
                 (date(2026, 6, 3), 10.6, 12.5, 10, 12.0, 200)])
    src = FakeSource({}, [], ohlcv={"A": df})
    out = ReturnScorer().score_step(_decision("A", "B"), [mem],
                                    date(2026, 6, 2), date(2026, 6, 3), src)
    assert set(out) == {"A"}                             # B 缺收益被丢弃
    assert out["A"].outcome == "continued"               # outcome 仍池类别
    assert out["A"].score == 0.20                        # score = 收益


# ── C2:day_baseline / advantage ──────────────────────────────────────────────

def test_pool_scorer_day_baseline_and_advantage_hand_computed():
    # 决策日池 {A, C};exit 日:A continued(+1)、C 掉出全部池 → faded(0)
    # → day_baseline = (1+0)/2 = 0.5(闭眼买全池的同日期望)
    decision_mem = DayMembership(limit_up=frozenset({"A", "C"}), blowup=frozenset(),
                                 limit_down=frozenset())
    mem = DayMembership(limit_up=frozenset({"A"}), blowup=frozenset(),
                        limit_down=frozenset({"B"}))
    out = PoolScorer().score_step(_decision("A", "B"), [mem],
                                  date(2026, 6, 2), date(2026, 6, 2), None,
                                  decision_mem=decision_mem)
    assert out["A"].day_baseline == 0.5
    assert out["A"].advantage == 0.5                     # 1.0 − 0.5
    assert out["B"].advantage == -1.5                    # nuked:−1.0 − 0.5
    assert out["A"].score == 1.0                         # 原始分不动


def test_pool_scorer_empty_pool_baseline_none_advantage_falls_back():
    # 空池日约定:决策日 limit_up 空(或 decision_mem=None)→ baseline=None,advantage 回退=score
    mem = DayMembership(limit_up=frozenset({"A"}), blowup=frozenset(), limit_down=frozenset())
    empty = DayMembership(limit_up=frozenset(), blowup=frozenset(), limit_down=frozenset())
    for dm in (empty, None):
        out = PoolScorer().score_step(_decision("A"), [mem],
                                      date(2026, 6, 2), date(2026, 6, 2), None,
                                      decision_mem=dm)
        assert out["A"].day_baseline is None
        assert out["A"].advantage == out["A"].score == 1.0


def test_return_scorer_day_baseline_pool_mean_return():
    # 决策日池 {A, B, C}:A +0.20、B −0.10、C 无 OHLCV(剔除,与"缺收益丢弃"一致)
    # → 基线 = (0.20 − 0.10)/2 = 0.05;候选 A 的超额 = 0.20 − 0.05 = 0.15
    decision_mem = DayMembership(limit_up=frozenset({"A", "B", "C"}), blowup=frozenset(),
                                 limit_down=frozenset())
    mem = DayMembership(limit_up=frozenset({"A", "B"}), blowup=frozenset(), limit_down=frozenset())
    df_a = _ohlcv([(date(2026, 6, 2), 10.0, 13, 9, 12.0, 100)])    # +0.20
    df_b = _ohlcv([(date(2026, 6, 2), 10.0, 11, 8, 9.0, 100)])     # −0.10
    src = FakeSource({}, [], ohlcv={"A": df_a, "B": df_b})
    out = ReturnScorer().score_step(_decision("A"), [mem],
                                    date(2026, 6, 2), date(2026, 6, 2), src,
                                    decision_mem=decision_mem)
    assert abs(out["A"].day_baseline - 0.05) < 1e-9
    assert abs(out["A"].advantage - 0.15) < 1e-9
    assert out["A"].score == 0.20                        # 原始分不动


def test_return_scorer_baseline_none_when_pool_has_no_returns():
    # 池成员全缺 OHLCV → 基线 None;候选 A 自己有收益 → advantage 回退=score
    decision_mem = DayMembership(limit_up=frozenset({"Z"}), blowup=frozenset(),
                                 limit_down=frozenset())
    mems = [DayMembership(limit_up=frozenset({"A"}), blowup=frozenset(), limit_down=frozenset())]
    df_a = _ohlcv([(date(2026, 6, 2), 10.0, 13, 9, 12.0, 100)])    # +0.20
    src = FakeSource({}, [], ohlcv={"A": df_a})
    out = ReturnScorer().score_step(_decision("A"), mems,
                                    date(2026, 6, 2), date(2026, 6, 2), src,
                                    decision_mem=decision_mem)
    assert out["A"].day_baseline is None
    assert out["A"].advantage == out["A"].score == 0.20


# ── C3 slice 3:协议 mem → mems(持有路径逐日成员);PoolScorer 取 mems[-1] ──────

def test_pool_scorer_uses_exit_day_from_mems_path():
    # 新协议:mems=entry..exit 逐日成员;PoolScorer 用 mems[-1](exit 日)保持终点语义。
    # 入场日 A 封板,exit 日 A 跌停 → 终点判 nuked(证 mems[-1] 被采用,非 mems[0])。
    entry_mem = DayMembership(limit_up=frozenset({"A"}), blowup=frozenset(), limit_down=frozenset())
    exit_mem = DayMembership(limit_up=frozenset(), blowup=frozenset(), limit_down=frozenset({"A"}))
    out = PoolScorer().score_step(_decision("A"), [entry_mem, exit_mem],
                                  date(2026, 6, 2), date(2026, 6, 3), None)
    assert out["A"].outcome == "nuked"
    assert out["A"].score == -1.0
