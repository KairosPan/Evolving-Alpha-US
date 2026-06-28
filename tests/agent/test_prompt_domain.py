"""PC-6 — read-side domain filter.

Operational-tagged H elements (domain="operational") must be invisible to the trading agent
prompt. Trading-tagged / untagged (default "trading") elements must still render.
Byte-identical guarantee: a harness with NO operational elements produces the same prompt
whether or not the filter code is present — verified by comparing explicit "trading" vs
untagged (default) element rendering.
"""
from alpha.harness.skill import Skill
from alpha.harness.memory import Lesson, Importance
from alpha.harness.doctrine import Doctrine, DoctrineEntry
from alpha.harness.registry import SkillRegistry, MemoryStore
from alpha.harness.state import HarnessState
from alpha.agent.prompt import build_system_prompt
from alpha.agent.retrieval import select_for_prompt


# ── harness builders ──────────────────────────────────────────────────────────

def _h_mixed() -> HarnessState:
    """Harness with one operational + one trading element per category (skills, lessons, doctrine)."""
    skills = SkillRegistry.from_skills([
        Skill(skill_id="trade_skill", name="Trade Skill", type="pattern", family="runner",
              phases=["trend"], trigger="gap hold", entry="ORB", exit_stop="VWAP",
              status="active", domain="trading"),
        Skill(skill_id="op_skill", name="Op Skill", type="pattern", family="runner",
              phases=["trend"], trigger="cron run", entry="tool call", exit_stop="error",
              status="active", domain="operational"),
        Skill(skill_id="trade_inc", name="Trade Inc", type="pattern", family="runner",
              phases=["trend"], trigger="t", entry="e", exit_stop="x",
              status="incubating", domain="trading"),
        Skill(skill_id="op_inc", name="Op Inc", type="pattern", family="runner",
              phases=["trend"], trigger="t", entry="e", exit_stop="x",
              status="incubating", domain="operational"),
    ])
    lessons = MemoryStore.from_lessons([
        Lesson(lesson_id="trade_lesson", phases=["trend"], outcome="principle",
               lesson="trade insight", domain="trading", importance=Importance(base=1.0)),
        Lesson(lesson_id="op_lesson", phases=["trend"], outcome="principle",
               lesson="op insight", domain="operational", importance=Importance(base=1.0)),
    ])
    doctrine = Doctrine(entries=[
        DoctrineEntry(section="trade_doc", guidance="trade guidance",
                      immutable=False, domain="trading"),
        DoctrineEntry(section="op_doc", guidance="op guidance",
                      immutable=False, domain="operational"),
        DoctrineEntry(section="redline", guidance="never blow up",
                      immutable=True, domain="trading"),
    ])
    return HarnessState(doctrine=doctrine, skills=skills, memory=lessons)


def _h_trading_only() -> HarnessState:
    """Harness with ONLY trading-domain elements (no operational) — the baseline."""
    skills = SkillRegistry.from_skills([
        Skill(skill_id="gap_and_go", name="Gap and Go", type="pattern", family="runner",
              phases=["trend"], trigger="gap hold", entry="ORB", exit_stop="VWAP",
              status="active"),
    ])
    lessons = MemoryStore.from_lessons([
        Lesson(lesson_id="L1", phases=["trend"], outcome="principle",
               lesson="respect the stop", importance=Importance(base=1.0)),
    ])
    doctrine = Doctrine.from_seed_list([
        {"section": "core", "regime": "all", "immutable": True, "guidance": "cut losses fast"},
    ])
    return HarnessState(doctrine=doctrine, skills=skills, memory=lessons)


# ── full injection: operational elements hidden ───────────────────────────────

def test_full_hides_operational_active_skill():
    sp = build_system_prompt(_h_mixed(), injection="full", phase_prior="trend")
    assert "op_skill" not in sp, "operational active skill must not appear in trading prompt"
    assert "Op Skill" not in sp


def test_full_shows_trading_active_skill():
    sp = build_system_prompt(_h_mixed(), injection="full", phase_prior="trend")
    assert "trade_skill" in sp, "trading active skill must appear in trading prompt"


def test_full_hides_operational_incubating_skill():
    sp = build_system_prompt(_h_mixed(), injection="full", phase_prior="trend")
    assert "op_inc" not in sp, "operational incubating skill must not appear in trading prompt"


def test_full_shows_trading_incubating_skill():
    sp = build_system_prompt(_h_mixed(), injection="full", phase_prior="trend")
    assert "trade_inc" in sp, "trading incubating skill must appear in trading prompt"


def test_full_hides_operational_lesson():
    sp = build_system_prompt(_h_mixed(), injection="full", phase_prior="trend")
    assert "op insight" not in sp, "operational lesson must not appear in trading prompt"
    assert "op_lesson" not in sp


def test_full_shows_trading_lesson():
    sp = build_system_prompt(_h_mixed(), injection="full", phase_prior="trend")
    assert "trade insight" in sp, "trading lesson must appear in trading prompt"


def test_full_hides_operational_mutable_doctrine():
    sp = build_system_prompt(_h_mixed(), injection="full", phase_prior="trend")
    assert "op_doc" not in sp, "operational mutable doctrine must not appear in trading prompt"
    assert "op guidance" not in sp


def test_full_shows_trading_mutable_doctrine():
    sp = build_system_prompt(_h_mixed(), injection="full", phase_prior="trend")
    assert "trade_doc" in sp, "trading mutable doctrine must appear in trading prompt"
    assert "trade guidance" in sp


