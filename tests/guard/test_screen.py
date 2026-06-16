from datetime import date, datetime
import pandas as pd
import pytest
from alpha.data.source import FakeSource
from alpha.data.firewall import AsOfGuard
from alpha.data.source import GuardedSource
from alpha.guard.screen import ssr_active


def _src(sym_closes):
    """sym_closes: {symbol: [close_6/10, close_6/11, close_6/12]}."""
    cal = [date(2026, 6, 10), date(2026, 6, 11), date(2026, 6, 12)]
    bars = {s: pd.DataFrame({"date": cal, "open": c, "high": c, "low": c, "close": c,
                             "volume": [1, 1, 1]}) for s, c in sym_closes.items()}
    return FakeSource(calendar=cal, bars=bars, snapshots={})


def test_ssr_active_when_prior_day_dropped_10pct():
    src = _src({"KNIFE": [10.0, 8.8, 9.0]})            # 6/11 close 8.8 = -12% vs 6/10 -> SSR on 6/12
    assert ssr_active(src, "KNIFE", date(2026, 6, 12)) is True


def test_ssr_active_at_exact_10pct_boundary():
    src = _src({"EDGE": [10.0, 9.0, 9.0]})             # exactly -10% prior day -> Reg SHO triggers (<=)
    assert ssr_active(src, "EDGE", date(2026, 6, 12)) is True


def test_ssr_inactive_when_prior_day_drop_below_threshold():
    src = _src({"MILD": [10.0, 9.2, 9.5]})             # -8% prior day -> no SSR
    assert ssr_active(src, "MILD", date(2026, 6, 12)) is False


def test_ssr_inactive_when_bars_missing():
    src = _src({"OTHER": [10.0, 9.0, 8.0]})
    assert ssr_active(src, "ABSENT", date(2026, 6, 12)) is False    # no bars -> never fabricate


def test_ssr_inactive_on_first_day():
    src = _src({"KNIFE": [10.0, 8.8, 9.0]})
    assert ssr_active(src, "KNIFE", date(2026, 6, 10)) is False     # no prior trading day


def test_ssr_is_guard_safe():
    src = _src({"KNIFE": [10.0, 8.8, 9.0]})
    gs = GuardedSource(src, AsOfGuard(date(2026, 6, 12)))           # reads only prior-day bars (< as_of)
    assert ssr_active(gs, "KNIFE", date(2026, 6, 12)) is True


from alpha.state.market import MarketState
from alpha.eval.decision import Candidate, DecisionPackage
from alpha.universe.universe import CandidateUniverse
from alpha.guard.screen import screen_decision, GuardedPolicy


def _state(d=date(2026, 6, 12), *, sn=0.7, ft=0.5, gainers=2, losers=0, fb=0):
    return MarketState(date=d, gainer_count=gainers, gap_up_count=0, loser_count=losers,
                       failed_breakout_count=fb, max_runner_tier=1, echelon=[], breadth_raw=1.0,
                       sentiment_norm=sn, follow_through_rate=ft,
                       as_of=datetime(d.year, d.month, d.day, 16, 0))


def _pkg(*symbols):
    return DecisionPackage(date=date(2026, 6, 12),
                           candidates=[Candidate(symbol=s, pattern="gap_and_go") for s in symbols])


def test_screen_keeps_clean_candidate_and_populates_regime():
    src = _src({"CLEAN": [10.0, 11.0, 12.0]})                       # rising -> no SSR
    out = screen_decision(_pkg("CLEAN"), source=src, state=_state())   # sn=0.7, ft=0.5 -> trend/frontside
    assert [c.symbol for c in out.candidates] == ["CLEAN"]
    assert out.regime is not None and out.regime.frontside is True
    assert out.key_risks == []


def test_screen_drops_ssr_candidate_and_records_reason():
    src = _src({"KNIFE": [10.0, 8.8, 9.0]})                         # prior-day -12% -> SSR
    out = screen_decision(_pkg("KNIFE"), source=src, state=_state())
    assert out.candidates == []
    assert any("KNIFE" in r and "SSR" in r for r in out.key_risks)
    assert out.no_trade_reason                                       # all vetoed -> no-trade reason set


