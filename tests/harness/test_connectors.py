import pytest
from alpha.harness.connectors import ConnectorEntry, ConnectorRegistry
from alpha.harness.state import HarnessState
from alpha.harness.doctrine import Doctrine
from alpha.harness.registry import MemoryStore, SkillRegistry


def _entry(cid="alpaca", **kw):
    base = dict(connector_id=cid, name="Alpaca", kind="data_source", impl_ref="alpaca",
                capabilities=["bars", "snapshots"], env_keys=["APCA_API_KEY_ID"],
                instructions="US equities bars/snapshots.", pit_key="announce_date:=process_date")
    base.update(kw)
    return ConnectorEntry(**base)


def test_entry_rejects_unknown_field():
    with pytest.raises(Exception):
        ConnectorEntry(connector_id="x", name="X", kind="data_source", impl_ref="alpaca",
                       capabilities=[], env_keys=[], instructions="", bogus=1)


def test_entry_defaults():
    e = _entry()
    assert e.enabled is True and e.required is False and e.tier == "T0_OBSERVE"
    assert e.domain == "trading" and e.notes == ""


def test_registry_dup_id_raises():
    with pytest.raises(ValueError):
        ConnectorRegistry.from_connectors([_entry(), _entry()])


def test_registry_get_all_len_bool():
    r = ConnectorRegistry.from_connectors([_entry()])
    assert r.get("alpaca").name == "Alpaca" and r.get("absent") is None
    assert len(r) == 1 and r.all()[0].connector_id == "alpaca"
    assert bool(ConnectorRegistry.empty()) is True and len(ConnectorRegistry.empty()) == 0


def test_registry_upsert_replaces():
    r = ConnectorRegistry.empty()
    r.upsert(_entry())
    r.upsert(_entry(name="Alpaca v2"))
    assert len(r) == 1 and r.get("alpaca").name == "Alpaca v2"


def _minimal_h(**kw):
    return HarnessState(doctrine=Doctrine(), skills=SkillRegistry.from_skills([]),
                        memory=MemoryStore.from_lessons([]), **kw)


def test_harness_roundtrip_carries_connectors():
    h = _minimal_h(connectors=ConnectorRegistry.from_connectors([_entry()]))
    d = h.to_dict()
    assert d["connectors"][0]["connector_id"] == "alpaca"
    h2 = HarnessState.from_dict(d)
    assert h2.connectors.get("alpaca").pit_key == "announce_date:=process_date"


def test_legacy_dump_without_connectors_yields_empty():
    h = _minimal_h()
    d = h.to_dict()
    d.pop("connectors")
    h2 = HarnessState.from_dict(d)
    assert len(h2.connectors) == 0
