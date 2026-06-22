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
