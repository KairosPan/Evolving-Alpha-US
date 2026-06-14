from __future__ import annotations


class HarnessError(RuntimeError):
    """Base class for harness-edit errors."""


class ImmutableDoctrineError(HarnessError):
    """Attempted to modify an immutable-core doctrine entry (a discipline red-line)."""


class InvalidTransitionError(HarnessError):
    """An illegal skill status transition (e.g. reviving a non-dormant skill)."""
