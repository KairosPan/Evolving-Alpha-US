"""Right-drawer view-models for the Teach cockpit: the PENDING change-set (the session's
proposed/accepted edits) and the CURRENT brain summary (the live six-component mirror).

Pure functions — no I/O. The route hands in the Sonia session dict and a HarnessState (read via
data_access.load_brain), so these stay trivially unit-testable. The drawer is a surfacing layer:
it never mutates the brain; edits still flow through Sonia's gated apply."""
from __future__ import annotations

from dataclasses import dataclass

from alpha.harness.state import HarnessState

# ── PENDING (the change-set) ─────────────────────────────────────────────────
_ACTIONABLE = ("proposed", "accepted")


@dataclass(frozen=True)
class MessageGroup:
    """One assistant turn's edits, grouped so apply/rollback stay per-message (matching Sonia's
    per-message snapshot). `accepted` drives the Apply button; `applied` flips the group to the
    rollback line."""
    message_id: str
    edits: list[dict]
    accepted: int
    applied: bool


@dataclass(frozen=True)
class PendingView:
    session_id: str
    groups: list[MessageGroup]
    pending_count: int          # edits still actionable (proposed + accepted) across all groups


def pending_view(session: dict | None) -> PendingView:
    """Flatten a Sonia session dict into per-message edit groups. Messages without edits are
    skipped; a None/empty session yields an empty view."""
    session = session or {}
    groups: list[MessageGroup] = []
    pending = 0
    for m in session.get("messages", []):
        edits = m.get("edits") or []
        if not edits:
            continue
        pending += sum(1 for e in edits if e.get("status") in _ACTIONABLE)
        groups.append(MessageGroup(
            message_id=m.get("message_id", ""),
            edits=edits,
            accepted=sum(1 for e in edits if e.get("status") == "accepted"),
            applied=any(e.get("status") == "applied" for e in edits),
        ))
    return PendingView(session_id=session.get("session_id", ""), groups=groups, pending_count=pending)


# ── CURRENT brain (the live six-component mirror) ────────────────────────────
_STUBS = (
    ("workflow",  "Workflow",  "Named multi-step playbooks Sonia composes from skills."),
    ("connector", "Connector", "External data/tool connections the agent draws on (Alpaca, EDGAR, MCP feeds…)."),
    ("subagent",  "Subagent",  "Specialized dispatch sub-agents the master agent delegates to."),
)


@dataclass(frozen=True)
class Component:
    """One brain component row. Live components carry a count + item objects (Skill/Lesson/
    DoctrineEntry) the template renders; stubs carry a blurb and no count."""
    key: str
    label: str
    path: str            # full-page link ("" for stubs)
    count: int | None    # None → stub
    items: list          # [] for stubs
    is_stub: bool
    blurb: str = ""


@dataclass(frozen=True)
class BrainView:
    components: list[Component]


def brain_view(state: HarnessState) -> BrainView:
    """Mirror the six brain components in the left-rail order: three live (doctrine/memory/skills,
    with item lists) and three read-only stubs (workflow/connector/subagent)."""
    doctrine = list(state.doctrine.entries)
    lessons = state.memory.all()
    skills = state.skills.all()
    blurb = {k: b for k, _, b in _STUBS}
    return BrainView(components=[
        Component("doctrine",  "Doctrine",  "/doctrine", len(doctrine), doctrine, False),
        Component("memory",    "Memory",    "/memory",   len(lessons),  lessons,  False),
        Component("workflow",  "Workflow",  "", None, [], True, blurb["workflow"]),
        Component("skills",    "Skill",     "/skills",   len(skills),   skills,   False),
        Component("connector", "Connector", "", None, [], True, blurb["connector"]),
        Component("subagent",  "Subagent",  "", None, [], True, blurb["subagent"]),
    ])
