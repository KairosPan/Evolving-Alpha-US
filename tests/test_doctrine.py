# tests/test_doctrine.py  (整体替换)
from youzi.harness.doctrine import DoctrineEntry, Doctrine


def _entries():
    return [
        DoctrineEntry.from_seed({"section": "退潮作战", "regime": "退潮",
                                 "immutable": False, "guidance": "降题材预期"}),
        DoctrineEntry.from_seed({"section": "纪律红线:退潮不接力", "regime": "all",
                                 "immutable": True, "guidance": "退潮期禁止接力"}),
        DoctrineEntry.from_seed({"section": "主升作战", "regime": "主升/震荡补涨",
                                 "immutable": False, "guidance": "持有龙头"}),
    ]


def test_from_seed_parses_multi_regime():
    e = _entries()[2]
    assert e.phases == ["主升", "震荡补涨"]
    assert e.regime_raw == "主升/震荡补涨"


def test_doctrine_for_regime_membership_and_all():
    doc = Doctrine(entries=_entries())
    assert [e.section for e in doc.for_regime("退潮")] == ["退潮作战", "纪律红线:退潮不接力"]
    # 主升作战 适用于 主升 与 震荡补涨 两相位; all 永远命中
    assert [e.section for e in doc.for_regime("震荡补涨")] == ["纪律红线:退潮不接力", "主升作战"]
    assert "纪律红线:退潮不接力" in [e.section for e in doc.for_regime("主升")]
    assert [e.section for e in doc.immutable_core()] == ["纪律红线:退潮不接力"]
    assert len(doc.mutable_entries()) == 2


def test_doctrine_entry_forbids_unknown_keys():
    import pytest
    from pydantic import ValidationError
    with pytest.raises(ValidationError):
        DoctrineEntry.from_seed({"section": "x", "regime": "all", "immutable": False,
                                 "guidance": "g", "typo_key": 1})


def test_doctrine_crud_with_immutable_protection():
    import pytest
    from youzi.harness.errors import ImmutableDoctrineError
    doc = Doctrine(entries=_entries())
    # 改写可变条目 OK
    doc.rewrite("退潮作战", "新的退潮指导")
    assert doc.get("退潮作战").guidance == "新的退潮指导"
    # 改写纪律红线 -> 拒绝
    with pytest.raises(ImmutableDoctrineError):
        doc.rewrite("纪律红线:退潮不接力", "篡改")
    # 删除纪律红线 -> 拒绝
    with pytest.raises(ImmutableDoctrineError):
        doc.remove("纪律红线:退潮不接力")
    # 删除可变条目 OK
    doc.remove("退潮作战")
    assert doc.get("退潮作战") is None
    # 新增 + 重复 section 拒绝
    doc.add(DoctrineEntry.from_seed({"section": "新作战", "regime": "主升",
                                     "immutable": False, "guidance": "g"}))
    with pytest.raises(ValueError):
        doc.add(DoctrineEntry.from_seed({"section": "主升作战", "regime": "主升",
                                         "immutable": False, "guidance": "dup"}))


def test_immutable_entry_blocks_direct_mutation():
    import pytest
    from youzi.harness.errors import ImmutableDoctrineError
    e = DoctrineEntry.from_seed({"section": "纪律", "regime": "all", "immutable": True, "guidance": "g"})
    with pytest.raises(ImmutableDoctrineError):
        e.guidance = "篡改"
    with pytest.raises(ImmutableDoctrineError):
        e.immutable = False          # 不能翻转 immutable 再改
    m = DoctrineEntry.from_seed({"section": "x", "regime": "主升", "immutable": False, "guidance": "g"})
    m.guidance = "改了"               # 可变条目允许
    assert m.guidance == "改了"
