"""A6 wiring: the three metered run entry points (save_decisions / run_verdict / refine_live) thread a
SpendMeter so every LLM call is recorded, a budget breach HALTS the run loudly (BudgetExceeded
propagates out of the run function — not swallowed by the loop), and meter=None is byte-identical.

Offline, keyless: MockLLM factories, FakeSource. The breach tests use an absurdly tiny ceiling so the
first metered call trips it — proving the governed-not-reported halt reaches the run boundary.
"""
import importlib
import sys
from datetime import date
from pathlib import Path

import pandas as pd
import pytest

from alpha.data.source import FakeSource
from alpha.eval.decision import Candidate, DecisionPackage
from alpha.eval.decision_store import DecisionStore
from alpha.harness.doctrine import Doctrine
from alpha.harness.edit_log import EditLog, EditProvenance
from alpha.harness.memory import Lesson
from alpha.harness.registry import MemoryStore, SkillRegistry
from alpha.harness.skill import Skill
from alpha.harness.state import HarnessState
from alpha.llm.client import MockLLMClient
from alpha.llm.metering import Budget, BudgetExceeded, SpendMeter
from alpha.loop.inner_loop import LoopConfig
from alpha.meta.store import LiveBrainStore

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))
import save_decisions as sd   # noqa: E402
import run_verdict as rv       # noqa: E402

_AGENT = lambda: MockLLMClient('{"candidates": [{"symbol": "RUN", "pattern": "gap_and_go"}]}')
_REFINER = lambda: MockLLMClient('{"ops": []}')
_TINY = Budget(usd=1e-12)      # any real call breaches (a few estimated tokens cost >> 1e-12 USD)


def _fake(n=8):
    cal = [date(2026, 6, d) for d in range(1, 1 + n)]
    snaps, px, closes = {}, 10.0, []
    for d in cal:
        prev = px; px = px * 1.15; closes.append(px)
        snaps[d] = pd.DataFrame({"symbol": ["RUN"], "name": ["RUN"], "open": [prev], "high": [px],
                                 "low": [prev], "close": [px], "volume": [1], "prev_close": [prev]})
    bars = {"RUN": pd.DataFrame({"date": cal, "open": [10.0] + closes[:-1], "high": closes,
                                 "low": [10.0] + closes[:-1], "close": closes, "volume": [1] * n})}
    return FakeSource(calendar=cal, bars=bars, snapshots=snaps), cal[0], cal[-1]


# --------------------------------------------------------------------------- save_decisions

def test_save_decisions_meter_records_one_call_per_day():
    src, start, end = _fake()
    meter = SpendMeter()
    pkgs = list(sd.produce_decisions(src, start, end, agent_llm_factory=_AGENT, meter=meter))
    summ = meter.summary()
    assert summ["n_calls"] == len(pkgs)                 # exactly one agent call per trading day
    assert summ["total_usd"] > 0
    assert set(summ["by_role"]) == {"agent"} and summ["by_role"]["agent"]["n"] == len(pkgs)
    assert summ["estimated_calls"] == summ["n_calls"]    # MockLLM has no provider usage -> estimated


def test_save_decisions_budget_breach_halts_the_run():
    src, start, end = _fake()
    with pytest.raises(BudgetExceeded):
        list(sd.produce_decisions(src, start, end, agent_llm_factory=_AGENT,
                                  meter=SpendMeter(_TINY)))


def test_save_decisions_meter_none_is_byte_identical():
    src, start, end = _fake()
    a = list(sd.produce_decisions(src, start, end, agent_llm_factory=_AGENT))              # unmetered
    b = list(sd.produce_decisions(src, start, end, agent_llm_factory=_AGENT, meter=None))  # explicit None
    assert [p.model_dump() for p in a] == [p.model_dump() for p in b]


def test_save_decisions_full_run_surfaces_summary(tmp_path):
    src, start, end = _fake()
    meter = SpendMeter()
    n = sd.save_decisions(src, start, end, DecisionStore(tmp_path), agent_llm_factory=_AGENT, meter=meter)
    assert n == 8 and meter.summary()["n_calls"] == 8


def test_save_decisions_cli_exits_nonzero_on_breach(tmp_path, monkeypatch, capsys):
    """The governed halt reaches the CLI: a --budget-usd breach prints loudly to stderr and exits 1
    (not merely logs) — deliverable (b), the governed-not-reported core, end to end through main()."""
    src, start, end = _fake()
    monkeypatch.delenv("ALPHA_EPISODES_DB", raising=False)
    monkeypatch.setattr(sd, "SnapshotSource", lambda *_a, **_k: src)
    monkeypatch.setattr(sd, "PITStore", lambda *_a, **_k: None)
    monkeypatch.setattr(sd, "verify_checksums", lambda *_a, **_k: None)
    monkeypatch.setattr(sd, "make_client", lambda role, **_k: _AGENT())
    monkeypatch.setattr(sys, "argv", ["save_decisions", "PIT", start.isoformat(), end.isoformat(),
                                      str(tmp_path / "out"), "--budget-usd", "1e-12"])
    with pytest.raises(SystemExit) as ei:
        sd.main()
    assert ei.value.code == 1                            # non-zero exit
    assert "HALTED" in capsys.readouterr().err           # loud, on stderr


