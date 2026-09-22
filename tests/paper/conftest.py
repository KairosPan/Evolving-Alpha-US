from __future__ import annotations

from datetime import datetime, timezone

import pytest


@pytest.fixture
def clock():
    """A clock that ticks one second per call, so ledger rows have distinct, sortable stamps."""
    state = {"n": 0}

    def now():
        state["n"] += 1
        return datetime(2026, 9, 22, 12, 0, 0, tzinfo=timezone.utc).replace(
            minute=state["n"] // 60, second=state["n"] % 60)
    return now
