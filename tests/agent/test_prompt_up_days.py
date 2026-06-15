"""US-3a lock: build_user_prompt renders a real up_days from the now-populated universe (was '?')."""
from datetime import date, datetime
from alpha.universe.universe import build_universe
from alpha.state.builder import build_market_state
from alpha.agent.prompt import build_user_prompt


def test_user_prompt_renders_runner_up_days(fake_source):
    day = date(2026, 6, 12)
    uni = build_universe(fake_source, day, rvol_window=2)         # RUN -> 2 trailing up-days
    state = build_market_state(uni, day, as_of=datetime(2026, 6, 12, 16, 0))
    text = build_user_prompt(state, uni)
    # FLOP's -8.3% day is inside the +/-10% band and its gap is 0%, so the only universe line is RUN
    # -> "no up_days=?" is a real assertion about RUN's rendered tier, not a vacuous empty-universe pass.
    assert "up_days=2" in text and "up_days=?" not in text
