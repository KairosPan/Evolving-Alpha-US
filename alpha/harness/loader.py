from __future__ import annotations

import json
import os
from pathlib import Path

from alpha.harness.doctrine import Doctrine
from alpha.harness.growth_regime import normalize_growth_phases
from alpha.harness.memory import Lesson
from alpha.harness.regime import normalize_phases
from alpha.harness.registry import MemoryStore, SkillRegistry
from alpha.harness.skill import Skill
from alpha.harness.state import HarnessState

# Phase vocabulary per pack (Option B — parallel per-scale clocks; P0.3). momo is the default and
# leaves every existing caller byte-identical; growth reads the scale-typed tokens in seeds_v2/.
_VOCABULARIES = {"momo": normalize_phases, "growth": normalize_growth_phases}

_REPO_ROOT = Path(__file__).resolve().parents[2]
# (directory, vocabulary) per named seed pack. Selected via env ALPHA_SEED_PACK (default momo).
SEED_PACKS: dict[str, tuple[Path, str]] = {
    "momo": (_REPO_ROOT / "seeds", "momo"),
    "growth": (_REPO_ROOT / "seeds_v2", "growth"),
}
DEFAULT_PACK = "momo"
SEED_PACK_ENV = "ALPHA_SEED_PACK"


def _read_json_list(path: Path) -> list[dict]:
    if not path.exists():
        raise FileNotFoundError(f"missing seed file: {path}")
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, list):
        raise ValueError(f"seed file top level must be a JSON array, got {type(data).__name__}: {path}")
    return data


def load_seeds(seeds_dir: str | Path, *, vocabulary: str = "momo") -> HarnessState:
    """Read skills.json / memory.json / doctrine.json, normalize + validate, assemble HarnessState.

    `vocabulary` selects the phase-token vocabulary ("momo" default — byte-identical to before;
    "growth" reads the seeds_v2 scale-typed tokens). Unknown vocabulary raises (fail-loud).
    """
    if vocabulary not in _VOCABULARIES:
        raise ValueError(f"unknown vocabulary {vocabulary!r}; known = {sorted(_VOCABULARIES)}")
    normalize = _VOCABULARIES[vocabulary]
    d = Path(seeds_dir)
    if not d.is_dir():
        raise FileNotFoundError(f"missing seeds directory: {d}")
    skills = SkillRegistry.from_skills(
        [Skill.from_seed(x, normalize=normalize) for x in _read_json_list(d / "skills.json")])
    memory = MemoryStore.from_lessons(
        [Lesson.from_seed(x, normalize=normalize) for x in _read_json_list(d / "memory.json")])
    doctrine = Doctrine.from_seed_list(_read_json_list(d / "doctrine.json"), normalize=normalize)
    # US-1e adds: cycle = StateMachine.from_seed_list(_read_json_list(d / "state_machine.json"))
    return HarnessState(doctrine=doctrine, skills=skills, memory=memory)


def active_pack_name() -> str:
    """The active seed pack name: env ALPHA_SEED_PACK, or 'momo' when unset/empty."""
    return os.environ.get(SEED_PACK_ENV) or DEFAULT_PACK


def resolve_pack(name: str | None = None) -> tuple[Path, str]:
    """Resolve a pack name (or the active one) to its (seeds_dir, vocabulary). Unknown name raises."""
    name = name or active_pack_name()
    if name not in SEED_PACKS:
        raise ValueError(f"unknown seed pack {name!r}; known = {sorted(SEED_PACKS)}")
    seeds_dir, vocabulary = SEED_PACKS[name]
    return Path(seeds_dir), vocabulary


def load_pack(name: str | None = None) -> HarnessState:
    """Load the named seed pack (or the active one — env ALPHA_SEED_PACK, default momo)."""
    seeds_dir, vocabulary = resolve_pack(name)
    return load_seeds(seeds_dir, vocabulary=vocabulary)
