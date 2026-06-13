from datetime import date
from youzi.universe.stock import StockSnapshot
from youzi.universe.universe import CandidateUniverse
from youzi.eval.oracle import PoolRecord, DayMembership, outcome, SCORE


def _uni(limit_up, blowup, limit_down):
    stocks = [StockSnapshot(code=c, name=c, status="limit_up") for c in limit_up]
    stocks += [StockSnapshot(code=c, name=c, status="blowup") for c in blowup]
    stocks += [StockSnapshot(code=c, name=c, status="limit_down") for c in limit_down]
    return CandidateUniverse.from_stocks(stocks)


def test_pool_record_and_get():
    rec = PoolRecord()
    d = date(2024, 6, 28)
    rec.record(d, _uni(["A", "B"], ["C"], ["D"]))
    mem = rec.get(d)
    assert isinstance(mem, DayMembership)
    assert mem.limit_up == frozenset({"A", "B"}) and mem.limit_down == frozenset({"D"})
    assert rec.get(date(2024, 6, 29)) is None


def test_pool_record_same_day_overwrites():
    rec = PoolRecord(); d = date(2024, 6, 28)
    rec.record(d, _uni(["A"], [], []))
    rec.record(d, _uni(["B"], [], []))      # 同日重录覆盖
    assert rec.get(d).limit_up == frozenset({"B"})


def test_outcome_categories():
    mem = DayMembership(limit_up=frozenset({"A"}), blowup=frozenset({"C"}),
                        limit_down=frozenset({"D"}))
    assert outcome("A", mem) == "continued"      # 次日仍涨停
    assert outcome("D", mem) == "nuked"          # 次日跌停
    assert outcome("C", mem) == "nuked"          # 次日炸板
    assert outcome("Z", mem) == "faded"          # 掉出
    assert SCORE["continued"] == 1.0 and SCORE["nuked"] == -1.0 and SCORE["faded"] == 0.0
