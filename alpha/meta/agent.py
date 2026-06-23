from __future__ import annotations

import copy

from alpha.harness.edit_log import EditLog, EditRecord
from alpha.harness.metatools import MetaTools
from alpha.llm.client import LLMClient
from alpha.meta import prompts
from alpha.meta.models import (
    LessonSource, ProposedDirection, ProposedEdit, new_edit_id,
)
from alpha.refine.apply import ALL_TOOLS, try_apply_op
from alpha.refine.ops import RefineOp, parse_ops

_KIND = {
    "write_skill": "skill", "patch_skill": "skill", "retire_skill": "skill",
    "revive_skill": "skill", "promote_skill": "skill",
    "process_memory": "memory", "update_memory": "memory", "demote_memory": "memory",
    "rewrite_doctrine": "doctrine",
}


class MetaAgent:
    """Stateless, per-request. Turns curated content into proposed brain edits (dry-run preview),
    then applies the accepted ones through the SAME gated path the autonomous Refiner uses."""

    def __init__(self, tools: MetaTools, llm: LLMClient, *, retire_min: int = 5, promote_min: int = 3) -> None:
        self.tools = tools
        self.h = tools.h
        self.llm = llm
        self._retire_min = retire_min
        self._promote_min = promote_min

    def propose_directions(self, source: LessonSource, *, comment: str | None = None) -> list[ProposedDirection]:
        system, user = prompts.build_directions_prompt(self.h, source, comment)
        return prompts.parse_directions(self.llm.complete(system, user))

    def _preview(self, op: RefineOp) -> ProposedEdit:
        scratch = copy.deepcopy(self.h)
        rec, reason = try_apply_op(MetaTools(scratch, EditLog()), scratch, op, allowed=ALL_TOOLS,
                                   min_retire_samples=self._retire_min, min_promote_samples=self._promote_min)
        if rec is not None:
            return ProposedEdit(edit_id=new_edit_id(), tool=op.tool, target_kind=rec.target_kind,
                                target_id=rec.target_id, op=rec.op, summary=rec.summary,
                                payload=rec.payload, rationale=op.rationale, args=dict(op.args))
        return ProposedEdit(edit_id=new_edit_id(), tool=op.tool, target_kind=_KIND.get(op.tool, ""),
                            rationale=op.rationale, args=dict(op.args), status="failed", apply_reason=reason)

    def expand_to_edits(self, source: LessonSource, direction: ProposedDirection, *,
                        comment: str | None = None) -> list[ProposedEdit]:
        system, user = prompts.build_edits_prompt(self.h, source, direction, comment)
        return [self._preview(op) for op in parse_ops(self.llm.complete(system, user))]

    def apply(self, accepted: list[ProposedEdit]) -> tuple[list[EditRecord], list[ProposedEdit]]:
        applied: list[EditRecord] = []
        for e in accepted:
            if e.status != "accepted":
                continue
            op = RefineOp(tool=e.tool, args=dict(e.args), rationale=e.rationale)
            rec, reason = try_apply_op(self.tools, self.h, op, allowed=ALL_TOOLS,
                                       min_retire_samples=self._retire_min, min_promote_samples=self._promote_min)
            if rec is not None:
                e.status, e.applied_seq, e.apply_reason = "applied", rec.seq, ""
                applied.append(rec)
            else:
                e.status, e.apply_reason = "failed", reason
        return applied, accepted

    def repropose_edit(self, source: LessonSource, direction: ProposedDirection,
                       prior_edit: ProposedEdit, comment: str) -> ProposedEdit:
        system, user = prompts.build_reedit_prompt(self.h, source, direction, prior_edit, comment)
        ops = parse_ops(self.llm.complete(system, user))
        if not ops:
            prior_edit.status, prior_edit.apply_reason, prior_edit.user_comment = (
                "failed", "model returned no usable edit", comment)
            return prior_edit
        out = self._preview(ops[0])
        out.edit_id, out.user_comment = prior_edit.edit_id, comment
        return out
