# tests/test_merge_credit.py
from youzi.refine.credit import merge_credit_reports, CreditReport, SkillCredit, UNATTRIBUTED


def _rep(per, unattr=None, n_scored=0):
    return CreditReport(per_skill=per, unattributed=unattr, n_scored=n_scored)


def _sc(sid, n, wins, losses, nukes, expectancy, expectancy_raw=None):
    # C2:expectancy 语义=advantage;expectancy_raw=原始 score 口径(默认与 expectancy 同值)
    return SkillCredit(skill_id=sid, n=n, wins=wins, losses=losses, nukes=nukes,
                       hit_rate=wins / n, nuke_rate=nukes / n, expectancy=expectancy,
                       expectancy_raw=expectancy if expectancy_raw is None else expectancy_raw)


def test_merge_empty_is_empty():
    m = merge_credit_reports([])
    assert m.per_skill == {} and m.unattributed is None and m.n_scored == 0


def test_merge_accumulates_per_skill():
    # 报告1: 技能 a n=2 wins=2 exp=1.0;报告2: a n=2 wins=0 nukes=2 exp=-1.0
    r1 = _rep({"a": _sc("a", 2, 2, 0, 0, 1.0)}, n_scored=2)
    r2 = _rep({"a": _sc("a", 2, 0, 2, 2, -1.0)}, n_scored=2)
    m = merge_credit_reports([r1, r2])
    a = m.per_skill["a"]
    assert a.n == 4 and a.wins == 2 and a.losses == 2 and a.nukes == 2
    assert a.hit_rate == 0.5 and a.nuke_rate == 0.5
    assert a.expectancy == 0.0          # (2*1.0 + 2*-1.0)/4
    assert m.n_scored == 4


def test_merge_accumulates_both_expectancy_calibers():
    # C2:advantage 与原始 score 双口径分别按 n 加权合并
    r1 = _rep({"a": _sc("a", 2, 2, 0, 0, expectancy=0.5, expectancy_raw=1.0)}, n_scored=2)
    r2 = _rep({"a": _sc("a", 2, 0, 2, 0, expectancy=-0.5, expectancy_raw=0.0)}, n_scored=2)
    m = merge_credit_reports([r1, r2])
    a = m.per_skill["a"]
    assert a.expectancy == 0.0          # (2*0.5 + 2*-0.5)/4:超额口径
    assert a.expectancy_raw == 0.5      # (2*1.0 + 2*0.0)/4:原始口径独立合并


def test_merge_unattributed_and_distinct_skills():
    r1 = _rep({"a": _sc("a", 1, 1, 0, 0, 1.0)},
              unattr=_sc(UNATTRIBUTED, 1, 0, 1, 0, 0.0), n_scored=2)
    r2 = _rep({"b": _sc("b", 1, 0, 1, 1, -1.0)}, n_scored=1)
    m = merge_credit_reports([r1, r2])
    assert set(m.per_skill) == {"a", "b"}
    assert m.unattributed is not None and m.unattributed.n == 1
    assert m.n_scored == 3
