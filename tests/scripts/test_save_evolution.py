"""Offline smoke for scripts/save_evolution.py: run the InnerLoop (injected MockLLM agent + refiner)
over a source and assemble the Evolution view dict the console renders."""
import json
import sys
from datetime import date
from pathlib import Path

import pandas as pd

from alpha.data.source import FakeSource
from alpha.llm.client import MockLLMClient

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))
import save_evolution as se   # noqa: E402

_AGENT = lambda: MockLLMClient('{"candidates": [{"symbol": "RUN", "pattern": "gap_and_go"}]}')
_REFINER = lambda: MockLLMClient('{"ops": []}')      # no edits -> empty but valid trajectory


def _fake(n=10):
    cal = [date(2026, 6, d) for d in range(1, 1 + n)]
    snaps, px, closes = {}, 10.0, []
    for d in cal:
        prev = px; px = px * 1.15; closes.append(px)
        snaps[d] = pd.DataFrame({"symbol": ["RUN"], "name": ["RUN"], "open": [prev], "high": [px],
                                 "low": [prev], "close": [px], "volume": [1], "prev_close": [prev]})
    bars = {"RUN": pd.DataFrame({"date": cal, "open": [10.0] + closes[:-1], "high": closes,
                                 "low": [10.0] + closes[:-1], "close": closes, "volume": [1] * n})}
    return FakeSource(calendar=cal, bars=bars, snapshots=snaps), cal[0], cal[-1]


def test_run_evolution_returns_console_shape():
    src, start, end = _fake()
    evo = se.run_evolution(src, start, end, agent_llm_factory=_AGENT, refiner_llm_factory=_REFINER)
    assert {"window", "summary", "edits"} <= set(evo)
    assert {"refines", "breaker_trips", "frozen_from", "n_edits"} <= set(evo["summary"])
    assert isinstance(evo["edits"], list)
    assert evo["window"]["start"] == start.isoformat()
    assert evo["summary"]["n_edits"] == len(evo["edits"])


def test_evolution_view_is_json_serializable():
    src, start, end = _fake()
    evo = se.run_evolution(src, start, end, agent_llm_factory=_AGENT, refiner_llm_factory=_REFINER)
    json.dumps(evo, default=str)   # must round-trip to disk without choking on payloads