# --------------------------------------------------------------------------- run_verdict

def test_run_verdict_meter_records_across_arms():
    src, start, end = _fake(12)
    meter = SpendMeter()
    rv.run_verdict(src, start, end, agent_llm_factory=_AGENT, refiner_llm_factory=_REFINER, meter=meter)
    summ = meter.summary()
    assert summ["n_calls"] > 0                           # every arm's agent/refiner calls metered
    assert set(summ["by_role"]) <= {"agent", "refiner"}
    assert summ["total_usd"] > 0


def test_run_verdict_budget_breach_halts_the_run():
    src, start, end = _fake(12)
    with pytest.raises(BudgetExceeded):
        rv.run_verdict(src, start, end, agent_llm_factory=_AGENT, refiner_llm_factory=_REFINER,
                       meter=SpendMeter(_TINY))


def test_run_verdict_meter_none_matches_today():
    src, start, end = _fake(12)
    a = rv.run_verdict(src, start, end, agent_llm_factory=_AGENT, refiner_llm_factory=_REFINER)
    b = rv.run_verdict(src, start, end, agent_llm_factory=_AGENT, refiner_llm_factory=_REFINER, meter=None)
    assert a.hch_minus_hexpert_mean_excess == b.hch_minus_hexpert_mean_excess


# --------------------------------------------------------------------------- refine_live

_REFINER_SCRIPT = (
    '{"ops": [{"tool": "process_memory", "args": {"lesson_id": "m_new", "phases": ["trend"], '
    '"outcome": "win", "lesson": "learned"}, "rationale": "new"}]}'
)


class _PickRun:
    def decide(self, state, universe):
        return DecisionPackage(date=state.date,
                               candidates=[Candidate(symbol=s.symbol, pattern="gap_and_go")
                                           for s in universe.all()])


def _refine_source(n=8):
    cal = [date(2026, 6, d) for d in range(1, 1 + n)]
    snaps, px, closes = {}, 10.0, []
    for d in cal:
        prev = px; px = px * 1.2; closes.append(px)
        snaps[d] = pd.DataFrame({"symbol": ["RUN"], "name": ["RUN"], "open": [prev], "high": [px],
                                 "low": [prev], "close": [px], "volume": [1], "prev_close": [prev]})
    bars = {"RUN": pd.DataFrame({"date": cal, "open": [10.0] + closes[:-1], "high": closes,
                                 "low": [10.0] + closes[:-1], "close": closes, "volume": [1] * n})}
    return FakeSource(calendar=cal, bars=bars, snapshots=snaps)


def _seed_brain(brain_dir):
    skills = SkillRegistry.from_skills([Skill(skill_id="gap_and_go", name="Gap", type="pattern",
                                              status="active")])
    lesson = Lesson.from_seed({"lesson_id": "m_teach", "phases": ["trend"], "outcome": "win",
                               "lesson": "taught"})
    h = HarnessState(doctrine=Doctrine(), skills=skills, memory=MemoryStore.from_lessons([lesson]))
    log = EditLog()
    log.append("process_memory", "memory", "m_teach", "create")
    log.stamp_last(EditProvenance(path="teaching", proposer="sonia"))
    LiveBrainStore(str(brain_dir)).save(h, log)


def _run_refine(tmp_path, *, meter):
    refine_live = importlib.import_module("scripts.refine_live")
    brain_dir, conflicts_dir = tmp_path / "brain", tmp_path / "conflicts"
    _seed_brain(brain_dir)
    src = _refine_source()
    cal = src.trading_calendar()
    return refine_live.run_refine_live(
        src, cal[0], cal[-1], brain_dir=str(brain_dir), conflicts_dir=str(conflicts_dir),
        agent_llm_factory=lambda: MockLLMClient("{}"),
        refiner_llm_factory=lambda: MockLLMClient(_REFINER_SCRIPT),
        agent_factory=lambda h: _PickRun(),
        loop_config=LoopConfig(horizon=2, screen=False, size=False),
        proposals_root=str(tmp_path / "proposals"), meter=meter)


def test_refine_live_meter_records_and_summary_on_return(tmp_path):
    meter = SpendMeter()
    out = _run_refine(tmp_path, meter=meter)
    assert "spend" in out and out["spend"]["n_calls"] > 0        # refiner calls metered + surfaced on packet
    assert out["spend"]["n_calls"] == meter.summary()["n_calls"]


def test_refine_live_budget_breach_halts_the_run(tmp_path):
    with pytest.raises(BudgetExceeded):
        _run_refine(tmp_path, meter=SpendMeter(_TINY))


def test_refine_live_meter_none_omits_spend_key(tmp_path):
    out = _run_refine(tmp_path, meter=None)
    assert "spend" not in out                                    # meter=None -> return dict unchanged
