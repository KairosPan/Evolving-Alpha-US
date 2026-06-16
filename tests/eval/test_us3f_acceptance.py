"""US-3f acceptance: options-flow data activates the dormant gamma_squeeze seed (the last incubating offense
skill). On a universe carrying options_flow, build_universe fills the field, the agent's user prompt shows
optflow=, and the system prompt SURFACES gamma_squeeze (its depends_on is now satisfied) while short_squeeze
stays hidden (no short-interest data). On a universe WITHOUT options_flow, gamma_squeeze is hidden. This
closes the US-3 enrichment arc: every incubating offense seed is now data-backed (activation via the generic
depends_on machinery; promotion to active stays evidence-gated)."""
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


def _source(*, with_options: bool):
    cal = [date(2026, 6, 11), CUR]
    cols = {"symbol": ["MEME"], "name": ["Memer"], "open": [10.0], "high": [13.0], "low": [10.0],
            "close": [12.0], "volume": [5], "prev_close": [10.0]}                      # +20% gainer
    if with_options:
        cols |= {"options_flow": [4.0], "social_sentiment": [0.9]}
    return FakeSource(calendar=cal, bars={}, snapshots={CUR: pd.DataFrame(cols)})


def _sys_prompt_for(src):
    uni = build_universe(src, CUR, gainer_pct=10.0, gap_pct=5.0, rvol_window=2)
    return build_system_prompt(load_seeds(SEEDS), phase_prior="ignition",
                               available_signals=available_data_signals(uni)), uni


def test_options_flow_activates_gamma_squeeze_end_to_end():
    sp, uni = _sys_prompt_for(_source(with_options=True))
    assert uni.get("MEME").options_flow == 4.0 and uni.get("MEME").social_sentiment == 0.9
    assert "gamma_squeeze" in sp                          # depends_on=[options_flow] satisfied -> surfaced
    assert "short_squeeze" not in sp                      # short-interest absent -> still hidden
    state = build_market_state(uni, CUR, as_of=datetime(2026, 6, 12, 16, 0))
    assert "optflow=4.0" in build_user_prompt(state, uni)   # the agent sees the gamma fuel


def test_without_options_flow_gamma_squeeze_stays_dormant():
    sp, uni = _sys_prompt_for(_source(with_options=False))
    assert uni.get("MEME").options_flow is None
    assert "gamma_squeeze" not in sp                      # no data -> depends_on unsatisfied -> hidden
