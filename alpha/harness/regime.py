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


def phase_from_read(regime_read: str) -> str | None:
    """Extract the first CANONICAL phase token from a free-text regime_read.

    The output contract makes regime_read a multi-token string (e.g. 'trend frontside' or
    'AI frontside; trend'), so normalize_phase() on the whole string returns None. Scan tokens
    (comma/semicolon/space-separated) and return the first that maps to a canonical phase, else None.
    """
    for tok in (regime_read or "").replace(",", " ").replace(";", " ").split():
        p = normalize_phase(tok)
        if p is not None:
            return p
    return None


def normalize_phases(raw: str | list[str] | None) -> tuple[list[str], bool]:
    """Normalize raw phase token(s) to (canonical_phases, applies_all).

    Accepts a single string (wrapped to one token, so a seed `regime: "all"` works) or a list;
    'all' (any case) sets applies_all; unrecognized tokens are dropped; first-seen order kept.

    NOTE: a single string is treated as ONE token — it is NOT split on delimiters. So a seed value
    like `"trend/flush"` normalizes to ([], False) silently. US seeds use list-of-phases
    (`phases: ["trend", "flush"]`); use that form for multiple phases. (Differs from the CN
    parse_regime_field, which split compound strings.)
    """
    if isinstance(raw, str):
        raw = [raw]
    phases: list[str] = []
    applies_all = False
    dropped: list[object] = []
    for item in raw or []:
        if isinstance(item, str) and item.strip().lower() == "all":
            applies_all = True
            continue
        p = normalize_phase(item)
        if p is None:
            dropped.append(item)           # unrecognized: still dropped, but named below (not silent)
        elif p not in phases:
            phases.append(p)
    if dropped:                            # loud, not silent (repo idiom: print 'warning:'; see integrity_check)
        print(f"warning: normalize_phases dropped unrecognized phase token(s) {dropped}; "
              f"canonical = {CANONICAL_PHASES}")
    return (phases, applies_all)


def is_family(x: object) -> bool:
    return isinstance(x, str) and x in FAMILIES
