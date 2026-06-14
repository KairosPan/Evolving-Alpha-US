from datetime import date
from alpha.eval.metrics import ScoredCandidate, EvalReport, build_report


def _sc(symbol, outcome, score, base=None):
    return ScoredCandidate(decision_date=date(2026, 6, 12), symbol=symbol, pattern="p",
                           outcome=outcome, score=score, day_baseline=base)


def test_advantage_backfill():
    assert _sc("A", "continued", 1.0, base=0.2).advantage == 0.8
    assert _sc("A", "continued", 1.0).advantage == 1.0        # no baseline -> falls back to score


def test_build_report_aggregates():
    scored = [_sc("A", "continued", 0.30, 0.10), _sc("B", "nuked", -0.20, 0.10),
              _sc("C", "faded", 0.0, 0.10)]
    rep = build_report(scored, n_decisions=5, n_no_trade=2, horizon=2)
    assert rep.n_candidates == 3 and rep.n_decisions == 5 and rep.n_no_trade == 2 and rep.horizon == 2
    assert abs(rep.hit_rate - 1/3) < 1e-9 and abs(rep.nuke_rate - 1/3) < 1e-9
    assert abs(rep.mean_score - (0.30 - 0.20 + 0.0)/3) < 1e-9
    assert abs(rep.mean_excess - ((0.20) + (-0.30) + (-0.10))/3) < 1e-9
    assert "p" in rep.by_pattern and rep.by_pattern["p"].n == 3


def test_empty_report():
    rep = build_report([], n_decisions=3, n_no_trade=3, horizon=2)
    assert rep.n_candidates == 0 and rep.hit_rate == 0.0 and rep.mean_score == 0.0
