"""P0.5 — pack-conditional prompt isomorphism (alpha/agent/prompt.py).

The growth pack rewrites the persona (sector-growth, thesis-first), reorders the injection (doctrine
prose before the quantitative skill panel; red-lines as tail constraints), and swaps the output-
contract regime enum to the growth market-clock tokens. The momo pack stays byte-identical.
"""
from alpha.agent.prompt import build_system_prompt
from alpha.harness.doctrine import Doctrine
from alpha.harness.growth_regime import normalize_growth_phases
from alpha.harness.loader import load_pack
from alpha.harness.memory import Lesson
from alpha.harness.registry import MemoryStore, SkillRegistry
from alpha.harness.skill import Skill
from alpha.harness.state import HarnessState


def _growth_h():
    """A tiny growth H (scale-typed tokens via the growth normalizer)."""
    skills = SkillRegistry.from_skills([
        Skill.from_seed({"skill_id": "breakout_entry", "name": "Base Breakout", "type": "pattern",
                         "phases": ["stock:advance"], "trigger": "pivot breaks on volume",
                         "entry": "buy the pivot", "exit_stop": "hard stop", "status": "active"},
                        normalize=normalize_growth_phases),
    ])
    doctrine = Doctrine.from_seed_list([
        {"section": "thesis_first", "regime": "all", "immutable": True,
         "guidance": "Every pick's primary reason must cite a thesis card, never an indicator."},
        {"section": "market_three_states", "phases": ["market:confirmed_uptrend"], "immutable": False,
         "guidance": "The market answers one question: is attack allowed now."},
    ], normalize=normalize_growth_phases)
    memory = MemoryStore.from_lessons([
        Lesson.from_seed({"lesson_id": "L-001", "outcome": "loss", "named_analog": "Peloton",
                          "lesson": "A theme that stops delivering earnings is over.",
                          "phases": ["theme:exhaustion"]}, normalize=normalize_growth_phases),
    ])
    return HarnessState(doctrine=doctrine, skills=skills, memory=memory, vocabulary="growth")


def _momo_h():
    skills = SkillRegistry.from_skills([
        Skill(skill_id="gap_and_go", name="Gap and Go", type="pattern", family="runner",
              phases=["trend"], trigger="gap + hold", entry="ORB reclaim", exit_stop="lose VWAP",
              status="active"),
    ])
    doctrine = Doctrine.from_seed_list([
        {"section": "core", "regime": "all", "immutable": True, "guidance": "respect the stop"},
    ])
    return HarnessState(doctrine=doctrine, skills=skills, memory=MemoryStore.from_lessons([]))


# ── growth persona + clock + output contract ──────────────────────────────────

def test_growth_persona_replaces_momo_persona():
    sp = build_system_prompt(_growth_h(), pack="growth", injection="full")
    assert "sector-growth" in sp                      # growth persona
    assert "speculative-momentum" not in sp           # momo persona gone
    assert "thesis" in sp.lower()                      # thesis-first framing


def test_growth_clock_line_uses_market_tokens_not_canonical_phases():
    sp = build_system_prompt(_growth_h(), pack="growth", injection="full")
    assert "market:confirmed_uptrend" in sp and "market:correction" in sp
    assert "theme:emerging" in sp and "stock:base" in sp      # all three clocks named
    assert "washout" not in sp and "flush" not in sp          # momo CANONICAL_PHASES absent


def test_growth_output_contract_accepts_growth_market_tokens():
    sp = build_system_prompt(_growth_h(), pack="growth", injection="full")
    contract = sp.rsplit("\n", 1)[-1]                          # the tail output-contract line
    assert '"regime_read"' in contract and "market:confirmed_uptrend" in contract
    assert "one of the 6 phases" not in sp                     # momo enum wording gone


def test_growth_doctrine_prose_precedes_skill_panel():
    """Isomorphism: thesis/cycle doctrine prose appears before the SKILLS (quantitative) panel."""
    sp = build_system_prompt(_growth_h(), pack="growth", injection="full")
    assert "market answers one question" in sp                 # a mutable-doctrine prose line
    assert sp.index("market answers one question") < sp.index("SKILLS (K)")


def test_growth_red_lines_are_tail_constraints_not_leading():
    """Red-lines (guard/limit state) inject AFTER the skill panel as tail constraints, not at the top."""
    sp = build_system_prompt(_growth_h(), pack="growth", injection="full")
    assert "HARD CONSTRAINTS" in sp
    assert "[RED-LINE] thesis_first" in sp
    assert sp.index("SKILLS (K)") < sp.index("[RED-LINE] thesis_first")   # red-line is a tail constraint
    assert sp.index("[RED-LINE] thesis_first") > sp.index("market answers one question")


def test_growth_branch_binds_to_h_vocabulary(monkeypatch):
    """pack=None resolves h.vocabulary — the pack rides WITH the harness, not the process env. A growth
    H renders the growth persona even when the env says momo (the reverse of the chimera-prompt bug)."""
    monkeypatch.setenv("ALPHA_SEED_PACK", "momo")             # env says momo...
    sp = build_system_prompt(_growth_h(), injection="full")   # ...but the H is growth -> growth wins
    assert "sector-growth" in sp


