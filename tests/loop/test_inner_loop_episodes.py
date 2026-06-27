"""Tests that InnerLoop optionally records episodes with realized exit_date at the maturity seam."""
from datetime import date
import pandas as pd

from alpha.data.source import FakeSource
from alpha.harness.skill import Skill
from alpha.harness.doctrine import Doctrine
from alpha.harness.registry import SkillRegistry, MemoryStore
from alpha.harness.state import HarnessState
from alpha.harness.snapshot import SnapshotStore
from alpha.harness.manager import HarnessManager
from alpha.eval.decision import Candidate, DecisionPackage
from alpha.eval.scorer import ReturnScorer
from alpha.llm.client import MockLLMClient
from alpha.loop.inner_loop import InnerLoop, LoopConfig
from alpha.memory.store import EpisodeStore


class _PickRun:
    """Deterministic LLM-free policy: pick every universe symbol as gap_and_go."""
    def decide(self, state, universe):
        return DecisionPackage(date=state.date,
                               candidates=[Candidate(symbol=s.symbol, pattern="gap_and_go")
                                           for s in universe.all()])


def _h():
    skills = SkillRegistry.from_skills([Skill(skill_id="gap_and_go", name="Gap and Go", type="pattern",
                                              status="active")])
    return HarnessState(doctrine=Doctrine(), skills=skills, memory=MemoryStore.from_lessons([]))


def _source(n=6):
    cal = [date(2026, 6, d) for d in range(1, 1 + n)]
    snaps, px = {}, 10.0
    closes = []
    for d in cal:
        prev = px
        px = px * 1.2                      # +20% gainer every day (screens in)
        closes.append(px)
        snaps[d] = pd.DataFrame({"symbol": ["RUN"], "name": ["RUN"], "open": [prev], "high": [px],
                                 "low": [prev], "close": [px], "volume": [1], "prev_close": [prev]})
    bars = {"RUN": pd.DataFrame({"date": cal, "open": [10.0] + closes[:-1], "high": closes,
                                 "low": [10.0] + closes[:-1], "close": closes, "volume": [1] * n})}
    return FakeSource(calendar=cal, bars=bars, snapshots=snaps)


def _loop(src, cfg, episode_store=None):
    import tempfile
    mgr = HarnessManager(_h(), SnapshotStore(tempfile.mkdtemp()))
    return InnerLoop(mgr, src, src.trading_calendar()[0], src.trading_calendar()[-1],
                     agent_llm=MockLLMClient("{}"), refiner_llm=MockLLMClient('{"ops": []}'),
                     config=cfg, scorer=ReturnScorer(), agent_factory=lambda h: _PickRun(),
                     episode_store=episode_store), mgr


def test_inner_loop_writes_episodes_with_realized_exit_date():
    """Episode exit_date must be the maturity cursor (decision_date + horizon trading days),
    strictly greater than entry_date, and learned_asof must equal exit_date."""
    src = _source(6)
    store = EpisodeStore.in_memory()
    loop, _ = _loop(src, LoopConfig(horizon=2, enable_refine=False, screen=False), episode_store=store)
    loop.run()
    eps = store.all()
    assert eps, "expected episodes for the scored steps (horizon=2, 6 days → 4 scored steps)"
    # exit_date is the realized maturity cursor, strictly after entry_date (decision_date)
    assert all(e.exit_date > e.entry_date for e in eps), (
        f"exit_date not > entry_date for some episode: {[(e.entry_date, e.exit_date) for e in eps]}"
    )
    assert all(e.learned_asof == e.exit_date for e in eps), (
        f"learned_asof != exit_date for some episode: {[(e.learned_asof, e.exit_date) for e in eps]}"
    )


def test_inner_loop_no_episode_store_still_runs():
    """Default (episode_store=None) must produce no episodes and not crash."""
    src = _source(6)
    loop, _ = _loop(src, LoopConfig(horizon=2, enable_refine=False, screen=False))
    report = loop.run()
    # no store → no assertion on episodes; just confirm the loop ran normally
    assert len(report.trajectory.steps) == 6
    assert len(report.trajectory.scored_steps()) == 4


# ---------------------------------------------------------------------------
# Task 4: decouple read (recall_store) from write (episode_store)
# ---------------------------------------------------------------------------

