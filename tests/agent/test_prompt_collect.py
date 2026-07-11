"""D3: the collect hook observes offered/dropped; default None is byte-identical."""
from datetime import date

from alpha.agent.prompt import build_system_prompt
from alpha.harness.doctrine import Doctrine
from alpha.harness.memory import Importance, Lesson
from alpha.harness.registry import SkillRegistry, MemoryStore
from alpha.harness.skill import Skill
from alpha.harness.state import HarnessState
from alpha.memory.episodes import Episode
from alpha.memory.store import EpisodeStore


def _h_with_content():
    # Mirrors tests/agent/test_prompt.py::_h_squeeze — one skill with no depends_on (always offered)
    # plus one skill whose depends_on names a signal absent from `available_signals` (a real
    # silent-drop point, per US-3c's available_signals-exclusion filter).
    skills = SkillRegistry.from_skills([
        Skill(skill_id="gap_and_go", name="Gap and Go", type="pattern", family="runner",
              phases=["trend"], trigger="gap + hold", entry="ORB reclaim", exit_stop="lose VWAP",
              status="active"),
        Skill(skill_id="short_squeeze", name="Short Squeeze", type="pattern", family="meme",
              phases=["ignition", "trend"], trigger="high SI", entry="e", exit_stop="x",
              depends_on=["short_interest", "days_to_cover"], status="active"),
    ])
    doctrine = Doctrine.from_seed_list([
        {"section": "core", "regime": "all", "immutable": True, "guidance": "respect the stop"},
    ])
    return HarnessState(doctrine=doctrine, skills=skills, memory=MemoryStore.from_lessons([]))


def test_collect_none_is_byte_identical():
    h = _h_with_content()
    assert build_system_prompt(h) == build_system_prompt(h, collect=None)


def test_collector_sees_offered_and_dropped_with_reasons():
    h = _h_with_content()
    records = []
    kwargs = dict(available_signals=frozenset())   # short_squeeze's depends_on goes unmet -> dropped
    out = build_system_prompt(h, collect=records.append, **kwargs)
    assert out == build_system_prompt(h, **kwargs)             # hook never changes output
    statuses = {r["status"] for r in records if "status" in r}
    assert {"offered", "dropped"} <= statuses
    dropped = [r for r in records if r.get("status") == "dropped"]
    assert all(r.get("reason") for r in dropped)               # every drop names its reason
    assert any(r.get("kind") == "assembled" for r in records)  # final text captured


def _lesson(lid, base):
    return Lesson(lesson_id=lid, outcome="principle", lesson=f"lesson {lid}",
                  importance=Importance(base=base))


def _ep(eid, exit_d, adv):
    return Episode(episode_id=eid, symbol="RUN", skill_id="gap_and_go", phase="trend frontside",
                   entry_date=date(2026, 6, 1), exit_date=exit_d, outcome="continued",
                   advantage=adv, learned_asof=exit_d)


def test_retrieval_path_reports_every_cut_reason():
    """injection='retrieval' with tight budgets exercises the cuts made INSIDE select_for_prompt /
    select_episodes_for_prompt (invisible to build_system_prompt's own filters): active-skill and
    trial budget-cuts, lesson weight-cut + budget-cut, episode budget-cut — each named exactly."""
    skills = SkillRegistry.from_skills([
        Skill(skill_id="a_skill", name="A", type="pattern", family="runner", phases=["trend"],
              trigger="t", entry="e", exit_stop="x", status="active"),
        Skill(skill_id="b_skill", name="B", type="pattern", family="runner", phases=["trend"],
              trigger="t", entry="e", exit_stop="x", status="active"),
        Skill(skill_id="trial_skill", name="T", type="pattern", family="runner", phases=["trend"],
              trigger="t", entry="e", exit_stop="x", status="incubating"),
    ])
    memory = MemoryStore.from_lessons([
        _lesson("keep", base=1.0),     # weight 1.0  -> survives, takes the single memory slot
        _lesson("m_cut", base=0.5),    # weight 0.5  -> above MIN_MEMORY_WEIGHT but past budget
        _lesson("w_cut", base=0.1),    # weight 0.1  -> below MIN_MEMORY_WEIGHT (0.15)
    ])
    doctrine = Doctrine.from_seed_list([
        {"section": "core", "regime": "all", "immutable": True, "guidance": "respect the stop"},
    ])
    h = HarnessState(doctrine=doctrine, skills=skills, memory=memory)
    store = EpisodeStore.in_memory()
    store.add(_ep("ep_keep", date(2026, 6, 5), 2.0))   # newer -> ranked first, takes the single slot
    store.add(_ep("ep_cut", date(2026, 6, 2), 1.0))    # older -> past episode_budget

    records = []
    kwargs = dict(injection="retrieval", phase_prior="trend", skill_budget=1, trial_slots=0,
                  memory_budget=1, asof=date(2026, 6, 20), episode_store=store, episode_budget=1)
    out = build_system_prompt(h, collect=records.append, **kwargs)
    assert out == build_system_prompt(h, **kwargs)               # hook never changes output

    dropped = {(r["kind"], r["id"]): r["reason"] for r in records if r.get("status") == "dropped"}
    assert dropped[("skill", "b_skill")] == "budget-cut"         # active past skill_budget=1
    assert dropped[("skill", "trial_skill")] == "budget-cut"     # trial past trial_slots=0
    assert dropped[("lesson", "w_cut")] == "weight-cut"          # under MIN_MEMORY_WEIGHT
    assert dropped[("lesson", "m_cut")] == "budget-cut"          # past memory_budget=1
    assert dropped[("episode", "ep_cut")] == "budget-cut"        # past episode_budget=1

    offered = {(r["kind"], r["id"]) for r in records if r.get("status") == "offered"}
    assert {("skill", "a_skill"), ("lesson", "keep"), ("episode", "ep_keep")} <= offered
    assert offered.isdisjoint(dropped)                           # nothing is both offered and dropped
