from __future__ import annotations

from dataclasses import dataclass

from alpha.harness.doctrine import Doctrine
from alpha.harness.memory import Lesson
from alpha.harness.registry import MemoryStore, SkillRegistry
from alpha.harness.skill import Skill


@dataclass
class HarnessState:
    """Harness state H = (p=doctrine, K=skills, M=memory).

    The regime state machine (cycle) and G sub-agents join in US-1e / US-2.
    """
    doctrine: Doctrine          # p
    skills: SkillRegistry       # K
    memory: MemoryStore         # M
    vocabulary: str = "momo"    # phase-token pack this H speaks ("momo"/"growth"); rides WITH the harness
                                #   so the write-waist normalizer and the prompt persona follow the H, not
                                #   the process env (P0.5). load_seeds/load_pack stamp it; legacy dumps
                                #   without the field default "momo".

    def active_skills_for(self, phase: str) -> list[Skill]:
        return [s for s in self.skills.by_phase(phase) if s.status == "active"]

    def to_dict(self) -> dict:
        # mode="json": date fields (e.g. Lesson.learned_asof) must serialize as ISO strings —
        # every consumer (LiveBrainStore/SnapshotStore/proposal packets) json.dumps this dict,
        # and python-mode datetime.date objects crash it. from_dict re-validates strings back.
        return {
            "skills": [s.model_dump(mode="json") for s in self.skills.all()],
            "memory": [l.model_dump(mode="json") for l in self.memory.all()],
            "doctrine": self.doctrine.model_dump(mode="json"),
            "vocabulary": self.vocabulary,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "HarnessState":
        # model_validate rebuilds immutable entries via the core constructor (bypassing the
        # __setattr__ guard at build time); the guard is back in force on the rebuilt object.
        # US-1e: add a `cycle` field above and a "cycle" key in to_dict/from_dict here.
        return cls(
            doctrine=Doctrine.model_validate(d["doctrine"]),
            skills=SkillRegistry.from_skills([Skill.model_validate(x) for x in d["skills"]]),
            memory=MemoryStore.from_lessons([Lesson.model_validate(x) for x in d["memory"]]),
            vocabulary=d.get("vocabulary", "momo"),   # legacy dumps (pre-P0.5) had no field -> momo
        )
