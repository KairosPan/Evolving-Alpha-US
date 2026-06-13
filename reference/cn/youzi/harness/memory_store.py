from __future__ import annotations

from youzi.harness.memory_item import Lesson


class MemoryStore:
    """记忆库 M(按 lesson_id 索引)。"""

    def __init__(self, lessons: dict[str, Lesson]) -> None:
        self._lessons = dict(lessons)          # 防御性拷贝,调用方不持有同一引用

    @classmethod
    def from_lessons(cls, lessons: list[Lesson]) -> "MemoryStore":
        index: dict[str, Lesson] = {}
        for lesson in lessons:
            if lesson.lesson_id in index:
                raise ValueError(f"重复 lesson_id: {lesson.lesson_id}")
            index[lesson.lesson_id] = lesson
        return cls(index)

    def get(self, lesson_id: str) -> Lesson | None:
        return self._lessons.get(lesson_id)

    def all(self) -> list[Lesson]:
        return list(self._lessons.values())

    def for_regime(self, phase: str) -> list[Lesson]:
        """该相位适用的教训:phase ∈ phases 或 applies_all。"""
        return [l for l in self._lessons.values() if phase in l.phases or l.applies_all]

    def for_ecology(self, ecology: str) -> list[Lesson]:
        return [l for l in self._lessons.values() if ecology in l.ecologies]

    def by_outcome(self, outcome: str) -> list[Lesson]:
        return [l for l in self._lessons.values() if l.outcome == outcome]

    def by_pattern(self, pattern: str) -> list[Lesson]:
        return [l for l in self._lessons.values() if l.pattern == pattern]

    def __len__(self) -> int:
        return len(self._lessons)

    def __bool__(self) -> bool:
        return True

    # ── CRUD ────────────────────────────────────────────────────────────

    _UPDATE_FORBIDDEN = {"importance"}

    def add(self, lesson: Lesson) -> None:
        if lesson.lesson_id in self._lessons:
            raise ValueError(f"重复 lesson_id: {lesson.lesson_id}")
        self._lessons[lesson.lesson_id] = lesson

    def update(self, lesson_id: str, **fields) -> Lesson:
        l = self._lessons.get(lesson_id)
        if l is None:
            raise KeyError(f"无此 lesson_id: {lesson_id}")
        bad = self._UPDATE_FORBIDDEN & fields.keys()
        if bad:
            raise ValueError(f"不可直接 update {sorted(bad)}:importance 是观测字段(由 demote_memory/时间衰减管理,Refiner 不可改)")
        snapshot = {k: getattr(l, k) for k in fields if k in type(l).model_fields}
        try:
            for k, v in fields.items():
                setattr(l, k, v)             # validate_assignment 走校验
        except Exception:
            for k, v in snapshot.items():
                setattr(l, k, v)
            raise
        return l

    def demote(self, lesson_id: str, factor: float) -> Lesson:
        l = self._lessons.get(lesson_id)
        if l is None:
            raise KeyError(f"无此 lesson_id: {lesson_id}")
        l.importance.demote(factor)
        return l
