"""PB-8: verdict-4 fence regression.

Prove that inserting `kind="task"` episodes into the shared recall brain.db has ZERO effect on
any HCH-vs-Hexpert number produced by compare_harnesses / multi_window.  The fence is
`for_asof(kind="trade")` (the default), which silently excludes every task row from every
recall/taboo/forge call on the verdict path.

Design:
  - Build a shared in-memory EpisodeStore (the recall_store).
  - Run 1: compare_harnesses over the fake window with the clean store.
  - Inject several kind="task" episodes with learned_asof <= the verdict window's asof.
  - Run 2: compare_harnesses over the SAME window with the SAME store (now contains task rows).
  - Assert every reported number is bit-identical.

If the assertion fails, a verdict-path consumer is calling for_asof(kind=None) — fix that
call site, do NOT loosen the fence.
"""
from __future__ import annotations

import tempfile
from datetime import date
from pathlib import Path

import pandas as pd

from alpha.data.source import FakeSource
from alpha.harness.loader import load_seeds
from alpha.harness.snapshot import SnapshotStore
from alpha.llm.client import MockLLMClient
from alpha.loop.compare import compare_harnesses, multi_window
from alpha.loop.inner_loop import LoopConfig
from alpha.memory.episodes import Episode
from alpha.memory.store import EpisodeStore

SEEDS = Path(__file__).resolve().parents[2] / "seeds"


# ---------------------------------------------------------------------------
# Helpers (mirror test_compare.py)
# ---------------------------------------------------------------------------

def _source(n: int = 6, rate: float = 1.15) -> FakeSource:
    cal = [date(2026, 6, d) for d in range(1, 1 + n)]
    snaps, px = {}, 10.0
    closes = []
    for d in cal:
        prev = px
        px = px * rate
        closes.append(px)
        snaps[d] = pd.DataFrame(
            {"symbol": ["RUN"], "name": ["RUN"],
             "open": [prev], "high": [px],
             "low": [prev], "close": [px],
             "volume": [1], "prev_close": [prev]},
        )
    bars = {
        "RUN": pd.DataFrame(
            {"date": cal, "open": [10.0] + closes[:-1], "high": closes,
             "low": [10.0] + closes[:-1], "close": closes, "volume": [1] * n},
        )
    }
    return FakeSource(calendar=cal, bars=bars, snapshots=snaps)


def _cfg() -> LoopConfig:
    return LoopConfig(horizon=2, evidence_min=2, refine_every=1)


def _agent_llm() -> MockLLMClient:
    return MockLLMClient(
        '{"regime_read": "trend", "candidates": '
        '[{"symbol": "RUN", "pattern": "gap_and_go", "confidence": 0.7}]}'
    )


def _refiner_llm() -> MockLLMClient:
    return MockLLMClient('{"ops": []}')


def _store_factory():
    return SnapshotStore(tempfile.mkdtemp())


def _run(recall_store: EpisodeStore) -> "ComparisonReport":  # noqa: F821
    src = _source()
    return compare_harnesses(
        lambda: load_seeds(SEEDS),
        src,
        src.trading_calendar()[0],
        src.trading_calendar()[-1],
        agent_llm_factory=_agent_llm,
        refiner_llm_factory=_refiner_llm,
        store_factory=_store_factory,
        loop_config=_cfg(),
        recall_store=recall_store,
    )


def _insert_task_episodes(store: EpisodeStore, n: int = 5) -> None:
    """Insert `n` kind="task" episodes with learned_asof inside the verdict window (PIT-visible)."""
    for i in range(n):
        store.add(
            Episode(
                episode_id=f"task:{i}",
                symbol="",
                skill_id="__task__",
                kind="task",
                entry_date=date(2026, 6, 1),
                exit_date=date(2026, 6, 1),
                outcome="succeeded",
                advantage=0.0,
                learned_asof=date(2026, 6, 1),  # <= verdict window asof → PIT-visible
            )
        )


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

def test_verdict_neutral_to_task_episodes_single_window():
    """compare_harnesses numbers are bit-identical before and after injecting kind="task" rows."""
    store = EpisodeStore.in_memory()

    # Run 1: clean store (no task rows)
    cr1 = _run(recall_store=store)

    # Inject task episodes into the SAME store
    _insert_task_episodes(store, n=5)

    # Run 2: store now has task rows — numbers MUST be unchanged
    cr2 = _run(recall_store=store)

    # Headline number
    assert cr1.hch_minus_hexpert_mean_excess == cr2.hch_minus_hexpert_mean_excess, (
        f"hch_minus_hexpert_mean_excess changed after task-row injection: "
        f"{cr1.hch_minus_hexpert_mean_excess!r} -> {cr2.hch_minus_hexpert_mean_excess!r}. "
        "A verdict-path consumer is calling for_asof(kind=None) — fix that call site."
    )
    # Supporting numbers
    assert cr1.hch_minus_hexpert_mean_score == cr2.hch_minus_hexpert_mean_score
    assert cr1.hch_minus_hexpert_hit_rate == cr2.hch_minus_hexpert_hit_rate
    assert cr1.hch_minus_hexpert_nuke_rate == cr2.hch_minus_hexpert_nuke_rate
    assert cr1.hch_beats_hexpert == cr2.hch_beats_hexpert

    # Per-arm candidate counts (taboo must not fire on task rows)
    assert cr1.arms["HCH"].report.n_candidates == cr2.arms["HCH"].report.n_candidates
    assert cr1.arms["Hexpert"].report.n_candidates == cr2.arms["Hexpert"].report.n_candidates


def test_verdict_neutral_to_task_episodes_multi_window():
    """multi_window per-window deltas and verdict labels are bit-identical after task-row injection."""
    src = _source(n=10)
    cal = src.trading_calendar()
    windows = [(cal[0], cal[4]), (cal[5], cal[9])]

    store = EpisodeStore.in_memory()

    def _mw(recall_store):
        return multi_window(
            lambda: load_seeds(SEEDS),
            src,
            windows,
            agent_llm_factory=_agent_llm,
            refiner_llm_factory=_refiner_llm,
            store_factory=_store_factory,
            loop_config=_cfg(),
            recall_store=recall_store,
        )

    # Run 1: clean
    mw1 = _mw(store)

    # Inject task episodes (learned_asof within the first window)
    _insert_task_episodes(store, n=7)

    # Run 2: after injection
    mw2 = _mw(store)

    assert mw1.deltas == mw2.deltas, (
        f"per-window deltas changed after task-row injection: {mw1.deltas!r} -> {mw2.deltas!r}. "
        "A verdict-path consumer is calling for_asof(kind=None) — fix that call site."
    )
    assert mw1.verdicts == mw2.verdicts
    assert mw1.mean_delta == mw2.mean_delta
    assert mw1.win_rate == mw2.win_rate
