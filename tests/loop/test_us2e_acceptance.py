"""US-2e acceptance: the §9/§10 statistical decision PROCEDURE renders end-to-end on the SEEDED harness
— a paired HCH-Hexpert day-level StatVerdict (bootstrap CI + permutation p + MDE), an offense/defense +
per-family contribution split, and a multi-window verdict tally. This validates the acceptance APPARATUS
deterministically; the empirical pass/fail verdict needs a live temp=0 LLM run (MockLLM ignores prompts)."""
import tempfile
from pathlib import Path
from datetime import date
import pandas as pd
from alpha.data.source import FakeSource
from alpha.harness.loader import load_seeds
from alpha.harness.snapshot import SnapshotStore
from alpha.llm.client import MockLLMClient
from alpha.loop.inner_loop import LoopConfig
from alpha.loop.compare import compare_harnesses, multi_window
from alpha.eval.stats import StatVerdict
from alpha.eval.contribution import ContributionReport

SEEDS = Path(__file__).resolve().parents[2] / "seeds"


def _source(n=10):
    cal = [date(2026, 6, d) for d in range(1, 1 + n)]
    snaps, px = {}, 10.0
    closes = []
    for d in cal:
        prev = px; px = px * 1.15; closes.append(px)
        snaps[d] = pd.DataFrame({"symbol": ["RUN"], "name": ["RUN"], "open": [prev], "high": [px],
                                 "low": [prev], "close": [px], "volume": [1], "prev_close": [prev]})
    bars = {"RUN": pd.DataFrame({"date": cal, "open": [10.0] + closes[:-1], "high": closes,
                                 "low": [10.0] + closes[:-1], "close": closes, "volume": [1] * n})}
    return FakeSource(calendar=cal, bars=bars, snapshots=snaps)


def _agent():
    return MockLLMClient('{"candidates": [{"symbol": "RUN", "pattern": "gap_and_go", "confidence": 0.7}]}')


def test_acceptance_procedure_renders_end_to_end():
    src = _source(10)
    cal = src.trading_calendar()
    cr = compare_harnesses(lambda: load_seeds(SEEDS), src, cal[0], cal[-1], agent_llm_factory=_agent,
                           refiner_llm_factory=lambda: MockLLMClient('{"ops": []}'),
                           store_factory=lambda: SnapshotStore(tempfile.mkdtemp()),
                           loop_config=LoopConfig(horizon=2, evidence_min=2, refine_every=1), shadow=True)
    # the statistical decision procedure produced a verdict with its uncertainty recorded
    assert isinstance(cr.stat_verdict, StatVerdict)
    assert cr.stat_verdict.verdict in {"win", "loss", "flat", "insufficient"}
    assert cr.stat_verdict.n_days == len(cr.hch_loop_report.trajectory.scored_steps())
    if cr.stat_verdict.n_days >= 2:                         # CI/MDE attached once estimable
        assert cr.stat_verdict.ci_low is not None and cr.stat_verdict.mde is not None
    # offense/defense contribution split is populated (gap_and_go is an offense seed skill)
    assert isinstance(cr.contribution, ContributionReport) and cr.contribution.offense.n >= 1
    # multi-window verdict tally (the temp=0 multi-seed surrogate)
    mw = multi_window(lambda: load_seeds(SEEDS), src, [(cal[0], cal[4]), (cal[5], cal[9])],
                      agent_llm_factory=_agent, refiner_llm_factory=lambda: MockLLMClient('{"ops": []}'),
                      store_factory=lambda: SnapshotStore(tempfile.mkdtemp()),
                      loop_config=LoopConfig(horizon=2, evidence_min=2, refine_every=1))
    assert len(mw.verdicts) == 2 and sum(mw.verdict_tally.values()) == 2
