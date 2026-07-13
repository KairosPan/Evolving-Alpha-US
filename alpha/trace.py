"""The non-deferred trace kernel (charter *Session Is Not the Context Window → Traces*; A4).

Trace design at large is deferred; four pieces are carved out non-deferred because decided
mechanisms already depend on them: the **principal-origin stamp**, the **append-time integrity
chain** (both wired at their own sites — `alpha/llm/chat.py` + `alpha/meta/models.py` message
capture, `alpha/harness/edit_log.py`), the **attribution tuple**, and the **kernel counter-event
schema**. This module is the shared vocabulary home for the first, third, and fourth, plus the
`Scope` labels the charter's *Memory Design* names as un-retrofittable.

Leaf module by design: imports only pydantic/typing and `alpha.__version__` — never
`alpha.harness`/`alpha.memory` — so the low-level `alpha/llm/chat.py` can import it without a cycle
(mirrors `alpha/redact.py`, `alpha/integrity.py`).
"""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict

from alpha import __version__ as KERNEL_VERSION

# --- Principal origin (charter *Trust Roots → Event-level principal origin*) ----------------------
# Stamped at intake from the physical entry path, NEVER inferred from content. `None` = legacy /
# unstamped (a message with no recorded entry path); it never equals "tool", so a legacy or
# model-authored message can never be mistaken for a stamped tool result.
MessageOrigin = Literal["kernel", "system", "tool", "user", "model"]


def is_tool_result(msg) -> bool:
    """True only for a message STAMPED as a tool result — keys off the origin stamp, never the
    forgeable ``"[tool:{name} result]"`` text convention a model could author itself."""
    return getattr(msg, "origin", None) == "tool"


# --- Scope labels (charter *Memory Design → scope labels from day one*; *The External Channel*) ---
# Rides every learned-context write so learning can be split when a second party/instance arrives;
# un-retrofittable if skipped. A4 lands the labels; the wider-than-evidence gate that consumes them
# is A8. Values are the charter's three, verbatim.
Scope = Literal["agent-global", "per-party", "per-session"]
DEFAULT_SCOPE: Scope = "agent-global"   # today's corpus is Kairos's craft = agent-global (see spec)

# Scope width ordering (narrow -> wide): per-session < per-party < agent-global. Consumed by A8's
# gate-level scope-mismatch check (an edit landing WIDER than its cited evidence's scope bounces).
_SCOPE_RANK: dict[str, int] = {"per-session": 0, "per-party": 1, "agent-global": 2}
SCOPES = frozenset(_SCOPE_RANK)   # the three valid scope values (membership test for the gate)


def scope_rank(scope: str) -> int:
    """Width rank of a scope (higher = wider). Unknown scopes rank narrowest (fail-toward-strict)."""
    return _SCOPE_RANK.get(scope, 0)


def is_scope_wider(landed: str, evidence: str) -> bool:
    """True iff `landed` is a WIDER scope than `evidence` — the scope-mismatch condition (A8)."""
    return scope_rank(landed) > scope_rank(evidence)


# --- Attribution tuple (charter *Traces*; *Edit Acceptance Protocol* — watchdog incident attribution)
class AttributionTuple(BaseModel):
    """body-version × model-id × kernel-version, stamped on an event so "which recent edits — or
    which release or model swap — are prime suspects" is computable and a model/release swap is
    never misattributed to innocent Body commits. A1's ``harness_digest`` is the body-version leg."""
    model_config = ConfigDict(frozen=True)
    body_digest: str | None = None      # harness_digest(h) — composed by the caller, passed in
    model_id: str | None = None         # the LLM model id in the decision, None if unknown
    kernel_version: str = KERNEL_VERSION


def attribution_of(*, body_digest: str | None, model_id: str | None) -> AttributionTuple:
    """Compose the attribution tuple, filling the kernel-version leg from ``alpha.__version__``."""
    return AttributionTuple(body_digest=body_digest, model_id=model_id, kernel_version=KERNEL_VERSION)


# --- Kernel counter-event schema (charter *Component Lifecycle & Telemetry*) ----------------------
class KernelCounterEvent(BaseModel):
    """The minimal per-component counter the kernel derives from events it observes ITSELF —
    schema only in A4. Success is execution-level ("completed without error"), the kernel's
    observation, never the component's self-report. The live derivation is the deferred
    Component-Lifecycle arc; landing the schema reconciles the v2.5 prerequisite with the Traces
    deferral (charter: "counters ride the session event log as kernel-stamped events")."""
    model_config = ConfigDict(frozen=True)
    component_id: str
    component_class: str                # skill | workflow | connector | subagent | plugin | tool
    invocations: int = 0
    exceptions: int = 0
    latency_ms: float = 0.0
    cost: float = 0.0
    origin: MessageOrigin = "kernel"    # kernel-derived, agent-unwritable
