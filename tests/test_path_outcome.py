# tests/test_path_outcome.py
import pytest

from youzi.eval.oracle import DayMembership, PathOutcome, outcome, path_outcome


def _mem(limit_up=(), blowup=(), limit_down=()):
    return DayMembership(limit_up=frozenset(limit_up), blowup=frozenset(blowup),
                         limit_down=frozenset(limit_down))


def test_all_days_limit_up_is_continued():
    mems = [_mem(limit_up={"A"}), _mem(limit_up={"A"})]
    res = path_outcome("A", mems)
    assert res.outcome == "continued"
    assert res.nuke_index is None


def test_limit_down_any_day_is_nuked_with_first_index():
    mems = [_mem(limit_up={"A"}), _mem(limit_down={"A"})]
    res = path_outcome("A", mems)
    assert res.outcome == "nuked"
    assert res.nuke_index == 1


def test_blowup_is_nuked():
    mems = [_mem(blowup={"A"})]
    assert path_outcome("A", mems).outcome == "nuked"


def test_limit_up_then_off_pool_is_faded():
    # 首日封板、次日掉出三池(既非涨停也非跌停/炸板)→ faded
    mems = [_mem(limit_up={"A"}), _mem(limit_up={"B"})]
    res = path_outcome("A", mems)
    assert res.outcome == "faded"
    assert res.nuke_index is None


def test_first_nuke_index_when_multiple_nuke_days():
    mems = [_mem(limit_up={"A"}), _mem(blowup={"A"}), _mem(limit_down={"A"})]
    assert path_outcome("A", mems).nuke_index == 1


def test_nuke_on_entry_day_index_zero():
    # 入场日(index 0)即跌停:nuke_index=0(T+1 结算细节由 ReturnScorer 处理)
    mems = [_mem(limit_down={"A"}), _mem(limit_up={"A"})]
    res = path_outcome("A", mems)
    assert res.outcome == "nuked"
    assert res.nuke_index == 0


def test_single_day_matches_terminal_outcome():
    # horizon=1 向后兼容:单元素 path_outcome == 现行 outcome(code, mems[0])
    for mem in (_mem(limit_up={"A"}), _mem(limit_down={"A"}),
                _mem(blowup={"A"}), _mem(limit_up={"B"})):
        assert path_outcome("A", [mem]).outcome == outcome("A", mem)


def test_empty_mems_raises():
    with pytest.raises(ValueError):
        path_outcome("A", [])


def test_path_outcome_is_frozen():
    res = PathOutcome(outcome="nuked", nuke_index=0)
    with pytest.raises(Exception):
        res.outcome = "faded"  # type: ignore[misc]
