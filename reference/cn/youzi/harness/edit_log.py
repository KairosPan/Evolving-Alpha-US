from __future__ import annotations

from pydantic import BaseModel, ConfigDict


class EditRecord(BaseModel):
    """一次 Harness 编辑的 Δ 审计记录(蓝图 §4 inner-loop CRUD 轨迹)。"""
    model_config = ConfigDict(frozen=True)
    seq: int
    tool: str                # write_skill / patch_skill / ... / rewrite_doctrine
    target_kind: str         # skill | memory | doctrine
    target_id: str           # skill_id / lesson_id / section
    op: str                  # create | update | retire | revive | promote | demote | rewrite
    summary: str = ""
    payload: dict | None = None   # old→new 等结构化负载,为 0b-3 回滚预留
    rationale: str = ""           # Refiner 给出的编辑理由(默认空,向后兼容)


class EditLog:
    """编辑审计 Δ 轨迹(append-only);EditRecord 可带 payload(old→new 等),为 Phase-0b-3 版本化/回滚预留。"""

    def __init__(self) -> None:
        self._records: list[EditRecord] = []

    def append(self, tool: str, target_kind: str, target_id: str,
               op: str, summary: str = "", payload: dict | None = None,
               rationale: str = "") -> EditRecord:
        rec = EditRecord(seq=len(self._records), tool=tool, target_kind=target_kind,
                         target_id=target_id, op=op, summary=summary, payload=payload,
                         rationale=rationale)
        self._records.append(rec)
        return rec

    def records(self) -> list[EditRecord]:
        return list(self._records)

    def by_kind(self, target_kind: str) -> list[EditRecord]:
        return [r for r in self._records if r.target_kind == target_kind]

    def by_tool(self, tool: str) -> list[EditRecord]:
        return [r for r in self._records if r.tool == tool]

    def __len__(self) -> int:
        return len(self._records)

    def __bool__(self) -> bool:
        return True

    def to_dict(self) -> list[dict]:
        return [r.model_dump() for r in self._records]

    @classmethod
    def from_dict(cls, data: list[dict]) -> "EditLog":
        log = cls()
        log._records = [EditRecord.model_validate(r) for r in data]
        return log
