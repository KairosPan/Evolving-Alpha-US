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
