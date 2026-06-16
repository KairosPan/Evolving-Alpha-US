"""Offline smoke for scripts/run_verdict.py: the verdict runner wires a captured source through
compare_harnesses/multi_window with injected MockLLM factories (real keys/data are not needed to validate
the apparatus). Proves the report STRUCTURE end-to-end on both the in-memory and the on-disk PIT path."""
import sys
import tempfile
from datetime import date
from pathlib import Path
import pandas as pd
from alpha.data.source import FakeSource
from alpha.data.pit_store import PITStore
from alpha.data.snapshot_source import SnapshotSource
from alpha.data.capture import capture_window
from alpha.llm.client import MockLLMClient
from alpha.loop.compare import ComparisonReport, MultiWindowReport

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))
import run_verdict as rv   # noqa: E402

_AGENT = lambda: MockLLMClient('{"candidates": [{"symbol": "RUN", "pattern": "gap_and_go"}]}')
_REFINER = lambda: MockLLMClient('{"ops": []}')


def _fake(n=12):
    cal = [date(2026, 6, d) for d in range(1, 1 + n)]
    snaps, px, closes = {}, 10.0, []
    for d in cal:
        prev = px; px = px * 1.15; closes.append(px)
        snaps[d] = pd.DataFrame({"symbol": ["RUN"], "name": ["RUN"], "open": [prev], "high": [px],
                                 "low": [prev], "close": [px], "volume": [1], "prev_close": [prev]})
    bars = {"RUN": pd.DataFrame({"date": cal, "open": [10.0] + closes[:-1], "high": closes,
                                 "low": [10.0] + closes[:-1], "close": closes, "volume": [1] * n})}
    return FakeSource(calendar=cal, bars=bars, snapshots=snaps), cal[0], cal[-1]


def test_run_verdict_single_window_structure():
    src, start, end = _fake()
    cr = rv.run_verdict(src, start, end, agent_llm_factory=_AGENT, refiner_llm_factory=_REFINER)
    assert isinstance(cr, ComparisonReport)
    assert set(cr.arms) == {"HCH", "Hexpert", "Hmin_chase", "Hmin_notrade"}
    assert cr.stat_verdict is not None and cr.stat_verdict.verdict in {"win", "loss", "flat", "insufficient"}
    assert cr.contribution is not None
    assert isinstance(cr.hch_minus_hexpert_mean_excess, float)


def test_run_verdict_multi_window():
    src, start, end = _fake()
    mw = rv.run_verdict(src, start, end, windows=3, agent_llm_factory=_AGENT, refiner_llm_factory=_REFINER)
    assert isinstance(mw, MultiWindowReport)
    assert mw.n_windows == 3
    assert len(mw.deltas) == 3 and len(mw.verdicts) == 3


def test_run_verdict_through_captured_pit_store():
    # the real CLI path: FakeSource -> capture_window -> PITStore (on disk) -> SnapshotSource -> verdict.
    src, start, end = _fake()
    store = PITStore(Path(tempfile.mkdtemp()))
    capture_window(src, store, start, end, ["RUN"])
    snap_src = SnapshotSource(store)
    cr = rv.run_verdict(snap_src, start, end, agent_llm_factory=_AGENT, refiner_llm_factory=_REFINER)
    assert isinstance(cr, ComparisonReport)
    assert set(cr.arms) == {"HCH", "Hexpert", "Hmin_chase", "Hmin_notrade"}


def test_formatters_render_key_sections():
    src, start, end = _fake()
    cr = rv.run_verdict(src, start, end, agent_llm_factory=_AGENT, refiner_llm_factory=_REFINER)
    out = rv.format_comparison(cr, header="hdr")
    for label in ("ARMS", "HEADLINE", "STAT VERDICT", "CONTRIBUTION", "HCH", "Hexpert"):
        assert label in out
    mw = rv.run_verdict(src, start, end, windows=3, agent_llm_factory=_AGENT, refiner_llm_factory=_REFINER)
    assert "MULTI-WINDOW" in rv.format_multi(mw)


def test_split_windows_partitions_contiguously():
    src, start, end = _fake(12)
    cal = src.trading_calendar()
    assert rv.split_windows(cal, start, end, 1, horizon=2) == [(start, end)]
    wins = rv.split_windows(cal, start, end, 3, horizon=2)
    assert len(wins) == 3
    assert wins[0][0] == start and wins[-1][1] == end          # cover the full span
    assert all(a[1] < b[0] for a, b in zip(wins, wins[1:]))     # contiguous, non-overlapping, ordered
    # a too-short span collapses to one window (never a sub-horizon slice)
    assert rv.split_windows(cal, start, cal[2], 3, horizon=2) == [(start, cal[2])]
