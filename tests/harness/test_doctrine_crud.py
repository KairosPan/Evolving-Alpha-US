import pytest
from alpha.harness.doctrine import DoctrineEntry, Doctrine
from alpha.harness.errors import ImmutableDoctrineError


def _doc():
    return Doctrine.from_seed_list([
        {"section": "core", "regime": "all", "immutable": True, "guidance": "stop discipline"},
        {"section": "trend", "regime": "trend", "immutable": False, "guidance": "ride leaders"},
    ])


def test_add_and_duplicate():
    doc = _doc()
    doc.add(DoctrineEntry(section="new", phases=["flush"], guidance="cut fast"))
    assert doc.get("new") is not None
    with pytest.raises(ValueError):
        doc.add(DoctrineEntry(section="trend", guidance="dup"))


def test_rewrite_mutable():
    doc = _doc()
    doc.rewrite("trend", "ride leaders; trim into blowoff")
    assert doc.get("trend").guidance == "ride leaders; trim into blowoff"


def test_rewrite_immutable_blocked():
    doc = _doc()
    with pytest.raises(ImmutableDoctrineError):
        doc.rewrite("core", "loosen the stop")
    assert doc.get("core").guidance == "stop discipline"     # unchanged


def test_rewrite_missing():
    doc = _doc()
    with pytest.raises(KeyError):
        doc.rewrite("nope", "x")


def test_remove_mutable_and_immutable():
    doc = _doc()
    doc.remove("trend")
    assert doc.get("trend") is None
    with pytest.raises(ImmutableDoctrineError):
        doc.remove("core")
    assert doc.get("core") is not None
    with pytest.raises(KeyError):
        doc.remove("nope")
