"""The canonical teach surface (A8 part a; closes G8's "two teach-ish surfaces over one brain").

Two faces write H through the one gate on a teaching path — Sonia the teacher (full scope) and the
Kairos worker (memory-only, least-privilege) — but each used to hard-code its own `allowed=` tool
set and re-spell its own `EditProvenance(path="teaching", ...)` at its own call site. This module is
the SINGLE SOURCE OF TRUTH for a teach edit's (write scope × provenance stamp); both faces derive
from it. "Unified write scope" = unified AUTHORITY (one place), not an identical tool set: widening
the worker to ALL_TOOLS would break least-privilege, narrowing Sonia to memory-only would break
teach-a-skill. The role-scoping is preserved; only its definition is consolidated.

When A7 retires the worker's proposing path (charter: Kairos does not propose at all), the change is
one line here — not a hunt across faces.

Consuming sites (both a face's PREVIEW and its REAL landing route through this authority — a preview
that resolves a wider scope than the write site would be a least-privilege lie):
  - Sonia:  `alpha/meta/agent.py::preview_op` (preview) + `MetaAgent.apply` (real landing).
  - Kairos: `alpha/converse/tools.py::make_propose_edit_tool` (preview) +
            `workbench/app.py::approve_edit` (real landing — saves the approved staged edit to H).

Not a gate: this module NAMES the write scope; `alpha/refine/apply.py::try_apply_op` still enforces
it. The values returned here are byte-for-byte what the faces used in force before A8.
"""
from __future__ import annotations

from alpha.harness.edit_log import EditProvenance
from alpha.refine.apply import ALL_TOOLS
from alpha.refine.ops import PASS_TOOLS

TEACH_FACES = ("sonia", "kairos")

# The one authority: face -> the tools a teaching edit from that face may touch.
#   sonia  (the teacher) = ALL_TOOLS         — the full playbook is the teacher's to shape
#   kairos (the worker)  = PASS_TOOLS["M"]    — memory-only, least-privilege (A7 retires this leg)
_TEACH_SCOPES: dict[str, frozenset[str]] = {
    "sonia": ALL_TOOLS,
    "kairos": PASS_TOOLS["M"],
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
