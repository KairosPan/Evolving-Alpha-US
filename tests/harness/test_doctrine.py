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
