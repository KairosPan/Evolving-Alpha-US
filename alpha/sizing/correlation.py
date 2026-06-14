from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Pick:
    """A proposed pick. narrative = the correlation key (theme/sympathy); '' = untagged (stands alone).
    The narrative tag is supplied upstream (agent in US-2 / theme data in US-3)."""
    symbol: str
    narrative: str
    confidence: float


def group_by_narrative(picks: list[Pick]) -> dict[str, list[Pick]]:
    """Group picks by narrative. Untagged picks ('') are keyed by symbol so they never merge."""
    groups: dict[str, list[Pick]] = {}
    for p in picks:
        key = p.narrative if p.narrative else p.symbol
        groups.setdefault(key, []).append(p)
    return groups


def correlated_groups(picks: list[Pick]) -> list[list[str]]:
    """Symbol groups (>=2 members) that share a real narrative — each is ONE correlated bet.
    Sorted for determinism."""
    out: list[list[str]] = []
    for members in group_by_narrative(picks).values():
        if len(members) >= 2 and any(m.narrative for m in members):
            out.append(sorted(m.symbol for m in members))
    return sorted(out)
