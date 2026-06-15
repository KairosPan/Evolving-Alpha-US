"""US-3c acceptance: short-interest data activates the dormant short_squeeze seed. On a universe carrying
short_interest/days_to_cover, build_universe fills the fields, the agent's user prompt shows si=/dtc=, and
the system prompt SURFACES short_squeeze (its depends_on is now satisfied) while gamma_squeeze stays hidden
(options_flow absent). On a universe WITHOUT short interest, short_squeeze is hidden. This is the headline
US-3c guarantee: depends_on is enforced and short_squeeze is live exactly when its data is."""
from datetime import date, datetime
from pathlib import Path
import pandas as pd
from alpha.data.source import FakeSource
from alpha.harness.loader import load_seeds
from alpha.universe.universe import build_universe
from alpha.state.builder import build_market_state
from alpha.agent.prompt import build_system_prompt, build_user_prompt, available_data_signals

SEEDS = Path(__file__).resolve().parents[2] / "seeds"
CUR = date(2026, 6, 12)


def _source(*, with_si: bool):
    cal = [date(2026, 6, 11), CUR]
    cols = {"symbol": ["SQZ"], "name": ["Squeezer"], "open": [10.0], "high": [13.0], "low": [10.0],
            "close": [12.0], "volume": [5], "prev_close": [10.0]}                      # +20% gainer
    if with_si:
        cols |= {"short_interest": [35.0], "days_to_cover": [7.0]}
    return FakeSource(calendar=cal, bars={}, snapshots={CUR: pd.DataFrame(cols)})


def _sys_prompt_for(src):
    uni = build_universe(src, CUR, gainer_pct=10.0, gap_pct=5.0, rvol_window=2)
    h = load_seeds(SEEDS)
    return build_system_prompt(h, phase_prior="ignition", available_signals=available_data_signals(uni)), uni


def test_short_interest_activates_short_squeeze_end_to_end():
    sp, uni = _sys_prompt_for(_source(with_si=True))
    assert uni.get("SQZ").short_interest == 35.0 and uni.get("SQZ").days_to_cover == 7.0
    assert "short_squeeze" in sp                                    # depends_on satisfied -> surfaced
    assert "gamma_squeeze" not in sp                                # options_flow absent -> still hidden
    state = build_market_state(uni, CUR, as_of=datetime(2026, 6, 12, 16, 0))
    assert "si=35%" in build_user_prompt(state, uni)               # the agent sees the squeeze fuel


def test_without_short_interest_short_squeeze_stays_dormant():
    sp, uni = _sys_prompt_for(_source(with_si=False))
    assert uni.get("SQZ").short_interest is None
    assert "short_squeeze" not in sp                                # no data -> depends_on unsatisfied -> hidden
