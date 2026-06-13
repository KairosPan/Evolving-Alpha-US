from __future__ import annotations

import json
from pathlib import Path

from youzi.harness.cycle import StateMachine
from youzi.harness.doctrine import Doctrine
from youzi.harness.harness import HarnessState
from youzi.harness.memory_item import Lesson
from youzi.harness.memory_store import MemoryStore
from youzi.harness.registry import SkillRegistry
from youzi.harness.skill import Skill


def _read_json(path: Path) -> list[dict]:
    if not path.exists():
        raise FileNotFoundError(f"种子文件缺失: {path}")
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, list):
        raise ValueError(f"种子文件顶层应为 JSON 数组, 实为 {type(data).__name__}: {path}")
    return data


def load_seeds(seeds_dir: str | Path) -> HarnessState:
    """读 seeds/{skills,memory,doctrine,state_machine}.json,归一+校验,组装 HarnessState。"""
    d = Path(seeds_dir)
    if not d.is_dir():
        raise FileNotFoundError(f"种子目录缺失: {d}")

    skills = SkillRegistry.from_skills(
        [Skill.from_seed(x) for x in _read_json(d / "skills.json")])
    memory = MemoryStore.from_lessons(
        [Lesson.from_seed(x) for x in _read_json(d / "memory.json")])
    doctrine = Doctrine.from_seed_list(_read_json(d / "doctrine.json"))
    cycle = StateMachine.from_seed_list(_read_json(d / "state_machine.json"))

    return HarnessState(doctrine=doctrine, skills=skills, memory=memory, cycle=cycle)
