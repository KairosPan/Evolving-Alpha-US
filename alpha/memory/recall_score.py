# alpha/memory/recall_score.py
"""Soft blended episode-recall score (P7 refinement #1).

v1 recall (alpha/agent/retrieval.py::select_episodes_for_prompt) ranks recalled episodes
lexicographically by (phase_match, learned_asof, |advantage|) — a hard, tie-broken filter. This
module ships the *soft blend* named in the recall spec's Out-of-scope: a weighted sum over five
components (relevance / recency / importance / regime-distance / narrative) as a PURE function with
documented, hand-set weights.

Additive / default-off: this module is a new leaf (imports only Episode). Nothing calls it until a
future wiring adopts `blended_recall` in retrieval.py — so the live/verdict recall path is
byte-identical and the recall_store-into-both-arms verdict symmetry is intact by construction. A
wiring MUST keep both verdict arms on the same store (like the `screen` flag) to preserve symmetry.

The weights are hand-set / 文献-informed and CALIBRATABLE — the deferred DEVELOPMENT-PLAN §4
"Offline recall-weight tuning" is the calibrator, not this module.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date as Date
from typing import Callable

from alpha.memory.episodes import Episode


@dataclass(frozen=True)
class RecallWeights:
    """Blend weights for `recall_score`. Hand-set defaults in DEFAULT_RECALL_WEIGHTS."""
    w_rel: float    # phase-relevance (match indicator) — reward for same-regime recall
    w_rec: float    # recency (exponential decay)
    w_imp: float    # impact (|advantage|, saturating)
    w_reg: float    # regime-distance PENALTY (subtracted) — asymmetric partner of w_rel
    w_narr: float   # narrative match — inert until a pre-decision narrative signal exists


# Hand-set starting values (NOT tuned). Ordering mirrors v1's lexicographic rank
# (phase-match first, then recency, then |advantage|); w_narr strong-but-inert-by-default;
# w_reg penalizes off-regime recall. See the P7 spec weights table.
DEFAULT_RECALL_WEIGHTS = RecallWeights(w_rel=1.0, w_rec=0.6, w_imp=0.4, w_reg=0.5, w_narr=0.8)


def _identity(p: str | None) -> str | None:
    return p


def _binary_distance(a: str | None, b: str | None) -> float:
    """Default regime-distance: 0.0 when the two canonical phases are equal, else 1.0.

    A future wiring supplies a GRADED growth-clock distance (confirmed↔pressure closer than
    confirmed↔correction) — which is the whole point of a separate `w_reg` knob."""
    return 0.0 if a == b else 1.0


def recall_score(
    ep: Episode,
    *,
    asof: Date,
    phase: str | None = None,
    narrative: str | None = None,
    weights: RecallWeights = DEFAULT_RECALL_WEIGHTS,
    half_life_days: float = 63.0,
    imp_cap: float = 3.0,
    phase_of: Callable[[str | None], str | None] = _identity,
    phase_distance: Callable[[str | None, str | None], float] = _binary_distance,
) -> float:
    """The soft blended recall score for one episode against the current decision context (pure).

        score = w_rel·relevance + w_rec·recency + w_imp·importance
                − w_reg·regime_distance + w_narr·narrative_match

    Each component is in [0, 1]; regime-distance enters as a penalty (subtracted). `phase`/`narrative`
    are the CURRENT decision's regime/narrative (None ⇒ that component is inert). `phase_of`
    canonicalizes both the episode phase and `phase` (default identity so callers can pass canonical
    tokens directly; a wiring passes phase_from_read for RAW-prose episode phases)."""
    ep_phase = phase_of(ep.phase or "") if ep.phase else None
    cur_phase = phase_of(phase) if phase else None

    relevance = 1.0 if (cur_phase is not None and ep_phase == cur_phase) else 0.0
    # regime distance only penalizes when we HAVE a current regime to compare against.
    distance = phase_distance(ep_phase, cur_phase) if cur_phase is not None else 0.0

    learned = ep.learned_asof or ep.exit_date
    age_days = max(0, (asof - learned).days)                 # PIT: never negative
    recency = 0.5 ** (age_days / half_life_days) if half_life_days > 0 else (1.0 if age_days == 0 else 0.0)

    importance = min(1.0, abs(ep.advantage) / imp_cap) if imp_cap > 0 else 0.0

    narrative_match = 1.0 if (narrative and ep.narrative and ep.narrative == narrative) else 0.0

    return (weights.w_rel * relevance
            + weights.w_rec * recency
            + weights.w_imp * importance
            - weights.w_reg * distance
            + weights.w_narr * narrative_match)


def blended_recall(
    episodes: list[Episode],
    *,
    asof: Date,
    phase: str | None = None,
    narrative: str | None = None,
    budget: int = 8,
    **score_kwargs,
) -> list[Episode]:
    """Rank episodes by the soft blend, newest-first on ties, and return the top `budget`.

    Drop-in for retrieval.py's ranking (v1's `select_episodes_for_prompt` sort) once wired. PIT-guards
    defensively: any `learned_asof > asof` episode is dropped before scoring (upstream `for_asof`
    already masks; this keeps the blend layer independently PIT-honest). `budget=None` ⇒ no cap."""
    masked = [e for e in episodes if (e.learned_asof or e.exit_date) <= asof]
    scored = sorted(
        masked,
        key=lambda e: (recall_score(e, asof=asof, phase=phase, narrative=narrative, **score_kwargs),
                       e.learned_asof or e.exit_date, e.episode_id),
        reverse=True,
    )
    return scored if budget is None else scored[:budget]
