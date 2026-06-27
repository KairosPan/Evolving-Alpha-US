import tempfile
from datetime import date
from pathlib import Path
import pandas as pd
from alpha.data.source import FakeSource
from alpha.harness.loader import load_seeds
from alpha.harness.snapshot import SnapshotStore
from alpha.llm.client import MockLLMClient
from alpha.loop.inner_loop import LoopConfig
from alpha.loop.compare import compare_harnesses, ComparisonReport, daily_advantage

SEEDS = Path(__file__).resolve().parents[2] / "seeds"


def _source(n, rate):
    cal = [date(2026, 6, d) for d in range(1, 1 + n)]
    snaps, px = {}, 10.0
    closes = []
    for d in cal:
        prev = px; px = px * rate; closes.append(px)
        snaps[d] = pd.DataFrame({"symbol": ["RUN"], "name": ["RUN"], "open": [prev], "high": [px],
                                 "low": [prev], "close": [px], "volume": [1], "prev_close": [prev]})
    bars = {"RUN": pd.DataFrame({"date": cal, "open": [10.0] + closes[:-1], "high": closes,
                                 "low": [10.0] + closes[:-1], "close": closes, "volume": [1] * n})}
    return FakeSource(calendar=cal, bars=bars, snapshots=snaps)


class _Counter:
    """Counts calls; returns a fresh object from `make` each time (factory isolation)."""
    def __init__(self, make): self._make = make; self.calls = 0
    def __call__(self): self.calls += 1; return self._make()


def _cfg():
    return LoopConfig(horizon=2, evidence_min=2, refine_every=1)


def test_four_arms_and_factory_isolation():
    src = _source(6, 1.15)                                  # +15%/day: RUN in-universe, advantage > 0
    hf = _Counter(lambda: load_seeds(SEEDS))
    af = _Counter(lambda: MockLLMClient('{"regime_read": "trend", "candidates": '
                                        '[{"symbol": "RUN", "pattern": "gap_and_go", "confidence": 0.7}]}'))
    rf = _Counter(lambda: MockLLMClient('{"ops": []}'))
    sf = _Counter(lambda: SnapshotStore(tempfile.mkdtemp()))
    cr = compare_harnesses(hf, src, src.trading_calendar()[0], src.trading_calendar()[-1],
                           agent_llm_factory=af, refiner_llm_factory=rf, store_factory=sf, loop_config=_cfg())
    assert isinstance(cr, ComparisonReport)
    assert set(cr.arms) == {"HCH", "Hexpert", "Hmin_chase", "Hmin_notrade"}
    assert hf.calls == 2 and af.calls == 2 and rf.calls == 1 and sf.calls == 1   # factory isolation
    # same agent script for HCH & Hexpert + empty-ops refiner -> identical picks -> excess delta ~ 0 -> verdict False
    assert cr.hch_beats_hexpert is False and abs(cr.hch_minus_hexpert_mean_excess) < 1e-9
    assert cr.hch_loop_report is not None and cr.arms["HCH"].n_refines is not None


def test_hch_beats_hexpert_when_excess_higher():
    src = _source(6, 1.15)
    hf = lambda: load_seeds(SEEDS)
    # run-order (shadow=False) is HCH then Hexpert -> seq factory gives HCH a winner, Hexpert no-trade
    seq = iter([MockLLMClient('{"candidates": [{"symbol": "RUN", "pattern": "gap_and_go"}]}'),
                MockLLMClient('{"no_trade_reason": "flat", "candidates": []}')])
    af = lambda: next(seq)
    cr = compare_harnesses(hf, src, src.trading_calendar()[0], src.trading_calendar()[-1],
                           agent_llm_factory=af, refiner_llm_factory=lambda: MockLLMClient('{"ops": []}'),
                           store_factory=lambda: SnapshotStore(tempfile.mkdtemp()), loop_config=_cfg())
    assert cr.hch_minus_hexpert_mean_excess > 0 and cr.hch_beats_hexpert is True


def test_shadow_runs_hexpert_first_and_completes():
    src = _source(8, 1.15)
    hf = lambda: load_seeds(SEEDS)
    af = lambda: MockLLMClient('{"candidates": [{"symbol": "RUN", "pattern": "gap_and_go"}]}')
    cr = compare_harnesses(hf, src, src.trading_calendar()[0], src.trading_calendar()[-1],
                           agent_llm_factory=af, refiner_llm_factory=lambda: MockLLMClient('{"ops": []}'),
                           store_factory=lambda: SnapshotStore(tempfile.mkdtemp()), loop_config=_cfg(),
                           shadow=True)
    assert set(cr.arms) == {"HCH", "Hexpert", "Hmin_chase", "Hmin_notrade"}   # shadow path completes end-to-end


