from __future__ import annotations

from alpha.harness.edit_log import EditLog, EditRecord
from alpha.harness.memory import Importance, Lesson
from alpha.harness.skill import Skill, SkillStats
from alpha.harness.state import HarnessState


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
