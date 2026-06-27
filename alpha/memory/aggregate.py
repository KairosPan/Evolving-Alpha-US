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
