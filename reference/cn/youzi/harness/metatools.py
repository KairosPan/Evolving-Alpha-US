from __future__ import annotations

from youzi.harness.edit_log import EditLog, EditRecord
from youzi.harness.harness import HarnessState
from youzi.harness.memory_item import Lesson
from youzi.harness.skill import Skill


def _jsonable(v: object) -> object:
    return v.model_dump() if hasattr(v, "model_dump") else v


class MetaTools:
    """论文 meta-tool API:Agent/Refiner 通过它就地编辑 H=(p,K,M)。

    每个方法先执行编辑(失败则抛错、不记日志),成功后追加一条 EditRecord。
    调用方应只经 MetaTools 方法编辑,不要直接改 self.h / self.log,否则绕过审计。
    """

    def __init__(self, harness: HarnessState, log: EditLog | None = None) -> None:
        self.h = harness
        self.log = log if log is not None else EditLog()

    # ── K 技能 ──
    def write_skill(self, skill: Skill, rationale: str = "") -> EditRecord:
        self.h.skills.write(skill)
        return self.log.append("write_skill", "skill", skill.skill_id, "create",
                               skill.name_cn, rationale=rationale)

    def patch_skill(self, skill_id: str, rationale: str = "", **fields) -> EditRecord:
        s = self.h.skills.get(skill_id)
        before = {k: _jsonable(getattr(s, k)) for k in fields if s is not None and k in type(s).model_fields}
        self.h.skills.patch(skill_id, **fields)
        after = {k: _jsonable(v) for k, v in fields.items()}
        return self.log.append("patch_skill", "skill", skill_id, "update",
                               ",".join(f"{k}={v}" for k, v in fields.items()),
                               payload={"before": before, "after": after}, rationale=rationale)

    def retire_skill(self, skill_id: str, permanent: bool = False, rationale: str = "") -> EditRecord:
        s = self.h.skills.get(skill_id)
        before = s.status if s is not None else None
        self.h.skills.retire(skill_id, permanent=permanent)
        after = "retired" if permanent else "dormant"
        return self.log.append("retire_skill", "skill", skill_id, "retire", after,
                               payload={"before": before, "after": after}, rationale=rationale)

    def revive_skill(self, skill_id: str, rationale: str = "") -> EditRecord:
        s = self.h.skills.get(skill_id)
        before = s.status if s is not None else None
        self.h.skills.revive(skill_id)
        return self.log.append("revive_skill", "skill", skill_id, "revive", "",
                               payload={"before": before, "after": "incubating"}, rationale=rationale)

    def promote_skill(self, skill_id: str, rationale: str = "") -> EditRecord:
        s = self.h.skills.get(skill_id)
        before = s.status if s is not None else None
        self.h.skills.promote(skill_id)
        return self.log.append("promote_skill", "skill", skill_id, "promote", "",
                               payload={"before": before, "after": "active"}, rationale=rationale)

    # ── M 记忆 ──
    def process_memory(self, lesson: Lesson, rationale: str = "") -> EditRecord:
        self.h.memory.add(lesson)
        return self.log.append("process_memory", "memory", lesson.lesson_id, "create",
                               lesson.lesson[:24], rationale=rationale)

    def update_memory(self, lesson_id: str, rationale: str = "", **fields) -> EditRecord:
        lesson = self.h.memory.get(lesson_id)
        before = {k: _jsonable(getattr(lesson, k)) for k in fields
                  if lesson is not None and k in type(lesson).model_fields}
        self.h.memory.update(lesson_id, **fields)
        after = {k: _jsonable(v) for k, v in fields.items()}
        return self.log.append("update_memory", "memory", lesson_id, "update",
                               ",".join(fields), payload={"before": before, "after": after},
                               rationale=rationale)

    def demote_memory(self, lesson_id: str, factor: float, rationale: str = "") -> EditRecord:
        lesson = self.h.memory.get(lesson_id)
        before_td = lesson.importance.time_decay if lesson is not None else None
        self.h.memory.demote(lesson_id, factor)
        return self.log.append("demote_memory", "memory", lesson_id, "demote", str(factor),
                               payload={"before_time_decay": before_td, "factor": factor},
                               rationale=rationale)

    # ── p doctrine ──
    def rewrite_doctrine(self, section: str, new_guidance: str, rationale: str = "") -> EditRecord:
        old = self.h.doctrine.get(section)
        old_guidance = old.guidance if old is not None else None
        self.h.doctrine.rewrite(section, new_guidance)   # immutable -> 抛错, 不记日志
        return self.log.append("rewrite_doctrine", "doctrine", section, "rewrite",
                               payload={"old": old_guidance, "new": new_guidance},
                               rationale=rationale)
