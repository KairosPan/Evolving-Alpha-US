from __future__ import annotations

import copy

from alpha.harness.edit_log import EditLog, EditRecord
from alpha.harness.metatools import MetaTools
from alpha.harness.state import HarnessState
from alpha.llm.client import LLMClient
from alpha.meta.models import ProposedEdit, new_edit_id
from alpha.meta.teach_surface import teach_provenance, teach_scope
from alpha.refine.apply import try_apply_op
from alpha.refine.ops import RefineOp

_KIND = {
    "write_skill": "skill", "patch_skill": "skill", "retire_skill": "skill",
    "revive_skill": "skill", "promote_skill": "skill",
    "process_memory": "memory", "update_memory": "memory", "demote_memory": "memory",
    "rewrite_doctrine": "doctrine",
}


def preview_op(harness: HarnessState, op: RefineOp, *, retire_min: int = 5, promote_min: int = 3) -> ProposedEdit:
    """Dry-run one op on a deepcopy of the brain; never mutates `harness`. Returns a ProposedEdit
    (status 'proposed' with payload on success, 'failed' + apply_reason on rejection)."""
    scratch = copy.deepcopy(harness)
    rec, reason = try_apply_op(MetaTools(scratch, EditLog()), scratch, op, allowed=teach_scope("sonia"),
                               min_retire_samples=retire_min, min_promote_samples=promote_min,
                               provenance=teach_provenance("sonia"))
    if rec is not None:
        return ProposedEdit(edit_id=new_edit_id(), tool=op.tool, target_kind=rec.target_kind,
                            target_id=rec.target_id, op=rec.op, summary=rec.summary,
                            payload=rec.payload, rationale=op.rationale, args=dict(op.args))
    return ProposedEdit(edit_id=new_edit_id(), tool=op.tool, target_kind=_KIND.get(op.tool, ""),
                        rationale=op.rationale, args=dict(op.args), status="failed", apply_reason=reason)


class MetaAgent:
    """Stateless, per-request. Turns curated content into proposed brain edits (dry-run preview),
    then applies the accepted ones through the SAME gated path the autonomous Refiner uses."""

    def __init__(self, tools: MetaTools, llm: LLMClient, *, retire_min: int = 5, promote_min: int = 3) -> None:
        self.tools = tools
        self.h = tools.h
        self.llm = llm
        self._retire_min = retire_min
        self._promote_min = promote_min

    def _preview(self, op: RefineOp) -> ProposedEdit:
        return preview_op(self.h, op, retire_min=self._retire_min, promote_min=self._promote_min)

    def apply(self, accepted: list[ProposedEdit], *,
              human_approver: str | None = None) -> tuple[list[EditRecord], list[ProposedEdit]]:
        """Apply user-accepted edits through the gate. human_approver records WHO accepted them
        (charter conformance 2026-07-09: a landed agent proposal names its human approver)."""
        applied: list[EditRecord] = []
        for e in accepted:
            if e.status != "accepted":
                continue
            op = RefineOp(tool=e.tool, args=dict(e.args), rationale=e.rationale)
            rec, reason = try_apply_op(self.tools, self.h, op, allowed=teach_scope("sonia"),
                                       min_retire_samples=self._retire_min, min_promote_samples=self._promote_min,
                                       provenance=teach_provenance("sonia", human_approver=human_approver))
            if rec is not None:
                e.status, e.applied_seq, e.apply_reason = "applied", rec.seq, ""
                applied.append(rec)
            else:
                e.status, e.apply_reason = "failed", reason
        return applied, accepted
