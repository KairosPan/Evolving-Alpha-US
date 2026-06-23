from __future__ import annotations

import copy

from alpha.harness.edit_log import EditLog
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
