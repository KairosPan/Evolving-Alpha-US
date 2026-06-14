import pytest
from alpha.harness.skill import Skill
from alpha.harness.registry import SkillRegistry
from alpha.harness.errors import InvalidTransitionError


def _skill(sid, status="incubating"):
    return Skill(skill_id=sid, name=sid, type="pattern", family="runner", phases=["trend"], status=status)


def test_write_and_duplicate():
    reg = SkillRegistry.from_skills([])
    reg.write(_skill("a"))
    assert reg.get("a") is not None
    with pytest.raises(ValueError):
        reg.write(_skill("a"))


def test_patch_allowed_field():
    reg = SkillRegistry.from_skills([_skill("a")])
    reg.patch("a", notes="updated", phases=["trend", "flush"])
    assert reg.get("a").notes == "updated"
    assert reg.get("a").phases == ["trend", "flush"]


def test_patch_forbidden_fields():
    reg = SkillRegistry.from_skills([_skill("a")])
    for bad in ({"status": "active"}, {"stats": {}}):
        with pytest.raises(ValueError):
            reg.patch("a", **bad)
    # skill_id is protected structurally: passing it as a field collides with the positional
    # param -> TypeError (still rejected, just a different error type)
    with pytest.raises(TypeError):
        reg.patch("a", **{"skill_id": "b"})


def test_patch_missing_target():
    reg = SkillRegistry.from_skills([])
    with pytest.raises(KeyError):
        reg.patch("nope", notes="x")


def test_patch_atomic_rollback():
    reg = SkillRegistry.from_skills([_skill("a")])
    # 'notes' is applied first (kwargs insertion order), then invalid 'type' fails validation
    # -> whole patch rolls back
    with pytest.raises(Exception):
        reg.patch("a", notes="changed", type="not_a_valid_type")
    assert reg.get("a").notes == ""        # rolled back, not left as "changed"


def test_lifecycle_transitions():
    reg = SkillRegistry.from_skills([_skill("a", status="incubating")])
    assert reg.promote("a").status == "active"
    assert reg.retire("a").status == "dormant"           # default retire -> dormant
    assert reg.revive("a").status == "incubating"        # dormant -> incubating
    reg.retire("a", permanent=True)
    assert reg.get("a").status == "retired"


def test_illegal_transitions():
    reg = SkillRegistry.from_skills([_skill("a", status="active")])
    with pytest.raises(InvalidTransitionError):
        reg.revive("a")                  # active is not dormant
    with pytest.raises(InvalidTransitionError):
        reg.promote("a")                 # active is not incubating
    reg.retire("a", permanent=True)
    with pytest.raises(InvalidTransitionError):
        reg.retire("a")                  # already permanently retired (non-permanent)
    with pytest.raises(InvalidTransitionError):
        reg.retire("a", permanent=True)  # already permanently retired (permanent too)
    # re-retiring an already-dormant skill (non-permanent) is rejected, not a silent no-op;
    # but a permanent retire of a dormant skill IS allowed (dormant -> retired)
    reg2 = SkillRegistry.from_skills([_skill("b", status="active")])
    reg2.retire("b")                     # active -> dormant
    with pytest.raises(InvalidTransitionError):
        reg2.retire("b")                 # already dormant
    assert reg2.retire("b", permanent=True).status == "retired"
