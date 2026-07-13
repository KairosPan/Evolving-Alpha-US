"""The canonical teach surface (A8 part a; closes G8's "two teach-ish surfaces over one brain").

Originally two faces wrote H through the one gate on a teaching path — Sonia the teacher (full
scope) and the Kairos worker (memory-only, least-privilege). A7 (2026-07-13, charter First Founding
Principle: "Kairos does not propose at all") RETIRED the worker leg — this was the "one line here"
the A8 consolidation anticipated. Sonia is now the sole teach face; `teach_scope("kairos")` /
`teach_provenance("kairos")` raise (unknown face). The worker's H-mutation propose path is gone
(no `propose_memory_edit` tool; the gate refuses `proposer="kairos"`); it keeps compute-use only.

This module is the SINGLE SOURCE OF TRUTH for a teach edit's (write scope × provenance stamp);
Sonia's PREVIEW and REAL landing both derive from it (a preview that resolves a wider scope than the
write site would be a least-privilege lie):
  - Sonia: `alpha/meta/agent.py::preview_op` (preview) + `MetaAgent.apply` (real landing).

Not a gate: this module NAMES the write scope; `alpha/refine/apply.py::try_apply_op` still enforces
it (and refuses the retired worker origin). The sonia value is byte-for-byte what it was before A7.
"""
from __future__ import annotations

from alpha.harness.edit_log import EditProvenance
from alpha.refine.apply import ALL_TOOLS

TEACH_FACES = ("sonia",)

# The one authority: face -> the tools a teaching edit from that face may touch.
#   sonia (the teacher) = ALL_TOOLS — the full playbook is the teacher's to shape.
# The kairos (worker) leg was retired by A7 (the worker does not propose); Sonia is the sole face.
_TEACH_SCOPES: dict[str, frozenset[str]] = {
    "sonia": ALL_TOOLS,
}


def teach_scope(face: str) -> frozenset[str]:
    """The tools a teaching edit from `face` may touch — the canonical write scope."""
    try:
        return _TEACH_SCOPES[face]
    except KeyError:
        raise ValueError(f"unknown teach face {face!r}; expected one of {TEACH_FACES}") from None


def teach_provenance(face: str, *, human_approver: str | None = None) -> EditProvenance:
    """The canonical teaching stamp: path='teaching', proposer=face, human_approver forwarded.
    `face` must be a known teach face (validated the same way `teach_scope` validates it)."""
    if face not in _TEACH_SCOPES:
        raise ValueError(f"unknown teach face {face!r}; expected one of {TEACH_FACES}")
    return EditProvenance(path="teaching", proposer=face, human_approver=human_approver)
