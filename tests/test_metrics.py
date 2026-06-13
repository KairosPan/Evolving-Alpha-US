from datetime import date
from youzi.eval.metrics import ScoredCandidate, EvalReport, build_report


def _sc(code, pattern, oc, score):
    return ScoredCandidate(decision_date=date(2024, 6, 27), code=code,
                           pattern=pattern, outcome=oc, score=score)


def test_build_report_aggregates():
    scored = [
        _sc("A", "highest_board", "continued", 1.0),
        _sc("B", "highest_board", "nuked", -1.0),
        _sc("C", "w2s", "continued", 1.0),
        _sc("D", "w2s", "faded", 0.0),
    ]
    rep = build_report(scored, n_decisions=4, n_no_trade=1)
    assert rep.n_candidates == 4 and rep.n_decisions == 4 and rep.n_no_trade == 1
    assert rep.horizon == 1               # 默认
    assert rep.hit_rate == 0.5            # 2 continued / 4
    assert rep.nuke_rate == 0.25          # 1 nuked / 4
    assert abs(rep.mean_score - (1 - 1 + 1 + 0) / 4) < 1e-9   # 0.25
    hb = rep.by_pattern["highest_board"]
    assert hb.n == 2 and hb.hit_rate == 0.5 and hb.mean_score == 0.0
    assert hb.nuke_rate == 0.5                # highest_board: 1 nuked of 2
    w2s = rep.by_pattern["w2s"]
    assert w2s.n == 2 and w2s.hit_rate == 0.5 and w2s.mean_score == 0.5
    assert w2s.nuke_rate == 0.0


def test_build_report_empty():
    rep = build_report([], n_decisions=3, n_no_trade=3)
    assert rep.n_candidates == 0 and rep.hit_rate == 0.0 and rep.mean_score == 0.0
    assert rep.by_pattern == {}


def test_build_report_horizon_passthrough():
    rep = build_report([], n_decisions=3, n_no_trade=3, horizon=2)
    assert rep.horizon == 2


def test_build_report_all_nuked():
    scored = [_sc("A", "p", "nuked", -1.0), _sc("B", "p", "nuked", -1.0)]
    rep = build_report(scored, n_decisions=2, n_no_trade=0)
    assert rep.hit_rate == 0.0 and rep.nuke_rate == 1.0 and rep.mean_score == -1.0


# ── C2:advantage / mean_excess ───────────────────────────────────────────────

def _sc_base(code, oc, score, base):
    return ScoredCandidate(decision_date=date(2024, 6, 27), code=code, pattern="p",
                           outcome=oc, score=score, day_baseline=base)


def test_advantage_backfilled_from_score_and_baseline():
    # 省略 advantage:有基线 → score−day_baseline;无基线 → 回退=score
    assert _sc_base("A", "continued", 1.0, 0.5).advantage == 0.5
    assert _sc_base("B", "nuked", -1.0, 0.5).advantage == -1.5
    assert _sc("C", "p", "faded", 0.25).advantage == 0.25          # baseline None → 回退


def test_old_json_scored_candidate_deserializes_without_new_fields():
    # 旧 JSON(无 advantage/day_baseline)反序列化兼容:advantage 回退=score
    old = {"decision_date": "2024-06-27", "code": "A", "pattern": "p",
           "outcome": "continued", "score": 1.0}
    sc = ScoredCandidate.model_validate(old)
    assert sc.day_baseline is None and sc.advantage == 1.0


def test_build_report_mean_excess():
    scored = [_sc_base("A", "continued", 1.0, 0.5),    # adv +0.5
              _sc_base("B", "faded", 0.0, 0.5),        # adv −0.5
              _sc("C", "p", "continued", 1.0)]         # 无基线 → adv 回退 +1.0
    rep = build_report(scored, n_decisions=3, n_no_trade=0)
    assert abs(rep.mean_excess - (0.5 - 0.5 + 1.0) / 3) < 1e-9
    assert abs(rep.mean_score - (1.0 + 0.0 + 1.0) / 3) < 1e-9      # 原始口径不动


def test_build_report_empty_mean_excess_zero():
    rep = build_report([], n_decisions=1, n_no_trade=1)
    assert rep.mean_excess == 0.0
