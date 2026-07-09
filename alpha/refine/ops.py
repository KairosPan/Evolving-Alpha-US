from __future__ import annotations

import json
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from alpha.llm.extract import extract_json_object

PassKind = Literal["p", "G", "K", "M"]
PASS_ORDER: tuple[PassKind, ...] = ("p", "G", "K", "M")

# Per-pass tool whitelist. G is a RESERVED no-op (no tools, no LLM call) until G sub-agents exist.
PASS_TOOLS: dict[PassKind, frozenset[str]] = {
    "p": frozenset({"rewrite_doctrine"}),
    "G": frozenset(),
    "K": frozenset({"write_skill", "patch_skill", "retire_skill", "revive_skill", "promote_skill"}),
    "M": frozenset({"process_memory", "update_memory", "demote_memory"}),
}


class RefineOp(BaseModel):
    """One proposed edit from the Refiner LLM (validated/applied later, behind discipline gates)."""
    model_config = ConfigDict(frozen=True)
    tool: str
    args: dict = Field(default_factory=dict)
    rationale: str = ""


def _parse_op_items(raw_ops: list) -> list[RefineOp]:
    """Validate a list of raw op dicts into RefineOps; drop malformed items (reject-don't-crash).
    Empty rationale is kept as '' (rejected later at apply time)."""
    ops: list[RefineOp] = []
    for item in raw_ops:
        if not isinstance(item, dict):
            continue
        tool = item.get("tool")
        if not isinstance(tool, str) or not tool.strip():
            continue
        args = item.get("args")
        if args is None:
            args = {}
        elif not isinstance(args, dict):
            continue
        rationale = item.get("rationale")
        if not isinstance(rationale, str):
            rationale = ""
        ops.append(RefineOp(tool=tool, args=args, rationale=rationale))
    return ops


def parse_ops(raw: str) -> list[RefineOp]:
    """Pull {"ops": [...]} from prose/fenced/thinking-prefixed LLM text; drop malformed items.
    Any structural failure yields []. Empty rationale is kept as '' (rejected later at apply time)."""
    extracted = extract_json_object(raw)
    if extracted is None:
        return []
    try:
        data = json.loads(extracted)
    except (json.JSONDecodeError, ValueError):
        return []
    if not isinstance(data, dict):
        return []
    raw_ops = data.get("ops")
    if not isinstance(raw_ops, list):       # non-list ops (5, "x", {}) -> no edits (reject-don't-crash)
        return []
    return _parse_op_items(raw_ops)


def parse_extraction(raw: str) -> tuple[list[RefineOp], bool, str]:
    """Parse the enforced-JSON crystallization reply into (ops, no_edit, reason). NEVER silent:
    - dict with a non-empty valid 'ops' list  -> (ops, False, "")
    - dict with truthy 'no_edit'               -> ([], True, reason or "no edit proposed")
    - anything else (empty/unknown/malformed)  -> ([], True, "model proposed no ops")."""
    extracted = extract_json_object(raw)
    data = None
    if extracted is not None:
        try:
            data = json.loads(extracted)
        except (json.JSONDecodeError, ValueError):
            data = None
    if not isinstance(data, dict):
        return [], True, "model returned no parseable JSON"
    raw_ops = data.get("ops")
    if isinstance(raw_ops, list):
        ops = _parse_op_items(raw_ops)
        if ops:
            return ops, False, ""
    if data.get("no_edit"):
        reason = data.get("reason")
        return [], True, reason if isinstance(reason, str) and reason.strip() else "no edit proposed"
    return [], True, "model proposed no ops"
