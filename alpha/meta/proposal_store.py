"""Evolution proposal packets (charter conformance 2026-07-09): the live self-study runners no
longer land edits on the live brain — they run on a fork and package the surviving delta as an
EvolutionProposal for the USER to adopt or discard. Flat by-id store, ConflictQueue file pattern."""
from __future__ import annotations

import os
import tempfile
from pathlib import Path

from pydantic import BaseModel, Field

from alpha.integrity import canonical_json, sha256_canonical_json
from alpha.meta.models import new_session_id, now_iso

PROPOSALS_DIR_ENV = "ALPHA_PROPOSALS_DIR"
DEFAULT_PROPOSALS_DIR = "./state/proposals"


def proposals_dir() -> str:
    return os.environ.get(PROPOSALS_DIR_ENV, DEFAULT_PROPOSALS_DIR)


def brain_hash(harness_dict: dict, log_dict: list[dict]) -> str:
    return sha256_canonical_json({"harness": harness_dict, "log": log_dict})


class EvolutionProposal(BaseModel):
    """One packaged fork run: the surviving edit delta + the evolved brain, pinned to its exact
    base body-version by content hash. Adoption is user-authority; the packet never self-lands."""
    proposal_id: str
    created_at: str
    kind: str                                   # "refine" | "forge"
    base_len: int                               # live log length at fork time
    base_hash: str                              # brain_hash(...) at fork time — the staleness pin
    window: dict = Field(default_factory=dict)  # e.g. {"start": ..., "end": ...}
    summary: str = ""
    records: list[dict] = Field(default_factory=list)   # the delta, for the user's review
    harness_dict: dict = Field(default_factory=dict)    # the evolved fork brain
    log_dict: list[dict] = Field(default_factory=list)  # the evolved fork log (full)


def _atomic_write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=path.parent, suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(text)
        os.replace(tmp, path)
    except BaseException:
        if os.path.exists(tmp):
            os.unlink(tmp)
        raise


class ProposalQueue:
    """Flat by-id store of pending evolution proposals (atomic write, newest-first listing)."""

    def __init__(self, root: str | Path) -> None:
        self._root = Path(root)

    def _path(self, proposal_id: str) -> Path:
        # proposal_id may come from a URL param; never let `..`/absolute paths escape the store.
        p = (self._root / f"{proposal_id}.json").resolve()
        if not p.is_relative_to(self._root.resolve()):
            raise ValueError(f"invalid proposal_id: {proposal_id!r}")
        return p

    def new(self, **fields) -> EvolutionProposal:
        prop = EvolutionProposal(proposal_id=new_session_id(), created_at=now_iso(), **fields)
        self.put(prop)
        return prop

    def put(self, proposal: EvolutionProposal) -> None:
        _atomic_write(self._path(proposal.proposal_id), proposal.model_dump_json())

    def get(self, proposal_id: str) -> EvolutionProposal | None:
        p = self._path(proposal_id)
        if not p.exists():
            return None
        return EvolutionProposal.model_validate_json(p.read_text(encoding="utf-8"))

    def all(self) -> list[EvolutionProposal]:
        if not self._root.is_dir():
            return []
        out: list[EvolutionProposal] = []
        for p in self._root.glob("*.json"):
            try:
                out.append(EvolutionProposal.model_validate_json(p.read_text(encoding="utf-8")))
            except Exception:
                continue
        return sorted(out, key=lambda x: x.proposal_id, reverse=True)

    def resolve(self, proposal_id: str) -> None:
        self._path(proposal_id).unlink(missing_ok=True)
