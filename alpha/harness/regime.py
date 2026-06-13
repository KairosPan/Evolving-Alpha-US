from __future__ import annotations

CANONICAL_PHASES = ["washout", "recovery", "ignition", "trend", "distribution", "flush"]
FAMILIES = ["runner", "swing", "event", "meme"]

# alias -> canonical phase (lowercase). Tolerant of Refiner-authored variants.
_PHASE_ALIASES = {
    "washout": "washout", "freeze": "washout", "bottom": "washout",
    "recovery": "recovery", "first-green": "recovery", "first_green": "recovery",
    "ignition": "ignition", "heating": "ignition",
    "trend": "trend", "momentum": "trend",
    "distribution": "distribution", "churn": "distribution",
    "flush": "flush", "exhaustion": "flush",
}


def normalize_phase(raw: object) -> str | None:
    """Map a raw phase token to a canonical phase, or None if unrecognized / not a string."""
    if not isinstance(raw, str):
        return None
    return _PHASE_ALIASES.get(raw.strip().lower())


def normalize_phases(raw: str | list[str] | None) -> tuple[list[str], bool]:
    """Normalize raw phase token(s) to (canonical_phases, applies_all).

    Accepts a single string (wrapped to one token, so a seed `regime: "all"` works) or a list;
    'all' (any case) sets applies_all; unrecognized tokens are dropped; first-seen order kept.
    """
    if isinstance(raw, str):
        raw = [raw]
    phases: list[str] = []
    applies_all = False
    for item in raw or []:
        if isinstance(item, str) and item.strip().lower() == "all":
            applies_all = True
            continue
        p = normalize_phase(item)
        if p is not None and p not in phases:
            phases.append(p)
    return (phases, applies_all)


def is_family(x: object) -> bool:
    return isinstance(x, str) and x in FAMILIES