def test_daily_advantage_mirrors_breaker_formula():
    src = _source(6, 1.15)
    from alpha.eval.walk_forward import WalkForwardEval
    from alpha.eval.scorer import ReturnScorer
    from alpha.agent.agent import LLMAgentPolicy
    traj = WalkForwardEval(src, src.trading_calendar()[0], src.trading_calendar()[-1], horizon=2,
                           scorer=ReturnScorer()).walk(
        LLMAgentPolicy(load_seeds(SEEDS),
                       MockLLMClient('{"candidates": [{"symbol": "RUN", "pattern": "gap_and_go"}]}')))
    da = daily_advantage(traj)
    assert da and all(isinstance(k, date) for k in da)        # keyed by decision date, one per scored step


def test_stat_verdict_and_contribution_populated():
    from alpha.eval.stats import StatVerdict
    from alpha.eval.contribution import ContributionReport
    src = _source(10, 1.15)
    cr = compare_harnesses(lambda: load_seeds(SEEDS), src, src.trading_calendar()[0],
                           src.trading_calendar()[-1],
                           agent_llm_factory=lambda: MockLLMClient('{"candidates": '
                                                                   '[{"symbol": "RUN", "pattern": "gap_and_go"}]}'),
                           refiner_llm_factory=lambda: MockLLMClient('{"ops": []}'),
                           store_factory=lambda: SnapshotStore(tempfile.mkdtemp()), loop_config=_cfg())
    assert isinstance(cr.stat_verdict, StatVerdict)
    # same agent script + empty-ops refiner -> HCH==Hexpert picks -> paired diff all 0 -> 'flat' at n_days==8.
    # A non-zero mean_diff would signal a REAL HCH/Hexpert divergence (breaker trip / dropped step), not float noise.
    assert cr.stat_verdict.verdict in {"flat", "insufficient"} and abs(cr.stat_verdict.mean_diff) < 1e-9
    assert cr.stat_verdict.n_days >= 1
    assert isinstance(cr.contribution, ContributionReport)
    assert cr.contribution.offense.n >= 1               # gap_and_go is an offense (pattern) seed skill


def test_multi_window_collects_verdict_tally():
    from alpha.loop.compare import multi_window
    src = _source(10, 1.15)
    cal = src.trading_calendar()
    mw = multi_window(lambda: load_seeds(SEEDS), src, [(cal[0], cal[4]), (cal[5], cal[9])],
                      agent_llm_factory=lambda: MockLLMClient('{"candidates": '
                                                              '[{"symbol": "RUN", "pattern": "gap_and_go"}]}'),
                      refiner_llm_factory=lambda: MockLLMClient('{"ops": []}'),
                      store_factory=lambda: SnapshotStore(tempfile.mkdtemp()), loop_config=_cfg())
    assert len(mw.verdicts) == 2                                   # one stat verdict label per window
    assert sum(mw.verdict_tally.values()) == 2                     # tally totals the windows
    assert all(v in {"win", "loss", "flat", "insufficient"} for v in mw.verdicts)


# ---------------------------------------------------------------------------
# Task 5: symmetric read-only recall_store across the verdict arms
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


def _run_compare(recall_store="__omit__", *, src=None):
    """Thin wrapper over compare_harnesses with deterministic MockLLM factories (picks RUN every day).
    recall_store='__omit__' -> pass NO kwarg (the default); else thread it through."""
    src = src if src is not None else _source(6, 1.15)
    kw = dict(
        agent_llm_factory=lambda: MockLLMClient('{"regime_read": "trend", "candidates": '
                                                '[{"symbol": "RUN", "pattern": "gap_and_go", "confidence": 0.7}]}'),
        refiner_llm_factory=lambda: MockLLMClient('{"ops": []}'),
        store_factory=lambda: SnapshotStore(tempfile.mkdtemp()), loop_config=_cfg())
    if recall_store != "__omit__":
        kw["recall_store"] = recall_store
    return compare_harnesses(lambda: load_seeds(SEEDS), src, src.trading_calendar()[0],
                             src.trading_calendar()[-1], **kw)


