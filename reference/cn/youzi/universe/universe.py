from __future__ import annotations

import pandas as pd

from youzi.universe.stock import StockSnapshot, StockStatus


class CandidateUniverse:
    """某交易日按 code 索引的候选个股集合(涨停/炸板/跌停)。"""

    def __init__(self, stocks: dict[str, StockSnapshot]) -> None:
        self._stocks = dict(stocks)          # 防御性拷贝

    @classmethod
    def from_stocks(cls, stocks: list[StockSnapshot]) -> "CandidateUniverse":
        index: dict[str, StockSnapshot] = {}
        for s in stocks:
            if s.code in index:
                raise ValueError(f"重复 code: {s.code}")
            index[s.code] = s
        return cls(index)

    def get(self, code: str) -> StockSnapshot | None:
        return self._stocks.get(code)

    def all(self) -> list[StockSnapshot]:
        return list(self._stocks.values())

    def by_status(self, status: StockStatus) -> list[StockSnapshot]:
        return [s for s in self._stocks.values() if s.status == status]

    def by_min_boards(self, n: int) -> list[StockSnapshot]:
        return [s for s in self._stocks.values() if s.boards is not None and s.boards >= n]

    def by_industry(self, industry: str) -> list[StockSnapshot]:
        return [s for s in self._stocks.values() if s.industry == industry]

    def __len__(self) -> int:
        return len(self._stocks)

    def __bool__(self) -> bool:
        return True              # 空但存在的 universe 仍为真(杀 falsy-trap)


def _to_snapshot(row: dict, status: str) -> StockSnapshot:
    def g(key, cast=None):
        v = row.get(key)
        if v is None or pd.isna(v):
            return None
        return cast(v) if cast else v
    return StockSnapshot(
        code=str(row["code"]),
        name=str(row.get("name", "")),
        status=status,
        boards=(int(b) if (b := g("boards")) is not None else None),
        pct=g("pct", float),
        seal_amount=g("seal_amount", float),
        turnover_rate=g("turnover_rate", float),
        first_seal_time=g("first_seal_time", str),
        blowup_count=(int(bc) if (bc := g("blowups")) is not None else None),
        industry=g("industry", str),
        float_mcap=g("float_mcap", float),
    )


def build_universe(source, day) -> CandidateUniverse:
    """合成当日候选 universe。顺序 dt→blowup→zt,涨停最后写入(冲突时 limit_up 优先)。"""
    stocks: dict[str, StockSnapshot] = {}
    for fetch, status in ((source.dt_pool, "limit_down"),
                          (source.zt_pool_blowup, "blowup"),
                          (source.zt_pool, "limit_up")):
        df = fetch(day)
        if df is None or df.empty:
            continue
        for rec in df.to_dict("records"):
            snap = _to_snapshot(rec, status)
            stocks[snap.code] = snap
    return CandidateUniverse(stocks)
