from __future__ import annotations
from datetime import date
import pandas as pd
import pytest
from alpha.data.source import FakeSource


@pytest.fixture
def fake_source():
    """Two symbols over 3 days. RUN gaps up and runs; FLOP fades."""
    cal = [date(2026, 6, 10), date(2026, 6, 11), date(2026, 6, 12)]
    bars = {
        "RUN": pd.DataFrame({
            "date": cal,
            "open":  [10.0, 12.5, 16.0], "high": [12.0, 15.0, 18.0],
            "low":   [9.5, 12.0, 15.0],  "close": [11.0, 14.0, 17.0],
            "volume": [1_000_000, 3_000_000, 5_000_000],
        }),
        "FLOP": pd.DataFrame({
            "date": cal,
            "open":  [20.0, 21.0, 18.0], "high": [22.0, 21.5, 18.5],
            "low":   [19.0, 17.5, 16.0], "close": [21.0, 18.0, 16.5],
            "volume": [500_000, 600_000, 700_000],
        }),
    }
    snapshots = {
        date(2026, 6, 12): pd.DataFrame({
            "symbol": ["RUN", "FLOP"], "name": ["Runner Inc", "Flopco"],
            "open": [16.0, 18.0], "high": [18.0, 18.5], "low": [15.0, 16.0],
            "close": [17.0, 16.5], "volume": [5_000_000, 700_000],
            "prev_close": [14.0, 18.0],
        }),
    }
    corp = pd.DataFrame({
        "symbol": ["RUN"], "announce_date": [date(2026, 6, 9)],
        "ex_date": [date(2026, 6, 20)], "kind": ["reverse_split"], "ratio": [0.1],
    })
    return FakeSource(calendar=cal, bars=bars, snapshots=snapshots, corp_actions=corp)


@pytest.fixture
def brain_session_isolation(tmp_path, monkeypatch):
    """Point EVERY shared-state dir at a tmp dir so a test never touches real on-disk state.
    Shared by tests/web, tests/sonia and tests/workbench (their autouse fixtures depend on this —
    DRY: one definition). Not autouse here, so the offline core suite is unaffected.
    ALL FIVE vars matter: the 2026-07-09 cross-face reconcile sweeps make each face open the
    OTHER face's store too — isolating only your own face's dirs lets a rollback test rewrite
    the operator's real ./state records (caught by the final review as a blocker)."""
    monkeypatch.setenv("ALPHA_LIVE_BRAIN_DIR", str(tmp_path / "brain"))
    monkeypatch.setenv("ALPHA_SESSIONS_DIR", str(tmp_path / "sessions"))
    monkeypatch.setenv("ALPHA_PROJECTS_DB", str(tmp_path / "projects" / "state.db"))
    monkeypatch.setenv("ALPHA_CONFLICTS_DIR", str(tmp_path / "conflicts"))
    monkeypatch.setenv("ALPHA_PROPOSALS_DIR", str(tmp_path / "proposals"))
