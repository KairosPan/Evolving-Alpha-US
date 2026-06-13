# alpha/universe/universe.py
from __future__ import annotations

from alpha.universe.stock import StockSnapshot, StockStatus


class CandidateUniverse:
    """Daily candidate set indexed by symbol."""

    def __init__(self, stocks: dict[str, StockSnapshot]) -> None:
        self._stocks = dict(stocks)

    @classmethod
    def from_stocks(cls, stocks: list[StockSnapshot]) -> "CandidateUniverse":
        index: dict[str, StockSnapshot] = {}
        for s in stocks:
            if s.symbol in index:
                raise ValueError(f"duplicate symbol: {s.symbol}")
            index[s.symbol] = s
        return cls(index)

    def get(self, symbol: str) -> StockSnapshot | None:
        return self._stocks.get(symbol)

    def all(self) -> list[StockSnapshot]:
        return list(self._stocks.values())

    def by_status(self, status: StockStatus) -> list[StockSnapshot]:
        return [s for s in self._stocks.values() if s.status == status]

    def __len__(self) -> int:
        return len(self._stocks)

    def __bool__(self) -> bool:
        return True
