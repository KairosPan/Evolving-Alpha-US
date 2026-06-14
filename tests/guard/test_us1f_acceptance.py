"""US-1f acceptance: sizing nets same-narrative picks to one risk-gated bet, and the guard layer
vetoes / stops / breaks as the immutable-core rules require — over a small end-to-end scenario."""
from alpha.regime.classifier import RegimeRead
from alpha.sizing.correlation import Pick
from alpha.sizing.portfolio import plan_portfolio
from alpha.sizing.position import SizingConfig
from alpha.guard.veto import CandidateContext, veto
from alpha.guard.stops import Position, stop_signals
from alpha.guard.breaker import Breaker, BreakerConfig


def test_sizing_and_guard_end_to_end():
    regime = RegimeRead(phase="trend", confidence=0.7, frontside=True, risk_gate=0.6)
    picks = [Pick("AI1", "ai", 0.9), Pick("AI2", "ai", 0.8), Pick("NUKE", "nuclear", 0.7)]
    plan = plan_portfolio(picks, risk_gate=regime.risk_gate, config=SizingConfig())
    # two AI names net to one bet; nuclear is a second bet -> two correlated/independent bets
    assert plan.correlated_groups == [["AI1", "AI2"]]
    assert plan.total_exposure <= plan.total_exposure_budget

    # guard clears a clean name but vetoes one with a pending reverse split
    assert veto(CandidateContext("AI1", regime)).vetoed is False
    assert veto(CandidateContext("AI2", regime, reverse_split_pending=True)).vetoed is True

    # a position that lost its stop on a backside flip gets form + regime stops
    flush = RegimeRead(phase="flush", confidence=0.6, frontside=False, risk_gate=0.15)
    sigs = stop_signals(Position("AI1", 10.0, 8.0, 9.0, 2, "ai"), flush, max_hold_days=5)
    assert {s.kind for s in sigs} == {"form", "regime"}

    # consecutive losses trip the portfolio breaker; a single name's drawdown halts adds to it
    b = Breaker(BreakerConfig(max_consecutive_losses=2, max_single_name_loss=0.15))
    b.record_day_pnl(-0.01)
    b.record_day_pnl(-0.01)
    assert b.check()[0] is True
    b.record_name_pnl("AI2", -0.20)
    assert b.check_name("AI2")[0] is True
