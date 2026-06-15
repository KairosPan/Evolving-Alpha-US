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
    def __init__(self, sched): self._sched = sched
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
    return HarnessState(doctrine=Doctrine(),
                        skills=SkillRegistry.from_skills([Skill(skill_id="gap_and_go", name="G",
                                                               type="pattern", status="active")]),
                        memory=MemoryStore.from_lessons([]))


def _loop(src, cfg, sched, shadow_daily):
    mgr = HarnessManager(_h(), SnapshotStore(tempfile.mkdtemp()))
    return InnerLoop(mgr, src, src.trading_calendar()[0], src.trading_calendar()[-1],
                     agent_llm=MockLLMClient("{}"), refiner_llm=MockLLMClient('{"ops": []}'),
                     config=cfg, scorer=_SchedScorer(sched), agent_factory=lambda h: _PickRun(),
                     shadow_daily=shadow_daily)


def test_shadow_path_trips_when_own_below_reference():
    src = _source(8)
    cal = src.trading_calendar()
    own = {d: -0.3 for d in cal}            # HCH advantage degraded vs the reference
    shadow = {d: 0.3 for d in cal}          # frozen-expert reference is healthy -> diff = -0.6/day
    cfg = LoopConfig(horizon=2, enable_refine=False, breaker_min_days=3, breaker_k_max=3)
    loop = _loop(src, cfg, own, shadow_daily=shadow)
    report = loop.run()
    assert report.breaker_events                                # the shadow path tripped
    assert "shadow" in report.breaker_events[-1].reason         # via the paired-diff trip
    assert report.frozen_from is not None                       # no checkpoints (enable_refine=False) -> freeze


def test_shadow_none_uses_fallback_path():
    src = _source(8)
    cal = src.trading_calendar()
    own = {cal[k]: (0.3 if k < 3 else -0.9) for k in range(8)}  # degrade -> fallback floor_abs trip
    cfg = LoopConfig(horizon=2, enable_refine=False, breaker_min_days=3, breaker_k_max=3, floor_abs=0.0)
    loop = _loop(src, cfg, own, shadow_daily=None)
    report = loop.run()
    assert report.breaker_events and "shadow" not in report.breaker_events[-1].reason   # fallback, not shadow


def test_shadow_future_only_series_is_ignored_anti_lookahead():
    src = _source(8)
    # reference series keyed ONLY by dates AFTER the run window -> filtered out -> no common days -> no trip
    shadow = {date(2026, 7, d): 0.3 for d in range(1, 9)}
    own = {d: -0.5 for d in src.trading_calendar()}            # own is awful, but there's nothing to pair with
    cfg = LoopConfig(horizon=2, enable_refine=False, breaker_min_days=3, breaker_k_max=3)
    loop = _loop(src, cfg, own, shadow_daily=shadow)
    report = loop.run()
    assert report.breaker_events == [] and report.frozen_from is None   # future-only reference never trips
