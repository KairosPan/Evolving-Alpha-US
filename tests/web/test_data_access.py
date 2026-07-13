"""Contract for the web data-access layer: it reads the REAL seeds (the system's evolving brain)
and exposes filter/stat helpers the templates consume. No web server involved here."""
from __future__ import annotations

from alpha_web import data_access as da
from alpha.harness.state import HarnessState


def test_phases_are_the_canonical_six_cycle_in_order():
    keys = [p.key for p in da.PHASES]
    assert keys == ["washout", "recovery", "ignition", "trend", "distribution", "flush"]
    # frontside (risk-on) is exactly recovery/ignition/trend — matches GCycle._FRONTSIDE
    frontside = {p.key for p in da.PHASES if p.frontside}
    assert frontside == {"recovery", "ignition", "trend"}
    # every phase carries display copy for the taxonomy view
    assert all(p.label and p.tagline for p in da.PHASES)


def test_growth_states_are_the_three_market_clock_states_stop_to_go():
    # left→right (pos 0..2) = rising risk appetite = stop | caution | go
    assert [s.key for s in da.GROWTH_STATES] == ["correction", "under_pressure", "confirmed_uptrend"]
    assert [s.tone for s in da.GROWTH_STATES] == ["stop", "caution", "go"]
    assert [s.pos for s in da.GROWTH_STATES] == [0, 1, 2]
    # only confirmed_uptrend is frontside (matches growth_clock._MAP)
    assert {s.key for s in da.GROWTH_STATES if s.frontside} == {"confirmed_uptrend"}
    # each state carries the full "market:<state>" token + display copy
    assert all(s.token == f"market:{s.key}" and s.label and s.tagline for s in da.GROWTH_STATES)


def test_is_growth_phase_routes_on_the_market_prefix():
    # growth tokens carry the "market:" prefix; momo tokens never do (disjoint vocabularies)
    assert da.is_growth_phase("market:confirmed_uptrend") is True
    assert da.is_growth_phase("market:panic_state") is True
    assert da.is_growth_phase("trend") is False
    assert da.is_growth_phase("washout") is False
    assert da.is_growth_phase(None) is False


def test_growth_state_key_strips_the_scale_prefix():
    assert da.growth_state_key("market:under_pressure") == "under_pressure"
    assert da.growth_state_key("trend") is None
    # a legal-but-non-dial market token (panic) yields a key not in the three-state table
    assert da.growth_state_key("market:panic_state") == "panic_state"
    assert "panic_state" not in da.GROWTH_STATE_BY_KEY


def test_detect_panic_fires_on_the_token_or_a_key_risk():
    assert da.detect_panic("market:panic_state") is True
    assert da.detect_panic("market:correction", ["panic-state rebound: leaders underperform"]) is True
    assert da.detect_panic("market:confirmed_uptrend", ["binary PDUFA inside the horizon"]) is False
    assert da.detect_panic("trend", []) is False
    assert da.detect_panic(None, None) is False


def test_growth_dial_arcs_are_three_60deg_arcs_across_the_top_semicircle():
    dial = da.growth_dial_arcs()
    assert len(dial["segments"]) == 3
    # each arc rotates into the 180°→360° top semicircle (west→top→east), 60° apart
    rotates = [s["rotate"] for s in dial["segments"]]
    assert rotates == [183.0, 243.0, 303.0]
    # markers sit on the ring (r=46) at the centre of each slot — mid arc peaks at the top (my minimal)
    assert dial["segments"][1]["mx"] == da.RING_CX          # centre arc marker centred horizontally
    assert min(s["my"] for s in dial["segments"]) == dial["segments"][1]["my"]
    # geometry carries the state so the template can tone/label each arc
    assert [s["state"].tone for s in dial["segments"]] == ["stop", "caution", "go"]


def test_load_brain_reads_the_real_seeds():
    state = da.load_brain()
    assert isinstance(state, HarnessState)
    # the shipped seeds: 12 doctrine entries, 8 lessons, 16 skills
    assert len(state.doctrine.entries) == 12
    assert len(state.memory) == 8
    assert len(state.skills) == 16


def test_brain_stats_summarizes_each_store():
    stats = da.brain_stats(da.load_brain())
    assert stats["doctrine"]["total"] == 12
    assert stats["doctrine"]["immutable"] == 7      # the seven red-lines
    assert stats["doctrine"]["mutable"] == 5
    assert stats["memory"]["total"] == 8
    assert stats["skills"]["total"] == 16
    assert stats["skills"]["active"] >= 1
    assert set(stats["skills"]["by_family"]) <= set(da.FAMILIES)


def test_filter_skills_by_family_and_status_and_type():
    state = da.load_brain()
    meme = da.filter_skills(state, family="meme")
    assert meme and all(s.family == "meme" for s in meme)
    incubating = da.filter_skills(state, status="incubating")
    assert incubating and all(s.status == "incubating" for s in incubating)
    detectors = da.filter_skills(state, type="failure_detector")
    assert detectors and all(s.type == "failure_detector" for s in detectors)
    # combined filters intersect
    combined = da.filter_skills(state, family="runner", type="pattern")
    assert all(s.family == "runner" and s.type == "pattern" for s in combined)


def test_filter_skills_by_phase_uses_registry_semantics():
    state = da.load_brain()
    trend = da.filter_skills(state, phase="trend")
    assert trend and all(("trend" in s.phases or s.applies_all_phases) for s in trend)


def test_filter_lessons_by_family_outcome_phase():
    state = da.load_brain()
    losses = da.filter_lessons(state, outcome="loss")
    assert losses and all(l.outcome == "loss" for l in losses)
    runner = da.filter_lessons(state, family="runner")
    assert runner and all(l.family == "runner" for l in runner)


def test_split_doctrine_separates_redlines_from_plays():
    immutable, mutable = da.split_doctrine(da.load_brain())
    assert immutable and all(e.immutable for e in immutable)
    assert mutable and all(not e.immutable for e in mutable)
    assert any(e.section == "trend_play" for e in mutable)


def test_load_brain_prefers_live_store_when_present(tmp_path, monkeypatch):
    from alpha_web import data_access as da
    from alpha.meta.store import LiveBrainStore
    store = LiveBrainStore(tmp_path / "brain")
    h, log = store.load()
    log.append("patch_skill", "skill", h.skills.all()[0].skill_id, "update", "x", rationale="r")
    store.save(h, log)
    monkeypatch.setenv("ALPHA_LIVE_BRAIN_DIR", str(tmp_path / "brain"))
    assert da.brain_badge() == {"is_live": True, "edit_count": 1}
    da.load_brain()                      # must not raise and must not write seeds over the store
    assert LiveBrainStore(tmp_path / "brain").edit_count() == 1


def test_brain_badge_seed_baseline_when_empty(tmp_path, monkeypatch):
    from alpha_web import data_access as da
    monkeypatch.setenv("ALPHA_LIVE_BRAIN_DIR", str(tmp_path / "empty"))
    assert da.brain_badge() == {"is_live": False, "edit_count": 0}
