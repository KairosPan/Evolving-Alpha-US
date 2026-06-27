from __future__ import annotations

from datetime import date, datetime
from pydantic import BaseModel, ConfigDict, Field

from alpha.harness.memory import Lesson
from alpha.harness.regime import normalize_phase
from alpha.harness.skill import Skill
from alpha.harness.state import HarnessState

DEFAULT_EPISODE_BUDGET = 8
DEFAULT_SKILL_BUDGET = 16
DEFAULT_MEMORY_BUDGET = 10
DEFAULT_TRIAL_SLOTS = 3
MIN_MEMORY_WEIGHT = 0.15     # lessons below this weight aren't rendered (demote takes effect at once)


class Selection(BaseModel):
    """Budgeted prompt-injection selection (frozen; members are read-only refs into H)."""
    model_config = ConfigDict(frozen=True)
    skills: list[Skill] = Field(default_factory=list)
    trials: list[Skill] = Field(default_factory=list)
    lessons: list[Lesson] = Field(default_factory=list)


def select_for_prompt(h: HarnessState, *, phase_prior: str | None,
                      skill_budget: int = DEFAULT_SKILL_BUDGET,
                      memory_budget: int = DEFAULT_MEMORY_BUDGET,
                      trial_slots: int = DEFAULT_TRIAL_SLOTS,
                      asof: date | datetime | None = None) -> Selection:
    """Pick the skills/trials/lessons to inject (pure, deterministic, read-only).

    skills: active, ranked (phase-prior hit first, then stats.n desc, then skill_id), top skill_budget.
    trials: incubating, newest-first (registry insertion order reversed), top trial_slots.
    lessons: importance.weight() >= MIN_MEMORY_WEIGHT and learned_asof <= asof (PIT mask),
             by (weight desc, lesson_id), top memory_budget.
    """
    if isinstance(asof, datetime):
        asof = asof.date()
    canon = normalize_phase(phase_prior) if phase_prior else None

    def _hit(s: Skill) -> bool:
        return canon is not None and (s.applies_all_phases or canon in s.phases)

    actives = sorted(h.skills.by_status("active"),
                     key=lambda s: (not _hit(s), -s.stats.n, s.skill_id))
    trials = list(reversed(h.skills.by_status("incubating")))[:trial_slots]
    lessons = sorted(
        (l for l in h.memory.all()
         if l.importance.weight() >= MIN_MEMORY_WEIGHT
         and (asof is None or l.learned_asof is None or l.learned_asof <= asof)),
        key=lambda l: (-l.importance.weight(), l.lesson_id))
    return Selection(skills=actives[:skill_budget], trials=trials, lessons=lessons[:memory_budget])


def select_episodes_for_prompt(episode_store, *, phase_prior: str | None,
                               asof: date | datetime | None = None,
                               budget: int = DEFAULT_EPISODE_BUDGET) -> list:
    """Recall PIT-masked episodes for the current regime, ranked (phase-match, recency, |advantage|), top
    budget. `episode_store` is duck-typed (.for_asof(asof) -> list[Episode]); None/asof-None -> []."""
    if episode_store is None:
        return []
    if isinstance(asof, datetime):
        asof = asof.date()
    if asof is None:
        return []
    canon = normalize_phase(phase_prior) if phase_prior else None
    pool = episode_store.for_asof(asof)                          # PIT-masked (learned_asof <= asof)

    def _key(e):
        match = 1 if (canon is not None and normalize_phase(e.phase or "") == canon) else 0
        return (match, e.learned_asof or e.exit_date, abs(e.advantage))

    pool.sort(key=_key, reverse=True)
    return pool[:budget]
