# tests/universe/test_universe.py
from __future__ import annotations
import pytest
from alpha.universe.stock import StockSnapshot
from alpha.universe.universe import CandidateUniverse


def _snap(symbol, status="gainer", rvol=None):
    return StockSnapshot(symbol=symbol, name=symbol + " Inc", status=status, rvol=rvol)


def test_from_stocks_indexes_by_symbol():
    u = CandidateUniverse.from_stocks([_snap("RUN"), _snap("MOON")])
    assert len(u) == 2
    assert u.get("RUN").symbol == "RUN"


def test_duplicate_symbol_rejected():
    with pytest.raises(ValueError):
        CandidateUniverse.from_stocks([_snap("RUN"), _snap("RUN")])


def test_by_status_and_bool():
    u = CandidateUniverse.from_stocks([_snap("RUN", "gainer"), _snap("DIP", "loser")])
    assert [s.symbol for s in u.by_status("gainer")] == ["RUN"]
    assert bool(CandidateUniverse.from_stocks([])) is True   # empty-but-exists is truthy
