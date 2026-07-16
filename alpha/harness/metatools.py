from __future__ import annotations

from alpha.harness.connectors import ConnectorEntry
from alpha.harness.edit_log import EditLog, EditRecord
from alpha.harness.memory import Importance, Lesson
from alpha.harness.skill import Skill, SkillStats
from alpha.harness.state import HarnessState
from alpha.harness.subagents import SubagentEntry
from alpha.harness.workflows import WorkflowEntry


def _jsonable(v: object) -> object:
    return v.model_dump() if hasattr(v, "model_dump") else v


def _require_rationale(rationale: str) -> None:
    if not rationale or not rationale.strip():
        raise ValueError("rationale is required for every harness edit")


class MetaTools:
    """The paper's meta-tool API: an Agent/Refiner edits H=(p,K,M) in place through this facade.
    (G sub-agents and the regime cycle join H in US-1e/US-2; this layer edits p/K/M.)

    Each tool executes the edit first; if it raises, H is unchanged and NOTHING is logged. On
    success it appends exactly one EditRecord (rationale + before/after payload). Edit only through
    these methods — touching h.skills/h.memory/h.doctrine directly bypasses the audit.
    """

    def __init__(self, harness: HarnessState, log: EditLog | None = None) -> None:
        self.h = harness
        self.log = log if log is not None else EditLog()

    # ── K skills ──
    def write_skill(self, skill: Skill, rationale: str) -> EditRecord:
        _require_rationale(rationale)
        clamped = skill.model_copy(update={"status": "incubating", "stats": SkillStats()})
        self.h.skills.write(clamped)                          # raises on dup -> not logged
        return self.log.append("write_skill", "skill", clamped.skill_id, "create",
                               clamped.name, payload={"before": None, "after": clamped.model_dump()},
                               rationale=rationale)

    def patch_skill(self, skill_id: str, rationale: str, **fields) -> EditRecord:
        _require_rationale(rationale)
        s = self.h.skills.get(skill_id)
        before = {k: _jsonable(getattr(s, k)) for k in fields if s is not None and k in type(s).model_fields}
        self.h.skills.patch(skill_id, **fields)              # raises -> not logged
        after = {k: _jsonable(v) for k, v in fields.items()}
        return self.log.append("patch_skill", "skill", skill_id, "update",
                               ",".join(fields), payload={"before": before, "after": after},
                               rationale=rationale)

    def retire_skill(self, skill_id: str, rationale: str, permanent: bool = False) -> EditRecord:
        _require_rationale(rationale)
        s = self.h.skills.get(skill_id)
        before = s.status if s is not None else None
        self.h.skills.retire(skill_id, permanent=permanent)
        after = "retired" if permanent else "dormant"
        return self.log.append("retire_skill", "skill", skill_id, "retire", after,
                               payload={"before": before, "after": after}, rationale=rationale)

    def revive_skill(self, skill_id: str, rationale: str) -> EditRecord:
        _require_rationale(rationale)
        s = self.h.skills.get(skill_id)
        before = s.status if s is not None else None
        self.h.skills.revive(skill_id)
        return self.log.append("revive_skill", "skill", skill_id, "revive", "",
                               payload={"before": before, "after": "incubating"}, rationale=rationale)

    def promote_skill(self, skill_id: str, rationale: str) -> EditRecord:
        _require_rationale(rationale)
        s = self.h.skills.get(skill_id)
        before = s.status if s is not None else None
        self.h.skills.promote(skill_id)
        return self.log.append("promote_skill", "skill", skill_id, "promote", "",
                               payload={"before": before, "after": "active"}, rationale=rationale)

    # ── M memory ──
    def process_memory(self, lesson: Lesson, rationale: str) -> EditRecord:
        _require_rationale(rationale)
        # Clamp importance on the create path (like write_skill clamps stats): the Refiner cannot
        # inject weight; importance is an observation field managed by demote_memory / time-decay.
        clamped = lesson.model_copy(update={"importance": Importance()})
        self.h.memory.add(clamped)
        return self.log.append("process_memory", "memory", clamped.lesson_id, "create",
                               clamped.lesson[:24], payload={"before": None, "after": clamped.model_dump()},
                               rationale=rationale)

    def update_memory(self, lesson_id: str, rationale: str, **fields) -> EditRecord:
        _require_rationale(rationale)
        l = self.h.memory.get(lesson_id)
        before = {k: _jsonable(getattr(l, k)) for k in fields if l is not None and k in type(l).model_fields}
        self.h.memory.update(lesson_id, **fields)
        after = {k: _jsonable(v) for k, v in fields.items()}
        return self.log.append("update_memory", "memory", lesson_id, "update",
                               ",".join(fields), payload={"before": before, "after": after},
                               rationale=rationale)

    def demote_memory(self, lesson_id: str, factor: float, rationale: str) -> EditRecord:
        _require_rationale(rationale)
        l = self.h.memory.get(lesson_id)
        before_td = l.importance.time_decay if l is not None else None
        self.h.memory.demote(lesson_id, factor)
        return self.log.append("demote_memory", "memory", lesson_id, "demote", str(factor),
                               payload={"before_time_decay": before_td, "factor": factor},
                               rationale=rationale)

    # ── p doctrine ──
    def rewrite_doctrine(self, section: str, new_guidance: str, rationale: str) -> EditRecord:
        _require_rationale(rationale)
        old = self.h.doctrine.get(section)
        old_guidance = old.guidance if old is not None else None
        self.h.doctrine.rewrite(section, new_guidance)       # immutable -> raises -> not logged
        return self.log.append("rewrite_doctrine", "doctrine", section, "rewrite",
                               payload={"old": old_guidance, "new": new_guidance}, rationale=rationale)

    # ── C connectors ──
    def write_connector(self, entry: ConnectorEntry, rationale: str) -> EditRecord:
        _require_rationale(rationale)
        self.h.connectors.upsert(entry)                       # id-keyed upsert (create/replace)
        return self.log.append("write_connector", "connector", entry.connector_id, "create",
                               entry.name, payload={"before": None, "after": entry.model_dump()},
                               rationale=rationale)

    def patch_connector(self, connector_id: str, fields: dict, rationale: str) -> EditRecord:
        _require_rationale(rationale)
        cur = self.h.connectors.get(connector_id)
        if cur is None:
            raise KeyError(f"unknown connector: {connector_id}")   # raises -> not logged
        before = cur.model_dump()
        updated = cur.model_copy(update=fields)
        self.h.connectors.upsert(updated)
        return self.log.append("patch_connector", "connector", connector_id, "update",
                               ",".join(fields), payload={"before": before, "after": updated.model_dump()},
                               rationale=rationale)

    def disable_connector(self, connector_id: str, rationale: str) -> EditRecord:
        return self.patch_connector(connector_id, {"enabled": False}, rationale)

    # ── W workflows ──
    def write_workflow(self, entry: WorkflowEntry, rationale: str) -> EditRecord:
        _require_rationale(rationale)
        self.h.workflows.upsert(entry)                        # id-keyed upsert (create/replace)
        return self.log.append("write_workflow", "workflow", entry.workflow_id, "create",
                               entry.name, payload={"before": None, "after": entry.model_dump()},
                               rationale=rationale)

    def patch_workflow(self, workflow_id: str, fields: dict, rationale: str) -> EditRecord:
        _require_rationale(rationale)
        cur = self.h.workflows.get(workflow_id)
        if cur is None:
            raise KeyError(f"unknown workflow: {workflow_id}")   # raises -> not logged
        before = cur.model_dump()
        # Re-VALIDATE the merged entry (not model_copy like the flat connector patch): WorkflowEntry
        # has a nested list[WorkflowStep], and model_copy(update=) would store raw dicts. dispatch
        # controls args, so the merge is safe.
        updated = WorkflowEntry.model_validate({**before, **fields})
        self.h.workflows.upsert(updated)
        return self.log.append("patch_workflow", "workflow", workflow_id, "update",
                               ",".join(fields), payload={"before": before, "after": updated.model_dump()},
                               rationale=rationale)

    def retire_workflow(self, workflow_id: str, rationale: str) -> EditRecord:
        _require_rationale(rationale)
        cur = self.h.workflows.get(workflow_id)
        if cur is None:
            raise KeyError(f"unknown workflow: {workflow_id}")   # raises -> not logged
        before = cur.status
        self.h.workflows.upsert(cur.model_copy(update={"status": "retired"}))
        return self.log.append("retire_workflow", "workflow", workflow_id, "retire", "retired",
                               payload={"before": before, "after": "retired"}, rationale=rationale)

    # ── A subagents ──
    def write_subagent(self, entry: SubagentEntry, rationale: str) -> EditRecord:
        _require_rationale(rationale)
        self.h.subagents.upsert(entry)                        # id-keyed upsert (create/replace)
        return self.log.append("write_subagent", "subagent", entry.subagent_id, "create",
                               entry.name, payload={"before": None, "after": entry.model_dump()},
                               rationale=rationale)

    def patch_subagent(self, subagent_id: str, fields: dict, rationale: str) -> EditRecord:
        _require_rationale(rationale)
        cur = self.h.subagents.get(subagent_id)
        if cur is None:
            raise KeyError(f"unknown subagent: {subagent_id}")   # raises -> not logged
        before = cur.model_dump()
        # Re-VALIDATE the merged entry (mirrors patch_workflow, not the flat connector model_copy):
        # closes the model_copy-bypasses-validation gap so a patch is validated like a create.
        updated = SubagentEntry.model_validate({**before, **fields})
        self.h.subagents.upsert(updated)
        return self.log.append("patch_subagent", "subagent", subagent_id, "update",
                               ",".join(fields), payload={"before": before, "after": updated.model_dump()},
                               rationale=rationale)

    def retire_subagent(self, subagent_id: str, rationale: str) -> EditRecord:
        _require_rationale(rationale)
        cur = self.h.subagents.get(subagent_id)
        if cur is None:
            raise KeyError(f"unknown subagent: {subagent_id}")   # raises -> not logged
        before = cur.status
        self.h.subagents.upsert(cur.model_copy(update={"status": "retired"}))
        return self.log.append("retire_subagent", "subagent", subagent_id, "retire", "retired",
                               payload={"before": before, "after": "retired"}, rationale=rationale)
