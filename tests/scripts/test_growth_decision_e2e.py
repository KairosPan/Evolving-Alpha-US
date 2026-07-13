"""P0 PROGRAM ACCEPTANCE GATE (DEVELOPMENT-PLAN §1 P0).

With the growth pack active (ALPHA_SEED_PACK=growth), Kairos produces one growth DecisionPackage
offline — FakeSource + MockLLMClient, no keys, no network — through the real decide path
(save_decisions.produce_decisions -> LLMAgentPolicy -> L4 guard -> L3 sizing). The assembled prompt
carries the growth persona and growth doctrine; the momo persona / CANONICAL_PHASES are absent.

Also pins the production pack-wiring: the default (momo) H is byte-identical, the env switch flips
the pack, run_verdict stays symmetric across arms, and the run-provenance sidecar records the pack.
"""
import sys
from datetime import date
from pathlib import Path

import pandas as pd

from alpha.data.source import FakeSource
from alpha.eval.decision import DecisionPackage
from alpha.eval.decision_store import DecisionStore
from alpha.harness.loader import load_pack, load_seeds
from alpha.harness.snapshot import harness_digest
from alpha.llm.client import MockLLMClient

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))
import save_decisions as sd   # noqa: E402
import run_verdict as rv       # noqa: E402

_MOMO_SEEDS = Path(__file__).resolve().parents[2] / "seeds"
# The mock cites a growth skill_id (breakout_entry) with a growth market-clock regime read.
_AGENT = lambda: MockLLMClient(
    '{"regime_read": "market:confirmed_uptrend", '
    '"candidates": [{"symbol": "RUN", "pattern": "breakout_entry", "reason": "thesis card AI-compute"}]}')


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


# ── THE acceptance gate ───────────────────────────────────────────────────────

def test_growth_pack_produces_growth_decision_package(monkeypatch):
    monkeypatch.setenv("ALPHA_SEED_PACK", "growth")
    src, start, end = _fake()
    records: list[dict] = []
    pkgs = list(sd.produce_decisions(src, start, end, agent_llm_factory=_AGENT, collect=records.append))

    # produced real packages that validate as DecisionPackages
    assert len(pkgs) == 8 and all(isinstance(p, DecisionPackage) for p in pkgs)
    assert [p.date for p in pkgs] == src.trading_calendar()

    # the growth H loaded (h_digest matches the growth pack, not momo)
    assert all(p.h_digest == harness_digest(load_pack("growth")) for p in pkgs)
    assert harness_digest(load_pack("growth")) != harness_digest(load_seeds(_MOMO_SEEDS))

    # the assembled system prompt is the GROWTH prompt (persona + doctrine), not the momo one
    assembled = [r["text"] for r in records if r.get("kind") == "assembled"]
    assert assembled, "expected an assembled-prompt audit record per day"
    ap = assembled[-1]
    assert "sector-growth" in ap                           # growth persona
    assert "market:confirmed_uptrend" in ap                # growth market-clock output contract + clock
    assert "thesis" in ap.lower()                          # growth doctrine present (thesis-first)
    assert "speculative-momentum" not in ap                # momo persona absent
    assert "washout" not in ap and "flush" not in ap       # momo CANONICAL_PHASES absent
    # doctrine-injection regression guard: the growth H's OWN mutable doctrine is actually injected —
    # a distinctive untagged entry's text AND a regime-TAGGED entry's text appear verbatim. This catches
    # a dropped/reordered doctrine panel (a real isomorphism regression), not just the static persona template.
    assert "first ask which phase of its cycle" in ap      # cycle_eye (mutable, untagged) guidance text
    assert "The market answers one question" in ap         # market_three_states (mutable, market:-TAGGED) guidance

    # a growth day surfaces a growth-doctrine-cited candidate that validates end to end
    sized = [p for p in pkgs if p.candidates]
    assert sized, "expected at least one day to surface a candidate through the guard"
    assert sized[-1].candidates[0].pattern == "breakout_entry"


# ── production pack-wiring pins ────────────────────────────────────────────────

def test_produce_decisions_default_is_momo_byte_identical(monkeypatch):
    monkeypatch.delenv("ALPHA_SEED_PACK", raising=False)
    src, start, end = _fake()
    pkgs = list(sd.produce_decisions(src, start, end, agent_llm_factory=_AGENT))
    assert all(p.h_digest == harness_digest(load_seeds(_MOMO_SEEDS)) for p in pkgs)   # unchanged default


def test_run_verdict_growth_is_symmetric_offline(monkeypatch):
    """run_verdict under the growth pack runs offline and hands BOTH arms the same (growth) pack."""
    monkeypatch.setenv("ALPHA_SEED_PACK", "growth")
    src, start, end = _fake()
    result = rv.run_verdict(src, start, end,
                            agent_llm_factory=_AGENT, refiner_llm_factory=_AGENT)
    assert "HCH" in result.arms and "Hexpert" in result.arms       # both arms ran on one pack


def test_save_decisions_sidecar_records_pack_and_screen(tmp_path, monkeypatch):
    monkeypatch.setenv("ALPHA_SEED_PACK", "growth")
    monkeypatch.delenv("ALPHA_UNIVERSE_SCREEN", raising=False)
    src, start, end = _fake()
    store = DecisionStore(tmp_path)
    sd.save_decisions(src, start, end, store, agent_llm_factory=_AGENT)
    import json
    side = json.loads((tmp_path / f"{start.isoformat()}.prompt.json").read_text())
    assert side["seed_pack"] == "growth"          # run provenance: which pack produced the decision
    assert side["universe_screen"] == "gainer"    # run provenance: which universe entry (default)
    # verdict-neutrality: the frozen DecisionStore package carries neither key
    dumped = store.get(start).model_dump()
    assert "seed_pack" not in dumped and "universe_screen" not in dumped
