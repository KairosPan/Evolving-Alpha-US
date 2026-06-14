from alpha.guard.breaker import Breaker, BreakerConfig


def test_no_trip_when_healthy():
    b = Breaker(BreakerConfig())
    b.record_day_pnl(-0.01)                  # small loss
    tripped, reasons = b.check()
    assert tripped is False and reasons == []


def test_single_day_loss_trips():
    b = Breaker(BreakerConfig(max_single_day_loss=0.05))
    b.record_day_pnl(-0.08)
    tripped, reasons = b.check()
    assert tripped is True and any("single-day" in r for r in reasons)


def test_consecutive_losses_trip():
    b = Breaker(BreakerConfig(max_consecutive_losses=3))
    for _ in range(3):
        b.record_day_pnl(-0.01)
    tripped, reasons = b.check()
    assert tripped is True and any("consecutive" in r for r in reasons)


def test_a_win_resets_consecutive_losses():
    b = Breaker(BreakerConfig(max_consecutive_losses=3))
    b.record_day_pnl(-0.01)
    b.record_day_pnl(-0.01)
    b.record_day_pnl(0.02)                   # win resets the streak
    b.record_day_pnl(-0.01)
    assert b.check()[0] is False


def test_mwcb_halts_new_entries():
    b = Breaker(BreakerConfig())
    b.set_mwcb(True)
    tripped, reasons = b.check()
    assert tripped is True and any("MWCB" in r for r in reasons)


def test_single_name_loss_trips():
    b = Breaker(BreakerConfig(max_single_name_loss=0.15))
    b.record_name_pnl("RUN", -0.10)
    b.record_name_pnl("RUN", -0.08)              # cumulative -18% <= -15%
    assert b.check_name("RUN")[0] is True
    assert b.check_name("OTHER")[0] is False     # untouched name is fine


def test_winning_name_not_tripped():
    b = Breaker(BreakerConfig(max_single_name_loss=0.15))
    b.record_name_pnl("WIN", -0.10)
    b.record_name_pnl("WIN", 0.30)               # net +20%
    assert b.check_name("WIN")[0] is False
