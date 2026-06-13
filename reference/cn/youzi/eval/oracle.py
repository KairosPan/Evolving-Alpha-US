from __future__ import annotations

from dataclasses import dataclass
from datetime import date as Date
from typing import Literal

from youzi.universe.universe import CandidateUniverse

Outcome = Literal["continued", "faded", "nuked"]

SCORE: dict[str, float] = {"continued": 1.0, "faded": 0.0, "nuked": -1.0}


@dataclass(frozen=True)
class DayMembership:
    """某交易日三池的 code 成员(用于事后判定被选标的的结果)。"""
    limit_up: frozenset[str]
    blowup: frozenset[str]
    limit_down: frozenset[str]


class PoolRecord:
    """按交易日录制 pool 成员;walk-forward 每到一个游标录一天(只录 ≤ 游标)。"""

    def __init__(self) -> None:
        self._by_day: dict[Date, DayMembership] = {}

    def record(self, day: Date, universe: CandidateUniverse) -> None:
        self._by_day[day] = DayMembership(
            limit_up=frozenset(s.code for s in universe.by_status("limit_up")),
            blowup=frozenset(s.code for s in universe.by_status("blowup")),
            limit_down=frozenset(s.code for s in universe.by_status("limit_down")),
        )

    def get(self, day: Date) -> DayMembership | None:
        return self._by_day.get(day)


def outcome(code: str, mem: DayMembership) -> Outcome:
    """已实现未来类别:horizon 天后该 code 在哪个池。跌停/炸板优先判 nuked。"""
    if code in mem.limit_down or code in mem.blowup:
        return "nuked"
    if code in mem.limit_up:
        return "continued"
    return "faded"


@dataclass(frozen=True)
class PathOutcome:
    """路径感知结算结果:outcome 类别 + 首个 nuked 日下标(stop-on-nuke 定价用)。"""
    outcome: Outcome
    nuke_index: int | None = None   # mems 中首个 nuked 日下标;未 nuked = None


def path_outcome(code: str, mems: list[DayMembership]) -> PathOutcome:
    """路径感知结算:扫 entry..exit 逐日成员(C3 proposal 4 + revision 3/5)。

    任一日 limit_down/blowup → nuked 且 stop-on-nuke(记首个 nuked 日下标,
    定价在 ReturnScorer 处理 T+1 顺延);全程 limit_up → continued;否则 faded。
    单元素 mems(horizon=1)结果 == 现行 outcome(code, mems[0]),向后兼容。
    """
    if not mems:
        raise ValueError("mems 不能为空(holding path 至少一日)")
    for i, mem in enumerate(mems):
        if code in mem.limit_down or code in mem.blowup:
            return PathOutcome(outcome="nuked", nuke_index=i)
    if all(code in mem.limit_up for mem in mems):
        return PathOutcome(outcome="continued")
    return PathOutcome(outcome="faded")
