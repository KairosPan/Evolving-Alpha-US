"""Data-access layer for the console: read the REAL seeds (the evolving brain) and expose the
filter/stat helpers the templates consume. Pure reads — the console never mutates harness state.

The six-phase cycle (`PHASES`) is the canonical taxonomy that drives the signature phase ring and
the regime colour language; its membership/order/frontside set mirrors `alpha.regime.classifier`.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from pathlib import Path

from alpha.harness.doctrine import DoctrineEntry
from alpha.harness.loader import load_seeds
from alpha.harness.memory import Lesson
from alpha.harness.skill import Skill
from alpha.harness.state import HarnessState
from alpha.meta.store import LiveBrainStore
from alpha.settings import Settings

# ── locations ────────────────────────────────────────────────────────────────
WEB_DIR = Path(__file__).resolve().parent
STATIC_DIR = WEB_DIR / "static"
TEMPLATES_DIR = WEB_DIR / "templates"
SEEDS_DIR = WEB_DIR.parent / "seeds"

FAMILIES = ["runner", "swing", "event", "meme"]


@dataclass(frozen=True)
class Phase:
    """One station of the speculation cycle — drives the phase ring, the colour language, and the
    regime taxonomy. `pos` is the clock position (0=top, clockwise) used to place the ring needle."""
    key: str
    label: str
    tagline: str          # one-line read of what the tape feels like in this phase
    frontside: bool       # risk-on (enter only here) vs backside (every pop sold)
    pos: int              # 0..5 around the ring


# Ordered cold -> heat -> cooldown, the thermal arc of a speculation cycle.
PHASES: list[Phase] = [
    Phase("washout", "Washout", "Cash is a position. Capitulation, no leadership yet.", False, 0),
    Phase("recovery", "Recovery", "First clean gap-and-go survivors. Probe size only.", True, 1),
    Phase("ignition", "Ignition", "The lead runner and first sympathy ignite. Enter the follow-through.", True, 2),
    Phase("trend", "Trend", "Full momentum. Ride the leaders, add on reclaims, trim blowoffs.", True, 3),
    Phase("distribution", "Distribution", "Leaders break on volume. Get smaller, raise stops.", False, 4),
    Phase("flush", "Flush", "The violent unwind. Squeezes top into max pain.", False, 5),
]
PHASE_BY_KEY: dict[str, Phase] = {p.key: p for p in PHASES}


def _live_store() -> LiveBrainStore | None:
    root = Settings.from_env().web_live_brain_dir
    return LiveBrainStore(root) if root else None


def load_brain(seeds_dir: str | Path = SEEDS_DIR) -> HarnessState:
    """The live brain: prefer the LiveBrainStore (ALPHA_LIVE_BRAIN_DIR) when it exists, else the
    frozen seeds. Side-effect-free: a GET never writes (init-from-seeds happens only on apply)."""
    store = _live_store()
    if store is not None and store.is_live():
        return store.load()[0]
    return load_seeds(seeds_dir)


def brain_badge() -> dict:
    """Live-vs-seed status + edit count for the console badge."""
    store = _live_store()
    if store is not None and store.is_live():
        return {"is_live": True, "edit_count": store.edit_count()}
    return {"is_live": False, "edit_count": 0}


# ── stats ────────────────────────────────────────────────────────────────────
def _count_by(items, attr) -> dict[str, int]:
    out: dict[str, int] = {}
    for it in items:
        out[getattr(it, attr)] = out.get(getattr(it, attr), 0) + 1
    return out


def brain_stats(state: HarnessState) -> dict:
    """Headline counts for the deck — totals + the breakdowns the cards surface."""
    doctrine = state.doctrine.entries
    lessons = state.memory.all()
    skills = state.skills.all()
    return {
        "doctrine": {
            "total": len(doctrine),
            "immutable": sum(e.immutable for e in doctrine),
            "mutable": sum(not e.immutable for e in doctrine),
        },
        "memory": {
            "total": len(lessons),
            "by_outcome": _count_by(lessons, "outcome"),
            "by_family": _count_by([l for l in lessons if l.family], "family"),
        },
        "skills": {
            "total": len(skills),
            "active": len(state.skills.by_status("active")),
            "incubating": len(state.skills.by_status("incubating")),
            "by_type": _count_by(skills, "type"),
            "by_family": _count_by(skills, "family"),
            "by_status": _count_by(skills, "status"),
        },
    }


# ── filters (templates pass query params straight through) ─────────────────────
def filter_skills(state: HarnessState, *, family: str | None = None, status: str | None = None,
                  type: str | None = None, phase: str | None = None) -> list[Skill]:
    out = state.skills.all()
    if family:
        out = [s for s in out if s.family == family]
    if status:
        out = [s for s in out if s.status == status]
    if type:
        out = [s for s in out if s.type == type]
    if phase:
        out = [s for s in out if phase in s.phases or s.applies_all_phases]
    return out


def filter_lessons(state: HarnessState, *, family: str | None = None, outcome: str | None = None,
                   phase: str | None = None) -> list[Lesson]:
    out = state.memory.all()
    if family:
        out = [l for l in out if l.family == family]
    if outcome:
        out = [l for l in out if l.outcome == outcome]
    if phase:
        out = [l for l in out if phase in l.phases or l.applies_all_phases]
    return out


def split_doctrine(state: HarnessState) -> tuple[list[DoctrineEntry], list[DoctrineEntry]]:
    """(immutable red-lines, evolvable plays) — the two halves the Doctrine page lays out."""
    return state.doctrine.immutable_core(), state.doctrine.mutable_entries()


# ── phase-ring geometry (the signature element) ────────────────────────────────
RING_CX = RING_CY = 60
RING_R = 46


def ring_segments(r: int = RING_R, gap_deg: float = 7.0) -> dict:
    """Precompute SVG geometry for the six-phase ring (Jinja has no trig). Each phase owns a 60°
    arc on a circle of radius `r`; the active phase brightens and gets an outer marker dot."""
    circ = 2 * math.pi * r
    visible = (60 - gap_deg) / 360.0
    dash = circ * visible
    segs = []
    for p in PHASES:
        rotate = -90 + 60 * p.pos + gap_deg / 2.0       # start of the visible arc (top = -90°)
        mid_rad = math.radians(-90 + 60 * p.pos + 30)   # centre of the segment, for the marker
        segs.append({
            "phase": p,
            "dasharray": f"{dash:.2f} {circ - dash:.2f}",
            "rotate": round(rotate, 2),
            "mx": round(RING_CX + r * math.cos(mid_rad), 2),
            "my": round(RING_CY + r * math.sin(mid_rad), 2),
        })
    return {"cx": RING_CX, "cy": RING_CY, "r": r, "segments": segs}
