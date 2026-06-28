import pytest
from pydantic import ValidationError
from alpha.harness.skill import Skill, SkillStats, GateSpec


def test_stats_record_ewma():
    s = SkillStats()
    s.record(True)
    assert s.n == 1 and s.wins == 1 and s.ewma_winrate == 1.0
    s.record(False, decay=0.5)
    assert s.n == 2 and s.losses == 1 and s.ewma_winrate == 0.5  # decay*new + (1-decay)*old = 0.5*0.0 + 0.5*1.0
    with pytest.raises(ValueError):
        s.record(True, decay=0.0)


def test_gatespec_rejects_unknown_keys():
    GateSpec(min_consecutive_up_days=2, status_in=["gainer"], min_rvol=3.0)
    with pytest.raises(ValidationError):
        GateSpec(min_boards=2)            # CN field name — must be rejected (extra=forbid)


def test_skill_from_seed_normalizes_phase_and_family():
    sk = Skill.from_seed({
        "skill_id": "gap_and_go", "name": "Gap and Go", "type": "pattern",
        "family": "runner", "phases": ["ignition", "momentum", "all"],
        "trigger": "gap up, hold above prior close", "entry": "buy ORB hold",
        "exit_stop": "lose VWAP", "taboo": ["chasing in risk-off"],
    })
    assert sk.phases == ["ignition", "trend"]   # momentum->trend, dedup; 'all' -> flag
    assert sk.applies_all_phases is True
    assert sk.family == "runner"
    assert sk.status == "incubating"            # default
    assert sk.stats.n == 0


def test_skill_rejects_bad_family():
    with pytest.raises(ValueError):
        Skill.from_seed({"skill_id": "x", "name": "X", "type": "pattern", "family": "crypto"})


def test_skill_rejects_unknown_seed_key():
    with pytest.raises(ValidationError):       # extra='forbid' -> loud failure on typo'd seed key
        Skill.from_seed({"skill_id": "x", "name": "X", "type": "pattern", "bogus_key": 1})


# PC-1 — Skill.domain field
def test_skill_domain_defaults_to_trading():
    sk = Skill.from_seed({"skill_id": "x", "name": "X", "type": "pattern"})
    assert sk.domain == "trading"


def test_skill_domain_operational_from_seed():
    sk = Skill.from_seed({"skill_id": "x", "name": "X", "type": "pattern", "domain": "operational"})
    assert sk.domain == "operational"


def test_skill_domain_survives_model_dump_round_trip():
    sk = Skill.from_seed({"skill_id": "x", "name": "X", "type": "pattern", "domain": "operational"})
    dumped = sk.model_dump()
    assert dumped["domain"] == "operational"
    sk2 = Skill(**dumped)
    assert sk2.domain == "operational"
