import pytest
from alpha.harness.workflows import WorkflowEntry, WorkflowRegistry, WorkflowStep
from alpha.harness.state import HarnessState
from alpha.harness.doctrine import Doctrine
from alpha.harness.registry import MemoryStore, SkillRegistry


def _entry(wid="morning_screen", **kw):
    base = dict(workflow_id=wid, name="Morning Screen",
                description="Run the daily gainer screen then a regime read.",
                steps=[WorkflowStep(ref="skill_x", note="first"),
                       WorkflowStep(ref="regime_read")],
                arg_hints=["date"], phases=["trend"])
    base.update(kw)
    return WorkflowEntry(**base)


def test_step_rejects_unknown_field():
    with pytest.raises(Exception):
        WorkflowStep(ref="skill_x", bogus=1)


def test_entry_rejects_unknown_field():
    with pytest.raises(Exception):
        WorkflowEntry(workflow_id="x", name="X", bogus=1)


def test_entry_defaults():
    e = _entry()
    assert e.user_only is True and e.status == "active" and e.content_hash == ""
    assert e.domain == "trading"
    assert e.steps[0].ref == "skill_x" and e.steps[0].note == "first"
    assert e.steps[1].note == ""                          # WorkflowStep.note defaults ""


def test_entry_empty_defaults():
    e = WorkflowEntry(workflow_id="w", name="W")
    assert e.description == "" and e.steps == [] and e.arg_hints == [] and e.phases == []


def test_registry_dup_id_raises():
    with pytest.raises(ValueError):
        WorkflowRegistry.from_workflows([_entry(), _entry()])


def test_registry_get_all_len_bool():
    r = WorkflowRegistry.from_workflows([_entry()])
    assert r.get("morning_screen").name == "Morning Screen" and r.get("absent") is None
    assert len(r) == 1 and r.all()[0].workflow_id == "morning_screen"
    assert bool(WorkflowRegistry.empty()) is True and len(WorkflowRegistry.empty()) == 0


def test_registry_upsert_replaces():
    r = WorkflowRegistry.empty()
    r.upsert(_entry())
    r.upsert(_entry(name="Morning Screen v2"))
    assert len(r) == 1 and r.get("morning_screen").name == "Morning Screen v2"


def _minimal_h(**kw):
    return HarnessState(doctrine=Doctrine(), skills=SkillRegistry.from_skills([]),
                        memory=MemoryStore.from_lessons([]), **kw)


def test_harness_roundtrip_carries_workflows():
    h = _minimal_h(workflows=WorkflowRegistry.from_workflows([_entry()]))
    d = h.to_dict()
    assert d["workflows"][0]["workflow_id"] == "morning_screen"
    assert d["workflows"][0]["steps"][0]["ref"] == "skill_x"    # nested step serialised
    h2 = HarnessState.from_dict(d)
    w = h2.workflows.get("morning_screen")
    assert w.steps[0].note == "first" and w.user_only is True


def test_legacy_dump_without_workflows_yields_empty():
    h = _minimal_h()
    d = h.to_dict()
    d.pop("workflows")
    h2 = HarnessState.from_dict(d)
    assert len(h2.workflows) == 0
