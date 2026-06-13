from youzi.universe.stock import StockSnapshot
from youzi.universe.universe import CandidateUniverse


def _stocks():
    return [
        StockSnapshot(code="1", name="龙", status="limit_up", boards=7, industry="芯片"),
        StockSnapshot(code="2", name="中", status="limit_up", boards=3, industry="芯片"),
        StockSnapshot(code="3", name="炸", status="blowup", boards=0, industry="军工"),
        StockSnapshot(code="4", name="跌", status="limit_down", boards=0, industry="军工"),
    ]


def test_universe_queries():
    u = CandidateUniverse.from_stocks(_stocks())
    assert u.get("1").name == "龙" and u.get("zzz") is None
    assert {s.code for s in u.by_status("limit_up")} == {"1", "2"}
    assert {s.code for s in u.by_min_boards(3)} == {"1", "2"}       # 连板>=3
    assert {s.code for s in u.by_min_boards(7)} == {"1"}
    assert {s.code for s in u.by_industry("芯片")} == {"1", "2"}
    assert len(u) == 4


def test_universe_rejects_duplicate_code():
    import pytest
    with pytest.raises(ValueError):
        CandidateUniverse.from_stocks([_stocks()[0], _stocks()[0]])


def test_empty_universe_is_truthy():
    u = CandidateUniverse.from_stocks([])
    assert bool(u) is True and len(u) == 0          # 杀 falsy-trap(0b-3 教训)


def test_build_universe_merges_three_pools():
    from datetime import date
    import pandas as pd
    from youzi.universe.universe import build_universe
    from tests.conftest import FakeSource

    d = date(2024, 6, 27)
    frames = {
        ("zt", d): pd.DataFrame({"code": ["1", "2"], "name": ["龙", "中"],
                                 "boards": [7, 3], "pct": [10.0, 10.0],
                                 "seal_amount": [8e8, 2e8], "industry": ["芯片", "芯片"]}),
        ("blowup", d): pd.DataFrame({"code": ["3"], "name": ["炸"], "pct": [3.0],
                                     "blowups": [2], "industry": ["军工"]}),
        ("dt", d): pd.DataFrame({"code": ["4"], "name": ["跌"], "pct": [-10.0],
                                 "industry": ["军工"]}),
    }
    u = build_universe(FakeSource(frames, [d]), d)
    assert len(u) == 4
    assert u.get("1").status == "limit_up" and u.get("1").boards == 7
    assert u.get("1").seal_amount == 8e8
    assert u.get("3").status == "blowup" and u.get("3").blowup_count == 2
    assert u.get("4").status == "limit_down"


def test_build_universe_empty_day():
    from datetime import date
    import pandas as pd
    from youzi.universe.universe import build_universe
    from tests.conftest import FakeSource
    d = date(2024, 6, 27)
    empty = {("zt", d): pd.DataFrame(), ("blowup", d): pd.DataFrame(),
             ("dt", d): pd.DataFrame()}
    u = build_universe(FakeSource(empty, [d]), d)
    assert len(u) == 0 and bool(u) is True


def test_build_universe_handles_nat_and_missing_fields():
    from datetime import date
    import pandas as pd
    from youzi.universe.universe import build_universe
    from tests.conftest import FakeSource
    d = date(2024, 6, 27)
    frames = {
        ("zt", d): pd.DataFrame(),
        ("blowup", d): pd.DataFrame(),
        # boards / industry 列缺失; first_seal_time = NaT
        ("dt", d): pd.DataFrame({"code": ["4"], "name": ["跌"], "pct": [-10.0],
                                 "first_seal_time": [pd.NaT]}),
    }
    s = build_universe(FakeSource(frames, [d]), d).get("4")
    assert s.status == "limit_down"
    assert s.first_seal_time is None     # NaT -> None(不存成 "NaT")
    assert s.boards is None              # 缺列 -> None
    assert s.industry is None
