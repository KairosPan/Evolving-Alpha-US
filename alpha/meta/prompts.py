from __future__ import annotations

import json

from alpha.harness.state import HarnessState
from alpha.llm.extract import extract_json_object
from alpha.meta.models import ProposedDirection, new_direction_id

_TOOLS_DOC = (
    "Allowed tools (emit ops in this exact vocabulary): "
    "write_skill(args: full skill incl skill_id,name,type,family,phases,trigger,entry,exit_stop,taboo), "
    "patch_skill(args: skill_id + fields to change), retire_skill(args: skill_id[,permanent]), "
    "revive_skill(args: skill_id), promote_skill(args: skill_id), "
    "process_memory(args: lesson incl lesson_id,outcome,lesson[,family,phases]), "
    "update_memory(args: lesson_id + fields), demote_memory(args: lesson_id, factor), "
    "rewrite_doctrine(args: section, new_guidance). "
    "NEVER rewrite an immutable [RED-LINE] doctrine section — it will be rejected."
)


def render_brain_summary(h: HarnessState) -> str:
    parts = ["DOCTRINE:"]
    for e in h.doctrine.immutable_core():
        parts.append(f"- [RED-LINE] {e.section}: {e.guidance}")
    for e in h.doctrine.mutable_entries():
        parts.append(f"- {e.section}: {e.guidance}")
    parts.append("\nSKILLS (id [status, family]):")
    for s in h.skills.all():
        parts.append(f"- {s.skill_id} [{s.status}, {s.family or 'any'}] trigger: {s.trigger}")
    parts.append("\nMEMORY (id [outcome]):")
    for l in h.memory.all():
        parts.append(f"- {l.lesson_id} [{l.outcome}] {l.lesson}")
    return "\n".join(parts)


def parse_directions(raw: str) -> list[ProposedDirection]:
    extracted = extract_json_object(raw)
    if extracted is None:
        return []
    try:
        data = json.loads(extracted)
    except (json.JSONDecodeError, ValueError):
        return []
    items = data.get("directions") if isinstance(data, dict) else None
    if not isinstance(items, list):
        return []
    out: list[ProposedDirection] = []
    for it in items:
        if not isinstance(it, dict) or not isinstance(it.get("title"), str) or not it["title"].strip():
            continue
        tk = it.get("target_kinds")
        out.append(ProposedDirection(
            direction_id=new_direction_id(),
            title=it["title"],
            summary=it.get("summary", "") if isinstance(it.get("summary"), str) else "",
            rationale=it.get("rationale", "") if isinstance(it.get("rationale"), str) else "",
            target_kinds=[x for x in tk if isinstance(x, str)] if isinstance(tk, list) else [],
        ))
    return out
