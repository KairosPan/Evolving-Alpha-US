from __future__ import annotations

from datetime import date, datetime
from typing import Callable

from pydantic import BaseModel, ConfigDict, Field

from alpha.harness.memory import Lesson
from alpha.harness.regime import normalize_phase, phase_from_read
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
                      asof: date | datetime | None = None,
                      collect: Callable[[dict], None] | None = None) -> Selection:
    """Pick the skills/trials/lessons to inject (pure, deterministic, read-only).

    skills: active, ranked (phase-prior hit first, then stats.n desc, then skill_id), top skill_budget.
    trials: incubating, newest-first (registry insertion order reversed), top trial_slots.
    lessons: importance.weight() >= MIN_MEMORY_WEIGHT and learned_asof <= asof (PIT mask),
             by (weight desc, lesson_id), top memory_budget.

    `collect`: D3 prompt-audit hook (observe-only, default None = no behavior change). Reports the
    budget/weight cuts made INSIDE this function — items dropped before ever reaching the caller, so
    `build_system_prompt` (which sees only the returned Selection) can't report them itself.
    """
    if isinstance(asof, datetime):
        asof = asof.date()
    canon = normalize_phase(phase_prior) if phase_prior else None

    def _hit(s: Skill) -> bool:
        return canon is not None and (s.applies_all_phases or canon in s.phases)

    actives = sorted(
        (s for s in h.skills.by_status("active") if getattr(s, "domain", "trading") == "trading"),
        key=lambda s: (not _hit(s), -s.stats.n, s.skill_id))
    trials_all = list(reversed(
        [s for s in h.skills.by_status("incubating") if getattr(s, "domain", "trading") == "trading"]
    ))
    trials = trials_all[:trial_slots]
    eligible_lessons = [l for l in h.memory.all()
                        if (asof is None or l.learned_asof is None or l.learned_asof <= asof)
                        and getattr(l, "domain", "trading") == "trading"]
    lessons_sorted = sorted(
        (l for l in eligible_lessons if l.importance.weight() >= MIN_MEMORY_WEIGHT),
        key=lambda l: (-l.importance.weight(), l.lesson_id))
    lessons = lessons_sorted[:memory_budget]

    if collect is not None:
        for s in actives[skill_budget:]:
            collect({"kind": "skill", "id": s.skill_id, "status": "dropped", "reason": "budget-cut"})
        for s in trials_all[trial_slots:]:
            collect({"kind": "skill", "id": s.skill_id, "status": "dropped", "reason": "budget-cut"})
        for l in eligible_lessons:
            if l.importance.weight() < MIN_MEMORY_WEIGHT:
                collect({"kind": "lesson", "id": l.lesson_id, "status": "dropped", "reason": "weight-cut"})
        for l in lessons_sorted[memory_budget:]:
            collect({"kind": "lesson", "id": l.lesson_id, "status": "dropped", "reason": "budget-cut"})

    return Selection(skills=actives[:skill_budget], trials=trials, lessons=lessons)


def select_episodes_for_prompt(episode_store, *, phase_prior: str | None,
                               asof: date | datetime | None = None,
                               budget: int = DEFAULT_EPISODE_BUDGET,
                               collect: Callable[[dict], None] | None = None) -> list:
    """Recall PIT-masked episodes for the current regime, ranked (phase-match, recency, |advantage|), top
    budget. `episode_store` is duck-typed (.for_asof(asof) -> list[Episode]); None/asof-None -> [].

    `collect`: D3 prompt-audit hook (observe-only, default None = no behavior change) — reports episodes
    beyond `budget` that never make it into the returned list."""
    if episode_store is None:
        return []
    if isinstance(asof, datetime):
        asof = asof.date()
    if asof is None:
        return []
    # phase_from_read (not normalize_phase) on BOTH sides: episodes store the RAW prose regime_read as
    # `.phase` (e.g. "trend frontside"), which normalize_phase() can't map — so extract the canonical
    # token from the prose. Idempotent on an already-canonical prior (phase_from_read("trend") == "trend").
    canon = phase_from_read(phase_prior) if phase_prior else None
    pool = episode_store.for_asof(asof, limit=None)             # full PIT-masked pool; rank then top-budget

    def _key(e):
        ep_canon = phase_from_read(e.phase or "")
        match = 1 if (canon is not None and ep_canon == canon) else 0
        return (match, e.learned_asof or e.exit_date, abs(e.advantage))

    pool.sort(key=_key, reverse=True)
    if collect is not None:
        for e in pool[budget:]:
            collect({"kind": "episode", "id": e.episode_id, "status": "dropped", "reason": "budget-cut"})
    return pool[:budget]