# ── momo byte-identity (regression pin) ───────────────────────────────────────

def test_momo_prompt_byte_identical_default_vs_explicit():
    h = _momo_h()
    assert build_system_prompt(h, phase_prior="trend") == \
        build_system_prompt(h, phase_prior="trend", pack="momo")


def test_momo_prompt_unchanged_shape():
    """The momo branch keeps its persona, CANONICAL_PHASES cycle line, leading red-lines, momo contract."""
    sp = build_system_prompt(_momo_h(), phase_prior="trend", pack="momo")
    assert "speculative-momentum" in sp and "sector-growth" not in sp
    assert "washout" in sp and "flush" in sp
    assert "one of the 6 phases" in sp                         # momo output contract enum
    assert "HARD CONSTRAINTS" not in sp                        # tail-constraint block is growth-only
    # momo red-lines lead (appear before the skill panel), unchanged
    assert sp.index("[RED-LINE] core") < sp.index("SKILLS (K)")


# ── momo full-literal golden pin (non-self-referential byte-identity) ──────────────────────────

def _momo_golden_h():
    """A minimal, fully-fixed momo H (one red-line, one mutable, one skill, one lesson) — the fixture
    the golden literal below is frozen against. No stats, no optional data -> deterministic assembly."""
    skills = SkillRegistry.from_skills([
        Skill(skill_id="gap_and_go", name="Gap and Go", type="pattern", family="runner",
              phases=["trend"], trigger="gap + hold", entry="ORB reclaim", exit_stop="lose VWAP",
              status="active"),
    ])
    doctrine = Doctrine.from_seed_list([
        {"section": "no_chase", "regime": "all", "immutable": True, "guidance": "respect the stop"},
        {"section": "add_on_reclaim", "phases": ["trend"], "immutable": False,
         "guidance": "add on the first reclaim"},
    ])
    memory = MemoryStore.from_lessons([
        Lesson(lesson_id="L1", phases=["trend"], outcome="win", named_analog="GME",
               lesson="ride the leader"),
    ])
    return HarnessState(doctrine=doctrine, skills=skills, memory=memory)


# The EXACT current momo system prompt for _momo_golden_h(). Frozen literal (not a comparison against
# a re-render), so it fails loudly on ANY drift in the momo persona / cycle line / doctrine ordering /
# skill or memory formatting / output contract — the byte-identity guarantee made non-self-referential.
# NOTE: the skill line ends with a single trailing space after "taboo: " (no taboos); keep it.
_MOMO_GOLDEN = "\n".join([
    "You are a US speculative-momentum trading co-pilot. Read the day's state and the candidate "
    "universe and propose ranked candidates with a plan. A human confirms; you never place orders.",
    "",
    "MARKET REGIME CYCLE (per-day phase): washout -> recovery -> ignition -> trend -> distribution "
    "-> flush (frontside/backside is a per-line momentum-direction read — early/healthy vs "
    "late/topping — not a fixed function of phase).",
    "",
    "DOCTRINE (immutable red-lines are absolute):",
    "- [RED-LINE] no_chase: respect the stop",
    "- add_on_reclaim [trend]: add on the first reclaim",
    "",
    "SKILLS (K):",
    "- Gap and Go (gap_and_go) [pattern, runner] phases[trend] trigger: gap + hold | entry: ORB "
    "reclaim | exit: lose VWAP | taboo: ",
    "",
    "MEMORY (M):",
    "- [WIN] GME: ride the leader",
    "",
    'Output STRICT JSON (no markdown fences): {"regime_read": "<one of the 6 phases + '
    'frontside/backside>", "candidates": [{"symbol": "<MUST be a ticker from the candidate universe>", '
    '"pattern": "<the matched skill_id>", "reason": "<brief>", "confidence": <0..1>, '
    '"narrative": "<short sympathy/theme key, e.g. ai-compute; the SAME key on two names means they '
    'are ONE correlated bet (sized together, not stacked); empty if the name stands alone>"}], '
    '"no_trade_reason": "<reason if no trade, else empty string>"}',
])


def test_momo_prompt_matches_frozen_golden():
    assert build_system_prompt(_momo_golden_h(), injection="full", pack="momo") == _MOMO_GOLDEN


def test_momo_h_renders_momo_regardless_of_env(monkeypatch):
    """The chimera-prompt fix: a momo H renders the momo persona even when ALPHA_SEED_PACK=growth —
    the persona follows h.vocabulary, so an env flip mid-process can never put a growth persona over a
    momo H (nor drop the momo one when the env is unset)."""
    monkeypatch.setenv("ALPHA_SEED_PACK", "growth")            # env says growth...
    sp = build_system_prompt(_momo_h(), phase_prior="trend")   # ...but the H is momo -> momo wins
    assert "speculative-momentum" in sp and "sector-growth" not in sp
