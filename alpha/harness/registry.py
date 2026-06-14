from __future__ import annotations

from alpha.harness.memory import Lesson
from alpha.harness.skill import Skill


class SkillRegistry:
    """K skill library indexed by id. US-1a: read + query only (CRUD/lifecycle in US-1b)."""

    def __init__(self, skills: dict[str, Skill]) -> None:
        self._skills = dict(skills)

    @classmethod
    def from_skills(cls, skills: list[Skill]) -> "SkillRegistry":
        index: dict[str, Skill] = {}
        for s in skills:
            if s.skill_id in index:
                raise ValueError(f"duplicate skill_id: {s.skill_id}")
            index[s.skill_id] = s
        return cls(index)

    def get(self, skill_id: str) -> Skill | None:
        return self._skills.get(skill_id)

    def all(self) -> list[Skill]:
        return list(self._skills.values())

    def by_status(self, status: str) -> list[Skill]:
        return [s for s in self._skills.values() if s.status == status]

    def by_type(self, type_: str) -> list[Skill]:
        return [s for s in self._skills.values() if s.type == type_]

    def by_phase(self, phase: str) -> list[Skill]:
        return [s for s in self._skills.values() if phase in s.phases or s.applies_all_phases]

    def by_family(self, family: str) -> list[Skill]:
        return [s for s in self._skills.values() if s.family == family]

    def __len__(self) -> int:
        return len(self._skills)

    def __bool__(self) -> bool:
        return True


class MemoryStore:
    """M memory library indexed by lesson id. US-1a: read + query only."""

    def __init__(self, lessons: dict[str, Lesson]) -> None:
        self._lessons = dict(lessons)

    @classmethod
    def from_lessons(cls, lessons: list[Lesson]) -> "MemoryStore":
        index: dict[str, Lesson] = {}
        for l in lessons:
            if l.lesson_id in index:
                raise ValueError(f"duplicate lesson_id: {l.lesson_id}")
            index[l.lesson_id] = l
        return cls(index)

    def get(self, lesson_id: str) -> Lesson | None:
        return self._lessons.get(lesson_id)

    def all(self) -> list[Lesson]:
        return list(self._lessons.values())

    def by_phase(self, phase: str) -> list[Lesson]:
        return [l for l in self._lessons.values() if phase in l.phases or l.applies_all_phases]

    def by_family(self, family: str) -> list[Lesson]:
        return [l for l in self._lessons.values() if l.family == family]

    def by_outcome(self, outcome: str) -> list[Lesson]:
        return [l for l in self._lessons.values() if l.outcome == outcome]

    def __len__(self) -> int:
        return len(self._lessons)

    def __bool__(self) -> bool:
        return True
