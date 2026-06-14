from __future__ import annotations

import json
from pathlib import Path

from alpha.harness.doctrine import Doctrine
from alpha.harness.memory import Lesson
from alpha.harness.registry import MemoryStore, SkillRegistry
from alpha.harness.skill import Skill
from alpha.harness.state import HarnessState


def _read_json_list(path: Path) -> list[dict]:
    if not path.exists():
        raise FileNotFoundError(f"missing seed file: {path}")
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, list):
        raise ValueError(f"seed file top level must be a JSON array, got {type(data).__name__}: {path}")
    return data


def load_seeds(seeds_dir: str | Path) -> HarnessState:
    """Read skills.json / memory.json / doctrine.json, normalize + validate, assemble HarnessState."""
    d = Path(seeds_dir)
    if not d.is_dir():
        raise FileNotFoundError(f"missing seeds directory: {d}")
    skills = SkillRegistry.from_skills([Skill.from_seed(x) for x in _read_json_list(d / "skills.json")])
    memory = MemoryStore.from_lessons([Lesson.from_seed(x) for x in _read_json_list(d / "memory.json")])
    doctrine = Doctrine.from_seed_list(_read_json_list(d / "doctrine.json"))
    # US-1e adds: cycle = StateMachine.from_seed_list(_read_json_list(d / "state_machine.json"))
    return HarnessState(doctrine=doctrine, skills=skills, memory=memory)
