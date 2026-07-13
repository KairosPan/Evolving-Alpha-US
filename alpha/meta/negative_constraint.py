"""Negative constraints — human-rejection mining for the self-learning channel (A3).

When the user DISCARDS a reflection→directions proposal in the cockpit, each direction it carried
becomes a NegativeConstraint keyed by its (tool:target_id) signature. The reflection detector reads
`signatures()` and SUPPRESSES any matching direction, so a rejected direction is **never
re-proposed** — the two-learning-paths rule: self-study forks-and-proposes, and the human's "no" is
consumed as a constraint, not a re-surfaced proposal.

Flat by-id JSON store (the ConflictQueue file pattern). Not coupled to brain edit-seqs — a signature
survives a brain rollback — so no cross-face reconcile-sweep coupling (unlike the brain-state dirs).
"""
from __future__ import annotations

import os
import tempfile
from pathlib import Path

from pydantic import BaseModel

from alpha.meta.models import new_session_id, now_iso


class NegativeConstraint(BaseModel):
    constraint_id: str
    created_at: str
    signature: str                 # "{tool}:{target_id}" — the rejected direction's stable key
    tool: str = ""
    target_id: str = ""
    reason: str = ""
    source_proposal_id: str = ""


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


class NegativeConstraintStore:
    """Flat by-id store of rejected-direction signatures (atomic write, newest-first listing)."""

    def __init__(self, root: str | Path) -> None:
        self._root = Path(root)

    def _path(self, constraint_id: str) -> Path:
        p = (self._root / f"{constraint_id}.json").resolve()
        if not p.is_relative_to(self._root.resolve()):
            raise ValueError(f"invalid constraint_id: {constraint_id!r}")
        return p

    def add(self, *, signature: str, tool: str = "", target_id: str = "", reason: str = "",
            source_proposal_id: str = "") -> NegativeConstraint:
        cid = new_session_id()
        c = NegativeConstraint(constraint_id=cid, created_at=now_iso(), signature=signature,
                               tool=tool, target_id=target_id, reason=reason,
                               source_proposal_id=source_proposal_id)
        _atomic_write(self._path(cid), c.model_dump_json())
        return c

    def all(self) -> list[NegativeConstraint]:
        if not self._root.is_dir():
            return []
        out: list[NegativeConstraint] = []
        for p in self._root.glob("*.json"):
            try:
                out.append(NegativeConstraint.model_validate_json(p.read_text(encoding="utf-8")))
            except Exception:
                continue
        return sorted(out, key=lambda c: c.constraint_id, reverse=True)

    def signatures(self) -> frozenset[str]:
        """The set of rejected direction signatures the detector must not re-propose."""
        return frozenset(c.signature for c in self.all())

    def resolve(self, constraint_id: str) -> None:
        self._path(constraint_id).unlink(missing_ok=True)
