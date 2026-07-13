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


def test_run_verdict_shadow_path():
    # shadow=True runs Hexpert FIRST and seeds HCH's paired breaker with its daily_advantage series — a
    # distinct compare_harnesses path; smoke it through run_verdict so the --shadow flag has coverage.
    src, start, end = _fake()
    cr = rv.run_verdict(src, start, end, shadow=True, agent_llm_factory=_AGENT, refiner_llm_factory=_REFINER)
    assert isinstance(cr, ComparisonReport)
    assert set(cr.arms) == {"HCH", "Hexpert", "Hmin_chase", "Hmin_notrade"}
    assert cr.stat_verdict is not None


def test_comparison_to_view_matches_console_shape():
    # the --json mapper must produce exactly the dict shape the console's verdict page consumes
    from alpha_web.sample import sample_verdict
    src, start, end = _fake()
    cr = rv.run_verdict(src, start, end, agent_llm_factory=_AGENT, refiner_llm_factory=_REFINER)
    view = rv.comparison_to_view(cr, start=start, end=end, horizon=2, screen=True)
    assert set(view) == set(sample_verdict())                       # same top-level contract
    for name in ("HCH", "Hexpert", "Hmin_chase", "Hmin_notrade"):
        assert {"n_decisions", "n_candidates", "mean_excess", "hit_rate", "nuke_rate"} <= set(view["arms"][name])
    assert {"refines", "trips", "frozen_from"} <= set(view["arms"]["HCH"])   # HCH evolution counters
    assert {"verdict", "n_days", "mean_diff", "ci_low", "ci_high", "p_value", "mde"} <= set(view["stat_verdict"])
    assert view["window"]["start"] == start.isoformat()


def test_comparison_to_view_records_universe_screen():
    # the resolved universe screen rides its OWN key in the console JSON, distinct from the L4 `screen`
    # flag (which is a bool) — so a browsed run is unambiguous about which universe entry produced it.
    src, start, end = _fake()
    cr = rv.run_verdict(src, start, end, agent_llm_factory=_AGENT, refiner_llm_factory=_REFINER)
    view = rv.comparison_to_view(cr, start=start, end=end, horizon=2, screen=True,
                                 universe_screen="trend_template")
    assert view["window"]["universe_screen"] == "trend_template"
    assert view["window"]["screen"] is True                          # L4 flag not overloaded
    default = rv.comparison_to_view(cr, start=start, end=end, horizon=2, screen=True)
    assert default["window"]["universe_screen"] == "gainer"          # default momo entry


def test_comparison_to_view_records_seed_pack():
    # the resolved pack (the loaded H's vocabulary) rides its own key in the console JSON, so a browsed
    # verdict is unambiguous about which pack (both arms) produced the comparison.
    src, start, end = _fake()
    cr = rv.run_verdict(src, start, end, agent_llm_factory=_AGENT, refiner_llm_factory=_REFINER)
    view = rv.comparison_to_view(cr, start=start, end=end, horizon=2, screen=True, seed_pack="growth")
    assert view["window"]["seed_pack"] == "growth"
    default = rv.comparison_to_view(cr, start=start, end=end, horizon=2, screen=True)
    assert default["window"]["seed_pack"] == "momo"                  # default momo pack


def test_run_verdict_json_flag_writes_console_file(tmp_path, monkeypatch):
    # the CLI --json path: write a file the console can read back
    import json
    src, start, end = _fake()
    out = tmp_path / "v.json"
    monkeypatch.setattr(sys, "argv", ["run_verdict", "PIT", start.isoformat(), end.isoformat(),
                                      "--json", str(out)])
    monkeypatch.setattr(rv, "SnapshotSource", lambda *_a, **_k: src)        # bypass the on-disk PIT load
    monkeypatch.setattr(rv, "PITStore", lambda *_a, **_k: None)
    monkeypatch.setattr(rv, "make_client", lambda role: _AGENT() if role == "agent" else _REFINER())
    rv.main()
    data = json.loads(out.read_text())
    assert {"window", "arms", "headline", "stat_verdict"} <= set(data)


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


# ---------------------------------------------------------------------------
# Task 6: run_verdict threads a read-only recall_store into BOTH arms (symmetric)
# ---------------------------------------------------------------------------

def _seed_taboo_store(symbol="RUN", n=3):
    """recall_store seeded so `symbol` is taboo: n PIT-old nuked episodes (learned long before the run)."""
    from alpha.memory.store import EpisodeStore
    from alpha.memory.episodes import Episode
    s = EpisodeStore.in_memory()
    for i in range(n):
        s.add(Episode(episode_id=f"{symbol}:{i}", symbol=symbol, skill_id="gap_and_go",
                      entry_date=date(2026, 1, 1), exit_date=date(2026, 1, 2),
                      outcome="nuked", advantage=-2.0, learned_asof=date(2026, 1, 2)))
    return s


def test_run_verdict_threads_recall_store():
    """recall_store passes through run_verdict into the comparison (read-only; never mutated by a verdict)."""
    store = _seed_taboo_store("RUN")
    n_before = len(store.for_asof(date(2099, 1, 1), limit=None))
    cr = rv.run_verdict(*_fake(), agent_llm_factory=_AGENT, refiner_llm_factory=_REFINER,
                        recall_store=store)
    assert isinstance(cr, ComparisonReport)
    assert len(store.for_asof(date(2099, 1, 1), limit=None)) == n_before   # read-only: unchanged


def test_run_verdict_recall_store_none_default():
    """No recall_store (the default None) -> today's verdict numbers (additive default-off)."""
    a = rv.run_verdict(*_fake(), agent_llm_factory=_AGENT, refiner_llm_factory=_REFINER)
    b = rv.run_verdict(*_fake(), agent_llm_factory=_AGENT, refiner_llm_factory=_REFINER,
                       recall_store=None)
    assert a.hch_minus_hexpert_mean_excess == b.hch_minus_hexpert_mean_excess


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
    # requesting more windows than the data supports is capped at len(days)//(horizon+1) = 12//3 = 4
    assert len(rv.split_windows(cal, start, end, 10, horizon=2)) == 4
