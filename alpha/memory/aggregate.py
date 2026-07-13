from __future__ import annotations
from datetime import date as Date, timedelta
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
# Taboo scoping refinements (P7 #2): phase-scoped + recency-windowed.
# Both are ADDITIVE, default-off pure filters over the episode list. The v1 taboo path
# (screen.py: summarize(for_asof(...)) -> is_episode_taboo) is UNCHANGED; a future guard wiring
# swaps its is_episode_taboo(...) call for is_episode_taboo_scoped(..., phase=, window_days=, asof=).
# ---------------------------------------------------------------------------

def _identity(p: str) -> str:
    return p


def within_recency_window(episodes: list[Episode], *, asof: Date, window_days: int) -> list[Episode]:
    """Keep episodes whose outcome became knowable within the last `window_days` of `asof`:
    (asof - window_days) <= learned_asof <= asof. Enforces BOTH bounds, so it is PIT-safe even on an
    un-masked list — an old blowup ages out of the window (stops tabooing a name forever)."""
    lo = asof - timedelta(days=window_days)
    return [e for e in episodes if lo <= (e.learned_asof or e.exit_date) <= asof]


def matching_phase(episodes: list[Episode], *, phase: str,
                   phase_of: Callable[[str], str | None] = _identity) -> list[Episode]:
    """Keep episodes whose canonicalized phase equals `phase_of(phase)`. `phase_of` defaults to
    identity (callers pass canonical tokens); a guard wiring passes phase_from_read for RAW-prose
    episode phases (episodes store the raw regime_read in `.phase`)."""
    target = phase_of(phase)
    return [e for e in episodes if phase_of(e.phase or "") == target]


def is_episode_taboo_scoped(episodes: list[Episode], symbol: str, *,
                            phase: str | None = None,
                            phase_of: Callable[[str], str | None] = _identity,
                            window_days: int | None = None, asof: Date | None = None,
                            min_samples: int = 3, nuke_rate: float = 0.5) -> bool:
    """Phase-scoped and/or recency-windowed taboo test for one symbol (pure, default-off).

    With no `phase` and no `window_days` this reduces EXACTLY to the v1 semantics
    `is_episode_taboo(summarize(episodes, key=symbol).get(symbol))`. Pass `phase` to veto only when
    the name nukes in the CURRENT regime; pass `window_days` (+`asof`) to ignore blowups older than
    the window. Both compose. `window_days` requires `asof` (raises ValueError — fail loud)."""
    if window_days is not None:
        if asof is None:
            raise ValueError("window_days requires asof")
        episodes = within_recency_window(episodes, asof=asof, window_days=window_days)
    if phase is not None:
        episodes = matching_phase(episodes, phase=phase, phase_of=phase_of)
    stats = summarize(episodes, key=lambda e: e.symbol).get(symbol)
    return is_episode_taboo(stats, min_samples=min_samples, nuke_rate=nuke_rate)


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
