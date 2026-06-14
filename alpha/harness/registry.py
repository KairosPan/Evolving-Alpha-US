from __future__ import annotations

from alpha.harness.errors import InvalidTransitionError
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

    # ── CRUD + lifecycle (US-1b) ──────────────────────────────────────────
    # write() is the seed/restore path (no clamping). The Refiner edits ONLY via MetaTools,
    # whose write_skill clamps status->incubating + resets stats. phases/applies_all_phases ARE
    # patchable in the US model (canonical fields, not derived from a raw regime string as in CN).
    # skill_id is protected structurally: it is patch()'s positional param, so passing it as a field
    # collides -> TypeError -> rejected. status via retire/revive/promote; stats is observation.
    _PATCH_FORBIDDEN = {"status", "stats"}

    def _require(self, skill_id: str) -> Skill:
        s = self._skills.get(skill_id)
        if s is None:
            raise KeyError(f"no such skill_id: {skill_id}")
        return s

    def write(self, skill: Skill) -> None:
        if skill.skill_id in self._skills:
            raise ValueError(f"duplicate skill_id: {skill.skill_id}")
        self._skills[skill.skill_id] = skill

    def patch(self, skill_id: str, **fields) -> Skill:
        s = self._require(skill_id)
        bad = self._PATCH_FORBIDDEN & fields.keys()
        if bad:
            raise ValueError(f"cannot patch {sorted(bad)}: status via retire/revive/promote; "
                             f"stats is an observation field (set by credit assignment)")
        snapshot = {k: getattr(s, k) for k in fields if k in type(s).model_fields}
        try:
            for k, v in fields.items():
                setattr(s, k, v)             # validate_assignment validates
        except Exception:
            for k, v in snapshot.items():    # roll back already-applied fields
                setattr(s, k, v)
            raise
        return s

    def retire(self, skill_id: str, permanent: bool = False) -> Skill:
        # Reject no-op retires so a hallucinating Refiner gets a signal (and no spurious EditRecord):
        s = self._require(skill_id)
        if s.status == "retired":
            raise InvalidTransitionError(f"{skill_id} is already permanently retired")
        if s.status == "dormant" and not permanent:
            raise InvalidTransitionError(f"{skill_id} is already dormant")
        s.status = "retired" if permanent else "dormant"     # dormant -> retired (permanent) is allowed
        return s

    def revive(self, skill_id: str) -> Skill:
        s = self._require(skill_id)
        if s.status != "dormant":
            raise InvalidTransitionError(f"{skill_id} is {s.status}, not dormant; cannot revive")
        s.status = "incubating"
        return s

    def promote(self, skill_id: str) -> Skill:
        s = self._require(skill_id)
        if s.status != "incubating":
            raise InvalidTransitionError(f"{skill_id} is {s.status}, not incubating; cannot promote")
        s.status = "active"
        return s


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

    # ── CRUD (US-1b) ──────────────────────────────────────────────────────
    # lesson_id is protected structurally (positional-param collision -> TypeError). importance is observation.
    _UPDATE_FORBIDDEN = {"importance"}

    def add(self, lesson: Lesson) -> None:
        if lesson.lesson_id in self._lessons:
            raise ValueError(f"duplicate lesson_id: {lesson.lesson_id}")
        self._lessons[lesson.lesson_id] = lesson

    def update(self, lesson_id: str, **fields) -> Lesson:
        l = self._lessons.get(lesson_id)
        if l is None:
            raise KeyError(f"no such lesson_id: {lesson_id}")
        bad = self._UPDATE_FORBIDDEN & fields.keys()
        if bad:
            raise ValueError(f"cannot update {sorted(bad)}: importance is an observation field "
                             f"(managed by demote_memory / time-decay)")
        snapshot = {k: getattr(l, k) for k in fields if k in type(l).model_fields}
        try:
            for k, v in fields.items():
                setattr(l, k, v)
        except Exception:
            for k, v in snapshot.items():
                setattr(l, k, v)
            raise
        return l

    def demote(self, lesson_id: str, factor: float) -> Lesson:
        l = self._lessons.get(lesson_id)
        if l is None:
            raise KeyError(f"no such lesson_id: {lesson_id}")
        l.importance.demote(factor)
        return l
