"""US-2a acceptance: the LLM agent (MockLLM) drives the seeded harness end-to-end through one
WalkForwardEval day-step, producing a scored decision — and the firewall holds (the agent only sees
state+universe). Runs the default injection='retrieval' path, so budgeted retrieval (Task 5) is
validated end-to-end on the real seed harness. This is the act half-loop the US-2b Refiner will close."""
from pathlib import Path
from datetime import date
import pandas as pd
from alpha.data.source import FakeSource
from alpha.harness.loader import load_seeds
from alpha.llm.client import MockLLMClient
from alpha.agent.agent import LLMAgentPolicy
from alpha.eval.walk_forward import WalkForwardEval
from alpha.eval.scorer import ReturnScorer

SEEDS = Path(__file__).resolve().parents[2] / "seeds"


def _source():
    cal = [date(2026, 6, 10), date(2026, 6, 11), date(2026, 6, 12), date(2026, 6, 15)]
    snaps = {}
    for d, rows in {date(2026, 6, 10): [("RUN", 14.0, 10.0)], date(2026, 6, 11): [("RUN", 18.0, 14.0)],
                    date(2026, 6, 12): [("RUN", 17.0, 18.0)], date(2026, 6, 15): [("RUN", 20.0, 17.0)]}.items():
        snaps[d] = pd.DataFrame({"symbol": ["RUN"], "name": ["RUN"], "open": [r[2] for r in rows],
                                 "high": [r[1] for r in rows], "low": [r[2] for r in rows],
                                 "close": [r[1] for r in rows], "volume": [1], "prev_close": [r[2] for r in rows]})
    bars = {"RUN": pd.DataFrame({"date": cal, "open": [10.0, 14.0, 18.0, 17.0], "high": [14, 18, 18, 20],
                                 "low": [10, 14, 17, 17], "close": [14.0, 18.0, 17.0, 20.0], "volume": [1, 1, 1, 1]})}
    return FakeSource(calendar=cal, bars=bars, snapshots=snaps)


def test_agent_drives_walk_forward_end_to_end():
    h = load_seeds(SEEDS)                       # the real defense-heavy seed harness
    # the agent always picks RUN with the gap_and_go skill (MockLLM scripts a valid JSON)
    llm = MockLLMClient('{"regime_read": "trend", "candidates": '
                        '[{"symbol": "RUN", "pattern": "gap_and_go", "confidence": 0.7}]}')
    agent = LLMAgentPolicy(h, llm)
    wf = WalkForwardEval(_source(), date(2026, 6, 10), date(2026, 6, 15), horizon=2, scorer=ReturnScorer())
    report = wf.run(agent)
    assert report.n_decisions == 4 and report.n_candidates >= 1     # RUN picked + scored on real bars
    assert llm.calls                                               # the LLM was actually consulted
