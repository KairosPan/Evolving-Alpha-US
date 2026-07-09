from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from alpha.harness.state import HarnessState
from alpha.llm.chat import ChatMessage
from alpha.llm.client import LLMClient
from alpha.meta import prompts
from alpha.refine.ops import RefineOp, parse_extraction


class ExtractionResult(BaseModel):
    """Outcome of one crystallization pass. `ops` is empty iff `no_edit`; `reason` is populated
    when `no_edit` (a one-sentence why, always non-empty)."""
    model_config = ConfigDict(frozen=True)
    ops: list[RefineOp] = Field(default_factory=list)
    no_edit: bool = False
    reason: str = ""


def extract_ops(client: LLMClient, h: HarnessState, conversation: list[ChatMessage]) -> ExtractionResult:
    """Deterministic crystallization: render (brain + op vocabulary) and (conversation), call
    client.complete() [enforced json_object on openai_compat], parse into ops-or-no_edit. Read-only
    on `h`. Never returns silently — parse_extraction guarantees a reason when no ops."""
    system = prompts.render_extraction_system(h)
    user = prompts.render_conversation(conversation)
    raw = client.complete(system, user)
    ops, no_edit, reason = parse_extraction(raw)
    return ExtractionResult(ops=ops, no_edit=no_edit, reason=reason)
