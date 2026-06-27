"""TDD test: refine_live writes episodes to ALPHA_EPISODES_DB when episodes_db is given.

Reuses the exact offline fixtures from tests/scripts/test_refine_live.py:
  - _seed_teaching_brain: brain dir with a teaching-owned lesson
  - _source(n=8): FakeSource with 8 days → 6 scored steps (horizon=2)
  - _PickRun: deterministic agent (no LLM)
  - LoopConfig(horizon=2, screen=False, size=False)
  - MockLLMClient with the same refiner script

The ONLY new assertion: EpisodeStore.open(db).all() is NON-EMPTY after the run
(episodes written at apply_credit via InnerLoop.episode_store).
"""
import importlib
import sys
from pathlib import Path

# Allow `import scripts.refine_live` via importlib path injection
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))

from alpha.memory.store import EpisodeStore
from alpha.llm.client import MockLLMClient
from alpha.loop.inner_loop import LoopConfig

# Re-import helpers from sibling test module
from tests.scripts.test_refine_live import (
    _PickRun,
    _source,
    _seed_teaching_brain,
    _REFINER_SCRIPT,
)


def test_refine_live_writes_episodes_when_db_given(tmp_path):
    brain_dir = tmp_path / "brain"
    conflicts_dir = tmp_path / "conflicts"
    db = tmp_path / "brain.db"

    _seed_teaching_brain(brain_dir)

    rl = importlib.import_module("scripts.refine_live")

    src = _source()  # n=8: 6 scored steps (horizon=2), satisfying evidence_min=6
    cal = src.trading_calendar()
    start, end = cal[0], cal[-1]

    rl.run_refine_live(
        src,
        start,
        end,
        brain_dir=str(brain_dir),
        conflicts_dir=str(conflicts_dir),
        agent_llm_factory=lambda: MockLLMClient("{}"),
        refiner_llm_factory=lambda: MockLLMClient(_REFINER_SCRIPT),
        agent_factory=lambda h: _PickRun(),
        horizon=2,
        loop_config=LoopConfig(horizon=2, screen=False, size=False),
        episodes_db=str(db),
    )

    s = EpisodeStore.open(str(db))
    assert len(s.all()) > 0, "Expected episodes to be written to brain.db after run_refine_live"


def test_refine_live_none_db_still_works(tmp_path):
    """Negative: episodes_db=None (default) → no error, run still returns a report."""
    brain_dir = tmp_path / "brain"
    conflicts_dir = tmp_path / "conflicts"

    _seed_teaching_brain(brain_dir)

    rl = importlib.import_module("scripts.refine_live")

    src = _source()
    cal = src.trading_calendar()
    start, end = cal[0], cal[-1]

    out = rl.run_refine_live(
        src,
        start,
        end,
        brain_dir=str(brain_dir),
        conflicts_dir=str(conflicts_dir),
        agent_llm_factory=lambda: MockLLMClient("{}"),
        refiner_llm_factory=lambda: MockLLMClient(_REFINER_SCRIPT),
        agent_factory=lambda h: _PickRun(),
        horizon=2,
        loop_config=LoopConfig(horizon=2, screen=False, size=False),
        episodes_db=None,
    )

    assert isinstance(out, dict), "run_refine_live should still return a report dict with episodes_db=None"
