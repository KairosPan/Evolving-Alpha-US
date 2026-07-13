"""Growth-doctrine phase vocabulary (P0.3, Option B — parallel per-scale clocks).

The growth manuscript reads three scale-typed clocks (market/theme/stock; §1), each meaningless
without its scale. Per the ratified Option B (2026-07-12-p01-phase-vocabulary-decision.md) this
namespace is DISJOINT from the momo `CANONICAL_PHASES`: scale rides inside the token as
`"<scale>:<phase>"` (e.g. "market:confirmed_uptrend", "theme:emerging", "stock:advance"). A momo
token has no ":" and a growth token has one, so the two never collide — and each normalizer drops
the other's tokens (loudly), which is the co-residence tripwire the momo/growth bar needs.

`normalize_growth_phases` mirrors `regime.normalize_phases`' signature so `load_seeds(...,
vocabulary="growth")` can pass it straight into the unchanged `from_seed` classmethods.
"""
from __future__ import annotations

GROWTH_SCALES = ["market", "theme", "stock"]

# Per-scale legal phases. `panic_state` is the manuscript's cross-cut market FLAG (§1.1), admitted
# as a legal market token so panic doctrine can be tagged; it is not a mutually-exclusive state.
GROWTH_PHASES: dict[str, list[str]] = {
    "market": ["confirmed_uptrend", "under_pressure", "correction", "panic_state"],
    "theme": ["emerging", "institutional", "public_laggard", "exhaustion"],
    "stock": ["base", "advance", "top", "decline"],
}

# The flat set of legal "scale:phase" tokens (for validation + the drop warning).
GROWTH_TOKENS = [f"{scale}:{phase}" for scale in GROWTH_SCALES for phase in GROWTH_PHASES[scale]]


def normalize_growth_phase(raw: object) -> str | None:
    """Map a raw token to a canonical "scale:phase", or None if not a legal growth token.

    A legal token is "<scale>:<phase>" where scale is a growth scale and phase is one of that
    scale's declared phases. Bare momo tokens (no ":") and unknown scale/phase pairs return None.
    """
    if not isinstance(raw, str):
        return None
    tok = raw.strip().lower()
    scale, sep, phase = tok.partition(":")
    if not sep:
        return None
    if scale in GROWTH_PHASES and phase in GROWTH_PHASES[scale]:
        return f"{scale}:{phase}"
    return None


def normalize_growth_phases(raw: str | list[str] | None) -> tuple[list[str], bool]:
    """Normalize raw growth phase token(s) to (canonical_tokens, applies_all).

    Same contract as `regime.normalize_phases` (single string wrapped to one token; 'all' any case
    sets applies_all; unrecognized tokens dropped but NAMED in a warning, not silent; first-seen
    order kept) — so it is a drop-in normalizer for the growth seed pack.
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
        p = normalize_growth_phase(item)
        if p is None:
            dropped.append(item)
        elif p not in phases:
            phases.append(p)
    if dropped:                            # loud, not silent (repo idiom: print 'warning:')
        print(f"warning: normalize_growth_phases dropped unrecognized token(s) {dropped}; "
              f"legal = {GROWTH_TOKENS}")
    return (phases, applies_all)


def growth_scale_of(token: str) -> str | None:
    """The scale of a legal growth token, or None if the token is not legal."""
    p = normalize_growth_phase(token)
    return p.split(":", 1)[0] if p is not None else None
