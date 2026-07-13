from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict

from alpha.integrity import sha256_canonical_json


class EditProvenance(BaseModel):
    """Who proposed an edit and on what basis (spec §5.3). Stamped at the gate, never by MetaTools.
    path "user_direct" = the charter's second hand (2026-07-08): the User's own edit through the
    same gate — stamped and audited, no deliberation. proposer "hermes" is retired vocabulary
    (pre-rename worker face) kept so persisted brains still validate; new records use "kairos"."""
    model_config = ConfigDict(frozen=True)
    path: Literal["self_study", "teaching", "user_direct"]
    proposer: Literal["refiner", "forge", "sonia", "hermes", "kairos", "user"]
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
    # Append-time integrity chain (A4; charter *Trust Roots → Record integrity*). Both default None
    # = unchained; finalized at persist time by the store's save() → EditLog.finalize_chain(). A
    # legacy snapshot loads with both None (an unchained prefix) and is tolerated by verify_chain().
    prev_chain_hash: str | None = None
    chain_hash: str | None = None


def _record_chain_hash(prev_chain_hash: str | None, rec: "EditRecord") -> str:
    """Hash of a record's content (EXCLUDING the two chain fields) salted by its predecessor's
    chain_hash, via the one canonicalizer (alpha.integrity). Hashes VERBATIM content: payload is a
    rollback-replay payload alpha/redact.py forbids scrubbing, so the audit log is never redacted —
    the redact-before-hash ordering invariant governs the (separate) session-message stream."""
    content = rec.model_dump(mode="json", exclude={"prev_chain_hash", "chain_hash"})
    return sha256_canonical_json({"prev": prev_chain_hash, "rec": content})


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
        # Reset the chain on the rewritten record: stamping changes hashed content, so any chain
        # finalized before the stamp must be recomputed at the next finalize_chain (persist time).
        self._records[-1] = self._records[-1].model_copy(
            update={"provenance": provenance, "prev_chain_hash": None, "chain_hash": None})
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

    def finalize_chain(self) -> None:
        """Compute the integrity chain over every currently-unchained record, linking from genesis
        (idempotent). Already-chained records (a loaded, previously-persisted brain) are preserved
        and advance `prev`; only unchained records (fresh appends, or a legacy brain being persisted
        for the first time under the feature) are hashed. Called at persist time by the store's
        save() — persist-time not append-time because stamp_last rewrites the last record after
        append, so the chain must wait until provenance is final."""
        prev: str | None = None
        for i, r in enumerate(self._records):
            if r.chain_hash is None:
                ch = _record_chain_hash(prev, r)
                self._records[i] = r.model_copy(update={"prev_chain_hash": prev, "chain_hash": ch})
                prev = ch
            else:
                prev = r.chain_hash

    def verify_chain(self) -> bool:
        """True iff the chained region is internally consistent (charter *Record integrity*).
        Tolerates a leading unchained legacy prefix and a pure trailing not-yet-finalized run; an
        unchained HOLE between chained records (storage loss/reorder/interior edit) fails."""
        prev: str | None = None
        started = False
        for i, r in enumerate(self._records):
            if r.chain_hash is None:
                if started:                                   # a gap after the chain began ...
                    if all(x.chain_hash is None for x in self._records[i:]):
                        return True                           # ... benign trailing unfinalized run
                    return False                              # ... interior hole = corruption
                continue                                      # still in the legacy prefix
            if r.prev_chain_hash != prev:
                return False
            if r.chain_hash != _record_chain_hash(r.prev_chain_hash, r):
                return False
            started = True
            prev = r.chain_hash
        return True

    def chain_head(self) -> str | None:
        """The external anchor: the last record's chain_hash (None on an empty/legacy-only log).
        Corruption-detection only without an out-of-band anchor (accepted T2-shell posture)."""
        return self._records[-1].chain_hash if self._records else None

    def to_dict(self) -> list[dict]:
        # mode="json": payloads may embed date-typed fields (e.g. a lesson's learned_asof);
        # json.dumps consumers crash on python-mode date objects. from_dict re-validates.
        # PURE (no finalize): serialization is not persistence — the chain is finalized by the
        # store's save() before it calls to_dict(), so a to_dict() over an unfinalized log dumps
        # unchained records byte-identically to the pre-A4 log (the evolution packet relies on
        # to_dict == per-record model_dump).
        return [r.model_dump(mode="json") for r in self._records]

    @classmethod
    def from_dict(cls, data: list[dict]) -> "EditLog":
        log = cls()
        log._records = [EditRecord.model_validate(r) for r in data]
        return log