def test_screen_drops_reverse_split_candidate(fake_source):
    # conftest fake_source: RUN has a pending reverse split (announced 6/9, ex 6/20); RUN rising -> no SSR
    out = screen_decision(_pkg("RUN"), source=fake_source, state=_state())
    assert out.candidates == [] and any("reverse split" in r for r in out.key_risks)


def test_screen_drops_all_in_risk_off_regime():
    src = _src({"CLEAN": [10.0, 11.0, 12.0]})
    out = screen_decision(_pkg("CLEAN"), source=src, state=_state(sn=0.1))   # proxy 0.1 -> washout, risk_gate 0.1
    assert out.candidates == [] and any("risk-off" in r for r in out.key_risks)


def test_screen_is_frozen_safe():
    src = _src({"CLEAN": [10.0, 11.0, 12.0]})
    pkg = _pkg("CLEAN", "CLEAN2")
    out = screen_decision(pkg, source=src, state=_state())
    assert len(pkg.candidates) == 2                                 # original untouched (frozen rebuild)
    assert out is not pkg


def test_guarded_policy_screens_inner_decision():
    src = _src({"KNIFE": [10.0, 8.8, 9.0]})
    class _Stub:
        def decide(self, state, universe):
            return _pkg("KNIFE")
    gp = GuardedPolicy(_Stub(), src)
    out = gp.decide(_state(), CandidateUniverse.from_stocks([]))
    assert out.candidates == [] and any("SSR" in r for r in out.key_risks)


def test_screen_drops_dilution_candidate_and_records_reason(fake_source):
    # fake_source RUN is a rising gainer (no SSR); attach an announced ATM filing -> dilution veto fires.
    # (pd, date, FakeSource are already imported at module level.)
    snap = fake_source.daily_snapshot(date(2026, 6, 12))
    src = FakeSource(calendar=fake_source.trading_calendar(), bars={},
                     snapshots={date(2026, 6, 12): snap},
                     corp_actions=pd.DataFrame({"symbol": ["RUN"], "announce_date": [date(2026, 6, 9)],
                                                "ex_date": [date(2026, 6, 20)], "kind": ["atm"], "ratio": [None]}))
    out = screen_decision(_pkg("RUN"), source=src, state=_state())
    assert out.candidates == [] and any("RUN" in r and "dilution" in r for r in out.key_risks)


def test_halt_then_dump_proxy():
    from alpha.guard.screen import halt_then_dump_proxy
    assert halt_then_dump_proxy({"prev_close": 10.0, "high": 13.0, "close": 9.5}) is True    # +30% spike, closed red
    assert halt_then_dump_proxy({"prev_close": 10.0, "high": 13.0, "close": 12.0}) is False  # spiked but held green
    assert halt_then_dump_proxy({"prev_close": 10.0, "high": 10.5, "close": 9.0}) is False   # no >=15% intraday spike
    assert halt_then_dump_proxy(None) is False                                               # missing -> never fabricate
    assert halt_then_dump_proxy({"prev_close": None, "high": 13.0, "close": 9.0}) is False   # missing prev_close
    assert halt_then_dump_proxy({"prev_close": float("nan"), "high": 13.0, "close": 9.0}) is False  # NaN -> missing
    assert halt_then_dump_proxy({"prev_close": 0.0, "high": 1.0, "close": 0.0}) is False     # prev<=0 guard
    assert halt_then_dump_proxy({}) is False                                                 # missing keys (.get -> None)


def test_screen_drops_halt_then_dump_candidate_and_records_reason():
    # SPIKE spiked >=15% intraday (high 13 vs prev 10) then round-tripped to close red (9.5) -> halt-then-dump.
    cal = [date(2026, 6, 11), date(2026, 6, 12)]
    snap = pd.DataFrame({"symbol": ["SPIKE"], "name": ["Spiker"], "open": [10.0], "high": [13.0],
                         "low": [9.0], "close": [9.5], "volume": [9], "prev_close": [10.0]})
    src = FakeSource(calendar=cal, bars={}, snapshots={date(2026, 6, 12): snap})
    out = screen_decision(_pkg("SPIKE"), source=src, state=_state())
    assert out.candidates == [] and any("SPIKE" in r and "halt-then-dump" in r for r in out.key_risks)
