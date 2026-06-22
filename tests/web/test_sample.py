"""The Decisions/Verdict pages render real artifacts when present, else a clearly-badged SAMPLE so
the UI is meaningful out of the box. The sample must be built from the REAL models (no fantasy
fields) and be internally consistent with the size/regime logic."""
from __future__ import annotations

from alpha_web import sample
from alpha_web import data_access as da
from alpha.eval.decision import DecisionPackage
from alpha.sizing.position import SizeTier, size_tier
from alpha.state.market import MarketState
from alpha.regime.classifier import GCycle, RegimeRead

_VALID_TIERS = {"flat", "probe", "core", "heavy"}
_PHASE_KEYS = {p.key for p in da.PHASES}


def test_sample_market_state_is_a_real_marketstate():
    st = sample.sample_market_state()
    assert isinstance(st, MarketState)
    assert st.echelon  # has a runner echelon


def test_sample_regime_is_derived_from_the_sample_state():
    st = sample.sample_market_state()
    reg = sample.sample_regime()
    assert isinstance(reg, RegimeRead)
    assert reg.phase in _PHASE_KEYS
    # derived, not hand-typed: recomputing from the state agrees
    assert GCycle().read(st) == reg


def test_sample_decision_uses_real_models_and_is_consistent():
    pkg = sample.sample_decision()
    assert isinstance(pkg, DecisionPackage)
    assert len(pkg.candidates) >= 3
    for c in pkg.candidates:
        assert c.symbol and c.pattern and c.entry and c.exit_stop
        assert c.size_tier in _VALID_TIERS
        # size_tier is the real mapping of conviction x regime appetite, not arbitrary
        assert c.size_tier == size_tier(c.confidence, pkg.regime.risk_gate)
        assert c.fill_feasibility is not None
        assert c.taboo_check  # at least one guard evaluated
    assert pkg.portfolio is not None
    assert pkg.portfolio.correlated_groups  # the "one correlated bet" doctrine made visible
    assert pkg.key_risks
    assert pkg.regime is not None


def test_sample_decision_is_deterministic():
    assert sample.sample_decision() == sample.sample_decision()


def test_sample_verdict_shape_matches_the_runner_report():
    v = sample.sample_verdict()
    assert {"HCH", "Hexpert"} <= set(v["arms"])
    assert "headline" in v and "stat_verdict" in v
    for arm in v["arms"].values():
        assert {"mean_excess", "hit_rate", "n_decisions"} <= set(arm)