def _seed_taboo_store(symbol="RUN", n=3):
    """recall_store seeded so `symbol` is taboo: n PIT-old nuked episodes (learned long before the run)."""
    from alpha.memory.episodes import Episode
    s = EpisodeStore.in_memory()
    for i in range(n):
        s.add(Episode(episode_id=f"{symbol}:{i}", symbol=symbol, skill_id="gap_and_go",
                      entry_date=date(2026, 1, 1), exit_date=date(2026, 1, 2),
                      outcome="nuked", advantage=-2.0, learned_asof=date(2026, 1, 2)))
    return s


def _count(store):
    """Total PIT-visible (far-future asof) non-superseded episodes — the read-only-ness probe."""
    return len(store.for_asof(date(2099, 1, 1), limit=None))


def _loop_recall(src, cfg, recall_store=None, episode_store=None):
    """Inner-loop builder with the screen ON so GuardedPolicy (taboo) + recall wrap the _PickRun agent."""
    import tempfile
    mgr = HarnessManager(_h(), SnapshotStore(tempfile.mkdtemp()))
    return InnerLoop(mgr, src, src.trading_calendar()[0], src.trading_calendar()[-1],
                     agent_llm=MockLLMClient("{}"), refiner_llm=MockLLMClient('{"ops": []}'),
                     config=cfg, scorer=ReturnScorer(), agent_factory=lambda h: _PickRun(),
                     recall_store=recall_store, episode_store=episode_store)


def test_recall_store_is_read_only_even_when_picks_mature():
    """recall_store is the READ handle only: even when the run's picks MATURE (and apply_credit would
    write), nothing lands in recall_store — the write goes to episode_store. Non-vacuous: we seed taboo
    on a symbol NOT in the universe (OTHER) so RUN survives the veto and matures normally; the supplied
    recall_store must stay unchanged while a write WOULD have occurred (proven by the control below).
    This FAILS under an `episode_store=self._recall_store` self-write mutation."""
    src = _source(6)                                    # universe = {RUN} only
    store_R = _seed_taboo_store("OTHER")                # taboo a NON-universe symbol -> never fires
    n_before = _count(store_R)
    loop = _loop_recall(src, LoopConfig(horizon=2, enable_refine=False, screen=True),
                        recall_store=store_R, episode_store=None)
    loop.run()
    assert _count(store_R) == n_before                  # read-only: the run did not write to recall_store

    # Control: a WRITE actually would have happened during that run. Re-run the identical loop with the
    # SAME store as episode_store= (the write handle) and confirm it grows -> the read-only assertion is
    # meaningful (RUN matured), not trivially true because the candidate was vetoed.
    store_W = _seed_taboo_store("OTHER")               # same inert seed, used as the WRITE handle
    n_w_before = _count(store_W)
    loop_w = _loop_recall(src, LoopConfig(horizon=2, enable_refine=False, screen=True),
                          recall_store=store_R, episode_store=store_W)
    loop_w.run()
    assert _count(store_W) > n_w_before                # the run DID write (RUN entered + matured)


def test_recall_store_drives_taboo_and_drops_candidate():
    """recall_store feeds taboo: a seeded RUN nuke history drops the universe symbol from every scored
    step's entries (the veto-fires case; complements the read-only/matures case above)."""
    src = _source(6)
    store_R = _seed_taboo_store("RUN")                  # 3 PIT-old nuked RUN episodes (RUN IS the universe)
    loop = _loop_recall(src, LoopConfig(horizon=2, enable_refine=False, screen=True),
                        recall_store=store_R, episode_store=None)
    report = loop.run()
    # RUN was vetoed -> never entered -> absent from every scored step's entries
    assert all("RUN" not in step.entries for step in report.trajectory.scored_steps())


def test_episode_store_is_write_only_independent_of_recall():
    """episode_store still records episodes at apply_credit; recall_store=None means no recall/taboo block."""
    src = _source(6)
    store_W = EpisodeStore.in_memory()
    loop = _loop_recall(src, LoopConfig(horizon=2, enable_refine=False, screen=True),
                        recall_store=None, episode_store=store_W)
    loop.run()
    assert _count(store_W) > 0                           # write path intact, independent of recall_store
