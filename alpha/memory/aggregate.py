from __future__ import annotations
from typing import Callable
from pydantic import BaseModel, ConfigDict
from alpha.memory.episodes import Episode


class EpisodeStats(BaseModel):
    """Aggregate outcome stats for a group of episodes (per symbol / skill / narrative)."""
    model_config = ConfigDict(frozen=True)
    n: int
    continued: int
    faded: int
    nuked: int
    mean_advantage: float

    @property
    def nuke_rate(self) -> float:
        return self.nuked / self.n if self.n else 0.0

    @property
    def win_rate(self) -> float:
        return self.continued / self.n if self.n else 0.0


def summarize(episodes: list[Episode], *, key: Callable[[Episode], str]) -> dict[str, EpisodeStats]:
    """Group episodes by `key` and tally outcomes + mean advantage. Pure + deterministic."""
    buckets: dict[str, list[Episode]] = {}
    for e in episodes:
        buckets.setdefault(key(e), []).append(e)
    out: dict[str, EpisodeStats] = {}
    for k, eps in buckets.items():
        n = len(eps)
        out[k] = EpisodeStats(
            n=n,
            continued=sum(1 for e in eps if e.outcome == "continued"),
            faded=sum(1 for e in eps if e.outcome == "faded"),
            nuked=sum(1 for e in eps if e.outcome == "nuked"),
            mean_advantage=(sum(e.advantage for e in eps) / n) if n else 0.0)
    return out


def is_episode_taboo(stats: EpisodeStats | None, *, min_samples: int = 3, nuke_rate: float = 0.5) -> bool:
    """A symbol/skill is taboo when it has enough history (>= min_samples) that mostly nukes (>= nuke_rate)."""
    return stats is not None and stats.n >= min_samples and stats.nuke_rate >= nuke_rate


# ---------------------------------------------------------------------------
# Task aggregator (kind="task" episodes, PC-7)
# ---------------------------------------------------------------------------

class TaskStats(BaseModel):
    """Aggregate outcome stats for kind='task' episodes (per skill_id or any key).

    Counts the task vocabulary (succeeded/failed/incomplete) and tracks externally-confirmed
    positives to guard against Goodhart's law (verdict 5): a synchronous agent-authored
    'succeeded' with no external confirmation is neutral — it raises n/succeeded but never
    confirmed_success or confirmed_n.

    confirmed_success: episodes both in the caller-supplied confirmation set AND outcome='succeeded'.
    confirmed_n:       episodes carrying any external confirmation signal (success or fail).
    confirmed_success_rate: confirmed_success / confirmed_n; 0.0 when confirmed_n == 0.
    """
    model_config = ConfigDict(frozen=True)
    n: int
    succeeded: int
    failed: int
    incomplete: int
    confirmed_success: int
    confirmed_n: int

    @property
    def confirmed_success_rate(self) -> float:
        return self.confirmed_success / self.confirmed_n if self.confirmed_n else 0.0


def summarize_task(
    episodes: list[Episode],
    *,
    key: Callable[[Episode], str],
    confirmed_ids: frozenset[str] = frozenset(),
) -> dict[str, TaskStats]:
    """Group task episodes by `key` and tally task outcomes + confirmed-positive counts.

    confirmed_ids: set of episode_id values that carry an external confirmation signal
        (e.g. EditProvenance.human_approver set, or an independent verifier pass).
        The caller resolves the join (applied_seq / edit_id); this function is a pure aggregator.

    Anti-Goodhart (verdict 5): a 'succeeded' episode NOT in confirmed_ids is neutral — it
    raises n and succeeded but does NOT contribute to confirmed_success or confirmed_n.
    Pure + deterministic; reads only, never writes.
    """
    buckets: dict[str, list[Episode]] = {}
    for e in episodes:
        buckets.setdefault(key(e), []).append(e)
    out: dict[str, TaskStats] = {}
    for k, eps in buckets.items():
        confirmed_eps = [e for e in eps if e.episode_id in confirmed_ids]
        out[k] = TaskStats(
            n=len(eps),
            succeeded=sum(1 for e in eps if e.outcome == "succeeded"),
            failed=sum(1 for e in eps if e.outcome == "failed"),
            incomplete=sum(1 for e in eps if e.outcome == "incomplete"),
            confirmed_success=sum(1 for e in confirmed_eps if e.outcome == "succeeded"),
            confirmed_n=len(confirmed_eps),
        )
    return out
