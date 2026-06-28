# tests/harness/test_doctrine.py
import pytest
from alpha.harness.doctrine import DoctrineEntry, Doctrine
from alpha.harness.errors import ImmutableDoctrineError


def test_immutable_entry_blocks_post_construction_edit():
    e = DoctrineEntry(section="risk_redline", phases=["flush"], immutable=True,
                      guidance="respect the regime; no chasing in risk-off")
    with pytest.raises(ImmutableDoctrineError):
        e.guidance = "changed"


def test_mutable_entry_allows_edit():
    e = DoctrineEntry(section="trend_play", phases=["trend"], immutable=False, guidance="ride leaders")
    e.guidance = "ride leaders, trim into blowoff"
    assert e.guidance == "ride leaders, trim into blowoff"


def test_doctrine_queries():
    doc = Doctrine.from_seed_list([
        {"section": "core", "regime": "all", "immutable": True, "guidance": "stop discipline"},
        {"section": "trend", "regime": "trend", "immutable": False, "guidance": "ride leaders"},
    ])
    assert {e.section for e in doc.immutable_core()} == {"core"}
    assert {e.section for e in doc.mutable_entries()} == {"trend"}
    # 'all' entry applies to any phase; 'trend' entry applies to trend
    sections = {e.section for e in doc.for_phase("trend")}
    assert sections == {"core", "trend"}
    assert doc.get("core").immutable is True


def test_doctrine_from_seed_normalizes_phase():
    doc = Doctrine.from_seed_list([{"section": "s", "regime": "momentum", "guidance": "g"}])
    assert doc.get("s").phases == ["trend"]


def test_doctrine_entry_domain_operational_round_trips():
    e = DoctrineEntry(section="ops_check", guidance="check system health",
                      domain="operational", immutable=False)
    assert e.domain == "operational"
    # round-trip: model_dump → model_validate must preserve domain
    e2 = DoctrineEntry.model_validate(e.model_dump())
    assert e2.domain == "operational"
    assert e2.immutable is False


def test_doctrine_entry_domain_orthogonal_to_immutable():
    # immutable=True entry defaults to domain="trading"
    e_imm = DoctrineEntry(section="risk_redline", phases=["flush"],
                          immutable=True, guidance="stop discipline")
    assert e_imm.domain == "trading"
    assert e_imm.immutable is True
    # domain="operational" entry can be immutable=False (orthogonal)
    e_op = DoctrineEntry(section="ops_alert", guidance="send alert",
                         domain="operational", immutable=False)
    assert e_op.domain == "operational"
    assert e_op.immutable is False
