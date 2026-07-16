from __future__ import annotations

from dataclasses import dataclass, field

from alpha.harness.connectors import ConnectorEntry, ConnectorRegistry
from alpha.harness.doctrine import Doctrine
from alpha.harness.memory import Lesson
from alpha.harness.registry import MemoryStore, SkillRegistry
from alpha.harness.skill import Skill
from alpha.harness.subagents import SubagentEntry, SubagentRegistry
from alpha.harness.workflows import WorkflowEntry, WorkflowRegistry


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
    connectors: ConnectorRegistry = field(default_factory=ConnectorRegistry.empty)   # C (4th Body component)
    workflows: WorkflowRegistry = field(default_factory=WorkflowRegistry.empty)      # W (5th Body component)
    subagents: SubagentRegistry = field(default_factory=SubagentRegistry.empty)      # A (6th Body component)

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
            "connectors": [c.model_dump(mode="json") for c in self.connectors.all()],
            "workflows": [w.model_dump(mode="json") for w in self.workflows.all()],
            "subagents": [a.model_dump(mode="json") for a in self.subagents.all()],
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
            connectors=ConnectorRegistry.from_connectors(
                [ConnectorEntry.model_validate(x) for x in d.get("connectors", [])]),  # legacy -> empty
            workflows=WorkflowRegistry.from_workflows(
                [WorkflowEntry.model_validate(x) for x in d.get("workflows", [])]),    # legacy -> empty
            subagents=SubagentRegistry.from_subagents(
                [SubagentEntry.model_validate(x) for x in d.get("subagents", [])]),    # legacy -> empty
        )
