from __future__ import annotations

from datetime import date as Date


class LookaheadError(RuntimeError):
    """A request asked for data dated after the as-of cursor — lookahead blocked."""


class AsOfGuard:
    """Monotonic time boundary: only data dated <= as_of may be accessed."""

    def __init__(self, as_of: Date) -> None:
        self._as_of = as_of

    @property
    def as_of(self) -> Date:
        return self._as_of

    def check(self, requested: Date) -> None:
        if requested > self._as_of:
            raise LookaheadError(f"lookahead blocked: requested {requested} > cursor {self._as_of}")

    def advance(self, new_as_of: Date) -> None:
        if new_as_of < self._as_of:
            raise ValueError(f"cursor cannot move backward: {new_as_of} < {self._as_of}")
        self._as_of = new_as_of
