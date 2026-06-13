from __future__ import annotations

from dataclasses import dataclass

from youzi.harness.cycle import StateMachine
from youzi.harness.doctrine import Doctrine
from youzi.harness.memory_item import Lesson
from youzi.harness.memory_store import MemoryStore
from youzi.harness.registry import SkillRegistry
from youzi.harness.skill import Skill


@dataclass
class HarnessState:
    """Harness 状态 H=(p,K,M)+情绪周期状态机。Phase-0b-1 为只读载入态;编辑/版本化见 0b-2。

    G(子 Agent)留待 Phase-1(LLM 驱动模块),此处暂不建模。
    """
    doctrine: Doctrine          # p
    skills: SkillRegistry       # K
    memory: MemoryStore         # M
    cycle: StateMachine         # G_cycle 种子

    def active_skills_for(self, phase: str) -> list[Skill]:
        """该相位下当前可用(active)的技能。"""
        return [s for s in self.skills.by_phase(phase) if s.status == "active"]

    def to_dict(self) -> dict:
        """序列化整个 H(skills/memory 各 model_dump 列表 + doctrine/cycle model_dump)。"""
        return {
            "skills": [s.model_dump() for s in self.skills.all()],
            "memory": [l.model_dump() for l in self.memory.all()],
            "doctrine": self.doctrine.model_dump(),
            "cycle": self.cycle.model_dump(),
        }

    @classmethod
    def from_dict(cls, d: dict) -> "HarnessState":
        """从 to_dict 还原。用 model_validate 重建(immutable 条目经 core 构造,绕过 __setattr__ 守卫故成功)。"""
        return cls(
            doctrine=Doctrine.model_validate(d["doctrine"]),
            skills=SkillRegistry.from_skills([Skill.model_validate(x) for x in d["skills"]]),
            memory=MemoryStore.from_lessons([Lesson.model_validate(x) for x in d["memory"]]),
            cycle=StateMachine.model_validate(d["cycle"]),
        )
