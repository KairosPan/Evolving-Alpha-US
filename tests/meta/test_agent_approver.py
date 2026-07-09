"""MetaAgent.apply records the human approver (charter conformance 2026-07-09): a landed Sonia
proposal names WHO accepted it."""
from alpha.harness.doctrine import Doctrine
from alpha.harness.edit_log import EditLog
from alpha.harness.metatools import MetaTools
from alpha.harness.registry import MemoryStore, SkillRegistry
from alpha.harness.state import HarnessState
from alpha.llm.client import MockLLMClient
from alpha.meta.agent import MetaAgent
from alpha.meta.models import ProposedEdit, new_edit_id


def _h():
    return HarnessState(doctrine=Doctrine(), skills=SkillRegistry.from_skills([]),
                        memory=MemoryStore.from_lessons([]))


def _accepted_edit() -> ProposedEdit:
    return ProposedEdit(edit_id=new_edit_id(), tool="process_memory",
                        args={"lesson_id": "s-1", "phases": ["trend"], "outcome": "win",
                              "lesson": "sonia teaches"},
                        rationale="teaching", status="accepted")


def test_apply_stamps_human_approver():
    h = _h()
    log = EditLog()
    applied, _ = MetaAgent(MetaTools(h, log), MockLLMClient("{}")).apply(
        [_accepted_edit()], human_approver="user")
    assert len(applied) == 1
    rec = log.records()[-1]
    assert rec.provenance.proposer == "sonia"
    assert rec.provenance.human_approver == "user"


def test_apply_default_leaves_approver_unset():
    h = _h()
    log = EditLog()
    MetaAgent(MetaTools(h, log), MockLLMClient("{}")).apply([_accepted_edit()])
    assert log.records()[-1].provenance.human_approver is None
