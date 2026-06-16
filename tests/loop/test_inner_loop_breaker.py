import tempfile
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
from alpha.eval.metrics import ScoredCandidate
from alpha.llm.client import MockLLMClient
from alpha.loop.inner_loop import InnerLoop, LoopConfig


class _PickRun:
    def decide(self, state, universe):
        return DecisionPackage(date=state.date,
                               candidates=[Candidate(symbol=s.symbol, pattern="gap_and_go")
                                           for s in universe.all()])


class _SchedScorer:
    """Returns a controlled advantage per decision date (day_baseline=0 so advantage == score)."""
    def __init__(self, sched: dict): self._sched = sched
    def score_step(self, decision, decision_mem, exit_mem, entry_day, exit_day, oracle):
        adv = self._sched.get(decision.date, 0.0)
        return {c.symbol: ScoredCandidate(decision_date=decision.date, symbol=c.symbol, pattern=c.pattern,
                                          outcome=("continued" if adv >= 0 else "nuked"),
                                          score=adv, day_baseline=0.0) for c in decision.candidates}


def _source(n):
    cal = [date(2026, 6, d) for d in range(1, 1 + n)]
    snaps, px = {}, 10.0
    closes = []
    for d in cal:
        prev = px; px = px * 1.2; closes.append(px)
        snaps[d] = pd.DataFrame({"symbol": ["RUN"], "name": ["RUN"], "open": [prev], "high": [px],
                                 "low": [prev], "close": [px], "volume": [1], "prev_close": [prev]})
    bars = {"RUN": pd.DataFrame({"date": cal, "open": [10.0] + closes[:-1], "high": closes,
                                 "low": [10.0] + closes[:-1], "close": closes, "volume": [1] * n})}
    return FakeSource(calendar=cal, bars=bars, snapshots=snaps)


def _h():
    return HarnessState(doctrine=Doctrine.from_seed_list(
        [{"section": "trend_play", "regime": "trend", "immutable": False, "guidance": "ride"}]),
        skills=SkillRegistry.from_skills([Skill(skill_id="gap_and_go", name="G", type="pattern",
                                                status="active")]),
        memory=MemoryStore.from_lessons([]))


def _loop(src, cfg, sched, refiner_script='{"ops": []}'):
    mgr = HarnessManager(_h(), SnapshotStore(tempfile.mkdtemp()))
    loop = InnerLoop(mgr, src, src.trading_calendar()[0], src.trading_calendar()[-1],
                     agent_llm=MockLLMClient("{}"), refiner_llm=MockLLMClient(refiner_script),
                     config=cfg, scorer=_SchedScorer(sched), agent_factory=lambda h: _PickRun())
    return loop, mgr


def test_breaker_freezes_without_checkpoint():
    # enable_refine=False -> no checkpoints ever -> the first trip must FREEZE (no rollback target).
    cal = [date(2026, 6, d) for d in range(1, 8)]               # 7 days
    sched = {cal[0]: 0.3, cal[1]: 0.3, cal[2]: 0.3, cal[3]: -0.9, cal[4]: -0.9}
    cfg = LoopConfig(horizon=2, enable_refine=False, breaker_min_days=3, breaker_k_max=3,
                     breaker_mad_c=2.0, floor_abs=0.0, screen=False)   # unguarded: the breaker calibrates on
    #   the scheduled advantage series; the L4 guard (default-on) is exercised in tests/loop/test_screen_*.py.
    loop, mgr = _loop(_source(7), cfg, sched)
    report = loop.run()
    assert report.frozen_from is not None
    assert report.breaker_events and report.breaker_events[-1].mode == "frozen"
    assert report.breaker_events[-1].rolled_back_to is None
    # credit stopped at freeze: fewer credited samples than total scored steps
    n_scored = len(report.trajectory.scored_steps())
    assert mgr.harness.skills.get("gap_and_go").stats.n < n_scored


def test_breaker_rolls_back_to_pre_degradation_checkpoint():
    # enable_refine=True (refine fires -> checkpoints exist). A healthy stretch builds checkpoints, then
    # degradation trips the breaker which rolls back to a checkpoint BEFORE the degraded window.
    cal = [date(2026, 6, d) for d in range(1, 12)]             # 11 days
    sched = {cal[k]: (0.3 if k < 6 else -0.9) for k in range(11)}
    cfg = LoopConfig(horizon=2, enable_refine=True, evidence_min=1, refine_every=1,
                     breaker_min_days=3, breaker_k_max=3, breaker_mad_c=2.0, floor_abs=0.0)
    loop, mgr = _loop(_source(11), cfg, sched)
    report = loop.run()
    modes = [e.mode for e in report.breaker_events]
    assert modes and modes[0] == "rollback"
    assert report.breaker_events[0].rolled_back_to is not None


def test_history_threading_survives_fallback_breaker(monkeypatch):
    # Regression: the fallback breaker computes a LOCAL advantage series; it must NOT clobber the outer
    # sentiment_raw `history` accumulator threaded into build_market_state (a name-collision bug would
    # rebind it on every breaker-check day). Spy on the history kwarg length: it must grow by exactly one
    # per day (the bug replaces it with the advantage list, jumping its length). screen=False isolates the
    # threading from guard vetoes.
    import alpha.loop.inner_loop as il
    real = il.build_market_state
    seen: list[int] = []

    def _spy(universe, day, *, history, **kw):
        seen.append(len(list(history)))
        return real(universe, day, history=history, **kw)

    monkeypatch.setattr(il, "build_market_state", _spy)
    cal = [date(2026, 6, d) for d in range(1, 10)]                 # 9 days
    sched = {cal[k]: (0.3 if k < 3 else -0.9) for k in range(9)}   # degrade -> fallback breaker fires
    cfg = LoopConfig(horizon=2, enable_refine=False, breaker_min_days=3, breaker_k_max=3,
                     breaker_mad_c=2.0, floor_abs=0.0, screen=False)
    loop, _ = _loop(_source(9), cfg, sched)
    report = loop.run()
    assert report.breaker_events                                   # the fallback breaker path executed
    assert seen == list(range(9))                                  # +1 per day, never replaced (bug -> jump)
