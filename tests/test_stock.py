from youzi.universe.stock import StockSnapshot


def test_stock_snapshot_minimal_and_full():
    s = StockSnapshot(code="000001", name="甲", status="limit_up", boards=3)
    assert s.code == "000001" and s.status == "limit_up" and s.boards == 3
    assert s.pct is None and s.seal_amount is None      # 缺失为 None, 不臆造
    full = StockSnapshot(code="300xxx", name="乙", status="blowup", boards=0,
                         pct=-2.0, seal_amount=None, turnover_rate=12.3,
                         first_seal_time="09:31:00", blowup_count=2,
                         industry="芯片", float_mcap=5.0e9)
    assert full.status == "blowup" and full.blowup_count == 2


def test_stock_snapshot_is_frozen():
    import pytest
    from pydantic import ValidationError
    s = StockSnapshot(code="1", name="甲", status="limit_up")
    with pytest.raises(ValidationError):
        s.boards = 9            # PIT 快照不可变


def test_stock_snapshot_status_validated():
    import pytest
    from pydantic import ValidationError
    with pytest.raises(ValidationError):
        StockSnapshot(code="1", name="甲", status="不存在的状态")


def test_minimal_limit_up_boards_unknown_is_none():
    s = StockSnapshot(code="1", name="甲", status="limit_up")
    assert s.boards is None      # 未提供时不臆造为 0
