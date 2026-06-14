from pathlib import Path
import pytest
from alpha.harness.loader import load_seeds
from alpha.harness.regime import FAMILIES, CANONICAL_PHASES
from alpha.harness.errors import ImmutableDoctrineError

SEEDS = Path(__file__).resolve().parents[2] / "seeds"


def _h():
    return load_seeds(SEEDS)


def test_seeds_load_into_harness():
    h = _h()
    assert len(h.skills) == 16 and len(h.memory) == 8 and len(h.doctrine.entries) == 12


def test_all_families_represented_in_skills():
    h = _h()
    for fam in FAMILIES:
        assert h.skills.by_family(fam), f"no seed skills for family {fam}"


def test_defense_heavy():
    h = _h()
    detectors = len(h.skills.by_type("failure_detector"))
    patterns = len(h.skills.by_type("pattern"))
    assert detectors > patterns, f"not defense-heavy: {detectors} detectors vs {patterns} patterns"


def test_phases_are_canonical():
    h = _h()
    for s in h.skills.all():
        for p in s.phases:
            assert p in CANONICAL_PHASES, f"{s.skill_id} has non-canonical phase {p}"
    # pin the silent-drop contract (normalize_phases drops unrecognized tokens) so this test isn't
    # tautological: a non-canonical seed phase normalizes to [] rather than slipping through.
    from alpha.harness.skill import Skill
    assert Skill.from_seed({"skill_id": "x", "name": "X", "type": "pattern",
                            "phases": ["bogus_phase"]}).phases == []


def test_seed_skills_carry_at_least_one_canonical_phase():
    # complements the above: real seed skills must classify into the cycle, not silently empty out
    h = _h()
    empty = [s.skill_id for s in h.skills.all() if not s.phases]
    assert empty == [], f"seed skills with no canonical phase (typo'd?): {empty}"


def test_immutable_core_present_and_protected():
    h = _h()
    core = h.doctrine.immutable_core()
    assert len(core) == 7
    sections = {e.section for e in core}
    assert {"stop_discipline", "no_chase_risk_off", "one_correlated_bet", "loss_circuit_breaker"} <= sections
    with pytest.raises(ImmutableDoctrineError):           # write-protected after load
        core[0].guidance = "loosen"


def test_squeeze_offense_is_incubating():
    h = _h()
    # offense that needs US-3 data ships incubating (not minted active)
    assert h.skills.get("short_squeeze").status == "incubating"
    assert h.skills.get("gamma_squeeze").status == "incubating"
