from datetime import date, datetime
from alpha.harness.skill import Skill
from alpha.harness.doctrine import Doctrine
from alpha.harness.registry import SkillRegistry, MemoryStore
from alpha.harness.state import HarnessState
from alpha.state.market import MarketState
from alpha.universe.stock import StockSnapshot
from alpha.universe.universe import CandidateUniverse
from alpha.agent.prompt import build_system_prompt, build_user_prompt, PROMPT_FINGERPRINT


def _h():
    skills = SkillRegistry.from_skills([
        Skill(skill_id="gap_and_go", name="Gap and Go", type="pattern", family="runner",
              phases=["trend"], trigger="gap + hold", entry="ORB reclaim", exit_stop="lose VWAP",
              status="active"),
    ])
    doctrine = Doctrine.from_seed_list([
        {"section": "core", "regime": "all", "immutable": True, "guidance": "respect the stop"},
    ])
    return HarnessState(doctrine=doctrine, skills=skills, memory=MemoryStore.from_lessons([]))


def test_system_prompt_contains_skill_doctrine_contract():
    sp = build_system_prompt(_h(), phase_prior="trend")
    assert "gap_and_go" in sp and "respect the stop" in sp
    assert "washout" in sp and "flush" in sp          # the 6-state cycle vocabulary
    assert '"candidates"' in sp and '"symbol"' in sp  # the JSON output contract
    assert isinstance(PROMPT_FINGERPRINT, str) and PROMPT_FINGERPRINT


def test_user_prompt_renders_state_and_universe():
    state = MarketState(date=date(2026, 6, 12), gainer_count=2, gap_up_count=1, loser_count=1,
                        failed_breakout_count=0, max_runner_tier=2, echelon=[], breadth_raw=1.0,
                        sentiment_norm=0.6, as_of=datetime(2026, 6, 12, 16, 0))
    uni = CandidateUniverse.from_stocks([
        StockSnapshot(symbol="RUN", name="Runner", status="gainer", pct_change=30.0, rvol=4.0),
    ])
    up = build_user_prompt(state, uni)
    assert "2026-06-12" in up and "RUN" in up and "gainer" in up


def test_user_prompt_renders_short_interest_when_present():
    state = MarketState(date=date(2026, 6, 12), gainer_count=1, gap_up_count=0, loser_count=0,
                        failed_breakout_count=0, max_runner_tier=1, echelon=[], breadth_raw=1.0,
                        as_of=datetime(2026, 6, 12, 16, 0))
    uni = CandidateUniverse.from_stocks([
        StockSnapshot(symbol="SQZ", name="Sq", status="gainer", pct_change=20.0, rvol=4.0,
                      short_interest=30.0, days_to_cover=6.0),
        StockSnapshot(symbol="PLAIN", name="Pl", status="gainer", pct_change=12.0, rvol=2.0),
    ])
    up = build_user_prompt(state, uni)
    assert "si=30%" in up and "dtc=6.0" in up           # high-SI name shows the suffix
    plain_line = [ln for ln in up.splitlines() if ln.startswith("- PLAIN")][0]
    assert "si=" not in plain_line                       # no short interest -> no suffix (no noise)


from alpha.agent.prompt import available_data_signals


def _h_squeeze():
    skills = SkillRegistry.from_skills([
        Skill(skill_id="gap_and_go", name="Gap and Go", type="pattern", family="runner",
              phases=["trend"], trigger="t", entry="e", exit_stop="x", status="active"),
        Skill(skill_id="short_squeeze", name="Short Squeeze", type="pattern", family="meme",
              phases=["ignition", "trend"], trigger="high SI", entry="e", exit_stop="x",
              depends_on=["short_interest", "days_to_cover"], status="incubating"),
        Skill(skill_id="gamma_squeeze", name="Gamma Squeeze", type="pattern", family="meme",
              phases=["ignition", "trend"], trigger="gamma", entry="e", exit_stop="x",
              depends_on=["options_flow"], status="incubating"),
    ])
    doctrine = Doctrine.from_seed_list([{"section": "core", "regime": "all", "immutable": True,
                                         "guidance": "respect the stop"}])
    return HarnessState(doctrine=doctrine, skills=skills, memory=MemoryStore.from_lessons([]))


