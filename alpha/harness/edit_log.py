from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict


class EditProvenance(BaseModel):
    """Who proposed an edit and on what basis (spec §5.3). Stamped at the gate, never by MetaTools."""
    model_config = ConfigDict(frozen=True)
    path: Literal["self_study", "teaching"]
    proposer: Literal["refiner", "forge", "sonia", "hermes"]
    evidence_kind: Literal["trade", "task"] | None = None  # None = legacy/trade-equivalent
    evidence_ref: dict | None = None
    reflection_lm_id: str | None = None
    reflection_seed: int | None = None
    human_approver: str | None = None
    parent_checkpoint_version: int | None = None
    resolution: str | None = None


class EditRecord(BaseModel):
    """Δ audit record for one harness edit (the inner-loop CRUD trajectory)."""
    model_config = ConfigDict(frozen=True)
    seq: int
    tool: str                       # write_skill / patch_skill / ... / rewrite_doctrine
    target_kind: str                # skill | memory | doctrine
    target_id: str                  # skill_id / lesson_id / section
    op: str                         # create | update | retire | revive | promote | demote | rewrite
    summary: str = ""
    payload: dict | None = None     # before/after, etc. (consumed by US-1c rollback)
    rationale: str = ""             # why the Refiner made the edit
    provenance: EditProvenance | None = None    # stamped at the gate (§5.3); None for legacy/ungated records


class EditLog:
    """Append-only edit audit trail. Serializes via to_dict/from_dict (US-1c persistence)."""

    def __init__(self) -> None:
        self._records: list[EditRecord] = []

    def append(self, tool: str, target_kind: str, target_id: str, op: str,
               summary: str = "", payload: dict | None = None, rationale: str = "") -> EditRecord:
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

    def stamp_last(self, provenance: "EditProvenance") -> EditRecord:
        """Replace the most-recently-appended record with a provenance-stamped copy (frozen-safe)."""
        if not self._records:
            raise IndexError("no record to stamp")
        self._records[-1] = self._records[-1].model_copy(update={"provenance": provenance})
        return self._records[-1]

    def latest_for(self, target_kind: str, target_id: str) -> EditRecord | None:
        """The most recent record touching (target_kind, target_id), or None."""
        for r in reversed(self._records):
            if r.target_kind == target_kind and r.target_id == target_id:
                return r
        return None

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