def test_verdict_recall_store_not_written_during_run():
    """A verdict reads the supplied pool but never WRITES to it: the HCH arm threads it as recall_store=
    (read) NOT episode_store= (write). This is non-vacuous only if the HCH arm actually MATURES picks
    during the run — so we seed taboo on a symbol NOT in the universe (OTHER), letting RUN survive the
    veto and mature normally. The supplied store must stay unchanged while a write WOULD have occurred
    (proven by the write-store growth control below). It FAILS under the episode_store=recall_store
    self-write bug (the HCH arm's matured RUN episodes would land in the supplied store)."""
    src = _source(6, 1.15)                                  # universe = {RUN} only
    store = _seed_taboo_store("OTHER")                      # taboo a NON-universe symbol -> never fires
    n_before = len(store.for_asof(date(2099, 1, 1), limit=None))
    _run_compare(recall_store=store, src=src)
    assert len(store.for_asof(date(2099, 1, 1), limit=None)) == n_before   # unchanged -> read-only

    # Control: a WRITE actually would have happened during that run. Drive an otherwise-identical InnerLoop
    # over the same source/window with the SAME store handed as episode_store= (the write path the verdict
    # must NOT use) and confirm it grows -> the read-only assertion above is meaningful, not trivially true.
    from alpha.harness.manager import HarnessManager
    from alpha.loop.inner_loop import InnerLoop
    from alpha.eval.scorer import ReturnScorer
    store_W = _seed_taboo_store("OTHER")                    # same inert seed, used as the WRITE handle
    n_w_before = len(store_W.for_asof(date(2099, 1, 1), limit=None))
    mgr = HarnessManager(load_seeds(SEEDS), SnapshotStore(tempfile.mkdtemp()))
    InnerLoop(mgr, src, src.trading_calendar()[0], src.trading_calendar()[-1],
              MockLLMClient('{"regime_read": "trend", "candidates": '
                            '[{"symbol": "RUN", "pattern": "gap_and_go", "confidence": 0.7}]}'),
              MockLLMClient('{"ops": []}'), config=_cfg(), scorer=ReturnScorer(),
              recall_store=store, episode_store=store_W).run()
    assert len(store_W.for_asof(date(2099, 1, 1), limit=None)) > n_w_before   # the run DID write (RUN matured)


def test_verdict_recall_store_drops_taboo_symbol_symmetrically():
    """When the supplied recall pool makes the universe symbol taboo, BOTH the HCH and Hexpert arms drop
    it (read applied symmetrically): no candidate is entered/scored in either arm -> both no-trade -> the
    excess delta is 0. (This is the veto-fires case; the not_written test above is the veto-doesn't-fire,
    matures-and-could-write case — together they cover both sides of the read/write decoupling.)"""
    store = _seed_taboo_store("RUN")                      # RUN IS the universe symbol -> taboo fires
    cr = _run_compare(recall_store=store)
    assert cr.arms["HCH"].report.n_candidates == 0       # HCH: RUN vetoed -> nothing entered/scored
    assert cr.arms["Hexpert"].report.n_candidates == 0   # Hexpert: same read -> same veto (symmetric)
    assert abs(cr.hch_minus_hexpert_mean_excess) < 1e-9  # both arms no-trade -> equal


def test_verdict_recall_store_none_byte_identical():
    """recall_store=None reproduces today's headline numbers (additive default-off)."""
    a = _run_compare(recall_store=None)
    b = _run_compare()                                    # no kwarg -> same default
    assert a.hch_minus_hexpert_mean_excess == b.hch_minus_hexpert_mean_excess


def test_multi_window_aggregates_deltas():
    from alpha.loop.compare import multi_window, MultiWindowReport
    src = _source(10, 1.15)
    cal = src.trading_calendar()
    windows = [(cal[0], cal[4]), (cal[5], cal[9])]              # two non-overlapping windows
    hf = lambda: load_seeds(SEEDS)
    af = lambda: MockLLMClient('{"candidates": [{"symbol": "RUN", "pattern": "gap_and_go"}]}')
    mw = multi_window(hf, src, windows, agent_llm_factory=af,
                      refiner_llm_factory=lambda: MockLLMClient('{"ops": []}'),
                      store_factory=lambda: SnapshotStore(tempfile.mkdtemp()), loop_config=_cfg())
    assert isinstance(mw, MultiWindowReport)
    assert mw.n_windows == 2 and len(mw.deltas) == 2
    assert 0.0 <= mw.win_rate <= 1.0
    assert abs(mw.mean_delta - sum(mw.deltas) / 2) < 1e-9
    assert isinstance(mw.sign_consistent, bool)