def test_available_data_signals_collects_non_none_fields():
    uni = CandidateUniverse.from_stocks([
        StockSnapshot(symbol="SQZ", name="Sq", status="gainer", short_interest=30.0, days_to_cover=6.0),
        StockSnapshot(symbol="PLAIN", name="Pl", status="gainer"),
    ])
    sigs = available_data_signals(uni)
    assert "short_interest" in sigs and "days_to_cover" in sigs and "options_flow" not in sigs
    assert "symbol" not in sigs and "status" not in sigs        # structural fields excluded (optional-only)


def test_depends_on_enforced_hides_squeeze_without_data():
    sp = build_system_prompt(_h_squeeze(), phase_prior="trend", injection="full",
                             available_signals=frozenset({"rvol"}))
    assert "short_squeeze" not in sp and "gamma_squeeze" not in sp      # depends_on unsatisfied -> hidden
    assert "gap_and_go" in sp                                           # no depends_on -> always shown


def test_depends_on_enforced_shows_squeeze_with_data():
    sigs = frozenset({"short_interest", "days_to_cover"})
    sp = build_system_prompt(_h_squeeze(), phase_prior="trend", injection="full", available_signals=sigs)
    assert "short_squeeze" in sp                                        # short-interest data live -> surfaced
    assert "gamma_squeeze" not in sp                                    # options_flow still absent -> hidden


def test_depends_on_default_none_is_backcompat():
    sp = build_system_prompt(_h_squeeze(), phase_prior="trend", injection="full")   # no available_signals
    assert "short_squeeze" in sp and "gamma_squeeze" in sp              # None = no enforcement (unchanged)


def test_depends_on_enforced_on_retrieval_path():
    # the filter applies after select_for_prompt too (retrieval injection), not just the 'full' path
    sigs = frozenset({"short_interest", "days_to_cover"})
    sp = build_system_prompt(_h_squeeze(), phase_prior="trend", injection="retrieval", available_signals=sigs)
    assert "short_squeeze" in sp and "gamma_squeeze" not in sp
    sp0 = build_system_prompt(_h_squeeze(), phase_prior="trend", injection="retrieval",
                              available_signals=frozenset())
    assert "short_squeeze" not in sp0                                   # no data signal -> hidden in retrieval too


def test_user_prompt_renders_free_float_when_present():
    state = MarketState(date=date(2026, 6, 12), gainer_count=1, gap_up_count=0, loser_count=0,
                        failed_breakout_count=0, max_runner_tier=1, echelon=[], breadth_raw=1.0,
                        as_of=datetime(2026, 6, 12, 16, 0))
    uni = CandidateUniverse.from_stocks([
        StockSnapshot(symbol="LO", name="Lo", status="gainer", pct_change=20.0, rvol=4.0, free_float=4.0),
        StockSnapshot(symbol="PLAIN", name="Pl", status="gainer", pct_change=12.0, rvol=2.0),
    ])
    up = build_user_prompt(state, uni)
    assert "float=4M" in up                              # low-float name shows the suffix
    plain_line = [ln for ln in up.splitlines() if ln.startswith("- PLAIN")][0]
    assert "float=" not in plain_line                    # no free_float -> no suffix (no noise)


def test_user_prompt_renders_options_flow_and_social_when_present():
    state = MarketState(date=date(2026, 6, 12), gainer_count=1, gap_up_count=0, loser_count=0,
                        failed_breakout_count=0, max_runner_tier=1, echelon=[], breadth_raw=1.0,
                        as_of=datetime(2026, 6, 12, 16, 0))
    uni = CandidateUniverse.from_stocks([
        StockSnapshot(symbol="MEME", name="Me", status="gainer", pct_change=20.0, rvol=4.0,
                      options_flow=3.5, social_sentiment=0.8),
        StockSnapshot(symbol="PLAIN", name="Pl", status="gainer", pct_change=12.0, rvol=2.0),
    ])
    up = build_user_prompt(state, uni)
    assert "optflow=3.5" in up and "social=0.8" in up      # meme name shows the suffixes
    plain_line = [ln for ln in up.splitlines() if ln.startswith("- PLAIN")][0]
    assert "optflow=" not in plain_line and "social=" not in plain_line   # no data -> no suffix (no noise)