def test_full_shows_trading_immutable_doctrine():
    sp = build_system_prompt(_h_mixed(), injection="full", phase_prior="trend")
    assert "redline" in sp, "trading immutable doctrine must appear in trading prompt"
    assert "never blow up" in sp


# ── retrieval injection: operational elements hidden ──────────────────────────

def test_retrieval_hides_operational_active_skill():
    sp = build_system_prompt(_h_mixed(), injection="retrieval", phase_prior="trend")
    assert "op_skill" not in sp, "operational active skill must not appear via retrieval path"


def test_retrieval_shows_trading_active_skill():
    sp = build_system_prompt(_h_mixed(), injection="retrieval", phase_prior="trend")
    assert "trade_skill" in sp, "trading active skill must appear via retrieval path"


def test_retrieval_hides_operational_incubating_skill():
    sp = build_system_prompt(_h_mixed(), injection="retrieval", phase_prior="trend")
    assert "op_inc" not in sp, "operational incubating skill must not appear via retrieval path"


def test_retrieval_hides_operational_lesson():
    sp = build_system_prompt(_h_mixed(), injection="retrieval", phase_prior="trend")
    assert "op insight" not in sp, "operational lesson must not appear via retrieval path"


def test_retrieval_shows_trading_lesson():
    sp = build_system_prompt(_h_mixed(), injection="retrieval", phase_prior="trend")
    assert "trade insight" in sp, "trading lesson must appear via retrieval path"


def test_retrieval_hides_operational_doctrine():
    sp = build_system_prompt(_h_mixed(), injection="retrieval", phase_prior="trend")
    assert "op_doc" not in sp, "operational doctrine must not appear via retrieval path"
    assert "op guidance" not in sp


def test_retrieval_shows_trading_doctrine():
    sp = build_system_prompt(_h_mixed(), injection="retrieval", phase_prior="trend")
    assert "trade_doc" in sp, "trading doctrine must appear via retrieval path"


# ── select_for_prompt directly ────────────────────────────────────────────────

def test_select_excludes_operational_active_skills():
    sel = select_for_prompt(_h_mixed(), phase_prior="trend")
    ids = [s.skill_id for s in sel.skills]
    assert "op_skill" not in ids, "select_for_prompt must not include operational active skills"
    assert "trade_skill" in ids


def test_select_excludes_operational_trials():
    sel = select_for_prompt(_h_mixed(), phase_prior="trend")
    ids = [s.skill_id for s in sel.trials]
    assert "op_inc" not in ids, "select_for_prompt must not include operational incubating skills"
    assert "trade_inc" in ids


def test_select_excludes_operational_lessons():
    sel = select_for_prompt(_h_mixed(), phase_prior="trend")
    lesson_ids = [l.lesson_id for l in sel.lessons]
    assert "op_lesson" not in lesson_ids, "select_for_prompt must not include operational lessons"
    assert "trade_lesson" in lesson_ids


# ── byte-identical guarantee (default "trading" renders identically to explicit) ──

def test_default_domain_renders_same_as_explicit_trading_full():
    """Untagged elements (default domain="trading") render identically to elements with explicit
    domain="trading" — confirms fail-closed direction: the filter does not strip anything new
    when no operational element is present.
    """
    # h_untagged: no domain kwarg (Skill/Lesson default = "trading")
    h_untagged = _h_trading_only()

    # h_tagged: same elements with explicit domain="trading"
    skills_tagged = SkillRegistry.from_skills([
        Skill(skill_id="gap_and_go", name="Gap and Go", type="pattern", family="runner",
              phases=["trend"], trigger="gap hold", entry="ORB", exit_stop="VWAP",
              status="active", domain="trading"),
    ])
    lessons_tagged = MemoryStore.from_lessons([
        Lesson(lesson_id="L1", phases=["trend"], outcome="principle",
               lesson="respect the stop", domain="trading", importance=Importance(base=1.0)),
    ])
    doctrine_tagged = Doctrine.from_seed_list([
        {"section": "core", "regime": "all", "immutable": True, "guidance": "cut losses fast"},
    ])
    h_tagged = HarnessState(doctrine=doctrine_tagged, skills=skills_tagged, memory=lessons_tagged)

    assert (build_system_prompt(h_untagged, injection="full") ==
            build_system_prompt(h_tagged, injection="full"))


def test_default_domain_renders_same_as_explicit_trading_retrieval():
    h_untagged = _h_trading_only()
    skills_tagged = SkillRegistry.from_skills([
        Skill(skill_id="gap_and_go", name="Gap and Go", type="pattern", family="runner",
              phases=["trend"], trigger="gap hold", entry="ORB", exit_stop="VWAP",
              status="active", domain="trading"),
    ])
    lessons_tagged = MemoryStore.from_lessons([
        Lesson(lesson_id="L1", phases=["trend"], outcome="principle",
               lesson="respect the stop", domain="trading", importance=Importance(base=1.0)),
    ])
    doctrine_tagged = Doctrine.from_seed_list([
        {"section": "core", "regime": "all", "immutable": True, "guidance": "cut losses fast"},
    ])
    h_tagged = HarnessState(doctrine=doctrine_tagged, skills=skills_tagged, memory=lessons_tagged)
    assert (build_system_prompt(h_untagged, injection="retrieval") ==
            build_system_prompt(h_tagged, injection="retrieval"))
