"""D3: the collect hook observes offered/dropped; default None is byte-identical."""
from alpha.agent.prompt import build_system_prompt
from alpha.harness.skill import Skill
from alpha.harness.doctrine import Doctrine
from alpha.harness.registry import SkillRegistry, MemoryStore
from alpha.harness.state import HarnessState


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
