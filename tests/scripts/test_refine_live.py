"""Offline e2e test for scripts/refine_live.py:
- Seeds a teaching-owned live brain (m_teach lesson owned by Sonia/teaching path).
- Runs run_refine_live with a deterministic agent (_PickRun) and a scripted refiner that emits:
    (a) demote_memory(m_teach) -> HELD (contests a teaching-owned element)
    (b) process_memory(m_new)  -> APPLIED (new lesson, not a contest)
- Asserts: held conflict in ConflictQueue AND live brain edit_count rose above seed.
"""
import importlib
import sys
from datetime import date
from pathlib import Path

import pandas as pd

# Allow `import scripts.refine_live` via importlib path injection
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))

from alpha.eval.decision import Candidate, DecisionPackage
from alpha.harness.doctrine import Doctrine
from alpha.harness.edit_log import EditLog, EditProvenance
from alpha.harness.memory import Lesson
from alpha.harness.registry import MemoryStore, SkillRegistry
from alpha.harness.skill import Skill
from alpha.harness.state import HarnessState
from alpha.llm.client import MockLLMClient
from alpha.loop.inner_loop import LoopConfig
from alpha.meta.conflict_store import ConflictQueue
from alpha.meta.store import LiveBrainStore
from alpha.data.source import FakeSource


# ---------------------------------------------------------------------------
# Deterministic agent policy (mirrors episodes test's _PickRun)
# ---------------------------------------------------------------------------
class _PickRun:
    """Pick every universe symbol as gap_and_go — no LLM required."""
    def decide(self, state, universe):
        return DecisionPackage(
            date=state.date,
            candidates=[Candidate(symbol=s.symbol, pattern="gap_and_go")
                        for s in universe.all()],
        )


# ---------------------------------------------------------------------------
# Fake data source (mirrors episodes test's _source, but n=8 so 6 scored steps
# satisfy evidence_min=6 with screen=False so GuardedPolicy doesn't filter the FakeSource)
# ---------------------------------------------------------------------------
def _source(n=8):
    cal = [date(2026, 6, d) for d in range(1, 1 + n)]
    snaps, px = {}, 10.0
    closes = []
    for d in cal:
        prev = px
        px = px * 1.2  # +20% gainer every day (screens in)
        closes.append(px)
        snaps[d] = pd.DataFrame({
            "symbol": ["RUN"], "name": ["RUN"], "open": [prev], "high": [px],
            "low": [prev], "close": [px], "volume": [1], "prev_close": [prev],
        })
    bars = {"RUN": pd.DataFrame({
        "date": cal,
        "open": [10.0] + closes[:-1],
        "high": closes,
        "low": [10.0] + closes[:-1],
        "close": closes,
        "volume": [1] * n,
    })}
    return FakeSource(calendar=cal, bars=bars, snapshots=snaps)


# ---------------------------------------------------------------------------
# Brain with a HarnessState that has gap_and_go skill (for _PickRun to produce scored decisions)
# ---------------------------------------------------------------------------
def _h():
    skills = SkillRegistry.from_skills([
        Skill(skill_id="gap_and_go", name="Gap and Go", type="pattern", status="active")
    ])
    return HarnessState(doctrine=Doctrine(), skills=skills, memory=MemoryStore.from_lessons([]))


def _seed_teaching_brain(brain_dir: Path, lesson_id: str = "m_teach") -> str:
    """Save a live brain whose EditLog records a TEACHING-owned memory lesson.
    A self-study op contesting it (demote_memory) will be HELD."""
    h = _h()
    # Add the teaching-owned lesson to the memory store
    lesson = Lesson.from_seed({
        "lesson_id": lesson_id,
        "phases": ["trend"],
        "outcome": "win",
        "lesson": "taught by sonia",
    })
    h = HarnessState(
        doctrine=h.doctrine,
        skills=h.skills,
        memory=MemoryStore.from_lessons([lesson]),
    )
    log = EditLog()
    log.append("process_memory", "memory", lesson_id, "create")
    log.stamp_last(EditProvenance(path="teaching", proposer="sonia"))
    LiveBrainStore(brain_dir).save(h, log)
    return lesson_id


# ---------------------------------------------------------------------------
# Refiner MockLLM: emits (a) demote_memory on existing teaching-owned lesson -> HELD,
# and (b) process_memory for a brand-new lesson -> APPLIED.
# Both ops go through the M-pass (demote_memory + process_memory are M-pass tools).
# ---------------------------------------------------------------------------
_REFINER_SCRIPT = (
    '{"ops": ['
    '{"tool": "demote_memory", "args": {"lesson_id": "m_teach", "factor": 0.5}, '
    '"rationale": "data says weak"},'
    '{"tool": "process_memory", "args": {"lesson_id": "m_new", "phases": ["trend"], '
    '"outcome": "win", "lesson": "learned new pattern"}, '
    '"rationale": "new pattern observed"}'
    ']}'
)


def test_refine_live_feeds_conflicts_and_persists(tmp_path):
    brain_dir = tmp_path / "brain"
    conflicts_dir = tmp_path / "conflicts"

    lid = _seed_teaching_brain(brain_dir)
    seed_edit_count = LiveBrainStore(str(brain_dir)).edit_count()
    assert seed_edit_count == 1, f"expected 1 seed edit, got {seed_edit_count}"

    refine_live = importlib.import_module("scripts.refine_live")

    src = _source()  # n=8: 6 scored steps (horizon=2), satisfying evidence_min=6
    cal = src.trading_calendar()
    start, end = cal[0], cal[-1]

    out = refine_live.run_refine_live(
        src,
        start,
        end,
        brain_dir=str(brain_dir),
        conflicts_dir=str(conflicts_dir),
        agent_llm_factory=lambda: MockLLMClient("{}"),
        refiner_llm_factory=lambda: MockLLMClient(_REFINER_SCRIPT),
        agent_factory=lambda h: _PickRun(),
        horizon=2,
        # screen=False: FakeSource doesn't pass the GuardedPolicy screen (no real corp/halt/SSR data).
        # size=False: avoids SizingPolicy overhead in offline test.
        loop_config=LoopConfig(horizon=2, screen=False, size=False),
    )

    # --- assertion 1: contesting op was HELD ---
    held = ConflictQueue(str(conflicts_dir)).all()
    assert any(
        c.op.get("args", {}).get("lesson_id") == lid for c in held
    ), f"Expected a held conflict for lesson_id={lid!r}, got: {held}"

    # --- assertion 2: non-conflicting edit (m_new) persisted to the live brain ---
    final_edit_count = LiveBrainStore(str(brain_dir)).edit_count()
    assert final_edit_count > seed_edit_count, (
        f"Expected live brain edit_count to rise above {seed_edit_count}, got {final_edit_count}"
    )
