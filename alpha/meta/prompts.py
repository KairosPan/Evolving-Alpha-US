from __future__ import annotations

import json

from alpha.harness.state import HarnessState
from alpha.llm.extract import extract_json_object
from alpha.meta.models import LessonSource, ProposedDirection, ProposedEdit, new_direction_id

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


def _source_block(source: LessonSource) -> str:
    head = f"TEACHING MATERIAL — {source.title or source.url or 'pasted text'}:\n"
    return head + source.text


def build_directions_prompt(h: HarnessState, source: LessonSource, comment: str | None) -> tuple[str, str]:
    system = (
        "You are the meta-agent's curriculum planner for a US momentum trading co-pilot. "
        "Given the co-pilot's current brain and a piece of teaching material, propose 2-4 DISTINCT, "
        "high-level evolution DIRECTIONS (not concrete edits yet). "
        'Output STRICT JSON: {"directions": [{"title": "...", "summary": "...", "rationale": "...", '
        '"target_kinds": ["skills"|"memory"|"doctrine", ...]}]}\n\n'
        + render_brain_summary(h)
    )
    user = _source_block(source)
    if comment:
        user += f"\n\nThe operator steered: {comment}"
    return system, user


def build_edits_prompt(h: HarnessState, source: LessonSource, direction: ProposedDirection,
                       comment: str | None) -> tuple[str, str]:
    system = (
        "You expand ONE chosen evolution direction into concrete edits to the trading brain. "
        + _TOOLS_DOC
        + ' Output STRICT JSON: {"ops": [{"tool": "...", "args": {...}, "rationale": "..."}]}. '
        "Every op needs a non-empty rationale citing the teaching material.\n\n"
        + render_brain_summary(h)
    )
    user = (f"CHOSEN DIRECTION: {direction.title}\n{direction.summary}\n"
            f"(target areas: {', '.join(direction.target_kinds) or 'any'})\n\n" + _source_block(source))
    if direction.target_kinds:
        user += f"\n\nPrefer edits to: {', '.join(direction.target_kinds)}."
    if comment:
        user += f"\n\nThe operator steered: {comment}"
    return system, user


def build_reedit_prompt(h: HarnessState, source: LessonSource, direction: ProposedDirection,
                        prior_edit: ProposedEdit, comment: str) -> tuple[str, str]:
    system = (
        "You revise a SINGLE proposed edit based on operator feedback. "
        + _TOOLS_DOC
        + ' Output STRICT JSON with EXACTLY ONE op: {"ops": [{"tool": "...", "args": {...}, '
        '"rationale": "..."}]}. Prefer the same tool/target as the prior edit.\n\n'
        + render_brain_summary(h)
    )
    user = (f"DIRECTION: {direction.title}\nPRIOR EDIT: tool={prior_edit.tool} "
            f"target={prior_edit.target_id} args={json.dumps(prior_edit.args)}\n"
            f"OPERATOR FEEDBACK: {comment}\n\n" + _source_block(source))
    return system, user


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
